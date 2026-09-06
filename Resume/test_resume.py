import os
import unittest
import json
from pathlib import Path

from tailor import calculate_deterministic_ats_score, parse_json_safely
from render_pdf import get_pdf_page_count, generate_resume_html, generate_resume_markdown

class TestResumeSuite(unittest.TestCase):

    def test_json_safe_parsing(self):
        """Tests that parse_json_safely extracts valid dicts from code fences or raw strings."""
        raw_json = '```json\n{"test_key": "test_value"}\n```'
        parsed = parse_json_safely(raw_json)
        self.assertEqual(parsed.get("test_key"), "test_value")

        plain_json = '{"number": 42}'
        self.assertEqual(parse_json_safely(plain_json).get("number"), 42)

    def test_deterministic_ats_scoring_math(self):
        """Tests that calculate_deterministic_ats_score computes weighted mathematical scores correctly."""
        sample_tailored = {
            "experiences": [
                {
                    "company": "Autopilot Local",
                    "role": "AI Solutions Consultant",
                    "bullets": ["Engineered Python and Gemini AI agent pipeline saving 50 hours/week."]
                }
            ],
            "education": [{"coursework": ["Business Analytics", "Data Science"]}],
            "skills": {
                "technical_skills": ["Python", "SQL", "Gemini API", "AI Agents"],
                "business_and_strategy": ["B2B Sales", "Strategic Partnerships"]
            }
        }
        sample_jd_analysis = {
            "top_priority_tech_skills": ["Python", "SQL", "AI Agents", "Java", "Docker"], # 3/5 matched -> 60%
            "top_priority_business_skills": ["B2B Sales", "Strategic Partnerships"],       # 2/2 matched -> 100%
            "ats_keywords": ["Python", "Data Science", "Consultant", "Kubernetes"]          # 3/4 matched -> 75%
        }
        score, breakdown = calculate_deterministic_ats_score(sample_tailored, sample_jd_analysis)
        self.assertIsInstance(score, int)
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 100)
        self.assertEqual(breakdown["tech_skills_score"], 60)
        self.assertEqual(breakdown["business_skills_score"], 100)
        self.assertEqual(breakdown["keyword_coverage_score"], 75)
        # Expected: 0.45*60 + 0.30*100 + 0.25*75 = 27 + 30 + 18.75 = 75.75 -> 76
        self.assertEqual(score, 76)

    def test_pdf_page_validator(self):
        """Tests that get_pdf_page_count accurately counts pages on existing PDFs."""
        base_pdf = Path("DanielSuh_Resume.pdf")
        if base_pdf.exists():
            pages = get_pdf_page_count(str(base_pdf))
            self.assertEqual(pages, 1)

    def test_html_and_markdown_generation(self):
        """Tests that HTML and Markdown resumes render without template syntax errors."""
        mock_data = {
            "personal_info": {"full_name": "Daniel Suh", "email": "ds42@berkeley.edu", "phone": "661-476-8194", "linkedin": "linkedin.com/in/daniel-suh-994411297"},
            "experiences": [
                {
                    "company": "Autopilot Local",
                    "role": "AI Solutions Consultant",
                    "location": "Berkeley, CA",
                    "date_range": "2026 - Present",
                    "bullets": ["Saved **50 sales hours** with AI."]
                }
            ],
            "education": [{"institution": "UC Berkeley", "degree_title": "BS", "location": "Berkeley, CA", "graduation_date": "2028", "major_minor_gpa": "Major in Business"}],
            "skills": {"technical_skills": ["Python"], "business_and_strategy": ["Sales"]}
        }
        html_out = generate_resume_html(mock_data)
        md_out = generate_resume_markdown(mock_data)
        self.assertIn("DANIEL SUH", html_out)
        self.assertIn("Autopilot Local", html_out)
        self.assertIn("# DANIEL SUH", md_out)
        self.assertIn("Autopilot Local", md_out)

    def test_master_profile_experiences_only(self):
        """Verifies master_profile contains experiences and 0 projects."""
        profile_path = Path(__file__).parent / "master_profile.json"
        if not profile_path.exists():
            profile_path = Path(__file__).parent / "master_profile.template.json"
        with open(profile_path, "r", encoding="utf-8") as f:
            profile = json.load(f)
        self.assertNotIn("projects", profile)
        exp_companies = [e["company"] for e in profile.get("experiences", [])]
        self.assertGreaterEqual(len(exp_companies), 1)

if __name__ == "__main__":
    unittest.main()
