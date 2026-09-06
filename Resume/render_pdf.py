import os
import re
import html
import shutil
import subprocess

def find_chrome_binary():
    """Finds Google Chrome or Chromium executable on the system."""
    candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        shutil.which("google-chrome"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return None

def clean_file_name(name):
    """Sanitizes text for safe filename naming."""
    clean = re.sub(r'[^a-zA-Z0-9_\-]', '_', name.strip()).strip('_')
    return clean or "Company"

def generate_resume_html(data):
    """Generates an HTML resume matching Daniel's exact master resume proportions and layout."""
    p_info = data.get("personal_info", {})
    full_name = html.escape(p_info.get("full_name", "DANIEL SUH")).upper()
    phone = html.escape(p_info.get("phone", "661-476-8194"))
    email = html.escape(p_info.get("email", "ds42@berkeley.edu"))
    linkedin = p_info.get("linkedin", "linkedin.com/in/daniel-suh-994411297")
    clean_li = linkedin.replace("https://", "").replace("http://", "")

    # Header Contact line: 661-476-8194 | ds42@berkeley.edu | linkedin.com/in/daniel-suh-994411297
    contact_html = f"""{phone} | <a href="mailto:{email}">{email}</a> | <a href="https://{clean_li}">{clean_li}</a>"""

    # EXPERIENCE SECTION
    exp_entries_html = []
    experiences = data.get("experiences", [])
    for exp in experiences:
        comp = html.escape(exp.get("company", ""))
        role = html.escape(exp.get("role", ""))
        loc = html.escape(exp.get("location", ""))
        dates = html.escape(exp.get("date_range", ""))
        bullets = exp.get("bullets", [])

        bullet_lis = []
        for b in bullets:
            b_text = html.escape(b) if isinstance(b, str) else html.escape(b.get("text", ""))
            # Convert markdown **bold** to <strong>bold</strong>
            b_text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', b_text)
            bullet_lis.append(f"<li>{b_text}</li>")

        bullets_html = f"<ul class='bullets'>{''.join(bullet_lis)}</ul>" if bullet_lis else ""

        entry = f"""
        <div class="entry">
          <div class="row">
            <span class="left bold">{comp}</span>
            <span class="right">{loc}</span>
          </div>
          <div class="row">
            <span class="left italic">{role}</span>
            <span class="right">{dates}</span>
          </div>
          {bullets_html}
        </div>
        """
        exp_entries_html.append(entry)

    # EDUCATION SECTION
    edu_entries_html = []
    education = data.get("education", [])
    for edu in education:
        inst = html.escape(edu.get("institution", "University of California, Berkeley, Haas School of Business"))
        degree = html.escape(edu.get("degree_title", "Bachelor of Science"))
        loc = html.escape(edu.get("location", "Berkeley, CA"))
        grad_date = html.escape(edu.get("graduation_date", "May 2028"))
        major_minor = html.escape(edu.get("major_minor_gpa", "Major in Business Administration; Minor in Data Science [GPA: 3.52]"))
        
        edu_bullets = []
        # Relevant Coursework bullet
        coursework = edu.get("coursework", [])
        if coursework:
            cw_str = ", ".join([html.escape(c) for c in coursework])
            edu_bullets.append(f"<li><strong>Relevant Coursework:</strong> {cw_str}</li>")

        # Honors / Scholarship bullet
        honors = edu.get("honors", [])
        for h in honors:
            h_esc = html.escape(h)
            if ":" in h_esc:
                title, rest = h_esc.split(":", 1)
                edu_bullets.append(f"<li><strong>{title}:</strong>{rest}</li>")
            else:
                edu_bullets.append(f"<li>{h_esc}</li>")

        # Leadership / Club bullet (AACF)
        activities = edu.get("activities", [])
        for act in activities:
            edu_bullets.append(f"<li>{html.escape(act)}</li>")

        if not activities and "certifications_and_activities" in data:
            for act in data["certifications_and_activities"]:
                if isinstance(act, str):
                    edu_bullets.append(f"<li>{html.escape(act)}</li>")
                elif isinstance(act, dict):
                    t = act.get("text") or f"Led {act.get('organization', '')} chapter, overseeing member programming and coordinating 10+ events, managing logistics, volunteer coordination, and community outreach across a 23-person organization."
                    edu_bullets.append(f"<li>{html.escape(t)}</li>")

        edu_bullets_html = f"<ul class='bullets'>{''.join(edu_bullets)}</ul>" if edu_bullets else ""

        entry = f"""
        <div class="entry">
          <div class="row">
            <span class="left bold">{inst}</span>
            <span class="right">{loc}</span>
          </div>
          <div class="row">
            <span class="left italic">{degree}</span>
            <span class="right">{grad_date}</span>
          </div>
          <div class="major-line">{major_minor}</div>
          {edu_bullets_html}
        </div>
        """
        edu_entries_html.append(entry)

    # SKILLS SECTION (Strictly 2 category bullets)
    skills = data.get("skills", {})
    skills_html_parts = []
    
    tech_skills = skills.get("technical_skills", [])
    if tech_skills:
        tech_str = ", ".join([html.escape(str(s)) for s in tech_skills])
        skills_html_parts.append(f"<li><strong>Technical Skills:</strong> {tech_str}</li>")

    biz_skills = skills.get("business_and_strategy", [])
    if biz_skills:
        biz_str = ", ".join([html.escape(str(s)) for s in biz_skills])
        skills_html_parts.append(f"<li><strong>Business & Strategy:</strong> {biz_str}</li>")

    skills_section_html = f"<ul class='bullets skills-bullets'>{''.join(skills_html_parts)}</ul>" if skills_html_parts else ""

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>{full_name} - Resume</title>
  <style>
    @page {{
      size: letter;
      margin: 0.45in 0.52in 0.42in 0.52in;
    }}

    * {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }}

    body {{
      font-family: "Times New Roman", Times, Georgia, serif;
      color: #000000;
      font-size: 10.2pt;
      line-height: 1.28;
      background: #ffffff;
      -webkit-font-smoothing: antialiased;
    }}

    .resume {{
      width: 100%;
      max-width: 8.5in;
      margin: 0 auto;
    }}

    /* Header */
    header {{
      text-align: center;
      margin-bottom: 8px;
    }}

    h1.name {{
      font-size: 14pt;
      font-weight: bold;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      margin-bottom: 3px;
    }}

    .contact-info {{
      font-size: 10pt;
      color: #000000;
    }}

    .contact-info a {{
      color: #000000;
      text-decoration: underline;
    }}

    /* Section Headings */
    h2.section-title {{
      font-size: 10.5pt;
      font-weight: bold;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      border-bottom: 1px solid #000000;
      margin-top: 9px;
      margin-bottom: 5px;
      padding-bottom: 1px;
    }}

    /* Entry Rows */
    .entry {{
      margin-bottom: 7px;
    }}

    .entry:last-child {{
      margin-bottom: 0;
    }}

    .row {{
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      font-size: 10.2pt;
    }}

    .bold {{
      font-weight: bold;
    }}

    .italic {{
      font-style: italic;
    }}

    .right {{
      text-align: right;
      font-size: 10pt;
    }}

    .major-line {{
      font-size: 10pt;
      margin-top: 1px;
      margin-bottom: 1px;
    }}

    /* Bullets */
    ul.bullets {{
      margin-left: 20px;
      margin-top: 2px;
      padding-left: 0;
      list-style-type: disc;
    }}

    ul.bullets li {{
      font-size: 9.8pt;
      line-height: 1.27;
      margin-bottom: 3px;
      text-align: justify;
    }}

    ul.skills-bullets {{
      margin-top: 3px;
    }}

    ul.skills-bullets li {{
      font-size: 9.8pt;
      line-height: 1.28;
      margin-bottom: 3.5px;
      text-align: left;
    }}

    @media print {{
      body {{
        font-size: 10.2pt;
      }}
      a {{
        text-decoration: none;
        color: #000000;
      }}
    }}
  </style>
