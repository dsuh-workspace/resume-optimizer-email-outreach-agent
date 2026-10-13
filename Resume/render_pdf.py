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

def generate_resume_html(data, font_size_pt: float = 9.8, line_height: float = 1.27, margin_bottom_px: float = 3.0):
    """Generates an HTML resume matching Daniel's exact master resume proportions and layout."""
    p_info = data.get("personal_info", {})
    full_name = html.escape(p_info.get("full_name", "DANIEL SUH")).upper()
    phone = html.escape(p_info.get("phone", "661-476-8194"))
    email = html.escape(p_info.get("email", "ds42@berkeley.edu"))
    linkedin = p_info.get("linkedin", "linkedin.com/in/daniel-suh-994411297")
    clean_li = linkedin.replace("https://", "").replace("http://", "")
    github = p_info.get("github", "github.com/dsuh-workspace")
    clean_gh = github.replace("https://", "").replace("http://", "")

    # Header Contact line: 661-476-8194 | ds42@berkeley.edu | linkedin.com/in/daniel-suh-994411297 | github.com/dsuh-workspace
    contact_html = f"""{phone} | <a href="mailto:{email}">{email}</a> | <a href="https://{clean_li}">{clean_li}</a> | <a href="https://{clean_gh}">{clean_gh}</a>"""

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
            # Strip markdown **bold** markers — bullet text must be uniform weight throughout
            b_text = re.sub(r'\*\*(.*?)\*\*', r'\1', b_text)
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
      font-size: {font_size_pt}pt;
      line-height: {line_height};
      margin-bottom: {margin_bottom_px}px;
      text-align: justify;
    }}

    ul.skills-bullets {{
      margin-top: 3px;
    }}

    ul.skills-bullets li {{
      font-size: {font_size_pt}pt;
      line-height: {line_height};
      margin-bottom: {margin_bottom_px}px;
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

    <!-- Education -->
    <section>
      <h2 class="section-title">EDUCATION</h2>
      {''.join(edu_entries_html)}
    </section>

    <!-- Experience -->
    <section>
      <h2 class="section-title">EXPERIENCE</h2>
      {''.join(exp_entries_html)}
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
    github = p_info.get("github", "github.com/dsuh-workspace")
    clean_gh = github.replace("https://", "").replace("http://", "")

    lines = []
    lines.append(f"# {full_name}")
    lines.append(f"{phone} | [{email}](mailto:{email}) | [{clean_li}](https://{clean_li}) | [{clean_gh}](https://{clean_gh})\n")

    lines.append("## EDUCATION\n")
    for edu in data.get("education", []):
        lines.append(f"**{edu.get('institution', 'University of California, Berkeley, Haas School of Business')}** — *{edu.get('location', 'Berkeley, CA')}*  ")
        lines.append(f"*{edu.get('degree_title', 'Bachelor of Science')}* — {edu.get('graduation_date', 'May 2028')}  ")
        lines.append(f"{edu.get('major_minor_gpa', 'Major in Business Administration; Minor in Data Science [GPA: 3.52]')}")
        
        if edu.get("coursework"):
            lines.append(f"- **Relevant Coursework:** {', '.join(edu['coursework'])}")
        for h in edu.get("honors", []):
            lines.append(f"- {h}")
        lines.append("")

    lines.append("## EXPERIENCE\n")
    for exp in data.get("experiences", []):
        lines.append(f"**{exp.get('company', '')}** — *{exp.get('location', '')}*  ")
        lines.append(f"*{exp.get('role', '')}* — {exp.get('date_range', '')}")
        for b in exp.get("bullets", []):
            b_text = b if isinstance(b, str) else b.get("text", "")
            lines.append(f"- {b_text}")
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
    """Render into an isolated job directory and publish only a readable PDF."""
    import signal
    import tempfile
    import time
    import pypdf
    chrome_bin = find_chrome_binary()
    if not chrome_bin:
        raise RuntimeError("Google Chrome / Chromium executable not found on system.")
    abs_html_path = os.path.abspath(html_path)
    abs_pdf_path = os.path.abspath(pdf_path)
    with tempfile.TemporaryDirectory(prefix='.copilot-render-', dir=os.path.dirname(abs_pdf_path)) as job_dir:
        rendered = os.path.join(job_dir, 'rendered.pdf')
        cmd = [chrome_bin, '--headless', '--disable-gpu', '--no-pdf-header-footer',
               '--no-first-run', '--no-default-browser-check', '--use-mock-keychain',
               '--disable-component-update', '--disable-sync', '--disable-background-networking',
               '--disable-extensions', f'--user-data-dir={job_dir}/profile',
               f'--print-to-pdf={rendered}', f'file://{abs_html_path}']
        with tempfile.TemporaryFile(mode='w+b') as log:
            process = subprocess.Popen(cmd, stdout=log, stderr=log, start_new_session=True)
            ready = False
            try:
                deadline = time.monotonic() + 60
                while time.monotonic() < deadline:
                    if os.path.isfile(rendered):
                        try:
                            with open(rendered, 'rb') as handle:
                                payload = handle.read()
                            if b'%%EOF' in payload[-1024:]:
                                import io
                                ready = len(pypdf.PdfReader(io.BytesIO(payload)).pages) > 0
                        except (OSError, ValueError, pypdf.errors.PdfReadError):
                            ready = False
                        if ready:
                            break
                    if process.poll() is not None:
                        break
                    time.sleep(0.1)
                if not ready:
                    log.seek(0)
                    details = log.read().decode(errors='replace')[-2000:]
                    raise RuntimeError(f"Chrome did not produce a valid PDF within the render window: {details}")
            finally:
                # Only this isolated render's process group is stopped. Some macOS
                # Chrome helpers keep running after the complete PDF is written.
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.wait(timeout=3)
            os.replace(rendered, abs_pdf_path)
    return abs_pdf_path

def get_pdf_page_count(pdf_path: str) -> int:
    """Calculates the exact number of pages in the generated PDF file."""
    try:
        import pypdf
        reader = pypdf.PdfReader(pdf_path)
        return len(reader.pages)
    except Exception as exc:
        raise RuntimeError(f"Cannot validate PDF page count for {pdf_path}: {exc}") from exc


def get_pdf_bottom_gap(pdf_path):
    """Measure visible text's bottom gap in points in our unrotated Chrome PDFs."""
    import math
    import pypdf
    page = pypdf.PdfReader(pdf_path).pages[0]
    if page.rotation:
        raise ValueError('Cannot validate resume spacing on a rotated page.')
    bottoms = []

    def visit(text, cm, tm, font, font_size):
        if not text.strip():
            return
        # Text coordinates must include Chrome's scaled, inverted page transform.
        baseline = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
        vertical_scale = math.hypot(tm[2] * cm[0] + tm[3] * cm[2],
                                    tm[2] * cm[1] + tm[3] * cm[3])
        # Include a conservative allowance for descenders below the baseline.
        bottoms.append(baseline - abs(font_size) * vertical_scale * 0.25)

    page.extract_text(visitor_text=visit)
    if not bottoms or not all(math.isfinite(y) for y in bottoms):
        raise ValueError('Cannot validate resume spacing: no measurable PDF text.')
    gap = min(bottoms) - float(page.mediabox.bottom)
    if gap < 0 or gap >= float(page.mediabox.height):
        raise ValueError('Cannot validate resume spacing: text is outside the page.')
    return gap


def save_resume_artifacts(tailored_data, output_dir, max_shrink_attempts: int = 3):
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

    # Self-healing 1-page layout optimization loop
    shrink_step = 1
    current_font = 9.8
    current_lh = 1.27
    current_mb = 3.0

    while page_count > 1 and shrink_step <= max_shrink_attempts:
        current_font -= 0.3
        current_lh -= 0.04
        current_mb -= 0.6
        print(f"🔄 [Layout Self-Healer] Page count is {page_count} > 1. Auto-shrinking layout attempt {shrink_step} (font: {current_font:.1f}pt)...")
        html_content = generate_resume_html(
            tailored_data,
            font_size_pt=current_font,
            line_height=current_lh,
            margin_bottom_px=current_mb
        )
        with open(html_file, "w", encoding="utf-8") as f:
            f.write(html_content)
        export_html_to_pdf(html_file, pdf_file)
        page_count = get_pdf_page_count(pdf_file)
        shrink_step += 1

    if page_count != 1:
        raise ValueError(f"Resume must be exactly one page; rendered {page_count} pages after layout adjustments.")

    # A one-page count alone permits an undersized resume with a large bottom gap.
    # Grow only typography/spacing, keeping all content and page margins intact.
    # Aim for <= 60 pt of bottom whitespace; allow <= 72 pt if growth overflows.
    bottom_gap = get_pdf_bottom_gap(pdf_file)
    while bottom_gap > 60 and current_font < 10.8:
        with open(pdf_file, 'rb') as handle:
            previous_pdf = handle.read()
        previous_html = html_content
        next_font = round(min(current_font + 0.2, 10.8), 2)
        next_lh = round(current_lh + 0.01, 2)
        next_mb = round(current_mb + 0.25, 2)
        html_content = generate_resume_html(tailored_data, font_size_pt=next_font,
                                           line_height=next_lh, margin_bottom_px=next_mb)
        with open(html_file, 'w', encoding='utf-8') as handle:
            handle.write(html_content)
        export_html_to_pdf(html_file, pdf_file)
        if get_pdf_page_count(pdf_file) != 1:
            with open(pdf_file, 'wb') as handle:
                handle.write(previous_pdf)
            html_content = previous_html
            with open(html_file, 'w', encoding='utf-8') as handle:
                handle.write(html_content)
            break
        bottom_gap = get_pdf_bottom_gap(pdf_file)
        current_font, current_lh, current_mb = next_font, next_lh, next_mb

    if bottom_gap > 72:
        raise ValueError(f'Resume layout needs review: {bottom_gap / 72:.2f} inches of bottom whitespace '
                         'remain after bounded spacing adjustments. No balanced one-page layout found.')
    tailored_data['layout_settings'] = {
        'bullet_font_pt': round(current_font, 2), 'line_height': round(current_lh, 2),
        'bullet_bottom_margin_px': round(current_mb, 2),
        'bottom_gap_pt': round(bottom_gap, 2), 'page_count': 1,
    }
    print(f'📄 [Layout Validator] One page verified; bottom whitespace: {bottom_gap / 72:.2f} inches.')

    return {
        "html": html_file,
        "md": md_file,
        "pdf": pdf_file,
        "page_count": page_count
    }
