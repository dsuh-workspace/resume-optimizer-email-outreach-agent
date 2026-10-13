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
import hashlib
import argparse
import datetime
from pathlib import Path

# Local imports
SCRIPT_DIR = Path(__file__).parent.resolve()
from tailor import tailor_resume, generate_report_markdown, get_genai_client
from publication import staged_packet, publish_packet
from render_pdf import save_resume_artifacts, clean_file_name

def load_master_profile(profile_path="master_profile.json"):
    path = Path(profile_path)
    if not path.is_absolute():
        path = SCRIPT_DIR / path
    if not path.exists():
        raise FileNotFoundError(f"Verified master profile missing: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def run_pipeline(jd_text, profile_path="master_profile.json", output_base_dir=None, target_pages=1,
                 *, target_company=None, target_role=None, preserve_source_bullets=False):
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
    identity = {} if target_company is None and target_role is None else {'target_company': target_company, 'target_role': target_role}
    if preserve_source_bullets:
        identity['preserve_source_bullets'] = True
    tailored_data = tailor_resume(master_profile, jd_text, client=client, target_pages=target_pages, **identity)

    report_data = tailored_data.get("tailoring_report", {})
    company = report_data.get("target_company", "Target_Company")
    role = report_data.get("target_role", "Target_Role")
    ats_score = report_data.get("ats_match_score", "N/A")
    breakdown = report_data.get("score_breakdown", {})
    tech_s = breakdown.get("tech_skills_score", "N/A")
    biz_s = breakdown.get("business_skills_score", "N/A")
    kw_s = breakdown.get("keyword_coverage_score", "N/A")

    print(f"🎯 Target Role: {role} at {company}")
    print(f"📊 Job-description Match Estimate: {ats_score}/100 (Tech: {tech_s}% | Biz: {biz_s}% | Keywords: {kw_s}%)")

    # 3. Create Output Directory
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    folder_name = f"{clean_file_name(company)}_{clean_file_name(role)}_{timestamp}"
    with staged_packet(output_base_dir if output_base_dir is not None else SCRIPT_DIR / 'output', folder_name) as (stage, destination):
        print("📄 Rendering resume artifacts...")
        artifacts = save_resume_artifacts(tailored_data, stage)
        tailored_data["artifact_sha256"] = hashlib.sha256(Path(artifacts["pdf"]).read_bytes()).hexdigest()
        (stage / "tailoring_report.md").write_text(generate_report_markdown(report_data), encoding='utf-8')
        (stage / "tailored_resume.json").write_text(json.dumps(tailored_data, indent=2), encoding='utf-8')
        publish_packet(stage, destination)
        artifacts = {key: str(destination / Path(value).name) if key in ('pdf', 'md', 'html') else value for key, value in artifacts.items()}
    out_dir = str(destination)
    report_path = str(destination / 'tailoring_report.md')

    print("\n" + "=" * 65)
    print("✅ SUCCESS! Tailored Resume Pack Generated:")
    print("=" * 65)
    print(f"📌 PDF Resume:         {os.path.abspath(artifacts['pdf'])}")
    print(f"📝 Markdown Resume:    {os.path.abspath(artifacts['md'])}")
    print(f"🌐 HTML Resume:        {os.path.abspath(artifacts['html'])}")
    print(f"📊 Job-description Match Report:   {os.path.abspath(report_path)}")
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
    parser.add_argument("--output-dir", type=str, default=None, help="Base output directory (default: private Resume/output)")
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
