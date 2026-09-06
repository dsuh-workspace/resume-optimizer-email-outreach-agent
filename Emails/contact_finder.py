#!/usr/bin/env python3
"""
Advanced Recruiter & Hiring Manager Discovery Engine
Author: Daniel Suh & Antigravity

Features:
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

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=BASE_DIR / ".env")
if not os.getenv("GEMINI_API_KEY") and (BASE_DIR.parent / ".env").exists():
    load_dotenv(dotenv_path=BASE_DIR.parent / ".env")

HUNTER_API_KEY = os.getenv("HUNTER_API_KEY")

def get_domain_fallback(company_name: str) -> str:
    """Helper to get clean company domain."""
    clean = re.sub(r'[^a-zA-Z0-9]', '', (company_name or "")).lower()
    return f"{clean}.com"

def generate_xray_search_links(company_name: str, role_title: str) -> Dict[str, str]:
    """
    Generates precision Google X-Ray Boolean search URLs for LinkedIn profiles and 'I am hiring' posts.
    """
    # 1. Leadership X-Ray (Hiring Manager)
    hm_query = f'site:linkedin.com/in "{company_name}" ("Head of" OR "Director of" OR "VP" OR "Lead" OR "Group Product Manager" OR "Manager") "{role_title.split()[0]}" -jobs -intern'
    hm_url = f"https://www.google.com/search?q={urllib.parse.quote(hm_query)}"

    # 2. LinkedIn "I'm Hiring" Beacon Search (Managers posting open headcount)
    beacon_query = f'site:linkedin.com/posts "{company_name}" ("hiring" OR "I\'m hiring" OR "growing our team" OR "join my team") "{role_title.split()[0]}"'
    beacon_url = f"https://www.google.com/search?q={urllib.parse.quote(beacon_query)}"

    # 3. Department Recruiter X-Ray
    rec_query = f'site:linkedin.com/in "{company_name}" ("Technical Recruiter" OR "University Recruiter" OR "Talent Partner" OR "Campus Recruiter" OR "Lead Recruiter")'
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
            # Remove trailing numbers/hashes like -984b or -12345
            slug = re.sub(r'-[0-9a-fA-F]{3,}$', '', slug)
            parts = [p.capitalize() for p in slug.split('-') if p and not p.isdigit()]
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

def search_leadership_via_ai(company_name: str, role_title: str) -> Dict[str, List[Dict[str, Any]]]:
    """
    Uses Gemini AI to identify the exact likely hiring managers (Group PM, Director, VP)
    and specialized recruiters (University/APM Recruiter) for a specific role and company.
    """
    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        return {"hiring_managers": [], "recruiters": []}

    prompt = f"""Identify 2-3 realistic current or standard leadership roles/names (Hiring Managers: Head of, Director of, VP, Group PM, Lead) and 2 specialized recruiter titles for '{role_title}' at '{company_name}'.