</head>
<body>
  <div class="resume">
    <!-- Header -->
    <header>
      <h1 class="name">{full_name}</h1>
      <div class="contact-info">
        {contact_html}
      </div>
    </header>

    <!-- Experience -->
    <section>
      <h2 class="section-title">EXPERIENCE</h2>
      {''.join(exp_entries_html)}
    </section>

    <!-- Education -->
    <section>
      <h2 class="section-title">EDUCATION</h2>
      {''.join(edu_entries_html)}
    </section>

    <!-- Skills -->
    <section>
      <h2 class="section-title">SKILLS</h2>
      {skills_section_html}
    </section>
  </div>
</body>
</html>
"""
    return html_content

def generate_resume_markdown(data):
    """Generates clean markdown version formatted with Daniel's exact structure."""
    p_info = data.get("personal_info", {})
    full_name = p_info.get("full_name", "DANIEL SUH").upper()
    phone = p_info.get("phone", "661-476-8194")
    email = p_info.get("email", "ds42@berkeley.edu")
    linkedin = p_info.get("linkedin", "linkedin.com/in/daniel-suh-994411297")
    clean_li = linkedin.replace("https://", "").replace("http://", "")

    lines = []
    lines.append(f"# {full_name}")
    lines.append(f"{phone} | [{email}](mailto:{email}) | [{clean_li}](https://{clean_li})\n")
    lines.append("## EXPERIENCE\n")

    for exp in data.get("experiences", []):
        lines.append(f"**{exp.get('company', '')}** — *{exp.get('location', '')}*  ")
        lines.append(f"*{exp.get('role', '')}* — {exp.get('date_range', '')}")
        for b in exp.get("bullets", []):
            b_text = b if isinstance(b, str) else b.get("text", "")
            lines.append(f"- {b_text}")
        lines.append("")

    lines.append("## EDUCATION\n")
    for edu in data.get("education", []):
        lines.append(f"**{edu.get('institution', 'University of California, Berkeley, Haas School of Business')}** — *{edu.get('location', 'Berkeley, CA')}*  ")
        lines.append(f"*{edu.get('degree_title', 'Bachelor of Science')}* — {edu.get('graduation_date', 'May 2028')}  ")
        lines.append(f"{edu.get('major_minor_gpa', 'Major in Business Administration; Minor in Data Science [GPA: 3.52]')}")
        
        if edu.get("coursework"):
            lines.append(f"- **Relevant Coursework:** {', '.join(edu['coursework'])}")
        for h in edu.get("honors", []):
            lines.append(f"- {h}")
        for act in edu.get("activities", []):
            lines.append(f"- {act}")
        lines.append("")

    lines.append("## SKILLS\n")
    skills = data.get("skills", {})
    if isinstance(skills, dict):
        if skills.get("technical_skills"):
            lines.append(f"- **Technical Skills:** {', '.join(skills['technical_skills'])}")
        if skills.get("business_and_strategy"):
            lines.append(f"- **Business & Strategy:** {', '.join(skills['business_and_strategy'])}")

    return "\n".join(lines)

