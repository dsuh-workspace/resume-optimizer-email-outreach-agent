#!/usr/bin/env python3
"""
Seniority & Hierarchy Sanity-Check Subagent
Author: Daniel Suh & Antigravity

Audits discovered candidate titles against the target role's seniority tier:
  - Internships/Co-ops: Flags Partners/C-Suite as Too Senior; elevates Campus Recruiters (P1) & Engagement Managers/Peers (P2).
  - Experienced/Mid-Level: Elevates Direct Engineering/Product/Sales Managers (P1) & Senior IC Peers (P2).
  - Preserves Hunter.io API credits by screening candidates before email resolution.
"""

import re
from typing import List, Dict, Any, Tuple, Optional

def detect_seniority_tier(role_title: str, jd_text: str = "") -> str:
    """
    Detects the seniority tier of the job application with strict priority on role_title:
      - 'INTERNSHIP': Summer Analyst, Intern, Co-Op, Student, Undergraduate.
      - 'NEW_GRAD': New Grad, Entry-Level, Associate, Rotational, Early Career.
      - 'EXECUTIVE': Director, VP, Head of, Principal, Partner, Chief.
      - 'MID_LEVEL': Standard experienced roles (Product Manager, Software Engineer, Consultant).
    """
    title_lower = (role_title or "").lower()
    jd_lower = (jd_text or "")[:1200].lower()

    # 1. Check title explicitly for Internship / Co-Op / Summer Analyst
    intern_title_keywords = ["intern", "summer analyst", "co-op", "coop", "internship", "student", "undergraduate", "summer associate"]
    if any(k in title_lower for k in intern_title_keywords):
        return "INTERNSHIP"

    # 2. Check title for New Grad / Entry Level
    new_grad_title_keywords = ["new grad", "entry-level", "entry level", "junior", "rotational", "early career"]
    if any(k in title_lower for k in new_grad_title_keywords):
        return "NEW_GRAD"

    # 3. Check title for Executive / Leadership
    exec_title_keywords = ["director", "vice president", "vp", "head of", "managing director", "partner", "chief", "principal"]
    if any(k in title_lower for k in exec_title_keywords):
        return "EXECUTIVE"

    # 4. If title is neutral (e.g. "Brand Sales Specialist" or "Developer"), check JD body context
    if any(k in jd_lower for k in ["sales internship program", "summer intern", "internship program", "actively enrolled", "registered undergraduate", "class of 2027", "class of 2028", "seeking a bachelor's"]):
        return "INTERNSHIP"

    if any(k in jd_lower for k in ["new graduate program", "rotational program", "university graduate"]):
        return "NEW_GRAD"

    return "MID_LEVEL"

