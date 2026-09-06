import os
import sys
import argparse
import asyncio
from pathlib import Path
from agent import find_email_via_hunter, generate_email_draft_async
from gmail_draft import create_gmail_draft
from resume_finder import find_tailored_resume

BASE_DIR = Path(__file__).resolve().parent

async def main():
    parser = argparse.ArgumentParser(description="Create a post-job-application follow-up Gmail draft with tailored resume.")
    parser.add_argument("--company", required=True, help="Company name (e.g. 'IBM', 'Stripe')")
    parser.add_argument("--role", required=True, help="Job role/title (e.g. 'Associate Product Manager')")
    parser.add_argument("--first_name", required=True, help="Recipient first name")
    parser.add_argument("--last_name", required=True, help="Recipient last name")
    parser.add_argument("--email", help="Recipient email (optional, will search via Hunter.io if not provided)")
    parser.add_argument("--details", default="", help="Custom details or key JD points to emphasize")
    parser.add_argument("--resume", default="auto", help="Path to resume PDF file (optional, defaults to auto-finding tailored PDF from Resume/output/)")

    args = parser.parse_args()

    company = args.company
    role = args.role
    first_name = args.first_name
    last_name = args.last_name
    email = args.email
    details = args.details
    resume = args.resume

    print("=" * 60)
    print(f"🎯 Post-Job-Application Follow-up Outreach: {role} at {company}")
    print("=" * 60)

    # 1. Resolve email if not provided
    if not email:
        print(f"🔍 Searching email for {first_name} {last_name} at {company} via Hunter.io...")
        email, score = find_email_via_hunter(first_name, last_name, company)
        if not email:
            print(f"❌ Error: Could not find email via Hunter.io for {first_name} {last_name} at {company}.")
            sys.exit(1)
        print(f"✅ Found email: {email} (Confidence: {score}%)")
    else:
        print(f"📧 Using provided email: {email}")

    # 2. Resolve custom tailored resume PDF
    resume_path = None
    if resume and resume.strip().lower() != "auto":
        custom_p = Path(resume).expanduser().resolve()
        if custom_p.exists():
            resume_path = str(custom_p)
            print(f"📎 Using specified resume: {resume_path}")
        else:
            print(f"⚠️ Warning: Specified resume path '{resume}' not found. Attempting auto-discovery...")
            resume_path = find_tailored_resume(company, role)
    else:
        print(f"📂 Searching for tailored resume for '{company}' in Resume output folder...")
        resume_path = find_tailored_resume(company, role)

    if resume_path:
        print(f"📎 Attached Resume: {os.path.basename(resume_path)}")
    else:
        print("⚠️ No resume found to attach. Proceeding without attachment.")

    # 3. Draft Email Copy
    print("\n🧠 Drafting personalized follow-up email...")
    subject, body = await generate_email_draft_async(
        recipient_name=f"{first_name} {last_name}",
        company_name=company,
        role=role,
        additional_details=details,
        resume_attached=bool(resume_path)
    )

    if not body:
        print("❌ Error: Generated email body was empty.")
        sys.exit(1)

    print("\n" + "-" * 25 + " Draft Preview " + "-" * 25)
    print(f"To:      {email}")
    print(f"Subject: {subject}")
    if resume_path:
        print(f"Attach:  {resume_path}")
    print("-" * 65)
    print(body)
    print("-" * 65 + "\n")

    # 4. Create Gmail Draft
    print("📤 Staging Gmail draft (Draft-Only Mode)...")
    draft = create_gmail_draft(to_email=email, subject=subject, body_text=body, attachment_path=resume_path)
    if draft:
        print(f"✅ SUCCESS: Gmail draft staged successfully! Draft ID: {draft.get('id')}")
    else:
        print("❌ Error: Failed to stage Gmail draft.")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
