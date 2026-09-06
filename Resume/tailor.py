import os
import re
import json
from pathlib import Path
from typing import Dict, Any, List, Tuple
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

# Load environment variables from current directory, parent directory, or sibling Emails folder
load_dotenv(dotenv_path=BASE_DIR / ".env")
if not os.getenv("GEMINI_API_KEY") and (BASE_DIR.parent / ".env").exists():
    load_dotenv(dotenv_path=BASE_DIR.parent / ".env")
if not os.getenv("GEMINI_API_KEY") and (BASE_DIR.parent / "Emails" / ".env").exists():
    load_dotenv(dotenv_path=BASE_DIR.parent / "Emails" / ".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

MODELS_TO_TRY = ["gemini-2.5-flash", "gemini-3.7-flash", "gemini-3.6-flash", "gemini-flash-latest"]

def get_genai_client():
    """Initializes and returns the Google GenAI client."""
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not set. Please ensure it is present in .env or ../Emails/.env.")
    try:
        from google import genai
        return genai.Client(api_key=GEMINI_API_KEY)
    except ImportError:
        raise ImportError("google-genai package is required. Install it via pip or run within the project's python environment.")

def generate_content_with_fallback(client, prompt: str, is_json: bool = True) -> str:
    """Generates content using Gemini models with automatic version fallback."""
    last_err = None
    config = {"response_mime_type": "application/json"} if is_json else {}

    for model_name in MODELS_TO_TRY:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=config
            )
            return response.text
        except Exception as e:
            last_err = e
            continue

    raise RuntimeError(f"All Gemini models failed. Last error: {last_err}")

def parse_json_safely(raw_text: str) -> dict:
    """Safely extracts JSON from model response text even if wrapped in markdown formatting."""
    try:
        return json.loads(raw_text)
    except Exception:
        clean = re.sub(r"^```[a-zA-Z]*\n|\n```$", "", raw_text.strip(), flags=re.MULTILINE).strip()
        match = re.search(r"(\{.*\})", clean, re.DOTALL)
        if match:
            return json.loads(match.group(1))
        raise ValueError(f"Could not parse valid JSON from text:\n{raw_text[:200]}...")

def analyze_job_description(jd_text: str, client=None) -> dict:
    """Extracts structured role details, required skills, priority ordering, and company pain points."""
    if client is None:
        client = get_genai_client()

    prompt = f"""
You are an executive recruiter, hiring manager, and ATS (Applicant Tracking System) optimization specialist.
Analyze the following Job Description to extract deep strategic insights:

<JOB_DESCRIPTION>
{jd_text}
</JOB_DESCRIPTION>

Return a STRICT JSON object with the following schema:
{{
  "company_name": "Name of the hiring company",
  "role_title": "Exact job title",
  "seniority_level": "Intern / Entry-Level / Mid / Senior",
  "industry_domain": "Industry sector (e.g. Enterprise AI, FinTech, Developer Tools, Brand Strategy, Consulting, etc.)",
  "role_orientation": "technical (AI/Engineering/Data) OR product_growth (PM/BizOps/Solutions) OR business_sales (Sales/BD/Logistics)",
  "core_pain_points": [
    "Top 2-3 specific business bottlenecks, operational challenges, or technical problems this role is hired to solve"
  ],
  "top_priority_tech_skills": [
    "Top 5 most critical technical skills/tools ordered strictly from highest to lowest priority"
  ],
  "top_priority_business_skills": [
    "Top 5 most critical business/strategic skills ordered strictly from highest to lowest priority"
  ],
  "ats_keywords": [
    "12-15 high-priority keyword terms and phrases found in the posting"
  ]
}}
"""
    raw_response = generate_content_with_fallback(client, prompt, is_json=True)
    return parse_json_safely(raw_response)