def audit_candidate_seniority(candidate: Dict[str, Any], seniority_tier: str, company_name: str = "") -> Dict[str, Any]:
    """
    Evaluates an individual candidate's position and department against the target seniority tier.
    Returns the candidate dict enriched with:
      - 'sanity_rating': 'OPTIMAL_GATEKEEPER' | 'HIGH_RELEVANCE_REFERRAL' | 'EXECUTIVE_SPONSOR_HIGH' | 'TOO_SENIOR_REJECT' | 'WRONG_PIPELINE_REJECT'
      - 'sanity_badge': Color-coded visual badge
      - 'sanity_rationale': Concise explanation of the recommendation
      - 'adjusted_score': Calibrated relevance score
    """
    pos = (candidate.get("position") or "").strip()
    pos_lower = pos.lower()
    dept = (candidate.get("department") or "").lower()
    base_score = candidate.get("relevance_score", 70)

    # Keywords classification
    exec_titles = ["partner", "managing director", "global head", "practice head", "vp", "vice president", "president", "chief", "founder", "c-level"]
    campus_rec_titles = ["campus", "university", "early career", "undergraduate", "emerging talent", "student", "recruiter", "talent acquisition"]
    peer_titles = ["engagement manager", "consultant", "senior consultant", "associate", "analyst", "product manager", "engineer", "lead", "specialist"]

    is_exec = any(t in pos_lower for t in exec_titles)
    is_campus_rec = any(t in pos_lower for t in ["campus", "university", "early career", "undergraduate", "emerging talent"])
    is_general_rec = any(t in pos_lower for t in ["recruiter", "talent", "hr", "sourcer", "staffing"])
    is_peer = any(t in pos_lower for t in peer_titles) and not is_exec and not is_general_rec

    if seniority_tier in ["INTERNSHIP", "NEW_GRAD"]:
        if is_exec:
            return {
                **candidate,
                "sanity_rating": "TOO_SENIOR_REJECT",
                "sanity_badge": "🔴 TOO SENIOR FOR INTERN OUTREACH",
                "sanity_rationale": "Partner / Executive level. Disconnected from intern resume screening; high probability of ignored cold outreach.",
                "adjusted_score": base_score - 40
            }
        elif is_campus_rec:
            return {
                **candidate,
                "sanity_rating": "OPTIMAL_GATEKEEPER",
                "sanity_badge": "🟢 OPTIMAL GATEKEEPER (PRIMARY)",
                "sanity_rationale": "Directly screens and manages the undergraduate and Summer Analyst candidate pool.",
                "adjusted_score": base_score + 35
            }
        elif is_peer:
            return {
                **candidate,
                "sanity_rating": "HIGH_RELEVANCE_REFERRAL",
                "sanity_badge": "🟢 PEER / REFERRAL TARGET (SECONDARY)",
                "sanity_rationale": "Active project team member / consultant. Ideal for 15-minute coffee chat and internal employee referral.",
                "adjusted_score": base_score + 25
            }
        elif is_general_rec:
            return {
                **candidate,
                "sanity_rating": "EXECUTIVE_SPONSOR_HIGH",
                "sanity_badge": "🟡 GENERAL RECRUITER",
                "sanity_rationale": "Talent partner at the firm; may route to campus recruiting team.",
                "adjusted_score": base_score + 10
            }
        else:
            return {
                **candidate,
                "sanity_rating": "EXECUTIVE_SPONSOR_HIGH",
                "sanity_badge": "🟡 MID-LEVEL MANAGER",
                "sanity_rationale": "Team lead or manager. May have headcount input, but campus recruiters have higher intern conversion.",
                "adjusted_score": base_score
            }

    else:
        # Experienced / Mid-Level roles
        if is_campus_rec:
            return {
                **candidate,
                "sanity_rating": "WRONG_PIPELINE_REJECT",
                "sanity_badge": "🔴 WRONG PIPELINE (CAMPUS ONLY)",
                "sanity_rationale": "Campus recruiter managing student programs; does not handle experienced hires.",
                "adjusted_score": base_score - 30
            }
        elif is_exec:
            return {
                **candidate,
                "sanity_rating": "EXECUTIVE_SPONSOR_HIGH",
                "sanity_badge": "🟡 EXECUTIVE SPONSOR",
                "sanity_rationale": "High-level department head. Good for strategic visibility if direct manager is not found.",
                "adjusted_score": base_score + 10
            }
        else:
            return {
                **candidate,
                "sanity_rating": "OPTIMAL_GATEKEEPER",
                "sanity_badge": "🟢 DIRECT HIRING MANAGER",
                "sanity_rationale": "Direct team lead / functional decision-maker for this position.",
                "adjusted_score": base_score + 30
            }

