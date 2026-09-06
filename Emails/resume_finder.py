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
    BASE_DIR.parent / "Resume" / "DanielSuh_Resume.pdf",
    BASE_DIR.parent / "Resume" / "resume.pdf",
    BASE_DIR.parent / "Resume" / "Resume.pdf",
    Path("/Users/danielsuh/Documents/Coding Stuff/Job Applications/Resume/DanielSuh_Resume.pdf"),
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