def calculate_deterministic_ats_score(tailored_data: dict, jd_analysis: dict) -> Tuple[int, Dict[str, Any]]:
    """
    Computes a mathematical ATS Keyword & Competency Alignment Score (0-100)
    based on exact and semantic presence in the generated resume text.
    """
    # 1. Aggregate all text from the tailored resume
    resume_text_corpus = []
    
    # Experiences / Projects
    for exp in tailored_data.get("experiences", []):
        resume_text_corpus.append(exp.get("company", ""))
        resume_text_corpus.append(exp.get("role", ""))
        for b in exp.get("bullets", []):
            b_text = b if isinstance(b, str) else b.get("text", "")
            resume_text_corpus.append(b_text)
            
    # Education & Coursework
    for edu in tailored_data.get("education", []):
        resume_text_corpus.append(edu.get("institution", ""))
        resume_text_corpus.append(edu.get("degree_title", ""))
        resume_text_corpus.append(edu.get("major_minor_gpa", ""))
        resume_text_corpus.extend(edu.get("coursework", []))
        resume_text_corpus.extend(edu.get("honors", []))
        resume_text_corpus.extend(edu.get("activities", []))
        
    # Skills
    skills = tailored_data.get("skills", {})
    resume_text_corpus.extend([str(s) for s in skills.get("technical_skills", [])])
    resume_text_corpus.extend([str(s) for s in skills.get("business_and_strategy", [])])
    
    full_text = " ".join(resume_text_corpus).lower()

    # 2. Check Tech Skills Coverage (45% weight)
    tech_skills_req = jd_analysis.get("top_priority_tech_skills", [])
    matched_tech = []
    missing_tech = []
    for ts in tech_skills_req:
        clean_ts = ts.lower().strip()
        # Direct word or token match
        if clean_ts and (clean_ts in full_text or any(token in full_text for token in re.split(r'[/,\s]+', clean_ts) if len(token) > 2)):
            matched_tech.append(ts)
        else:
            missing_tech.append(ts)
            
    tech_score = (len(matched_tech) / max(len(tech_skills_req), 1)) * 100

    # 3. Check Business Skills Coverage (30% weight)
    biz_skills_req = jd_analysis.get("top_priority_business_skills", [])
    matched_biz = []
    missing_biz = []
    for bs in biz_skills_req:
        clean_bs = bs.lower().strip()
        if clean_bs and (clean_bs in full_text or any(token in full_text for token in re.split(r'[/,\s]+', clean_bs) if len(token) > 2)):
            matched_biz.append(bs)
        else:
            missing_biz.append(bs)
            
    biz_score = (len(matched_biz) / max(len(biz_skills_req), 1)) * 100

    # 4. Check ATS Keywords Coverage (25% weight)
    ats_keywords_req = jd_analysis.get("ats_keywords", [])
    matched_kw = []
    missing_kw = []
    for kw in ats_keywords_req:
        clean_kw = kw.lower().strip()
        if clean_kw and (clean_kw in full_text or any(token in full_text for token in re.split(r'[/,\s]+', clean_kw) if len(token) > 3)):
            matched_kw.append(kw)
        else:
            missing_kw.append(kw)
            
    kw_score = (len(matched_kw) / max(len(ats_keywords_req), 1)) * 100

    # 5. Composite Weighted ATS Score
    composite_score = round((0.45 * tech_score) + (0.30 * biz_score) + (0.25 * kw_score))
    # Bound between 0 and 100
    composite_score = min(max(composite_score, 0), 100)

    breakdown = {
        "composite_score": composite_score,
        "tech_skills_score": round(tech_score),
        "business_skills_score": round(biz_score),
        "keyword_coverage_score": round(kw_score),
        "matched_tech_skills": matched_tech,
        "missing_tech_skills": missing_tech,
        "matched_business_skills": matched_biz,
        "missing_business_skills": missing_biz,
        "matched_keywords": matched_kw,
        "missing_keywords": missing_kw,
    }

    return composite_score, breakdown