def run_seniority_sanity_audit(
    discovered_contacts: Dict[str, List[Dict[str, Any]]],
    role_title: str,
    company_name: str,
    jd_text: str = ""
) -> Dict[str, Any]:
    """
    Executes full sanity check and re-ranking across all candidate pools.
    Returns:
      {
        'seniority_tier': str,
        'recommended_p1': Optional[Dict[str, Any]],
        'recommended_p2': Optional[Dict[str, Any]],
        'audited_hiring_managers': List[Dict[str, Any]],
        'audited_recruiters': List[Dict[str, Any]],
        'total_evaluated': int
      }
    """
    tier = detect_seniority_tier(role_title, jd_text)
    
    raw_hms = discovered_contacts.get("hiring_managers", [])
    raw_recs = discovered_contacts.get("recruiters", [])

    audited_hms = [audit_candidate_seniority(c, tier, company_name) for c in raw_hms]
    audited_recs = [audit_candidate_seniority(c, tier, company_name) for c in raw_recs]

    all_audited = audited_hms + audited_recs
    all_sorted = sorted(all_audited, key=lambda x: x.get("adjusted_score", 0), reverse=True)

    rec_p1 = None
    rec_p2 = None

    if tier in ["INTERNSHIP", "NEW_GRAD"]:
        gatekeepers = [c for c in all_sorted if c.get("sanity_rating") == "OPTIMAL_GATEKEEPER"]
        referrals = [c for c in all_sorted if c.get("sanity_rating") == "HIGH_RELEVANCE_REFERRAL"]
        
        rec_p1 = gatekeepers[0] if gatekeepers else (all_sorted[0] if all_sorted else None)
        
        if referrals:
            rec_p2 = referrals[0]
        elif len(gatekeepers) > 1:
            rec_p2 = gatekeepers[1]
        elif len(all_sorted) > 1:
            rec_p2 = all_sorted[1]
    else:
        hiring_mgrs = [c for c in audited_hms if c.get("sanity_rating") != "WRONG_PIPELINE_REJECT"]
        recruiters = [c for c in audited_recs if c.get("sanity_rating") != "WRONG_PIPELINE_REJECT"]
        
        rec_p1 = hiring_mgrs[0] if hiring_mgrs else (all_sorted[0] if all_sorted else None)
        rec_p2 = recruiters[0] if recruiters else (all_sorted[1] if len(all_sorted) > 1 else None)

    return {
        "seniority_tier": tier,
        "recommended_p1": rec_p1,
        "recommended_p2": rec_p2,
        "audited_hiring_managers": sorted(audited_hms, key=lambda x: x.get("adjusted_score", 0), reverse=True),
        "audited_recruiters": sorted(audited_recs, key=lambda x: x.get("adjusted_score", 0), reverse=True),
        "total_evaluated": len(all_audited)
    }

def render_sanity_report_cli(audit_data: Dict[str, Any], company_name: str, role_title: str) -> None:
    """Prints a beautiful formatted sanity check report to terminal."""
    tier = audit_data.get("seniority_tier", "MID_LEVEL")
    p1 = audit_data.get("recommended_p1", {})
    p2 = audit_data.get("recommended_p2", {})

    print("\n" + "=" * 68)
    print(f"🧠 CONTACT SENIORITY & HIERARCHY SANITY AUDIT")
    print(f"🏢 Company: {company_name} | 💼 Role: {role_title}")
    print(f"🎯 Detected Seniority Tier: 🎓 {tier}")
    print("=" * 68)

    print("\n📋 EVALUATION OF DISCOVERED CANDIDATES:")
    
    all_candidates = audit_data.get("audited_recruiters", []) + audit_data.get("audited_hiring_managers", [])
    for idx, c in enumerate(all_candidates, 1):
        name = c.get("name", "Unknown")
        pos = c.get("position", "N/A")
        badge = c.get("sanity_badge", "🟡 EVALUATED")
        reason = c.get("sanity_rationale", "")
        email = c.get("email", "Pattern verified")
        print(f"\n  [{idx}] {name} — {pos}")
        print(f"      {badge}")
        print(f"      💡 {reason}")
        print(f"      📧 {email}")

    print("\n" + "-" * 68)
    print("⭐ RECOMMENDED OUTREACH STRATEGY:")
    if p1:
        print(f"  🥇 PRIMARY (Gatekeeper): {p1.get('name')} ({p1.get('position')}) -> {p1.get('email')}")
    if p2:
        print(f"  🥈 SECONDARY (Referral): {p2.get('name')} ({p2.get('position')}) -> {p2.get('email')}")
    print("=" * 68 + "\n")
