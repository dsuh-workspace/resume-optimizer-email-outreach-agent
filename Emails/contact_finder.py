#!/usr/bin/env python3
"""
Advanced Recruiter & Hiring Manager Discovery Engine
Author: Daniel Suh & Antigravity

Features:
  - JD Team Context Extraction: Pulls named people, team name, department, reporting structure from JD text
  - Hybrid Waterfall Enrichment: Hunter.io Domain Search + Title/Domain Keyword Decomposition
  - Google X-Ray & LinkedIn Post Beacon Query Generation
  - Ranked Candidate Match scoring for Hiring Managers (Priority 1) & Recruiters (Priority 2)
  - Corporate Email Pattern Synthesis & Verification
"""

import os
import re
import json
import urllib.parse
import requests
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dotenv import load_dotenv
from email_validator import is_valid_email, validate_email, sanitize_and_validate_email, check_domain_dns

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=BASE_DIR / ".env")
if not os.getenv("GEMINI_API_KEY") and (BASE_DIR.parent / ".env").exists():
    load_dotenv(dotenv_path=BASE_DIR.parent / ".env")

HUNTER_API_KEY = os.getenv("HUNTER_API_KEY")


def extract_jd_team_context(jd_text: str, company_name: str = "", role_title: str = "") -> Dict[str, Any]:
    """
    Extracts structured team and contact intelligence from raw JD text using Gemini AI.

    Returns a dict with:
      - 'team_name':       e.g. "Special Projects", "Platform Growth", "Developer Relations"
      - 'department':      e.g. "Product", "Strategy & Operations", "Engineering"
      - 'named_people':    List of {name, title} — real people explicitly named in the JD text
                           (gold contacts — these definitely work there right now)
      - 'reports_to_title': e.g. "VP of Special Projects", "Head of Strategy" (from "Reports to...")
      - 'adjacent_teams':  e.g. ["Engineering", "Finance", "Research"] (from "partnering with...")
      - 'team_keywords':   Flat list of all department/team signal words for scoring boosts
    """
    gemini_key = os.getenv("GEMINI_API_KEY")
    empty = {
        "team_name": "", "department": "", "named_people": [],
        "reports_to_title": "", "adjacent_teams": [], "team_keywords": []
    }
    if not gemini_key or not jd_text:
        return empty

    # Cap JD text to avoid token waste — first 2000 chars has all the structural info
    jd_snippet = jd_text[:2500]

    prompt = f"""You are a job description intelligence parser. Extract structured contact-finding signals from this JD.

Job Description (for '{role_title}' at '{company_name}'):
\"\"\"
{jd_snippet}
\"\"\"

Extract and return ONLY a valid JSON object with these fields:

{{
  "team_name": "The specific team or group this role sits on (e.g. 'Special Projects', 'Platform Growth', 'Developer Relations'). Empty string if not mentioned.",
  "department": "The primary department (e.g. 'Product', 'Engineering', 'Strategy & Operations', 'Finance'). Empty string if unclear.",
  "named_people": [
    {{
      "name": "Full name of a real person explicitly named in the JD text (NOT a placeholder like '[Manager Name]')",
      "title": "Their title as stated in the JD"
    }}
  ],
  "reports_to_title": "The title of who this role reports to, if mentioned (e.g. 'VP of Special Projects', 'Head of Strategy'). Empty string if not mentioned.",
  "adjacent_teams": ["List of other team or department names this role explicitly partners with, e.g. 'Engineering', 'Finance', 'Research'"],
  "team_keywords": ["Flat list of all distinctive team/department signal words useful for matching against LinkedIn titles and Hunter.io contacts, e.g. 'special projects', 'strategy', 'operations', 'growth', 'platform'"]
}}

STRICT RULES:
- Only include real named people if they are explicitly mentioned BY NAME in the JD text. Do NOT invent names.
- If no people are named, return an empty list for named_people.
- team_keywords should be lowercase, deduplicated, and directly useful for string matching against job titles.
- Return ONLY the JSON object. No explanation."""

    try:
        from google import genai
        client = genai.Client(api_key=gemini_key)
        response = client.models.generate_content(
            model='gemini-flash-latest',
            contents=prompt,
            config={'response_mime_type': 'application/json'}
        )
        data = json.loads(response.text)

        # Validate named_people: strip any entries with empty names (hallucination guard)
        raw_named = data.get("named_people", [])
        named_people = [p for p in raw_named if isinstance(p, dict) and p.get("name", "").strip()]
        if len(raw_named) != len(named_people):
            print(f"ℹ️  JD Context: {len(raw_named) - len(named_people)} unnamed person entry(s) stripped.")

        team_name = (data.get("team_name") or "").strip()
        department = (data.get("department") or "").strip()
        reports_to = (data.get("reports_to_title") or "").strip()
        adjacent = [t.strip() for t in data.get("adjacent_teams", []) if t.strip()]
        keywords = [k.strip().lower() for k in data.get("team_keywords", []) if k.strip()]

        # Auto-derive keywords from team_name and department if Gemini missed them
        for extra in [team_name, department]:
            for word in re.split(r'[\s&/]+', extra.lower()):
                if len(word) > 3 and word not in keywords:
                    keywords.append(word)

        result = {
            "team_name": team_name,
            "department": department,
            "named_people": named_people,
            "reports_to_title": reports_to,
            "adjacent_teams": adjacent,
            "team_keywords": keywords
        }

        summary_parts = []
        if team_name:
            summary_parts.append(f"Team: '{team_name}'")
        if department:
            summary_parts.append(f"Dept: '{department}'")
        if named_people:
            summary_parts.append(f"Named people: {[p['name'] for p in named_people]}")
        if reports_to:
            summary_parts.append(f"Reports to: '{reports_to}'")
        if summary_parts:
            print(f"📋 JD Context Extracted — {' | '.join(summary_parts)}")

        return result

    except Exception as e:
        print(f"⚠️ JD team context extraction note: {e}")
        return empty