def tailor_resume(master_profile: dict, jd_text: str, client=None, target_pages: int = 1) -> dict:
    """
    Tailors master profile experiences, projects, coursework, and skills to match the target JD.
    Dynamically selects between Experiences and Projects to optimize for the role orientation.
    """
    if client is None:
        client = get_genai_client()

    jd_analysis = analyze_job_description(jd_text, client)
    company = jd_analysis.get("company_name", "Target Company")
    role = jd_analysis.get("role_title", "Target Role")
    orientation = jd_analysis.get("role_orientation", "product_growth")

    prompt = f"""
You are an elite career strategist and executive resume writer who has coached candidates into top roles at Google, Stripe, IBM, and top venture startups.
Your mission is to tailor Daniel Suh's master resume for a specific job application by highlighting his 4 verified Work Experiences from his Master Profile against the target Job Description.

### ROLE CONTEXT:
- Target Company: {company}
- Target Role: {role}
- Role Orientation: {orientation}
- Core Company Pain Points: {json.dumps(jd_analysis.get('core_pain_points', []))}
- Top Tech Skills Needed: {json.dumps(jd_analysis.get('top_priority_tech_skills', []))}
- Top Business Skills Needed: {json.dumps(jd_analysis.get('top_priority_business_skills', []))}

### PROFESSIONAL EXPERIENCE ALLOCATION:
1. Daniel's resume contains strictly his **4 Verified Professional Work Experiences**:
   - **Autopilot Local** (AI Solutions Consultant)
   - **Aroma Vault** (Founder)
   - **ClayThis** (Business Development Intern)
   - **Blue Water Battery Logistics** (Lead Generation Intern)
2. Include ALL 4 work experiences under the `experiences` array. Do NOT invent, include, or substitute separate personal projects.
3. Total experience bullet allocation MUST be exactly **10 bullets total** distributed across the 4 experiences (e.g. 3 for Autopilot Local, 2 for Aroma Vault, 3 for ClayThis, 2 for Blue Water Battery).

### CORE OBJECTIVES & THE GOOGLE X-Y-Z FORMULA:
Every single bullet point MUST follow the Google "X-Y-Z" formula:
"Accomplished [X], as measured by [Y], by doing [Z]"
- **X (Outcome / Business Value)**: Start with a powerful tier-1 action verb (*Architected, Spearheaded, Engineered, Formulated, Validated, Negotiated, Synthesized*).
- **Y (Quantifiable Impact)**: Emphasize concrete metrics (*saving 50 hours/week, 90% accuracy, 74% reduction, 5,000+ active users, 15% response rate, ~70% gross margins*).
- **Z (Mechanism & Tooling)**: State the exact technical stack, tools, APIs, frameworks, and strategic methodologies used.

### CRITICAL CONSTRAINTS:
1. **ZERO HALLUCINATION**: Use ONLY Daniel's authentic background facts, metrics, and roles. NEVER invent employers, fake degrees, or unearned awards.
2. **DYNAMIC LEFT-TO-RIGHT SKILLS ORDERING**:
   - In `Technical Skills`, place the JD's highest priority matching tools as the **very first items from left to right**.
   - In `Business & Strategy`, place the JD's highest priority matching competencies as the **very first items from left to right**.
3. **DYNAMIC COURSEWORK ORDERING**:
   - Re-order Daniel's Haas coursework (*Introduction to Business Analytics, Foundations of Data Science, Probability and Statistics for Business, Financial Accounting, Competitive Strategy*) so the courses most relevant to the role appear first.
4. **PAGE DENSITY & FIT**:
   - Each bullet should be substantial (~22 to 32 words, filling 1.5 to 2 complete lines on the page).

<MASTER_PROFILE>
{json.dumps(master_profile, indent=2)}
</MASTER_PROFILE>

<JOB_DESCRIPTION>
{jd_text}
</JOB_DESCRIPTION>

Return a STRICT JSON object with this exact structure:
{{
  "personal_info": {{
    "full_name": "DANIEL SUH",
    "phone": "661-476-8194",
    "email": "ds42@berkeley.edu",
    "linkedin": "linkedin.com/in/daniel-suh-994411297"
  }},
  "target_company": "{company}",
  "target_role": "{role}",
  "experiences": [
    {{
      "company": "Company Name or Project Name",
      "location": "Location or Link (e.g. Berkeley, CA or github.com/danielsuh/...)",
      "role": "Role Title or Creator & Developer",
      "date_range": "Date Range",
      "bullets": [
        "X-Y-Z bullet 1 (22-32 words)...",
        "X-Y-Z bullet 2 (22-32 words)..."
      ]
    }}
  ],
  "education": [
    {{
      "institution": "University of California, Berkeley, Haas School of Business",
      "location": "Berkeley, CA",
      "degree_title": "Bachelor of Science",
      "graduation_date": "May 2028",
      "major_minor_gpa": "Major in Business Administration; Minor in Data Science [GPA: 3.52]",
      "coursework": [
        "Course 1", "Course 2", "Course 3", "Course 4", "Course 5"
      ],
      "honors": [
        "Leadership Award Scholar: Competitive, multi-year merit scholarship recognizing leadership and community impact ($42,000 total)."
      ],
      "activities": [
        "Led AACF chapter, overseeing member programming and coordinating 10+ events, managing logistics, volunteer coordination, and community outreach across a 23-person organization."
      ]
    }}
  ],
  "skills": {{
    "technical_skills": [
      "Top JD matching tech skill 1", "Top tech skill 2", "...remaining skills"
    ],
    "business_and_strategy": [
      "Top JD matching business skill 1", "Top business skill 2", "...remaining skills"
    ]
  }},
  "tailoring_report": {{
    "core_pain_points_addressed": ["How bullets address the company's specific needs"],
    "key_strengths_highlighted": ["Value propositions highlighted in this version"],
    "interview_talking_points": [
      "Key story / metric #1 to bring up in interviews",
      "Key story / metric #2 to bring up in interviews",
      "Strategic question to ask the interviewer"
    ]
  }}
}}
"""
    raw_response = generate_content_with_fallback(client, prompt, is_json=True)
    tailored_data = parse_json_safely(raw_response)

    if "personal_info" not in tailored_data or not tailored_data["personal_info"].get("full_name"):
        tailored_data["personal_info"] = master_profile.get("personal_info", {})

    # Compute Deterministic Mathematical ATS Score
    score, breakdown = calculate_deterministic_ats_score(tailored_data, jd_analysis)
    
    if "tailoring_report" not in tailored_data:
        tailored_data["tailoring_report"] = {}
        
    tailored_data["tailoring_report"]["ats_match_score"] = score
    tailored_data["tailoring_report"]["score_breakdown"] = breakdown
    tailored_data["tailoring_report"]["target_company"] = company
    tailored_data["tailoring_report"]["target_role"] = role
    tailored_data["tailoring_report"]["matched_keywords"] = breakdown["matched_keywords"]
    tailored_data["tailoring_report"]["missing_keywords_not_in_profile"] = breakdown["missing_keywords"]

    return tailored_data