Return ONLY a valid JSON object matching this schema:
{{
  "hiring_managers": [
    {{"name": "Full Name", "position": "Exact Title & Division (e.g. Group Product Manager, Developer Platform)"}}
  ],
  "recruiters": [
    {{"name": "Full Name", "position": "Exact Title (e.g. University & Emerging Talent Recruiter - APM Lead)"}}
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
        return {
            "hiring_managers": data.get("hiring_managers", []),
            "recruiters": data.get("recruiters", [])
        }
    except Exception as e:
        print(f"⚠️ AI leadership search note: {e}")
        return {"hiring_managers": [], "recruiters": []}

def discover_ranked_contacts(company_name: str, role_title: str = "") -> Dict[str, List[Dict[str, Any]]]:
    """
    Multi-Source Waterfall Discovery Engine:
      1. Hunter.io Domain Search (Live Corporate Directory)
      2. AI Leadership & Recruiter Resolution (Domain & Division Specific)
      3. Email Pattern Synthesis & Deliverability Scoring
    """
    xray_links = generate_xray_search_links(company_name, role_title)
    hms: List[Dict[str, Any]] = []
    recs: List[Dict[str, Any]] = []

    # 1. Primary Source: Hunter.io Domain Directory
    if HUNTER_API_KEY and "YOUR_" not in HUNTER_API_KEY:
        try:
            from agent import get_company_domain
            domain = get_company_domain(company_name)
        except Exception:
            domain = get_domain_fallback(company_name)

        url = "https://api.hunter.io/v2/domain-search"
        params = {"domain": domain, "api_key": HUNTER_API_KEY, "limit": 20}

        try:
            resp = requests.get(url, params=params, timeout=15)
            if resp.status_code == 200:
                emails_list = resp.json().get("data", {}).get("emails", [])
                hm_keywords = ["head", "vp", "director", "lead", "manager", "principal", "chief", "founder", "group"]
                recruiter_keywords = ["recruiter", "talent", "hr", "people", "sourcer", "acquisition", "staffing"]
                role_terms = [w.lower() for w in re.split(r'\W+', role_title) if len(w) > 3 and w.lower() not in ["associate", "senior", "specialist", "junior", "lead", "manager", "intern", "coop"]]

                for item in emails_list:
                    pos = (item.get("position") or "").strip()
                    pos_lower = pos.lower()
                    dept = (item.get("department") or "").lower()
                    fname = (item.get("first_name") or "").strip()
                    lname = (item.get("last_name") or "").strip()
                    email = item.get("value")
                    score = item.get("confidence", 0)

                    if not email or not fname:
                        continue

                    contact_obj = {
                        "name": f"{fname} {lname}".strip(),
                        "first_name": fname,
                        "last_name": lname,
                        "email": email,
                        "position": pos or "Leader",
                        "department": dept,
                        "confidence": score,
                        "relevance_score": score,
                        "source": "Hunter.io Directory"
                    }

                    if any(rk in pos_lower or rk in dept for rk in recruiter_keywords):
                        contact_obj["relevance_score"] += 10
                        recs.append(contact_obj)

                    is_leader = any(lk in pos_lower for lk in hm_keywords) or dept in ["management", "executive", "it", "product", "sales"]
                    if is_leader and not any(rk in pos_lower for rk in recruiter_keywords):
                        if any(rt in pos_lower or rt in dept for rt in role_terms):
                            contact_obj["relevance_score"] += 25
                        hms.append(contact_obj)
        except Exception as e:
            print(f"⚠️ Hunter.io domain search error: {e}")

    # 2. Secondary AI Enrichment Waterfall (If direct matches are sparse)
    if len(hms) < 2 or len(recs) < 1:
        ai_data = search_leadership_via_ai(company_name, role_title)
        
        for hm in ai_data.get("hiring_managers", []):
            name = hm.get("name", "").strip()
            fname, lname = extract_name_from_input(name)
            if fname:
                email, conf = verify_or_synthesize_email(fname, lname, company_name)
                hms.append({
                    "name": name,
                    "first_name": fname,
                    "last_name": lname,
                    "email": email,
                    "position": hm.get("position", "Product Leader"),
                    "confidence": conf,
                    "relevance_score": conf + 20,
                    "source": "AI & Pattern Synthesis"
                })

        for rec in ai_data.get("recruiters", []):
            name = rec.get("name", "").strip()
            fname, lname = extract_name_from_input(name)
            if fname:
                email, conf = verify_or_synthesize_email(fname, lname, company_name)
                recs.append({
                    "name": name,
                    "first_name": fname,
                    "last_name": lname,
                    "email": email,
                    "position": rec.get("position", "Technical Recruiter"),
                    "confidence": conf,
                    "relevance_score": conf + 15,
                    "source": "AI & Pattern Synthesis"
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

    return {
        "hiring_managers": list(unique_hms.values())[:4],
        "recruiters": list(unique_recs.values())[:3],
        "xray_links": xray_links
    }

def verify_or_synthesize_email(first_name: str, last_name: str, company_name: str) -> Tuple[str, int]:
    """
    Finds direct email via Hunter.io Email Finder, or synthesizes based on domain pattern.
    """
    if HUNTER_API_KEY and "YOUR_" not in HUNTER_API_KEY:
        try:
            from agent import find_email_via_hunter
            email, score = find_email_via_hunter(first_name, last_name, company_name)
            if email:
                return email, score or 85
        except Exception:
            pass

    # Synthesis fallback
    try:
        from agent import get_company_domain
        domain = get_company_domain(company_name)
    except Exception:
        domain = get_domain_fallback(company_name)

    clean_f = re.sub(r'[^a-zA-Z0-9]', '', first_name).lower()
    clean_l = re.sub(r'[^a-zA-Z0-9]', '', last_name).lower()
    if clean_f and clean_l:
        return f"{clean_f}.{clean_l}@{domain}", 75
    elif clean_f:
        return f"{clean_f}@{domain}", 65
    return f"recruiting@{domain}", 50

def prompt_hunter_failsafe_loop(
    company_name: str,
    role_title: str,
    contact_type: str = "Hiring Manager",
    input_func = input
) -> Tuple[str, str, str]:
    """
    Fail-safe loop: Prompts the user to supply candidate names & positions (or LinkedIn URLs)
    to query Hunter.io until a verified email is returned or the user tells the system to stop/give up.
    Returns:
      (contact_name, contact_email, contact_position)
    """
    xrays = generate_xray_search_links(company_name, role_title)
    search_link = xrays.get("hiring_manager_xray") if "hiring" in contact_type.lower() else xrays.get("recruiter_xray")

    print(f"\n⚠️ FAIL-SAFE TRIGGERED: Searching Hunter.io for a verified {contact_type} at {company_name}.")
    print(f"🔗 Google X-Ray Search Link: {search_link}")

    while True:
        user_input = input_func(f"\nEnter {contact_type} Name or LinkedIn URL (or type 'stop'/'skip' to give up): ").strip()
        
        if not user_input or user_input.lower() in ["stop", "skip", "give up", "exit", "quit", "cancel", "default"]:
            print(f"🛑 Fail-safe stopped by user. Routing to standard company alias.")
            domain = get_domain_fallback(company_name)
            fallback_email = f"team-lead@{domain}" if "hiring" in contact_type.lower() else f"recruiting@{domain}"
            return f"{contact_type} Lead", fallback_email, "Team Lead"

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
                if found_email:
                    print(f"🎉 SUCCESS! Hunter.io found verified email: {found_email} ({conf}% confidence)")
                    return full_name, found_email, pos_title
                else:
                    print(f"❌ No verified email found on Hunter.io for '{full_name}' at {company_name}.")
            except Exception as e:
                print(f"⚠️ Hunter.io lookup error: {e}")
        else:
            synth_email, score = verify_or_synthesize_email(fname, lname, company_name)
            print(f"✅ Generated pattern-verified email: {synth_email} ({score}% confidence)")
            return full_name, synth_email, pos_title

        print(f"👉 Please provide another name from LinkedIn, or type 'stop' to give up.")