def get_domain_fallback(company_name: str) -> str:
    """Helper to get clean company domain."""
    clean = re.sub(r'[^a-zA-Z0-9]', '', (company_name or "")).lower()
    return f"{clean}.com"

def generate_xray_search_links(company_name: str, role_title: str, jd_context: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    """
    Generates precision Google X-Ray Boolean search URLs for LinkedIn profiles and 'I am hiring' posts.
    When jd_context is provided (from extract_jd_team_context), the queries are sharpened to target
    the specific team, department, and reporting structure mentioned in the JD.
    """
    ctx = jd_context or {}
    team_name = ctx.get("team_name", "")
    department = ctx.get("department", "")
    reports_to = ctx.get("reports_to_title", "")

    # Build the most specific HM search term we can:
    # Priority: reports_to_title > team_name > first word of role_title
    if reports_to:
        # JD said who this role reports to — that's exactly who we want
        hm_term = reports_to
        hm_query = f'site:linkedin.com/in "{company_name}" "{hm_term}" -jobs'
    elif team_name:
        # We know the team — search for the head/director/lead of that team
        hm_query = (
            f'site:linkedin.com/in "{company_name}" '
            f'("Head of" OR "Director of" OR "VP" OR "Lead" OR "Manager") '
            f'"{team_name}" -jobs -intern'
        )
    else:
        # Generic fallback
        hm_query = (
            f'site:linkedin.com/in "{company_name}" '
            f'("Head of" OR "Director of" OR "VP" OR "Lead" OR "Group Product Manager" OR "Manager") '
            f'"{role_title.split()[0]}" -jobs -intern'
        )
    hm_url = f"https://www.google.com/search?q={urllib.parse.quote(hm_query)}"

    # Beacon search — use team name if available for more specific "I'm hiring" posts
    beacon_term = team_name or role_title.split()[0]
    beacon_query = (
        f'site:linkedin.com/posts "{company_name}" '
        f'("hiring" OR "I\'m hiring" OR "growing our team" OR "join my team") '
        f'"{beacon_term}"'
    )
    beacon_url = f"https://www.google.com/search?q={urllib.parse.quote(beacon_query)}"

    # Recruiter X-Ray — add department filter if we know the department
    if department:
        rec_query = (
            f'site:linkedin.com/in "{company_name}" '
            f'("Technical Recruiter" OR "University Recruiter" OR "Talent Partner" OR "Campus Recruiter" OR "Lead Recruiter") '
            f'"{department}"'
        )
    else:
        rec_query = (
            f'site:linkedin.com/in "{company_name}" '
            f'("Technical Recruiter" OR "University Recruiter" OR "Talent Partner" OR "Campus Recruiter" OR "Lead Recruiter")'
        )
    rec_url = f"https://www.google.com/search?q={urllib.parse.quote(rec_query)}"

    return {
        "hiring_manager_xray": hm_url,
        "hiring_beacon_posts": beacon_url,
        "recruiter_xray": rec_url,
        "hm_query_raw": hm_query,
        "beacon_query_raw": beacon_query,
        "rec_query_raw": rec_query
    }


def extract_name_from_input(user_input: str) -> Tuple[str, str]:
    """
    Extracts (first_name, last_name) from either a full name or a LinkedIn profile URL.
    Examples:
      - 'https://www.linkedin.com/in/david-song-12345/' -> ('David', 'Song')
      - 'David Song' -> ('David', 'Song')
    """
    clean_input = (user_input or "").strip()
    if "linkedin.com/in/" in clean_input:
        match = re.search(r'linkedin\.com/in/([^/?#]+)', clean_input)
        if match:
            slug = match.group(1)
            # Filter out any token that contains digits (e.g. 12345, 96ag, b8492)
            parts = [p.capitalize() for p in slug.split('-') if p and not re.search(r'\d', p)]
            if len(parts) >= 2:
                return parts[0], parts[-1]
            elif len(parts) == 1:
                return parts[0], ""
    
    parts = clean_input.split()
    if len(parts) >= 2:
        return parts[0].capitalize(), parts[-1].capitalize()
    elif len(parts) == 1:
        return parts[0].capitalize(), ""
    return "", ""

def search_leadership_via_ai(company_name: str, role_title: str, jd_context: Optional[Dict[str, Any]] = None) -> Dict[str, List[Dict[str, Any]]]:
    """
    Uses Gemini AI to identify likely hiring manager TITLES and campus recruiter TITLES
    for a specific role and company. When jd_context is supplied, the prompt is sharpened
    to target the specific team/department extracted from the JD.
    Names are only returned when Gemini has high confidence they are currently employed;
    otherwise the name field is left blank to prevent hallucination.
    """
    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        return {"hiring_managers": [], "recruiters": [], "title_only_hints": []}

    ctx = jd_context or {}
    team_name = ctx.get("team_name", "")
    department = ctx.get("department", "")
    reports_to = ctx.get("reports_to_title", "")
    adjacent = ctx.get("adjacent_teams", [])

    # Build enriched context paragraph for the prompt
    context_lines = []
    if team_name:
        context_lines.append(f"- The role sits on the '{team_name}' team.")
    if department:
        context_lines.append(f"- The primary department is '{department}'.")
    if reports_to:
        context_lines.append(f"- The JD explicitly states this role reports to: '{reports_to}'. "
                             f"This is the primary hiring manager — prioritize finding this exact title.")
    if adjacent:
        context_lines.append(f"- The role partners closely with: {', '.join(adjacent)}.")
    context_block = "\n".join(context_lines) if context_lines else ""

    team_context_section = f"\nJD TEAM INTELLIGENCE (use this to sharpen your search):\n{context_block}\n" if context_block else ""

    prompt = f"""You are a corporate intelligence assistant with strict anti-hallucination rules.

Identify the most likely CURRENT hiring manager roles and campus/university recruiter roles
for the position '{role_title}' at '{company_name}'.{team_context_section}
STRICT RULES:
- You MUST NOT invent or guess employee names.
- If you are NOT highly confident a specific named person currently holds this role at {company_name},
  leave the "name" field as an empty string "".
- You may always return a confident job TITLE even when the name is unknown.
- If the JD says this role reports to a specific title, that title should be your first hiring_manager entry.
- Return 2-3 hiring manager entries and 2 recruiter entries.
- Return ONLY valid JSON, no explanation text.

Return ONLY a valid JSON object matching this schema:
{{
  "hiring_managers": [
    {{"name": "Full Name or empty string if uncertain", "position": "Exact Title & Division (e.g. Head of Special Projects, Strategy & Operations)"}}
  ],
  "recruiters": [
    {{"name": "Full Name or empty string if uncertain", "position": "Exact Title (e.g. University & Emerging Talent Recruiter - APM Lead)"}}
  ]
}}"""

    try:
        from google import genai
        client = genai.Client(api_key=gemini_key)
        response = client.models.generate_content(
            model='gemini-flash-latest',
            contents=prompt,
            config={'response_mime_type': 'application/json'}
        )
        data = json.loads(response.text)
        # Strip entries with blank names — titles only are still useful for auditing
        # but cannot be used for Hunter.io email lookups.
        raw_hms = data.get("hiring_managers", [])
        raw_recs = data.get("recruiters", [])
        named_hms = [e for e in raw_hms if e.get("name", "").strip()]
        named_recs = [e for e in raw_recs if e.get("name", "").strip()]
        blank_count = (len(raw_hms) - len(named_hms)) + (len(raw_recs) - len(named_recs))
        if blank_count:
            print(f"ℹ️  AI hallucination guard: {blank_count} unnamed entry(s) stripped — Hunter lookup skipped for those.")
        return {
            "hiring_managers": named_hms,
            "recruiters": named_recs,
            # Preserve title-only entries for UX display even if no Hunter lookup can be done
            "title_only_hints": [e for e in (raw_hms + raw_recs) if not e.get("name", "").strip()]
        }
    except Exception as e:
        print(f"⚠️ AI leadership search note: {e}")
        return {"hiring_managers": [], "recruiters": [], "title_only_hints": []}


def format_stage1_failure_report(attempts: List[Dict[str, Any]], company_name: str, role_title: str) -> str:
    """Formats a structured diagnostic report detailing what failed across the 3 automated discovery attempts."""
    lines = [
        "\n" + "=" * 70,
        "📋 STAGE 1 AUTOMATIC DISCOVERY FAILURE REPORT",
        f"Target: '{role_title}' at '{company_name}'",
        "=" * 70
    ]
    for att in attempts:
        num = att.get("attempt", "?")
        strategy = att.get("strategy", "Unknown")
        status = att.get("status", "FAILED")
        reason = att.get("reason", "Unknown error")
        icon = "✅" if status == "SUCCESS" else "❌"
        lines.append(f"{icon} Attempt {num} [{strategy}]: {status}")
        lines.append(f"   └─ Diagnostic: {reason}")
    lines.append("-" * 70)
    lines.append("⚠️ All 3 automated discovery attempts failed to establish verified deliverable contacts.")
    lines.append("👉 Transitioning to STAGE 2: Interactive Hunter.io Fail-Safe & Google X-Ray Search.")
    lines.append("=" * 70 + "\n")
    return "\n".join(lines)

def discover_ranked_contacts(company_name: str, role_title: str = "", jd_text: str = "") -> Dict[str, Any]:
    """
    Multi-Source Waterfall Discovery Engine with 4 Discovery Tiers:
      - Attempt 0 (Gold): JD Named People — real contacts explicitly named in the JD text
      - Attempt 1: Hunter.io Live Domain Directory Search (team-keyword boosted)
      - Attempt 2: AI Leadership & Recruiter Resolution + Hunter.io Email Finder (team-context sharpened)
      - Attempt 3: Corporate Domain Pattern Synthesis & Deliverability Verification

    If all automated attempts fail, formats a diagnostic failure report and transitions to Stage 2.
    """
    # ---- Extract JD Team Context (runs before anything else) ----
    print("📋 Extracting team context from job description...")
    jd_context = extract_jd_team_context(jd_text, company_name, role_title)
    team_keywords = jd_context.get("team_keywords", [])

    xray_links = generate_xray_search_links(company_name, role_title, jd_context=jd_context)
    hms: List[Dict[str, Any]] = []
    recs: List[Dict[str, Any]] = []
    attempts: List[Dict[str, Any]] = []

    # -----------------------------------------------------------------
    # ATTEMPT 0: JD Named People — Gold contacts explicitly mentioned in the JD
    # -----------------------------------------------------------------
    named_people = jd_context.get("named_people", [])
    att0_found = 0
    if named_people:
        print(f"🥇 JD Named People found: {[p['name'] for p in named_people]} — attempting direct email resolution...")
        for person in named_people:
            pname = person.get("name", "").strip()
            ptitle = person.get("title", "Gold Contact").strip()
            pfname, plname = extract_name_from_input(pname)
            if not pfname or not plname:
                continue
            found_email, conf = "", 0
            try:
                from agent import find_email_via_hunter
                found_email, conf = find_email_via_hunter(pfname, plname, company_name)
            except Exception:
                pass
            if found_email and is_valid_email(found_email, target_company=company_name):
                contact = {
                    "name": pname,
                    "first_name": pfname,
                    "last_name": plname,
                    "email": found_email,
                    "position": ptitle,
                    "department": jd_context.get("department", ""),
                    "confidence": conf or 0,
                    "relevance_score": 120,  # Highest possible — JD literally named this person
                    "source": "JD Named Person (Gold)"
                }
                # Classify into HM or recruiter based on title
                rec_keywords = ["recruiter", "talent", "hr", "sourcer", "campus", "university"]
                if any(rk in ptitle.lower() for rk in rec_keywords):
                    recs.append(contact)
                else:
                    hms.append(contact)
                att0_found += 1
                print(f"  ✅ Resolved JD-named contact: {pname} ({found_email})")
            else:
                print(f"  ⚠️ No Hunter.io verified email found for JD-named person '{pname}' — skipping unverified synthesis to prevent bounces.")

    if att0_found > 0:
        attempts.append({
            "attempt": 0,
            "strategy": "JD Named People (Gold Contacts)",
            "status": "SUCCESS",
            "reason": f"Resolved {att0_found}/{len(named_people)} explicitly JD-named people"
        })

    # -----------------------------------------------------------------
    # ATTEMPT 1: Hunter.io Live Domain Directory Search
    # -----------------------------------------------------------------
    att1_success = False
    att1_reason = ""
    if not HUNTER_API_KEY or "YOUR_" in HUNTER_API_KEY:
        att1_reason = "Hunter.io API key not configured or is placeholder in .env"
    else:
        try:
            from agent import get_company_domain
            domain = get_company_domain(company_name)
        except Exception:
            domain = get_domain_fallback(company_name)

        url = "https://api.hunter.io/v2/domain-search"

        # Tiered scoring for hiring manager title signals (Priority 4 fix)
        HM_TITLE_SCORES: Dict[str, int] = {
            "head of": 55, "vice president": 50, "vp": 50,
            "director": 45, "group product manager": 45,
            "principal": 40, "senior manager": 35, "senior director": 45,
            "manager": 20, "lead": 8,  # weak signals — low base score
        }
        RECRUITER_TITLE_SCORES: Dict[str, int] = {
            "campus recruiter": 65, "university recruiter": 65,
            "early career": 60, "emerging talent": 60,
            "talent acquisition": 45, "recruiter": 40,
            "hr": 20, "sourcer": 35, "staffing": 30, "people": 15,
        }
        recruiter_keywords = list(RECRUITER_TITLE_SCORES.keys())

        # Role-domain terms for bonus scoring (strip generic noise words)
        role_terms = [w.lower() for w in re.split(r'\W+', role_title)
                      if len(w) > 3 and w.lower() not in
                      {"associate", "senior", "specialist", "junior", "lead",
                       "manager", "intern", "coop", "summer", "analyst"}]

        # Priority 3 fix: two targeted department-filtered calls instead of one generic call
        # This surfaces HR/campus recruiters (often absent from top-20 generic results)
        emails_by_id: Dict[str, Any] = {}
        for dept_filter in ["hr", "management", None]:
            params: Dict[str, Any] = {
                "domain": domain, "api_key": HUNTER_API_KEY, "limit": 100
            }
            if dept_filter:
                params["department"] = dept_filter
            try:
                resp = requests.get(url, params=params, timeout=15)
                if resp.status_code == 200:
                    for item in resp.json().get("data", {}).get("emails", []):
                        key = item.get("value", "")
                        if key and key not in emails_by_id:
                            emails_by_id[key] = item
                elif resp.status_code == 402:
                    att1_reason = "Hunter.io monthly credit quota exhausted (HTTP 402). Only verified mailboxes or direct user input can proceed."
                    print(f"⚠️ {att1_reason}")
                    break
                elif resp.status_code == 429:
                    att1_reason = "Hunter.io rate limit reached (HTTP 429). Only verified mailboxes or direct user input can proceed."
                    print(f"⚠️ {att1_reason}")
                    break
                elif resp.status_code == 401:
                    att1_reason = "Hunter.io API authentication failed (HTTP 401 Unauthorized)."
                    break
            except Exception as e:
                att1_reason = f"Hunter.io domain search network exception: {e}"
                break

        emails_list = list(emails_by_id.values())

        try:
            valid_found = 0
            for item in emails_list:
                pos = (item.get("position") or "").strip()
                pos_lower = pos.lower()
                dept = (item.get("department") or "").lower()
                fname = (item.get("first_name") or "").strip()
                lname = (item.get("last_name") or "").strip()
                email = item.get("value")
                confidence = item.get("confidence", 0)

                if not email or not fname or not is_valid_email(email, target_company=company_name):
                    continue

                contact_obj = {
                    "name": f"{fname} {lname}".strip(),
                    "first_name": fname,
                    "last_name": lname,
                    "email": email,
                    "position": pos or "Leader",
                    "department": dept,
                    "confidence": confidence,
                    "relevance_score": confidence,
                    "source": "Hunter.io Directory"
                }

                # --- Recruiter classification (check first — takes priority) ---
                rec_score_bonus = 0
                for kw, bonus in RECRUITER_TITLE_SCORES.items():
                    if kw in pos_lower or kw in dept:
                        rec_score_bonus = max(rec_score_bonus, bonus)
                if rec_score_bonus:
                    contact_obj["relevance_score"] += rec_score_bonus
                    recs.append(contact_obj)
                    valid_found += 1
                    continue  # Don't double-count as HM

                # --- Hiring Manager classification (tiered scoring, no broad dept match) ---
                hm_score_bonus = 0
                for kw, bonus in HM_TITLE_SCORES.items():
                    if kw in pos_lower:
                        hm_score_bonus = max(hm_score_bonus, bonus)
                if hm_score_bonus:
                    # Role-domain relevance bonus
                    if role_terms and any(rt in pos_lower or rt in dept for rt in role_terms):
                        hm_score_bonus += 20
                    # JD team context bonus: boost contacts matching the specific team/department from the JD
                    if team_keywords and any(tk in pos_lower or tk in dept for tk in team_keywords):
                        hm_score_bonus += 15
                    contact_obj["relevance_score"] += hm_score_bonus
                    hms.append(contact_obj)
                    valid_found += 1

                # Also apply team_keywords boost to recruiters already added
                elif rec_score_bonus and team_keywords:
                    if any(tk in pos_lower or tk in dept for tk in team_keywords):
                        contact_obj["relevance_score"] += 15

            if valid_found > 0:
                att1_success = True
                att1_reason = f"Found {valid_found} deliverable contacts in Hunter.io live directory for '{domain}' (scanned {len(emails_list)} total)"
            elif not att1_reason:
                att1_reason = f"Hunter.io directory returned {len(emails_list)} contacts for '{domain}', but 0 matched role criteria with deliverable emails"
        except Exception as e:
            if not att1_reason:
                att1_reason = f"Hunter.io domain search network exception: {e}"

    attempts.append({
        "attempt": 1,
        "strategy": "Hunter.io Live Domain Directory Search",
        "status": "SUCCESS" if att1_success else "FAILED",
        "reason": att1_reason
    })

    # -----------------------------------------------------------------
    # ATTEMPT 2: AI Leadership Resolution + Hunter.io Email Finder
    # -----------------------------------------------------------------
    att2_success = False
    att2_reason = ""
    # Pass jd_context so Gemini targets the specific team/reports-to structure
    ai_data = search_leadership_via_ai(company_name, role_title, jd_context=jd_context)
    ai_hms = ai_data.get("hiring_managers", [])
    ai_recs = ai_data.get("recruiters", [])

    if not ai_hms and not ai_recs:
        att2_reason = "Gemini AI returned 0 identified leadership or recruiter profiles for this role/company"

    else:
        verified_in_att2 = 0
        if HUNTER_API_KEY and "YOUR_" not in HUNTER_API_KEY:
            try:
                from agent import find_email_via_hunter
                for c_list, target_bucket, pos_default in [
                    (ai_hms, hms, "Product Leader"),
                    (ai_recs, recs, "Technical Recruiter")
                ]:
                    for cand in c_list:
                        cname = cand.get("name", "").strip()
                        cfname, clname = extract_name_from_input(cname)
                        if cfname and clname:
                            found_em, conf = find_email_via_hunter(cfname, clname, company_name)
                            if found_em and is_valid_email(found_em, target_company=company_name):
                                target_bucket.append({
                                    "name": cname,
                                    "first_name": cfname,
                                    "last_name": clname,
                                    "email": found_em,
                                    "position": cand.get("position", pos_default),
                                    "confidence": conf or 0,
                                    "relevance_score": (conf or 0) + 20,
                                    "source": "AI & Hunter Email Finder"
                                })
                                verified_in_att2 += 1
            except Exception as e:
                att2_reason = f"Hunter.io email-finder lookup exception: {e}"

        if verified_in_att2 > 0:
            att2_success = True
            att2_reason = f"Verified {verified_in_att2} direct candidate mailbox addresses via Hunter.io Email Finder"
        elif not att2_reason:
            cand_names = [c.get('name') for c in (ai_hms + ai_recs) if c.get('name')]
            att2_reason = f"AI identified candidates {cand_names[:3]}, but Hunter.io Email Finder returned no verified mailbox"

    attempts.append({
        "attempt": 2,
        "strategy": "AI Leadership Resolution + Hunter Email Finder",
        "status": "SUCCESS" if att2_success else "FAILED",
        "reason": att2_reason
    })

    # -----------------------------------------------------------------
    # ATTEMPT 3: Corporate Domain Verification (Anti-Bounce Policy)
    # -----------------------------------------------------------------
    att3_success = False
    att3_reason = ""
    try:
        from agent import get_company_domain
        domain = get_company_domain(company_name)
    except Exception:
        domain = get_domain_fallback(company_name)

    domain_ok, domain_msg = check_domain_dns(domain)
    if not domain_ok:
        att3_reason = f"Target company domain '{domain}' failed DNS host verification ({domain_msg})"
    else:
        # Per Zero-Hallucination & Anti-Bounce mandate:
        # We do NOT silently inject unverified synthesized emails into candidate pools.
        # Synthesized first.last@domain emails lack mailbox verification and result in 550 bounces.
        att3_reason = (
            f"Domain '{domain}' is active with DNS host resolution, but automated mailbox verification "
            f"is required via Hunter.io or Stage 2 user lookup to prevent email bounces."
        )
        att3_success = False

    attempts.append({
        "attempt": 3,
        "strategy": "Domain Check (not mailbox verification)",
        "status": "SUCCESS" if att3_success else "FAILED",
        "reason": att3_reason
    })

    # Sort & Deduplicate
    unique_hms = {}
    for h in sorted(hms, key=lambda x: x.get("relevance_score", 0), reverse=True):
        if h["name"] not in unique_hms:
            unique_hms[h["name"]] = h

    unique_recs = {}
    for r in sorted(recs, key=lambda x: x.get("relevance_score", 0), reverse=True):
        if r["name"] not in unique_recs:
            unique_recs[r["name"]] = r

    stage1_failed = (len(unique_hms) == 0 and len(unique_recs) == 0)
    report_text = ""
    if stage1_failed:
        report_text = format_stage1_failure_report(attempts, company_name, role_title)
        print(report_text)

    return {
        "hiring_managers": list(unique_hms.values())[:4],
        "recruiters": list(unique_recs.values())[:3],
        "xray_links": xray_links,
        "stage1_attempts": attempts,
        "stage1_failed": stage1_failed,
        "failure_report": report_text
    }

def verify_or_synthesize_email(first_name: str, last_name: str, company_name: str):
    """Legacy name: only returns a Hunter-verified mailbox, never synthesizes one."""
    from agent import find_email_via_hunter
    email, score = find_email_via_hunter(first_name, last_name, company_name)
    if email and score is not None and score >= 50:
        return email, score
    return '', 0


def prompt_hunter_failsafe_loop(
    company_name: str,
    role_title: str,
    contact_type: str = "Hiring Manager",
    input_func = input,
    user_provided_emails=None
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Fail-safe loop: Prompts the user to supply candidate names & positions (or LinkedIn URLs)
    to query Hunter.io until a verified email is returned or the user tells the system to stop/give up.
    Returns:
      (contact_name, contact_email, contact_position) or (None, None, None) if skipped
    """
    xrays = generate_xray_search_links(company_name, role_title)
    search_link = xrays.get("hiring_manager_xray") if "hiring" in contact_type.lower() else xrays.get("recruiter_xray")

    print(f"\n⚠️ FAIL-SAFE TRIGGERED: Searching Hunter.io for a verified {contact_type} at {company_name}.")
    print(f"🔗 Google X-Ray Search Link: {search_link}")

    while True:
        user_input = input_func(f"\nEnter {contact_type} Name or LinkedIn URL (or type 'stop'/'skip' to give up): ").strip()
        
        if not user_input or user_input.lower() in ["stop", "skip", "give up", "exit", "quit", "cancel", "default"]:
            print(f"\n🛑 Stage 2 skipped by user. Per user instructions, generic fallback aliases (#3) are disabled.")
            print(f"⚠️ Ending workflow for {contact_type}.")
            return None, None, None

        # Direct email entry support
        if "@" in user_input and "." in user_input:
            clean_in_email, err = sanitize_and_validate_email(user_input, target_company=company_name)
            if clean_in_email:
                local_prefix = clean_in_email.split("@")[0].replace(".", " ").title()
                pos_input = input_func(f"Enter {contact_type}'s Title (optional, e.g. 'Group Product Manager'): ").strip()
                pos_title = pos_input or ("Group Product Manager" if "hiring" in contact_type.lower() else "Technical Recruiter")
                if user_provided_emails is not None:
                    user_provided_emails.add(clean_in_email.lower())
                print(f"✅ Accepted direct validated email: {clean_in_email}")
                return local_prefix, clean_in_email, pos_title
            else:
                print(f"⚠️ Provided email '{user_input}' failed validation: {err}. Please enter a valid name or email.")
                continue

        pos_input = input_func(f"Enter {contact_type}'s Title (optional, e.g. 'Group Product Manager'): ").strip()
        pos_title = pos_input or ("Group Product Manager" if "hiring" in contact_type.lower() else "Technical Recruiter")

        fname, lname = extract_name_from_input(user_input)
        full_name = f"{fname} {lname}".strip() or user_input

        if not fname or not lname:
            print(f"⚠️ Please provide both first and last name (e.g. 'David Song') or a valid LinkedIn URL.")
            continue

        print(f"🔍 Querying Hunter.io Email Finder for '{full_name}' at '{company_name}'...")
        if HUNTER_API_KEY and "YOUR_" not in HUNTER_API_KEY:
            try:
                from agent import find_email_via_hunter
                found_email, conf = find_email_via_hunter(fname, lname, company_name)
                if found_email and is_valid_email(found_email, target_company=company_name):
                    print(f"🎉 SUCCESS! Hunter.io found verified valid email: {found_email} ({conf}% confidence)")
                    return full_name, found_email, pos_title
                else:
                    print(f"❌ No verified valid email found on Hunter.io for '{full_name}' at {company_name}.")
            except Exception as e:
                print(f"⚠️ Hunter.io lookup error: {e}")
        else:
            synth_email, score = verify_or_synthesize_email(fname, lname, company_name)
            if is_valid_email(synth_email, target_company=company_name):
                print(f"✅ Hunter-verified email: {synth_email} ({score}% confidence)")
                return full_name, synth_email, pos_title

        print(f"👉 Please provide another name from LinkedIn, or type 'stop' to give up.")