def generate_report_markdown(report_data: dict, jd_analysis: dict = None) -> str:
    """Formats the tailoring report into readable markdown with mathematical scoring breakdown."""
    score = report_data.get("ats_match_score", "N/A")
    breakdown = report_data.get("score_breakdown", {})
    company = report_data.get("target_company", "Target Company")
    role = report_data.get("target_role", "Target Role")
    pain_points = report_data.get("core_pain_points_addressed", [])
    matched_kw = report_data.get("matched_keywords", [])
    missing_kw = report_data.get("missing_keywords_not_in_profile", [])
    strengths = report_data.get("key_strengths_highlighted", [])
    interview = report_data.get("interview_talking_points", [])

    tech_score = breakdown.get("tech_skills_score", "N/A")
    biz_score = breakdown.get("business_skills_score", "N/A")
    kw_score = breakdown.get("keyword_coverage_score", "N/A")

    lines = [
        f"# 📊 ATS Optimization & Tailoring Report: {role} at {company}",
        f"",
        f"### 🎯 Overall ATS Match Score: `{score}/100`",
        f"",
        "| Competency Area | Match Score | Weight |",
        "| :--- | :---: | :---: |",
        f"| **Technical Skills & Tools** | `{tech_score}%` | 45% |",
        f"| **Business & Domain Strategy** | `{biz_score}%` | 30% |",
        f"| **ATS Keywords & Terms** | `{kw_score}%` | 25% |",
        "",
        "---",
        "",
        "## 🎯 Key Strengths & Value Propositions Highlighted",
    ]
    for s in strengths:
        lines.append(f"- {s}")

    if pain_points:
        lines.extend([
            "",
            "## 🛡️ Company Pain Points Addressed in Bullets",
        ])
        for p in pain_points:
            lines.append(f"- {p}")

    lines.extend([
        "",
        "## ✅ Matched ATS Keywords & Skills",
        ", ".join([f"`{k}`" for k in matched_kw]) if matched_kw else "None identified",
        "",
        "## ⚠️ Keywords Missing from Master Profile (Opportunities to Address in Follow-up / Interview)",
        ", ".join([f"`{k}`" for k in missing_kw]) if missing_kw else "None — complete coverage!",
        "",
        "---",
        "",
        "## 💡 High-Impact Interview Talking Points",
    ])
    for pt in interview:
        lines.append(f"1. {pt}")

    return "\n".join(lines)