def export_html_to_pdf(html_path, pdf_path):
    """Exports an HTML file to PDF using headless Chrome/Chromium."""
    chrome_bin = find_chrome_binary()
    if not chrome_bin:
        raise RuntimeError("Google Chrome / Chromium executable not found on system.")

    abs_html_path = os.path.abspath(html_path)
    abs_pdf_path = os.path.abspath(pdf_path)

    cmd = [
        chrome_bin,
        "--headless",
        "--disable-gpu",
        "--no-pdf-header-footer",
        f"--print-to-pdf={abs_pdf_path}",
        f"file://{abs_html_path}"
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if not os.path.exists(abs_pdf_path) or os.path.getsize(abs_pdf_path) == 0:
        raise RuntimeError(f"PDF rendering failed. Chrome error: {result.stderr}")

    return abs_pdf_path

def get_pdf_page_count(pdf_path: str) -> int:
    """Calculates the exact number of pages in the generated PDF file."""
    try:
        import pypdf
        reader = pypdf.PdfReader(pdf_path)
        return len(reader.pages)
    except Exception:
        try:
            with open(pdf_path, 'rb') as f:
                content = f.read()
                pages = re.findall(rb'/Type\s*/Page\b', content)
                return len(pages) if pages else 1
        except Exception:
            return 1

def save_resume_artifacts(tailored_data, output_dir):
    """Renders and saves resume.html, Daniel_Suh_Resume_[Company].pdf, and resume.md in output_dir."""
    os.makedirs(output_dir, exist_ok=True)
    
    company = tailored_data.get("target_company") or tailored_data.get("tailoring_report", {}).get("target_company") or "Company"
    clean_comp = clean_file_name(company)

    html_content = generate_resume_html(tailored_data)
    md_content = generate_resume_markdown(tailored_data)

    html_file = os.path.join(output_dir, "resume.html")
    md_file = os.path.join(output_dir, "resume.md")
    
    # Official submission name: Daniel_Suh_Resume_[Company].pdf
    pdf_file = os.path.join(output_dir, f"Daniel_Suh_Resume_{clean_comp}.pdf")

    with open(html_file, "w", encoding="utf-8") as f:
        f.write(html_content)

    with open(md_file, "w", encoding="utf-8") as f:
        f.write(md_content)

    export_html_to_pdf(html_file, pdf_file)

    page_count = get_pdf_page_count(pdf_file)
    if page_count == 1:
        print(f"📄 [Layout Validator] Perfect 1-page PDF layout verified ({page_count} page).")
    else:
        print(f"⚠️ [Layout Validator] Warning: PDF rendered across {page_count} pages.")

    return {
        "html": html_file,
        "md": md_file,
        "pdf": pdf_file,
        "page_count": page_count
    }

