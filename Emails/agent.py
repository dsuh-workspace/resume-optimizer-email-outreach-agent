import os
import csv
import re
import requests
import asyncio
import json
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
from dotenv import load_dotenv
from google.antigravity import Agent, LocalAgentConfig, CapabilitiesConfig
from gmail_draft import create_gmail_draft
from reliability_store import application_operation_key
from resume_finder import find_tailored_resume, load_verified_packet
from email_validator import contact_verification, is_valid_email, validate_email, sanitize_and_validate_email, verify_email_with_hunter

BASE_DIR = Path(__file__).resolve().parent

# Load environment variables from .env file
load_dotenv(dotenv_path=BASE_DIR / ".env")
if not os.getenv("GEMINI_API_KEY") and (BASE_DIR.parent / ".env").exists():
    load_dotenv(dotenv_path=BASE_DIR.parent / ".env")

# Initialize API Keys
HUNTER_API_KEY = os.getenv("HUNTER_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

def get_company_domain(company_name: str) -> str:
    """Uses Google GenAI API to find the official website domain of a company."""
    if not company_name:
        return "company.com"

    # If the input already looks like a domain
    if "." in company_name and " " not in company_name:
        return company_name.lower().strip()

    if not GEMINI_API_KEY or "YOUR_" in GEMINI_API_KEY:
        print("Gemini API key is not configured. Defaulting domain guess to company name.")
        clean_name = re.sub(r'[^a-zA-Z0-9]', '', company_name).lower()
        return f"{clean_name}.com"
        
    try:
        from google import genai
        client = genai.Client(api_key=GEMINI_API_KEY)
        prompt = (
            f"What is the main official website domain name for '{company_name}'? "
            f"Return ONLY the domain name (e.g. google.com, stripe.com, notion.so, cursor.com, linear.app). "
            f"Do not include any protocol (http/https), punctuation, or explanation."
        )
        response = client.models.generate_content(
            model='gemini-flash-latest',
            contents=prompt,
        )
        domain = response.text.strip().lower()
        domain = re.sub(r'[`\'"\s]', '', domain)
        print(f"Gemini resolved '{company_name}' to domain: '{domain}'")
        return domain
    except Exception as e:
        # Fallback to gemini-flash-latest if needed
        try:
            from google import genai
            client = genai.Client(api_key=GEMINI_API_KEY)
            response = client.models.generate_content(
                model='gemini-flash-latest',
                contents=prompt,
            )
            domain = re.sub(r'[`\'"\s]', '', response.text.strip().lower())
            return domain
        except Exception:
            clean_name = re.sub(r'[^a-zA-Z0-9]', '', company_name).lower()
            return f"{clean_name}.com"

def find_email_via_hunter(first_name: str, last_name: str, company_name: str) -> Tuple[Optional[str], Optional[int]]:
    """Finds the contact's email address using Hunter.io API (returns email, score)."""
    if not HUNTER_API_KEY or "YOUR_" in HUNTER_API_KEY:
        print("Hunter.io API key is not configured in .env.")
        return None, None

    domain = get_company_domain(company_name)
    
    url = "https://api.hunter.io/v2/email-finder"
    params = {
        "domain": domain,
        "first_name": first_name,
        "last_name": last_name,
        "api_key": HUNTER_API_KEY
    }
    
    try:
        response = requests.get(url, params=params, timeout=15)
        if response.status_code == 200:
            data = response.json()
            email = data.get("data", {}).get("email")
            score = data.get("data", {}).get("score")
            verification = data.get("data", {}).get("verification") or {}
            v_status = verification.get("status")

            if email:
                is_valid, reason = validate_email(email, hunter_api_key=HUNTER_API_KEY, target_company=company_name)
                if not is_valid or v_status == "invalid" or score is None or score < 50:
                    print(f"⚠️ Hunter.io email '{email}' rejected: {reason if not is_valid else 'verification status is invalid'}")
                    return None, None
                print(f"Hunter.io found verified valid email: {email} (Confidence Score: {score}%)")
                return email, score
            else:
                print(f"Hunter.io could not find a verified email for {first_name} {last_name} at {domain}.")
                return None, None
        elif response.status_code == 401:
            print("Hunter.io API error (401): Invalid API key.")
            return None, None
        elif response.status_code == 402:
            print("Hunter.io API error (402): Account credit limit reached.")
            return None, None
        elif response.status_code == 429:
            print("Hunter.io API error (429): Rate limit exceeded.")
            return None, None
        else:
            print(f"Hunter.io API returned status code {response.status_code}: {response.text}")
            return None, None
    except Exception as e:
        print(f"Error calling Hunter.io API: {e}")
        return None, None

def search_company_contacts_via_hunter(company_name: str, role_title: str = "") -> Dict[str, Optional[Dict[str, Any]]]:
    """
    Searches Hunter.io Domain Search for both the Hiring Manager (Priority 1) and Recruiter (Priority 2).
    Returns:
      {
        'hiring_manager': {'name': ..., 'first_name': ..., 'last_name': ..., 'email': ..., 'position': ..., 'confidence': ...} or None,
        'recruiter': {'name': ..., 'first_name': ..., 'last_name': ..., 'email': ..., 'position': ..., 'confidence': ...} or None
      }
    """
    if not HUNTER_API_KEY or "YOUR_" in HUNTER_API_KEY:
        return {"hiring_manager": None, "recruiter": None}

    domain = get_company_domain(company_name)
    url = "https://api.hunter.io/v2/domain-search"
    params = {
        "domain": domain,
        "api_key": HUNTER_API_KEY,
        "limit": 100  # Increased from 15 — large companies need wider coverage
    }

    try:
        response = requests.get(url, params=params, timeout=15)
        if response.status_code != 200:
            return {"hiring_manager": None, "recruiter": None}

        data = response.json()
        emails_list = data.get("data", {}).get("emails", [])

        # Tiered HM scoring — consistent with contact_finder.py
        HM_TITLE_SCORES = {
            "head of": 55, "vice president": 50, "vp": 50, "director": 45,
            "group product manager": 45, "principal": 40, "senior manager": 35,
            "manager": 20, "lead": 8,
        }
        recruiter_keywords = ["campus recruiter", "university recruiter", "early career",
                              "emerging talent", "talent acquisition", "recruiter",
                              "hr", "sourcer", "staffing", "people"]

        # Extract role domain words (e.g. 'product' from 'Associate Product Manager')
        role_terms = [w.lower() for w in re.split(r'\W+', role_title)
                      if len(w) > 3 and w.lower() not in
                      {"associate", "senior", "specialist", "junior", "lead",
                       "manager", "intern", "coop", "summer", "analyst"}]

        best_hm = None
        best_recruiter = None

        for item in emails_list:
            pos = (item.get("position") or "").lower()
            dept = (item.get("department") or "").lower()
            fname = item.get("first_name") or ""
            lname = item.get("last_name") or ""
            email = item.get("value")
            score = item.get("confidence", 0)

            if not email or not fname or not is_valid_email(email, target_company=company_name):
                continue

            contact_obj = {
                "name": f"{fname} {lname}".strip(),
                "first_name": fname,
                "last_name": lname,
                "email": email,
                "position": item.get("position") or "Team Leader",
                "confidence": score
            }

            # Check Recruiter first (takes priority over HM check)
            if any(rk in pos or rk in dept for rk in recruiter_keywords):
                if not best_recruiter or score > best_recruiter.get("confidence", 0):
                    best_recruiter = contact_obj
                continue  # Don't double-count as HM

            # Check Hiring Manager via tiered scoring
            hm_bonus = max(
                (bonus for kw, bonus in HM_TITLE_SCORES.items() if kw in pos),
                default=0
            )
            if hm_bonus:
                effective_score = score + hm_bonus
                if role_terms and any(rt in pos or rt in dept for rt in role_terms):
                    effective_score += 20
                if not best_hm or effective_score > (best_hm.get("confidence", 0)):
                    best_hm = {**contact_obj, "confidence": effective_score}

        return {
            "hiring_manager": best_hm,
            "recruiter": best_recruiter
        }

    except Exception as e:
        print(f"Error querying Hunter.io domain search: {e}")
        return {"hiring_manager": None, "recruiter": None}


# --- Custom Agent Tools for Google Antigravity SDK ---

def find_contact_email(first_name: str, last_name: str, company_name: str) -> str:
    """Finds the contact's professional email address using Hunter.io API.

    Args:
        first_name: The contact's first name.
        last_name: The contact's last name.
        company_name: The name of the company they work at.
    """
    email, score = find_email_via_hunter(first_name, last_name, company_name)
    if email and is_valid_email(email, target_company=company_name):
        return email
    else:
        return f"ERROR: Could not resolve valid professional email for {first_name} {last_name} at {company_name}."

def get_tailored_resume_for_job(company_name: str, role: str = "") -> str:
    """Finds the custom-tailored resume PDF for a target company and role in Resume/output/.

    Args:
        company_name: The name of the target company.
        role: Optional role/title applied to.
    """
    pdf_path, _ = load_verified_packet(company_name, role)
    if pdf_path and os.path.exists(pdf_path):
        return pdf_path
    return "ERROR: Tailored resume PDF not found."

def save_gmail_draft(to_email: str, subject: str, body_text: str, attachment_path: str = "auto", company_name: str = "", role: str = "") -> str:
    """Creates a draft email in the user's Gmail account and attaches the tailored resume PDF.

    Args:
        to_email: The recipient's email address.
        subject: The subject of the email.
        body_text: The main text content/body of the email.
        attachment_path: Absolute file path to the resume PDF. If 'auto' or empty, automatically resolves from Resume/output/.
        company_name: Target company name (used for auto resume resolution if attachment_path is 'auto').
        role: Target role/title (used for auto resume resolution).
    """
    try:
        cleaned_to, err = sanitize_and_validate_email(to_email, target_company=company_name)
        if not cleaned_to:
            return f"ERROR: Invalid recipient email '{to_email}': {err}"
        to_email = cleaned_to

        contact_verification(to_email, target_company=company_name)
        resolved_attachment, resume_data = load_verified_packet(company_name, role)
        if attachment_path and attachment_path.strip().lower() != 'auto' and Path(attachment_path).resolve() != Path(resolved_attachment):
            raise ValueError('Attachment must match the validated company/role packet.')
        import sys
        sys.path.insert(0, str(BASE_DIR.parent / 'Resume'))
        from evidence import validate_outreach_evidence
        validate_outreach_evidence(body_text, resume_data, role)

        draft = create_gmail_draft(
            to_email=to_email,
            subject=subject,
            body_text=body_text,
            attachment_path=resolved_attachment,
            idempotency_key=f"{application_operation_key(company_name, role)}:touch1:{to_email.lower()}"
        )
        if draft:
            attach_msg = f" [Attached: {os.path.basename(resolved_attachment)}]" if resolved_attachment else " [No attachment]"
            return f"SUCCESS: Gmail draft created. ID: {draft.get('id')}{attach_msg}"
        else:
            return "ERROR: Gmail draft creation failed."
    except Exception as e:
        return f"ERROR: Failed to save draft: {e}"

def get_pending_contacts() -> str:
    """Reads contacts.csv and returns a list of contacts with 'Pending' status as a JSON string.
    Each contact contains: First Name, Last Name, Company, Role, Details, Status, Email, Resume Path.
    """
    csv_file = BASE_DIR / "contacts.csv"
    
    # Create template CSV if it doesn't exist
    if not csv_file.exists():
        with open(csv_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["First Name", "Last Name", "Company", "Role", "Details", "Status", "Email", "Resume Path"])
            writer.writerow(["Jane", "Doe", "Google", "Product Manager", "Applied via website yesterday for the APM role; focused on payments data analytics", "Pending", "", ""])
        print(f"Created template '{csv_file}'.")
    
    contacts = []
    with open(csv_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader):
            if row.get("Status", "").strip().lower() == "pending":
                row["_row_index"] = idx
                contacts.append(row)
                
    return json.dumps(contacts)

def update_contact_status(first_name: str, last_name: str, company_name: str, status: str, email: str = "", resume_path: str = "") -> str:
    """Updates the status, email, and resume path fields of a contact in contacts.csv.

    Args:
        first_name: First name of the contact.
        last_name: Last name of the contact.
        company_name: Company of the contact.
        status: New status value (e.g. 'Draft Created', 'Failed: Email Not Found').
        email: Email address of the contact (optional).
        resume_path: Path of the attached resume PDF (optional).
    """
    if email and not is_valid_email(email, target_company=company_name, allow_placeholders=True):
        return f"ERROR: Contact email '{email}' failed validation."

    import io
    from reliability_store import store_lock, atomic_write
    csv_file = BASE_DIR / "contacts.csv"
    try:
        with store_lock(csv_file):
            if not csv_file.exists():
                return "ERROR: contacts.csv does not exist."
            original = csv_file.read_text(encoding='utf-8')
            reader = csv.DictReader(io.StringIO(original), strict=True)
            headers = reader.fieldnames
            required = {'First Name', 'Last Name', 'Company', 'Status'}
            required.update({'Email'} if email else set())
            required.update({'Resume Path'} if resume_path else set())
            if not headers or len(set(headers)) != len(headers) or not required.issubset(headers):
                raise ValueError('Invalid or duplicate contact CSV headers.')
            rows = list(reader)
            if any(None in row or any(value is None for value in row.values()) for row in rows):
                raise ValueError('Malformed contact CSV row; data was preserved.')
            norm = lambda value: value.strip().casefold()
            matches = [row for row in rows if norm(row['First Name']) == norm(first_name)
                       and (not last_name.strip() or norm(row['Last Name']) == norm(last_name))
                       and norm(row['Company']) == norm(company_name)]
            if len(matches) != 1:
                raise ValueError('Ambiguous contact match.' if matches else 'Contact not found in contacts.csv.')
            row = matches[0]
            row['Status'] = status
            if email:
                row['Email'] = email
            if resume_path:
                row['Resume Path'] = resume_path
            content = io.StringIO(newline='')
            writer = csv.DictWriter(content, fieldnames=headers)
            writer.writeheader()
            writer.writerows(rows)
            atomic_write(csv_file.with_suffix('.csv.bak'), original)
            atomic_write(csv_file, content.getvalue())
        return f"SUCCESS: Updated contact {first_name} {last_name} at {company_name} status to: {status}"
    except (OSError, ValueError, csv.Error) as exc:
        return f"ERROR: {exc}"


import datetime

def calculate_business_days_ahead(start_date: Optional[datetime.date] = None, days: int = 2) -> datetime.date:
    """Calculates the date exactly N business days ahead, skipping weekends (Saturday & Sunday)."""
    if start_date is None:
        start_date = datetime.date.today()
    
    current = start_date
    added = 0
    while added < days:
        current += datetime.timedelta(days=1)
        if current.weekday() < 5:  # 0=Monday, 4=Friday, 5=Saturday, 6=Sunday
            added += 1
    return current

def calculate_touch_schedule(creation_date: Optional[datetime.date] = None) -> Dict[str, Any]:
    """
    Calculates standard Touch 1 and Touch 2 schedule:
      - Touch 1: Next business day at 9:03 AM (skipping weekends).
      - Touch 2: 2 business days after Touch 1 send at 9:06 AM.
    """
    if creation_date is None:
        creation_date = datetime.date.today()
    
    touch1_date = calculate_business_days_ahead(creation_date, days=1)
    touch2_date = calculate_business_days_ahead(touch1_date, days=2)
    
    return {
        "touch1_date": touch1_date,
        "touch1_scheduled_send": f"{touch1_date.strftime('%Y-%m-%d')} 09:03 AM",
        "touch1_formatted": f"{touch1_date.strftime('%A, %B %d, %Y')} at 9:03 AM",
        "touch2_date": touch2_date,
        "touch2_due_date": str(touch2_date),
        "touch2_send_time": "09:06 AM",
        "touch2_formatted": f"{touch2_date.strftime('%A, %B %d, %Y')} at 9:06 AM"
    }


# --- Single Email Drafting ---

def generate_touch2_nudge(recipient_name: str, role: str) -> Tuple[str, str]:
    """Generates 100% deterministic Touch 2 short nudge template with zero LLM variance."""
    first_name = recipient_name.strip().split()[0] if recipient_name else ""
    if not first_name or first_name.lower() in ["hiring", "team", "recruiter", "hiring manager"]:
        salutation = "Hi there,"
    else:
        salutation = f"Hi {first_name},"

    subject = f"Following up: {role} — Daniel Suh"
    body = f"""{salutation}

Following up in case my note below got buried, totally understand things get busy. Would still love the chance to connect if timing works on your end!

Thanks for your time,
Daniel Suh
linkedin.com/in/daniel-suh-994411297 | 661-476-8194"""
    return subject, body

async def generate_email_draft_async(
    recipient_name: str,
    company_name: str,
    role: str,
    additional_details: str = "",
    resume_attached: bool = True,
    touch_number: int = 1,
    recipient_type: str = "hiring_manager"
) -> Tuple[str, str]:
    """Generates personalized job application follow-up email copy (Touch 1 or Touch 2 Quick Bump) targeting either the Hiring Manager (Priority 1) or Recruiter (Priority 2)."""
    if touch_number == 2:
        return generate_touch2_nudge(recipient_name, role)

    context_file = BASE_DIR / "email-agent-context.md"
    memory_file = BASE_DIR / "memory.md"
    skills_dir = BASE_DIR / "skills"
    master_profile_file = BASE_DIR.parent / "Resume" / "master_profile.json"

    agent_context = context_file.read_text(encoding="utf-8") if context_file.exists() else ""
    memory_context = memory_file.read_text(encoding="utf-8") if memory_file.exists() else ""
    master_profile_str = master_profile_file.read_text(encoding="utf-8") if master_profile_file.exists() else "{}"

    if recipient_type.lower() in ["recruiter", "talent", "hr"]:
        recipient_guidance = """
- **TARGET RECIPIENT: RECRUITER / TALENT PARTNER (PRIORITY 2)**:
  - You are writing to the recruiter / talent partner managing the hiring pipeline.
  - Highlight role qualification alignment, resume review, and enthusiasm for the position.
  - Mention that Daniel's tailored resume PDF is attached.
  - Low-friction ask: "If my profile aligns with what the team is looking for, I'd love to connect for a brief introductory chat. Happy to work around your schedule!"
"""
    else:
        recipient_guidance = """
- **TARGET RECIPIENT: HIRING MANAGER / TEAM LEAD (PRIORITY 1 - HIGHEST IMPORTANCE)**:
  - You are writing directly to the team leader / functional decision-maker (e.g. Head of Product, Director of Engineering, VP of Sales).
  - Emphasize **hands-on technical execution, roadmap contribution, and concrete business metrics** (e.g. saving 50 sales hours/week at Autopilot Local, building autonomous multi-agent engines).
  - Speak directly to team challenges and product architecture.
  - Mention that Daniel's tailored resume PDF is attached.
  - Low-friction ask: "If you have 10–15 minutes sometime in the coming weeks, I’d value the chance to hear more about your team’s technical priorities. Happy to work around your calendar!"
"""

    system_instructions = f"""
You are Daniel Suh's personal automated job application follow-up assistant.
Your goal is to draft a concise, warm, and high-impact follow-up email.

Strict Operating Rules:
- **Exclusively Post-Job-Application Follow-ups**: Express genuine excitement about the role applied to.
- **Always draft — never send automatically.**
- Adhere strictly to Daniel's voice: friendly, direct, warm, concise (under 120 words).
- **TOUCH 1 (INITIAL APPLICATION FOLLOW-UP)**:
  - Length: 80–120 words.
  - **MANDATORY CONCRETE METRIC & PROJECT**: Paragraph 2 MUST cite **1 specific project or work experience with exact quantifiable metrics** from Daniel's verified profile matching the JD (e.g. "built an automated pipeline with Python and Gemini that saved 50 sales hours/week at Autopilot Local", "scaled to 5,000+ monthly customers with ~70% gross margins at Aroma Vault", "achieved a 15% response rate across 300+ enterprise prospects at ClayThis", "developed an autonomous multi-agent outreach engine using Python, Google Antigravity SDK, and Gmail APIs").
  - NEVER write vague generic claims without citing an authentic project and quantifiable metric.
  - Subject format: `Following up: [Role Title] — Daniel Suh`
{recipient_guidance}
- Never use raw placeholders like '[Your Name]', '[Company]', or '[Role]'.
- End with Daniel's exact requested signature block:
  Thanks for your time,
  Daniel Suh
  linkedin.com/in/daniel-suh-994411297 | 661-476-8194

Daniel's Verified Master Profile (Experiences & Projects Bank):
{master_profile_str}

Context & Guidelines:
{agent_context}

Memory Context:
{memory_context}
"""

    config = LocalAgentConfig(
        system_instructions=system_instructions,
        skills_paths=[str(skills_dir.resolve())] if skills_dir.exists() else [],
    )

    async with Agent(config) as agent:
        prompt = f"""
Draft a personalized Touch 1 email for:
- Recipient Name: {recipient_name}
- Recipient Type: {recipient_type.upper()}
- Company: {company_name}
- Role/Title: {role}
- Custom Details/Context: {additional_details}

Format your output cleanly:
Subject: <Subject Line>
---
<Email Body>
"""
        response = await agent.chat(prompt)
        content = await response.text()
        
        default_subject = f"Following up: {role} — Daniel Suh"
        subject = default_subject
        body = content.strip()
        
        # Parse Subject and Body safely
        if "---" in content:
            parts = content.split("---", 1)
            subject_candidate = parts[0].strip()
            body_candidate = parts[1].strip()
            
            # Remove possible markdown headers
            subject_clean = re.sub(r'^[#*\s]*subject\s*:\s*', '', subject_candidate, flags=re.IGNORECASE).strip()
            if subject_clean:
                subject = subject_clean
            if body_candidate:
                body = body_candidate
        elif "subject:" in content.lower():
            match = re.search(r'subject\s*:\s*(.*?)\n\n?(.*)', content, re.IGNORECASE | re.DOTALL)
            if match:
                subject = match.group(1).strip()
                body = match.group(2).strip()

        # Clean code fences if wrapped in ```text
        body = re.sub(r'^```[a-zA-Z]*\n', '', body)
        body = re.sub(r'\n```$', '', body)

        return subject, body

def generate_email_draft(recipient_name: str, company_name: str, role: str, additional_details: str = "", resume_attached: bool = True) -> Tuple[str, str]:
    """Synchronous wrapper for generating email drafts."""
    return asyncio.run(generate_email_draft_async(recipient_name, company_name, role, additional_details, resume_attached))

# --- Main Autonomous CSV Processing Loop ---

async def process_contacts():
    """Runs the main autonomous contact processing loop using the Antigravity Agent."""
    context_file = BASE_DIR / "email-agent-context.md"
    memory_file = BASE_DIR / "memory.md"
    skills_dir = BASE_DIR / "skills"
    master_profile_file = BASE_DIR.parent / "Resume" / "master_profile.json"

    agent_context = context_file.read_text(encoding="utf-8") if context_file.exists() else ""
    memory_context = memory_file.read_text(encoding="utf-8") if memory_file.exists() else ""
    master_profile_str = master_profile_file.read_text(encoding="utf-8") if master_profile_file.exists() else "{}"

    system_instructions = f"""
You are Daniel Suh's personal automated job application follow-up assistant.
Your goal is to process pending contacts in `contacts.csv`, look up emails using Hunter.io, resolve the custom tailored resume PDF from `Resume/output/`, draft high-converting follow-up emails, and stage them as Gmail drafts.

Operating rules:
- **Always draft — never send automatically.**
- Post-job-application follow-ups only.
- Adhere strictly to Daniel's voice: friendly, direct, concise, warm.
- **MANDATORY CONCRETE METRIC & PROJECT**: Always cite 1 specific project or work experience with exact quantifiable metrics from Daniel's profile matching the role.
- End with Daniel's exact signature:
  Thanks for your time,
  Daniel Suh
  linkedin.com/in/daniel-suh-994411297 | 661-476-8194

Daniel's Verified Master Profile (Experiences & Projects Bank):
{master_profile_str}

Guidelines:
{agent_context}

Memory Context:
{memory_context}
"""

    config = LocalAgentConfig(
        system_instructions=system_instructions,
        skills_paths=[str(skills_dir.resolve())] if skills_dir.exists() else [],
        tools=[get_pending_contacts, update_contact_status, find_contact_email, get_tailored_resume_for_job, save_gmail_draft],
        capabilities=CapabilitiesConfig(),
    )

    async with Agent(config) as agent:
        prompt = (
            "Start processing all pending contacts in contacts.csv.\n"
            "For each pending contact:\n"
            "1. Retrieve the contact details using get_pending_contacts.\n"
            "2. Find their email address using find_contact_email.\n"
            "3. If email is not found, update the contact status to 'Failed: Email Not Found'.\n"
            "4. If email is found, find the custom tailored resume PDF using get_tailored_resume_for_job.\n"
            "5. Draft a warm, personalized follow-up email adhering to skills/Job Application Follow-up/SKILL.md, referencing the application and attached tailored resume.\n"
            "6. Save the draft in Gmail using save_gmail_draft with the attached resume PDF.\n"
            "7. Update the contact status in the CSV to 'Draft Created' along with the email and resume path.\n"
            "Process each contact one by one and output a clean summary when completed."
        )
        print("🚀 Starting Antigravity Agent to process job application follow-ups...")
        response = await agent.chat(prompt)
        async for chunk in response:
            print(chunk, end="", flush=True)
        print()

if __name__ == "__main__":
    asyncio.run(process_contacts())

