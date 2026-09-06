# 📄 Personalized AI Resume Generator & ATS Optimizer

An automated, intelligent resume tailoring system that generates **pixel-perfect, ATS-compliant PDF and Markdown resumes** customized for any job description using Google Gemini AI.

---

## 🌟 Key Features

1. **AI-Powered Tailoring with Zero Hallucination**:
   - Analyzes the target Job Description (role title, company, required tech stack, soft skills, and ATS buzzwords).
   - Dynamically selects, ranks, and customizes bullet points from your `master_profile.json` to emphasize relevant impact and metrics matching the JD.
   - Never invents fake employers, degrees, or roles.
2. **ATS Match Scoring & Optimization Report**:
   - Scores alignment with the job description (`ATS Match Score: 0-100`).
   - Details matched keywords vs. missing competencies.
   - Generates custom **interview talking points** and strategic stories.
3. **Multi-Format Export**:
   - **ATS-Optimized PDF**: Typeset via Headless Chromium / Google Chrome with clean single-column hierarchy, standard fonts, and selectable text.
   - **Markdown (`resume.md`)**: Perfect for quick copy-pasting into text job application fields.
   - **HTML (`resume.html`)**: Clean semantic source.
   - **JSON (`tailored_resume.json`)**: Structured resume payload.
4. **Interactive & CLI Modes**:
   - Run interactively with step-by-step terminal prompts, or automate in bulk with CLI flags.

---

## 🚀 Quick Start

### 1. Configure Master Profile
Edit `master_profile.json` with your real experiences, projects, skills, and coursework. Add as many bullet points and tags as you want — the engine will automatically select the best ones for each job.

### 2. Generate a Tailored Resume

**Interactive Mode:**
```bash
python3 generate_resume.py
# or
./run.sh
```

**Direct CLI Mode:**
```bash
python3 generate_resume.py --jd sample_jd.txt
```

**Inline Text Mode:**
```bash
python3 generate_resume.py --jd "Paste entire job posting here..."
```

---

## 📁 Output Structure

Every run creates a timestamped folder inside `output/`:
```
output/Stripe_Associate_Product_Manager_20260827_170045/
├── resume.pdf             # Pixel-perfect ATS PDF
├── resume.md              # Markdown formatted resume
├── resume.html            # Web-rendered version
├── tailoring_report.md    # ATS score, keyword match breakdown & interview tips
└── tailored_resume.json   # Machine-readable structured resume data
```

---

## ⚙️ Requirements & Environment

- **Python 3.9+** with `google-genai` and `python-dotenv`.
- **Google Chrome** (standard on macOS at `/Applications/Google Chrome.app`).
- `GEMINI_API_KEY` configured in `.env` or `../.env`.
