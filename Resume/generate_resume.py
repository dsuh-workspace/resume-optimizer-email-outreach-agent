#!/usr/bin/env python3
"""
Personalized AI Resume Generator & ATS Optimizer
Author: Daniel Suh & Antigravity
Usage:
  python generate_resume.py --jd sample_jd.txt
  python generate_resume.py --interactive
"""

import os
import sys
import json
import argparse
import datetime
import re
from pathlib import Path

# Local imports
SCRIPT_DIR = Path(__file__).parent.resolve()
from tailor import tailor_resume, generate_report_markdown, get_genai_client
from render_pdf import save_resume_artifacts

def load_master_profile(profile_path="master_profile.json"):
    path = Path(profile_path)
    if not path.is_absolute():
        path = SCRIPT_DIR / path
    if not path.exists():
        template_path = SCRIPT_DIR / "master_profile.template.json"
        if template_path.exists():
            print(f"ℹ️  Notice: '{path.name}' not found. Loading template '{template_path.name}'...")
            path = template_path
        else:
            raise FileNotFoundError(f"Master profile not found at: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def clean_folder_name(name):
    """Sanitizes text for safe directory naming."""
    return re.sub(r'[^a-zA-Z0-9_\-]', '_', name.strip()).strip('_')

def run_pipeline(jd_text, profile_path="master_profile.json", output_base_dir="output", target_pages=1):
    """Main orchestration function."""
    print("=" * 65)
    print("🚀 Starting AI Resume Tailoring Pipeline")
    print("=" * 65)

    # 1. Load Master Profile
    print(f"📂 Loading Master Profile from: {profile_path}...")
    master_profile = load_master_profile(profile_path)
    user_name = master_profile.get("personal_info", {}).get("full_name", "Candidate")
    print(f"👤 Candidate: {user_name}")

    # 2. Tailor Resume via Gemini
    print("🧠 Analyzing Job Description & Tailoring Experience via Gemini AI...")
    client = get_genai_client()
    tailored_data = tailor_resume(master_profile, jd_text, client=client, target_pages=target_pages)

    report_data = tailored_data.get("tailoring_report", {})
    company = report_data.get("target_company", "Target_Company")
    role = report_data.get("target_role", "Target_Role")
    ats_score = report_data.get("ats_match_score", "N/A")
    breakdown = report_data.get("score_breakdown", {})
    tech_s = breakdown.get("tech_skills_score", "N/A")
    biz_s = breakdown.get("business_skills_score", "N/A")
    kw_s = breakdown.get("keyword_coverage_score", "N/A")

    print(f"🎯 Target Target: {role} at {company}")
    print(f"📊 ATS Match Score: {ats_score}/100 (Tech: {tech_s}% | Biz: {biz_s}% | Keywords: {kw_s}%)")

    # 3. Create Output Directory
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    folder_name = f"{clean_folder_name(company)}_{clean_folder_name(role)}_{timestamp}"
    out_dir = os.path.join(output_base_dir, folder_name)
    os.makedirs(out_dir, exist_ok=True)

    # 4. Render HTML, Markdown, and PDF
    print("📄 Rendering ATS-Optimized HTML, Markdown, and Headless Chrome PDF...")
    artifacts = save_resume_artifacts(tailored_data, out_dir)

    # 5. Save Tailoring Report & JSON
    report_md = generate_report_markdown(report_data)
    report_path = os.path.join(out_dir, "tailoring_report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_md)

    json_path = os.path.join(out_dir, "tailored_resume.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(tailored_data, f, indent=2)

    print("\n" + "=" * 65)
    print("✅ SUCCESS! Tailored Resume Pack Generated:")
    print("=" * 65)
    print(f"📌 PDF Resume:         {os.path.abspath(artifacts['pdf'])}")
    print(f"📝 Markdown Resume:    {os.path.abspath(artifacts['md'])}")
    print(f"🌐 HTML Resume:        {os.path.abspath(artifacts['html'])}")
    print(f"📊 ATS Match Report:   {os.path.abspath(report_path)}")
    print(f"📁 Full Output Folder: {os.path.abspath(out_dir)}")
    print("=" * 65)

    return {
        "output_dir": out_dir,
        "pdf": artifacts["pdf"],
        "md": artifacts["md"],
        "html": artifacts["html"],
        "report": report_path,
        "ats_score": ats_score,
        "company": company,
        "role": role
    }

def interactive_mode():
    """Interactive CLI prompt for easy use without remembering flags."""
    print("=" * 65)
    print("🎯 Interactive Resume Generator & ATS Tailoring Tool")
    print("=" * 65)

    default_profile = "master_profile.json"
    profile_path = input(f"Enter path to master profile JSON [{default_profile}]: ").strip()
    if not profile_path:
        profile_path = default_profile

    print("\nHow would you like to provide the Job Description?")
    print("1. Path to a text file (e.g. sample_jd.txt)")
    print("2. Paste raw Job Description text directly")
    choice = input("Select option (1 or 2) [1]: ").strip() or "1"

    jd_text = ""
    if choice == "1":
        jd_file = input("Enter path to JD text file [sample_jd.txt]: ").strip() or "sample_jd.txt"
        if not os.path.exists(jd_file):
            print(f"❌ Error: File '{jd_file}' not found.")
            sys.exit(1)
        with open(jd_file, "r", encoding="utf-8") as f:
            jd_text = f.read()
    else:
        print("\nPaste the Job Description below. When finished, press Ctrl+D (on Mac/Linux) or type 'EOF' on a new line:")
        lines = []
        try:
            while True:
                line = input()
                if line.strip() == "EOF":
                    break
                lines.append(line)
        except EOFError:
            pass
        jd_text = "\n".join(lines).strip()

    if not jd_text.strip():
        print("❌ Error: Job description is empty.")
        sys.exit(1)

    pages = input("Target resume length in pages (1 or 2) [1]: ").strip() or "1"
    target_pages = int(pages) if pages.isdigit() else 1

    run_pipeline(jd_text, profile_path=profile_path, target_pages=target_pages)

def main():
    parser = argparse.ArgumentParser(description="Generate tailored, ATS-optimized PDF and Markdown resumes for job descriptions.")
    parser.add_argument("--jd", type=str, help="Path to job description text file or raw JD string")
    parser.add_argument("--profile", type=str, default="master_profile.json", help="Path to master profile JSON (default: master_profile.json)")
    parser.add_argument("--output-dir", type=str, default="output", help="Base output directory (default: output)")
    parser.add_argument("--pages", type=int, default=1, help="Target resume page length (default: 1)")
    parser.add_argument("--interactive", "-i", action="store_true", help="Launch interactive prompt mode")

    args = parser.parse_args()

    if args.interactive or len(sys.argv) == 1:
        interactive_mode()
        return

    if not args.jd:
        print("❌ Error: Please provide a job description using --jd <file_or_text> or run with --interactive")
        sys.exit(1)

    if os.path.exists(args.jd):
        with open(args.jd, "r", encoding="utf-8") as f:
            jd_text = f.read()
    else:
        jd_text = args.jd

    run_pipeline(jd_text, profile_path=args.profile, output_base_dir=args.output_dir, target_pages=args.pages)

if __name__ == "__main__":
    main()
