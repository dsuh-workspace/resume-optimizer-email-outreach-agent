import os
import re
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent
RESUME_OUTPUT_DIRS = [
    BASE_DIR.parent / "Resume" / "output",
    Path("/Users/danielsuh/Documents/Coding Stuff/Job Applications/Resume/output"),
    Path("/Users/danielsuh/Documents/Coding Stuff/Resume/output"),
]
BASE_RESUME_PATHS = [
    BASE_DIR.parent / "Resume" / "Daniel_Suh_Resume.pdf",
    BASE_DIR.parent / "Resume" / "DanielSuh_Resume.pdf",
    BASE_DIR.parent / "Resume" / "resume.pdf",
    BASE_DIR.parent / "Resume" / "Resume.pdf",
    Path("/Users/danielsuh/Documents/Coding Stuff/Job Applications/Resume/Daniel_Suh_Resume.pdf"),
    Path("/Users/danielsuh/Documents/Coding Stuff/Job Applications/Resume/DanielSuh_Resume.pdf"),
    Path("/Users/danielsuh/Documents/Coding Stuff/Resume/Daniel_Suh_Resume.pdf"),
    Path("/Users/danielsuh/Documents/Coding Stuff/Resume/DanielSuh_Resume.pdf"),
]

def clean_token(text: str) -> str:
    """Cleans a string to lowercase alphanumeric characters for fuzzy matching."""
    return re.sub(r'[^a-zA-Z0-9]', '', (text or "")).lower()

def find_tailored_resume(company_name: str, role: Optional[str] = None) -> Optional[str]:
    """
    Searches for the tailored resume PDF corresponding to a company/role in Resume/output/.
    
    1. Checks subdirectories in Resume/output/ for matching company name and role.
    2. Sorts matching directories by modification time (most recent first).
    3. Finds the tailored PDF (e.g. Daniel_Suh_Resume_<Company>.pdf, or any .pdf in folder).
    4. Falls back to base DanielSuh_Resume.pdf if no custom folder exists.
    
    Returns:
        Absolute path to the PDF file as a string, or None if no resume is found.
    """
    clean_comp = clean_token(company_name)
    clean_r = clean_token(role) if role else ""

    matching_dirs = []

    for out_dir in RESUME_OUTPUT_DIRS:
        if not out_dir.exists() or not out_dir.is_dir():
            continue
        
        for item in out_dir.iterdir():
            if not item.is_dir():
                continue
            
            folder_clean = clean_token(item.name)
            
            # Check if company name is part of the folder name
            if clean_comp and (clean_comp in folder_clean or folder_clean.startswith(clean_comp)):
                # Score higher if role also matches
                score = 2 if (clean_r and clean_r in folder_clean) else 1
                try:
                    mtime = item.stat().st_mtime
                except Exception:
                    mtime = 0
                matching_dirs.append((score, mtime, item))

    # Sort matching directories: highest score first, then most recently modified
    if matching_dirs:
        matching_dirs.sort(key=lambda x: (x[0], x[1]), reverse=True)
        for _, _, target_dir in matching_dirs:
            # 1. Look for Daniel_Suh_Resume_*.pdf or resume.pdf
            pdf_candidates = list(target_dir.glob("*.pdf"))
            if pdf_candidates:
                # Prefer named resume file over generic
                preferred = [p for p in pdf_candidates if "daniel" in p.name.lower()]
                selected = preferred[0] if preferred else pdf_candidates[0]
                abs_path = str(selected.resolve())
                print(f"[Resume Finder] Found tailored resume for '{company_name}': {abs_path}")
                return abs_path

    # Fallback to base resume
    for base_pdf in BASE_RESUME_PATHS:
        if base_pdf.exists():
            abs_path = str(base_pdf.resolve())
            print(f"[Resume Finder] No specific output folder found for '{company_name}'. Using base resume: {abs_path}")
            return abs_path

    print(f"[Resume Finder] Warning: No resume PDF found for company '{company_name}'.")
    return None


def load_verified_packet(company_name: str, role: str):
    """Require an exact company/role packet with validated evidence; no base fallback."""
    import json
    import sys
    resume_dir = BASE_DIR.parent / 'Resume'
    if str(resume_dir) not in sys.path:
        sys.path.insert(0, str(resume_dir))
    from evidence import validate_resume_evidence
    profile = json.loads((resume_dir / 'master_profile.json').read_text())
    candidates = sorted((resume_dir / 'output').glob('*/tailored_resume.json'), key=lambda p: p.stat().st_mtime, reverse=True)
    for candidate in candidates:
        data = json.loads(candidate.read_text())
        report = data.get('tailoring_report', {})
        company = report.get('target_company') or data.get('target_company')
        title = report.get('target_role') or data.get('target_role')
        if clean_token(company) != clean_token(company_name) or clean_token(title) != clean_token(role):
            continue
        if data.get('evidence_version') != 1:
            raise ValueError('Matching resume has no source evidence. Regenerate it before outreach.')
        validate_resume_evidence(data, profile)
        pdfs = sorted(candidate.parent.glob('*.pdf'))
        if len(pdfs) != 1:
            raise ValueError('Matching packet must contain exactly one resume PDF.')
        import hashlib
        if data.get('artifact_sha256') != hashlib.sha256(pdfs[0].read_bytes()).hexdigest():
            raise ValueError('Resume PDF does not match the validated packet. Regenerate it before outreach.')
        return str(pdfs[0]), data
    raise FileNotFoundError(f'No evidence-backed resume for {role} at {company_name}. Generate one first.')
