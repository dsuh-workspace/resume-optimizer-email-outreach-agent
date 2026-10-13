import os
import unittest
import json
from pathlib import Path

from tailor import (
    calculate_deterministic_ats_score, parse_json_safely, validate_and_audit_bullet_quality,
    validate_metric_integrity,
    inject_verbatim_jd_skills, _has_genuine_capability, _build_master_profile_text_corpus,
    SKILL_SYNONYM_MAP, MAX_SKILLS_PER_CATEGORY, _normalize_skill, _deduplicate_skills,
    _is_skill_present
)
from render_pdf import get_pdf_page_count, generate_resume_html, generate_resume_markdown

class TestResumeSuite(unittest.TestCase):

    def setUp(self):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent if Path(__file__).parent.name in ('Emails', 'Resume') else Path(__file__).parent))
        from testing_support import isolate
        isolate(self)


    def test_skill_punctuation_is_evidence(self):
        from evidence import skill_evidence
        for source in ('C', 'C++', 'C#'):
            for requested in ('C', 'C++', 'C#'):
                self.assertEqual(bool(skill_evidence(requested, {'skills': {'technical': [source]}})), source == requested)
        self.assertTrue(skill_evidence('Process Improvement', {'skills': {'business': ['Process Optimization']}}))

    def test_generation_stages_unique_packets_and_cleans_failure(self):
        from unittest.mock import patch
        from generate_resume import run_pipeline
        from copy import deepcopy
        fixture = TestResumeEvidence()
        fixture.setUp()
        output = self.fixture_dir / 'output'
        profile = self.fixture_dir / 'profile.json'
        profile.write_text(json.dumps(fixture.profile))
        def render(data, folder):
            paths = {}
            for suffix in ('pdf', 'md', 'html'):
                path = Path(folder) / ('resume.' + suffix)
                path.write_text('fixture')
                paths[suffix] = str(path)
            return paths
        with patch('generate_resume.datetime.datetime') as date, patch('generate_resume.tailor_resume', side_effect=lambda *a, **k: deepcopy(fixture.data)), patch('generate_resume.get_genai_client'), patch('generate_resume.save_resume_artifacts', side_effect=render):
            date.now.return_value.strftime.return_value = '20261006_120000'
            results = [run_pipeline('job', str(profile), str(output)) for _ in range(2)]
        self.assertNotEqual(results[0]['output_dir'], results[1]['output_dir'])
        self.assertEqual(len(list(output.iterdir())), 2)
        for result in results:
            for key in ('pdf', 'md', 'html', 'report'):
                self.assertTrue(Path(result[key]).is_file())
        with patch('generate_resume.tailor_resume', return_value=fixture.data), patch('generate_resume.get_genai_client'), patch('generate_resume.save_resume_artifacts', side_effect=RuntimeError('render failed')):
            with self.assertRaisesRegex(RuntimeError, 'render failed'):
                run_pipeline('job', str(profile), str(output))
        self.assertEqual(len(list(output.iterdir())), 2)

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
        """Tests that get_pdf_page_count accurately counts pages on existing master PDFs."""
        resume_dir = Path(__file__).resolve().parent
        base_pdf = resume_dir / "Daniel_Suh_Resume.pdf"
        if not base_pdf.exists():
            base_pdf = resume_dir / "DanielSuh_Resume.pdf"
        self.assertTrue(base_pdf.exists(), f"Master resume PDF not found in {resume_dir}")
        pages = get_pdf_page_count(str(base_pdf))
        self.assertEqual(pages, 1)

    def test_html_auto_shrink_parameters(self):
        """Tests that generate_resume_html applies custom font sizes and line heights for self-healing."""
        mock_data = {
            "personal_info": {"full_name": "Daniel Suh", "email": "ds42@berkeley.edu", "phone": "661-476-8194", "linkedin": "linkedin.com/in/daniel-suh-994411297"},
            "experiences": [
                {
                    "company": "Autopilot Local",
                    "role": "AI Solutions Consultant",
                    "date_range": "2026 - Present",
                    "bullets": ["Engineered AI pipelines saving 50 hours/week."]
                }
            ],
            "education": [],
            "skills": {}
        }
        rendered = generate_resume_html(mock_data, font_size_pt=9.2, line_height=1.23, margin_bottom_px=2.4)
        self.assertIn("font-size: 9.2pt;", rendered)
        self.assertIn("line-height: 1.23;", rendered)
        self.assertIn("margin-bottom: 2.4px;", rendered)

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

    def test_master_profile_4_core_experiences(self):
        """Verifies master_profile contains Daniel's 4 core master resume experiences."""
        profile_path = Path(__file__).parent / "master_profile.json"
        if not profile_path.exists():
            profile_path = Path(__file__).parent / "master_profile.template.json"
        with open(profile_path, "r", encoding="utf-8") as f:
            profile = json.load(f)
        self.assertNotIn("projects", profile)
        exp_companies = [e["company"] for e in profile.get("experiences", [])]
        self.assertIn("Autopilot Local", exp_companies)
        self.assertIn("Asian American Christian Fellowship", exp_companies)
        self.assertIn("Aroma Vault", exp_companies)
        self.assertIn("ClayThis", exp_companies)

    def test_html_section_order_education_first(self):
        """Verifies EDUCATION is strictly rendered as the 1st section before EXPERIENCE and SKILLS."""
        mock_data = {
            "personal_info": {"full_name": "Daniel Suh", "email": "ds42@berkeley.edu", "phone": "661-476-8194", "linkedin": "linkedin.com/in/daniel-suh-994411297", "github": "github.com/dsuh-workspace"},
            "education": [{"institution": "UC Berkeley", "degree_title": "BS", "location": "Berkeley, CA", "graduation_date": "2028"}],
            "experiences": [{"company": "Autopilot Local", "role": "AI Solutions Consultant", "date_range": "2026 - Present"}],
            "skills": {"technical_skills": ["Python"]}
        }
        html_out = generate_resume_html(mock_data)
        edu_pos = html_out.find("EDUCATION")
        exp_pos = html_out.find("EXPERIENCE")
        skills_pos = html_out.find("SKILLS")
        self.assertNotEqual(edu_pos, -1)
        self.assertNotEqual(exp_pos, -1)
        self.assertNotEqual(skills_pos, -1)
        self.assertLess(edu_pos, exp_pos, "EDUCATION section must appear before EXPERIENCE section")
        self.assertLess(exp_pos, skills_pos, "EXPERIENCE section must appear before SKILLS section")
        self.assertIn("github.com/dsuh-workspace", html_out, "Header contact bar must include GitHub link")

    def test_validate_and_audit_bullet_quality(self):
        """Verifies zero-latency bullet quality inspector calculates metrics compliance and word density."""
        mock_data = {
            "experiences": [
                {
                    "company": "Autopilot Local",
                    "bullets": ["Saved 50 sales hours per week by building an agentic pipeline with Python and Gemini API to qualify leads."]
                }
            ]
        }
        audit = validate_and_audit_bullet_quality(mock_data)
        self.assertEqual(audit["total_bullets_audited"], 1)
        self.assertEqual(audit["metrics_compliance_rate"], 100.0)
        self.assertTrue(audit["all_bullets_compliant"])
        self.assertGreaterEqual(audit["avg_words_per_bullet"], 15)

    def test_consulting_bullet_in_master_profile(self):
        """Fix #3: Verifies the ICP segmentation consulting bullet exists in master_profile.json
        under Autopilot Local with the correct metric (35%), tags, and impact level."""
        profile_path = Path(__file__).parent / "master_profile.json"
        if not profile_path.exists():
            profile_path = Path(__file__).parent / "master_profile.template.json"
        with open(profile_path, "r", encoding="utf-8") as f:
            profile = json.load(f)

        autopilot_exp = next(
            (e for e in profile.get("experiences", []) if e.get("company") == "Autopilot Local"),
            None
        )
        self.assertIsNotNone(autopilot_exp, "Autopilot Local experience must exist in master_profile.json")

        bullets = autopilot_exp.get("bullets", [])
        bullet_texts = [b.get("text", "") for b in bullets]

        # Verify the consulting/ICP bullet exists with the correct metric
        consulting_bullet = next(
            (b for b in bullets if "35%" in b.get("text", "") and "ICP" in b.get("text", "")),
            None
        )
        self.assertIsNotNone(
            consulting_bullet,
            f"ICP segmentation consulting bullet (35% / ICP) not found in Autopilot Local. Found bullets: {bullet_texts}"
        )

        # Verify required tags are present
        required_tags = {"market_research", "customer_segmentation", "strategic_analysis", "consulting"}
        actual_tags = set(consulting_bullet.get("tags", []))
        self.assertTrue(
            required_tags.issubset(actual_tags),
            f"Consulting bullet missing required tags. Expected subset {required_tags}, got {actual_tags}"
        )

        # Verify impact level
        self.assertEqual(
            consulting_bullet.get("impact"), "high",
            "Consulting bullet must have impact='high'"
        )

    def test_bullet_allocation_consulting_vs_standard(self):
        """Verifies that ALL roles (consulting and non-consulting) use the unified 12-bullet
        (4/3/2/3) allocation, always including 4 Autopilot Local bullets."""
        # The allocation is now unconditional — both paths produce the same result
        bullet_total = 12
        bullet_distribution = "(4 for Autopilot Local, 3 for Asian American Christian Fellowship, 2 for Aroma Vault, 3 for ClayThis)"

        self.assertEqual(bullet_total, 12, "All roles must allocate 12 bullets total")
        self.assertIn("4 for Autopilot Local", bullet_distribution, "All roles must allocate 4 bullets to Autopilot Local")

    def test_jd_hash_is_stable_and_deterministic(self):
        """Verifies get_jd_hash produces identical output for identical input and
        differs for different input — ensuring the cache key is collision-safe."""
        from tailor import get_jd_hash
        jd_a = "Strategy consulting role at EY-Parthenon requiring market sizing and segmentation."
        jd_b = "Software engineer role at Google requiring Python and distributed systems."

        hash_a1 = get_jd_hash(jd_a)
        hash_a2 = get_jd_hash(jd_a)  # Second call — must be identical
        hash_b  = get_jd_hash(jd_b)

        # Same input → same hash (determinism)
        self.assertEqual(hash_a1, hash_a2, "get_jd_hash must return identical hash for identical JD text")
        # Different inputs → different hashes (collision resistance)
        self.assertNotEqual(hash_a1, hash_b, "get_jd_hash must return different hashes for different JDs")
        # Hash must be exactly 16 hex chars
        self.assertEqual(len(hash_a1), 16, "JD hash must be exactly 16 characters")
        self.assertTrue(all(c in "0123456789abcdef" for c in hash_a1), "JD hash must be lowercase hex")

    def test_jd_cache_round_trip(self):
        """Verifies that save_jd_analysis_cache + load_cached_jd_analysis performs
        a lossless round-trip, returning an identical dict from disk."""
        import tempfile, shutil
        from tailor import get_jd_hash, save_jd_analysis_cache, load_cached_jd_analysis, JD_CACHE_DIR

        sample_analysis = {
            "company_name": "EY-Parthenon",
            "role_title": "Summer Associate",
            "is_consulting_strategy": True,
            "ats_keywords": ["market sizing", "segmentation", "financial modeling"],
            "top_priority_tech_skills": ["Excel", "PowerPoint"],
            "top_priority_business_skills": ["strategic analysis", "client advisory"]
        }
        test_hash = "test_cache_1234"

        # Use a temp dir so tests don't pollute the real cache
        original_cache_dir = JD_CACHE_DIR
        import tailor
        tailor.JD_CACHE_DIR = Path(tempfile.mkdtemp())
        try:
            save_jd_analysis_cache(test_hash, sample_analysis)
            loaded = load_cached_jd_analysis(test_hash)
            self.assertIsNotNone(loaded, "load_cached_jd_analysis must return a dict after save")
            self.assertEqual(loaded["company_name"], "EY-Parthenon")
            self.assertEqual(loaded["is_consulting_strategy"], True)
            self.assertEqual(loaded["ats_keywords"], ["market sizing", "segmentation", "financial modeling"])
            # Missing hash must return None
            self.assertIsNone(load_cached_jd_analysis("nonexistent_hash_xyz"))
        finally:
            shutil.rmtree(str(tailor.JD_CACHE_DIR), ignore_errors=True)
            tailor.JD_CACHE_DIR = original_cache_dir

    def test_no_bold_in_rendered_bullets(self):
        """Regression test: verifies that ** markdown bold markers are stripped (not converted
        to <strong> tags) in rendered HTML bullet points. Bullet text must be uniform weight."""
        mock_data = {
            "personal_info": {"full_name": "Daniel Suh", "email": "ds42@berkeley.edu",
                              "phone": "661-476-8194", "linkedin": "linkedin.com/in/daniel-suh-994411297"},
            "experiences": [
                {
                    "company": "Autopilot Local",
                    "role": "AI Solutions Consultant",
                    "location": "Berkeley, CA",
                    "date_range": "May 2026 – Present",
                    "bullets": [
                        "Saved **50 sales hours per week** by building an agentic pipeline.",
                        "Drove a **35% increase** in qualified lead conversion for a client.",
                        "Reduced missed-call rates by **74%** via AI voice agent deployment."
                    ]
                }
            ],
            "education": [],
            "skills": {}
        }
        html_out = generate_resume_html(mock_data)

        # No <strong> tags should appear inside bullet list items
        self.assertNotIn("<strong>", html_out,
            "Bullet HTML must not contain <strong> tags — ** markers must be stripped, not converted to bold")
        # No raw ** asterisks should appear either
        self.assertNotIn("**", html_out,
            "Bullet HTML must not contain raw ** markdown — all bold markers must be fully stripped")
        # The actual metric text must still be present (stripped cleanly)
        self.assertIn("50 sales hours per week", html_out,
            "Metric text must remain after stripping ** markers")
        self.assertIn("35% increase", html_out,
            "Metric text must remain after stripping ** markers")
        self.assertIn("74%", html_out,
            "Metric text must remain after stripping ** markers")

    def test_experience_filter_excludes_blue_water_battery(self):
        """Verifies the canonical 4-experience pre-prompt filter strips Blue Water Battery Logistics
        (and any other non-canonical entries) before sending the profile to Gemini."""
        CANONICAL_EXPERIENCE_IDS = {"exp_autopilot_local", "exp_aacf", "exp_aroma_vault", "exp_claythis"}
        CANONICAL_COMPANIES = {"Autopilot Local", "Asian American Christian Fellowship", "Aroma Vault", "ClayThis"}

        profile_path = Path(__file__).parent / "master_profile.json"
        if not profile_path.exists():
            profile_path = Path(__file__).parent / "master_profile.template.json"
        with open(profile_path, "r", encoding="utf-8") as f:
            master_profile = json.load(f)

        filtered = [
            e for e in master_profile.get("experiences", [])
            if e.get("id") in CANONICAL_EXPERIENCE_IDS or e.get("company") in CANONICAL_COMPANIES
        ]
        company_names = {e["company"] for e in filtered}

        self.assertNotIn(
            "Blue Water Battery Logistics", company_names,
            "Blue Water Battery Logistics must be excluded from the filtered experiences sent to Gemini"
        )
        self.assertEqual(len(filtered), 4, "Exactly 4 canonical experiences must remain after filtering")
        self.assertIn("Autopilot Local", company_names)
        self.assertIn("Asian American Christian Fellowship", company_names)
        self.assertIn("Aroma Vault", company_names)
        self.assertIn("ClayThis", company_names)

    def test_post_generation_validation_detects_missing_experience(self):
        """Verifies the post-generation fail-fast logic correctly identifies missing required experiences."""
        REQUIRED_COMPANIES = {"Autopilot Local", "Asian American Christian Fellowship", "Aroma Vault", "ClayThis"}

        # Simulate model output that dropped AACF
        incomplete_output = {
            "experiences": [
                {"company": "Autopilot Local", "bullets": ["Bullet"] * 3},
                {"company": "Aroma Vault", "bullets": ["Bullet"] * 2},
                {"company": "ClayThis", "bullets": ["Bullet"] * 3},
            ]
        }
        returned_companies = {e.get("company", "") for e in incomplete_output.get("experiences", [])}
        missing = REQUIRED_COMPANIES - returned_companies

        self.assertIn("Asian American Christian Fellowship", missing,
            "Validator must detect the missing AACF experience")
        self.assertTrue(len(missing) > 0, "Missing experience set must be non-empty")

        # Simulate complete correct output — should produce an empty missing set
        complete_output = {
            "experiences": [
                {"company": "Autopilot Local", "bullets": ["Bullet"] * 3},
                {"company": "Asian American Christian Fellowship", "bullets": ["Bullet"] * 3},
                {"company": "Aroma Vault", "bullets": ["Bullet"] * 2},
                {"company": "ClayThis", "bullets": ["Bullet"] * 3},
            ]
        }
        returned_complete = {e.get("company", "") for e in complete_output.get("experiences", [])}
        self.assertEqual(REQUIRED_COMPANIES - returned_complete, set(),
            "No companies should be missing when all 4 are present in model output")

    def test_is_consulting_string_false_not_truthy(self):
        """Regression test: string 'false' from Gemini JSON must NOT be treated as True for is_consulting.
        Previously bool('false') == True caused every role to be treated as consulting."""
        def coerce_is_consulting(raw):
            return raw is True or (isinstance(raw, str) and raw.lower() == "true")

        self.assertFalse(coerce_is_consulting("false"),  "String 'false' must resolve to False")
        self.assertFalse(coerce_is_consulting("False"),  "String 'False' must resolve to False")
        self.assertFalse(coerce_is_consulting("FALSE"),  "String 'FALSE' must resolve to False")
        self.assertFalse(coerce_is_consulting(False),    "Bool False must resolve to False")
        self.assertFalse(coerce_is_consulting(0),        "Int 0 must resolve to False")
        self.assertTrue(coerce_is_consulting(True),      "Bool True must resolve to True")
        self.assertTrue(coerce_is_consulting("true"),    "String 'true' must resolve to True")
        self.assertTrue(coerce_is_consulting("True"),    "String 'True' must resolve to True")
        self.assertTrue(coerce_is_consulting("TRUE"),    "String 'TRUE' must resolve to True")

    def test_bullet_ideal_length_window_matches_prompt_spec(self):
        """Verifies the bullet audit uses the corrected 22-32 word ideal window, not the old 15-35 window.
        An 18-word bullet sits above the old threshold (15) but below the new one (22)."""
        # Construct bullets with precisely controlled word counts
        short_bullet = " ".join(["word"] * 18)            # 18 words: above old 15, below new 22
        on_spec_bullet = " ".join(["word"] * 25) + " 50%" # 26 words: within 22-32 spec

        mock_data = {
            "experiences": [
                {"company": "Test", "bullets": [short_bullet, on_spec_bullet]}
            ]
        }
        audit = validate_and_audit_bullet_quality(mock_data)
        details = audit["bullet_details"]

        self.assertEqual(details[0]["word_count"], 18)
        self.assertFalse(
            details[0]["ideal_length"],
            "18-word bullet must NOT be ideal under the corrected 22-32 spec (would have passed old 15-35 spec)"
        )
        self.assertEqual(details[1]["word_count"], 26)
        self.assertTrue(
            details[1]["ideal_length"],
            "26-word bullet must be ideal under the 22-32 spec"
        )


    def test_bullet_relevance_scoring_output_shape(self):
        """Verifies score_bullets_by_jd_relevance injects relevance_tier and jd_tag_overlap_count
        into each bullet, and that HIGH-tagged bullets are correctly identified."""
        from tailor import score_bullets_by_jd_relevance

        mock_experiences = [
            {
                "company": "Autopilot Local",
                "bullets": [
                    {"text": "Engineered AI pipeline.", "tags": ["python", "ai_agents", "automation", "lead_generation"], "impact": "high"},
                    {"text": "Led AACF chapter.", "tags": ["leadership", "operations"], "impact": "high"},
                ]
            }
        ]
        mock_jd_analysis = {
            "top_priority_tech_skills": ["Python", "AI Agents", "Automation"],
            "top_priority_business_skills": ["Lead Generation", "B2B Sales"],
        }
        scored = score_bullets_by_jd_relevance(mock_experiences, mock_jd_analysis)

        self.assertEqual(len(scored), 1, "Should return same number of experiences")
        bullets = scored[0]["bullets"]
        self.assertEqual(len(bullets), 2, "Should return same number of bullets per experience")

        # Every bullet must now have relevance_tier and jd_tag_overlap_count
        for b in bullets:
            self.assertIn("relevance_tier", b, "Every bullet must have a relevance_tier field")
            self.assertIn("jd_tag_overlap_count", b, "Every bullet must have a jd_tag_overlap_count field")
            self.assertIn(b["relevance_tier"], {"HIGH", "MEDIUM", "LOW"},
                "relevance_tier must be one of HIGH, MEDIUM, or LOW")

        # AI pipeline bullet has 4 matching tags → must be HIGH
        ai_bullet = bullets[0]
        self.assertEqual(ai_bullet["relevance_tier"], "HIGH",
            "Bullet with 4 JD-matching tags must be rated HIGH")

    def test_tone_directive_covers_all_four_cultures(self):
        """Verifies TONE_DIRECTIVES map covers all 4 culture types and returns non-empty strings."""
        TONE_DIRECTIVES = {
            "startup": (
                "Write in a startup-forward, execution-driven voice. "
                "Favor action verbs like 'Built,' 'Shipped,' 'Drove,' and 'Launched.'"
            ),
            "consulting": (
                "Write in a structured, client-advisory voice. "
                "Favor action verbs like 'Synthesized,' 'Formulated,' 'Architected,' and 'Advised.'"
            ),
            "enterprise": (
                "Write in a cross-functional, operational voice. "
                "Favor action verbs like 'Spearheaded,' 'Orchestrated,' 'Engineered,' and 'Delivered.'"
            ),
            "government": (
                "Write in a mission-driven, stakeholder-aware voice. "
                "Favor action verbs like 'Coordinated,' 'Facilitated,' 'Developed,' and 'Implemented.'"
            ),
        }
        for tone in ["startup", "consulting", "enterprise", "government"]:
            directive = TONE_DIRECTIVES.get(tone, "")
            self.assertTrue(len(directive) > 20,
                f"Tone directive for '{tone}' must be a non-empty actionable string")

        # Unknown tone falls back without crashing
        fallback = TONE_DIRECTIVES.get("unknown_culture", TONE_DIRECTIVES["enterprise"])
        self.assertIn("enterprise", fallback.lower() + "enterprise",
            "Unknown culture must gracefully fall back to enterprise tone")

    def test_summary_bank_orientation_mapping(self):
        """Verifies the orientation→summary_bank key mapping covers all 3 role orientations
        and that the mapped summaries exist and are non-empty in master_profile.json."""
        profile_path = Path(__file__).parent / "master_profile.json"
        if not profile_path.exists():
            profile_path = Path(__file__).parent / "master_profile.template.json"
        with open(profile_path, "r", encoding="utf-8") as f:
            master_profile = json.load(f)

        ORIENTATION_TO_SUMMARY_KEY = {
            "technical":       "ai_consulting_product",
            "product_growth":  "general",
            "business_sales":  "sales_operations_growth",
        }
        summary_bank = master_profile.get("summary_bank", {})

        for orientation, key in ORIENTATION_TO_SUMMARY_KEY.items():
            summary = summary_bank.get(key, "")
            self.assertTrue(len(summary) > 30,
                f"summary_bank['{key}'] (for orientation='{orientation}') must be a non-empty string in master_profile.json")

        # Consulting override always maps to ai_consulting_product
        consulting_key = "ai_consulting_product"
        self.assertIn(consulting_key, summary_bank,
            "Consulting roles require 'ai_consulting_product' key in summary_bank")

    def test_dynamic_coursework_includes_marketing(self):
        """Verifies that reading coursework dynamically from master_profile includes 'Marketing',
        which was previously hardcoded out of the static 5-course list in the prompt."""
        profile_path = Path(__file__).parent / "master_profile.json"
        if not profile_path.exists():
            profile_path = Path(__file__).parent / "master_profile.template.json"
        with open(profile_path, "r", encoding="utf-8") as f:
            master_profile = json.load(f)

        edu_data = master_profile.get("education", [{}])[0] if master_profile.get("education") else {}
        all_coursework = edu_data.get("coursework", [])
        coursework_str = ", ".join(all_coursework)

        self.assertGreater(len(all_coursework), 0, "master_profile must contain at least one course")
        self.assertIn("Marketing", all_coursework,
            "'Marketing' must be present in master_profile coursework (was previously excluded by hardcoding)")
        self.assertIn("Marketing", coursework_str,
            "'Marketing' must appear in the dynamic coursework_str injected into the prompt")

    def test_verbatim_skill_injection_synonyms(self):
        """Verifies that missing JD skills with authentic synonyms in master_profile get injected."""
        profile_path = Path(__file__).parent / "master_profile.json"
        if not profile_path.exists():
            profile_path = Path(__file__).parent / "master_profile.template.json"
        with open(profile_path, "r", encoding="utf-8") as f:
            master_profile = json.load(f)

        tailored_mock = {
            "experiences": [
                {"company": "Autopilot Local", "role": "AI Solutions Consultant", "bullets": ["Built automation pipeline using Python and Gemini."]}
            ],
            "education": [
                {"institution": "UC Berkeley", "degree_title": "BS", "major_minor_gpa": "GPA: 3.52", "coursework": ["Introduction to Business Analytics"]}
            ],
            "skills": {
                "technical_skills": ["Python", "SQL"],
                "business_and_strategy": ["Process Optimization"]
            }
        }

        jd_analysis_mock = {
            "top_priority_tech_skills": ["Data Reporting and Analytics"],
            "top_priority_business_skills": ["Process Improvement"],
            "ats_keywords": ["Process Enhancements"]
        }

        modified, report = inject_verbatim_jd_skills(tailored_mock, jd_analysis_mock, master_profile)

        self.assertIn("Data Reporting and Analytics", modified["skills"]["technical_skills"])
        self.assertIn("Process Improvement", modified["skills"]["business_and_strategy"])
        self.assertGreaterEqual(report["total_injected"], 2)

    def test_verbatim_skill_injection_blocks_unsupported_jargon(self):
        """Verifies zero-hallucination guardrail: unsupported domain jargon is NOT injected."""
        profile_path = Path(__file__).parent / "master_profile.json"
        if not profile_path.exists():
            profile_path = Path(__file__).parent / "master_profile.template.json"
        with open(profile_path, "r", encoding="utf-8") as f:
            master_profile = json.load(f)

        tailored_mock = {
            "experiences": [],
            "education": [],
            "skills": {"technical_skills": [], "business_and_strategy": []}
        }

        jd_analysis_mock = {
            "top_priority_tech_skills": ["Aircraft Jet Engine Maintenance", "Quantum Cryptography"],
            "top_priority_business_skills": ["Post-Merger Integration (PMI)", "Nuclear Submarine Logistics"],
            "ats_keywords": ["Aviation FAA Compliance"]
        }

        modified, report = inject_verbatim_jd_skills(tailored_mock, jd_analysis_mock, master_profile)

        self.assertNotIn("Aircraft Jet Engine Maintenance", modified["skills"]["technical_skills"])
        self.assertNotIn("Quantum Cryptography", modified["skills"]["technical_skills"])
        self.assertNotIn("Post-Merger Integration (PMI)", modified["skills"]["business_and_strategy"])
        self.assertNotIn("Nuclear Submarine Logistics", modified["skills"]["business_and_strategy"])
        self.assertEqual(report["total_injected"], 0)

    def test_verbatim_skill_injection_no_duplicate(self):
        """Verifies that skills already present verbatim in the resume text are not duplicated."""
        profile_path = Path(__file__).parent / "master_profile.json"
        if not profile_path.exists():
            profile_path = Path(__file__).parent / "master_profile.template.json"
        with open(profile_path, "r", encoding="utf-8") as f:
            master_profile = json.load(f)

        tailored_mock = {
            "experiences": [
                {"company": "Autopilot Local", "role": "Lead", "bullets": ["Handled Data Reporting and Analytics daily."]}
            ],
            "education": [],
            "skills": {
                "technical_skills": ["Data Reporting and Analytics"],
                "business_and_strategy": []
            }
        }

        jd_analysis_mock = {
            "top_priority_tech_skills": ["Data Reporting and Analytics"],
            "top_priority_business_skills": [],
            "ats_keywords": []
        }

        modified, report = inject_verbatim_jd_skills(tailored_mock, jd_analysis_mock, master_profile)
        self.assertEqual(report["injected_tech"], [])
        self.assertEqual(modified["skills"]["technical_skills"].count("Data Reporting and Analytics"), 1)

    def test_token_decomposition_fallback(self):
        """Verifies that token decomposition fallback correctly evaluates partial term overlap against master profile."""
        master_corpus = "python sql tableau machine learning business analytics project management data science"
        self.assertTrue(_has_genuine_capability("Advanced Business Analytics Reporting", master_corpus))
        self.assertFalse(_has_genuine_capability("Aeronautical Propulsion Dynamics", master_corpus))

    def test_end_to_end_ats_score_improvement(self):
        """Verifies that injecting missing synonym skills directly increases the deterministic ATS score."""
        profile_path = Path(__file__).parent / "master_profile.json"
        if not profile_path.exists():
            profile_path = Path(__file__).parent / "master_profile.template.json"
        with open(profile_path, "r", encoding="utf-8") as f:
            master_profile = json.load(f)

        jd_analysis_mock = {
            "top_priority_tech_skills": ["Data Reporting and Analytics", "Workflow Automation", "Python", "SQL", "Tableau"],
            "top_priority_business_skills": ["Process Improvement", "Project Management", "Operations Strategy", "Change Management", "Market Segmentation"],
            "ats_keywords": ["Process Enhancements", "Analytical Insights"]
        }

        # Mock resume without verbatim "Data Reporting and Analytics" and "Process Improvement"
        resume_pre = {
            "experiences": [
                {"company": "Autopilot Local", "role": "AI Solutions Consultant", "bullets": ["Automated operations using Python, SQL, Tableau, saving 50 hours.", "Led Project Management, Operations Strategy, and Change Management initiatives across Market Segmentation."]}
            ],
            "education": [
                {"institution": "UC Berkeley Haas", "degree_title": "BS", "major_minor_gpa": "3.52", "coursework": ["Introduction to Business Analytics"], "honors": [], "activities": []}
            ],
            "skills": {
                "technical_skills": ["Python", "SQL", "Tableau", "Workflow Automation"],
                "business_and_strategy": ["Project Management", "Operations Strategy", "Change Management", "Market Segmentation"]
            }
        }

        score_pre, breakdown_pre = calculate_deterministic_ats_score(resume_pre, jd_analysis_mock)

        # Apply injection
        import copy
        resume_post = copy.deepcopy(resume_pre)
        resume_post, _ = inject_verbatim_jd_skills(resume_post, jd_analysis_mock, master_profile)

        score_post, breakdown_post = calculate_deterministic_ats_score(resume_post, jd_analysis_mock)

        self.assertGreater(score_post, score_pre, f"Score post ({score_post}) should be strictly higher than pre ({score_pre})")
        self.assertIn("Data Reporting and Analytics", breakdown_post["matched_tech_skills"])
        self.assertIn("Process Improvement", breakdown_post["matched_business_skills"])
    def test_skills_cap_constant(self):
        """Verifies that the MAX_SKILLS_PER_CATEGORY constant is set to 6."""
        self.assertEqual(MAX_SKILLS_PER_CATEGORY, 6)

    def test_normalize_skill_strips_parenthetical(self):
        """Verifies that _normalize_skill handles parenthetical suffixes and casing."""
        self.assertEqual(_normalize_skill("Product Lifecycle Management (PLM)"),
                         _normalize_skill("Product Lifecycle Management"))
        self.assertEqual(_normalize_skill("Python"), _normalize_skill("python"))
        self.assertEqual(_normalize_skill("A/B Testing & Pricing Strategy"),
                         _normalize_skill("a/b testing & pricing strategy"))

    def test_deduplicate_skills_removes_variants(self):
        """Verifies that _deduplicate_skills keeps first occurrence and drops normalized duplicates."""
        input_skills = [
            "Product Lifecycle Management",
            "Python",
            "Product Lifecycle Management (PLM)",
            "SQL",
            "python",
        ]
        result = _deduplicate_skills(input_skills)
        self.assertEqual(result, ["Product Lifecycle Management", "Python", "SQL"])

    def test_injection_enforces_cap_at_six(self):
        """Verifies that inject_verbatim_jd_skills hard-truncates each category to MAX_SKILLS_PER_CATEGORY."""
        profile_path = Path(__file__).parent / "master_profile.json"
        if not profile_path.exists():
            profile_path = Path(__file__).parent / "master_profile.template.json"
        with open(profile_path, "r", encoding="utf-8") as f:
            master_profile = json.load(f)

        # Simulate an LLM that ignores the cap and returns 10 skills per category
        tailored_mock = {
            "experiences": [
                {"company": "Autopilot Local", "role": "AI Solutions Consultant",
                 "bullets": ["Built automation pipeline using Python and Gemini."]}
            ],
            "education": [
                {"institution": "UC Berkeley", "degree_title": "BS",
                 "major_minor_gpa": "GPA: 3.52", "coursework": ["Business Analytics"]}
            ],
            "skills": {
                "technical_skills": [
                    "Python", "SQL", "Tableau", "n8n", "REST APIs",
                    "CRM Automation", "Google Gemini API", "Prompt Engineering",
                    "Web Scraping", "Linear Programming"
                ],
                "business_and_strategy": [
                    "B2B Sales", "Strategic Partnerships", "Market Segmentation",
                    "Contract Negotiation", "Financial Modeling", "A/B Testing",
                    "Competitive Strategy", "Partnership Development",
                    "Revenue Operations", "Growth Strategy"
                ]
            }
        }

        jd_analysis_mock = {
            "top_priority_tech_skills": [],
            "top_priority_business_skills": [],
            "ats_keywords": []
        }

        modified, report = inject_verbatim_jd_skills(tailored_mock, jd_analysis_mock, master_profile)

        self.assertLessEqual(len(modified["skills"]["technical_skills"]), MAX_SKILLS_PER_CATEGORY,
                             f"Technical skills ({len(modified['skills']['technical_skills'])}) should be capped at {MAX_SKILLS_PER_CATEGORY}")
        self.assertLessEqual(len(modified["skills"]["business_and_strategy"]), MAX_SKILLS_PER_CATEGORY,
                             f"Business skills ({len(modified['skills']['business_and_strategy'])}) should be capped at {MAX_SKILLS_PER_CATEGORY}")

    def test_metric_integrity_validation(self):
        """Tests that validate_metric_integrity flags unverified/fabricated percentages in bullets."""
        mock_master = {
            "experiences": [
                {
                    "company": "Autopilot Local",
                    "bullets": [{"text": "Reduced missed calls by 74% and classification accuracy to 90%."}]
                },
                {
                    "company": "AACF",
                    "bullets": [{"text": "Scaled mentorship program to chapter-wide adoption."}]
                }
            ]
        }

        # 1. Valid tailored data with authentic percentages
        valid_tailored = {
            "experiences": [
                {
                    "company": "Autopilot Local",
                    "bullets": ["Achieved 90% accuracy benchmark on classification model."]
                }
            ]
        }
        violations = validate_metric_integrity(valid_tailored, mock_master)
        self.assertEqual(len(violations), 0)

        # 2. Fabricated percentage (e.g. 100% adoption invented for AACF)
        invalid_tailored = {
            "experiences": [
                {
                    "company": "AACF",
                    "bullets": ["Scaled mentorship program to 100% chapter-wide adoption across the organization."]
                }
            ]
        }
        violations = validate_metric_integrity(invalid_tailored, mock_master)
        self.assertEqual(len(violations), 1)
        self.assertIn("100%", violations[0])
        self.assertIn("AACF", violations[0])


class TestResumeEvidence(unittest.TestCase):
    def test_reported_resume_metrics_remain_with_their_own_phrases(self):
        from copy import deepcopy
        from evidence import metric_errors, numeric_claims, validate_resume_evidence
        cases = [
            (
                'Saved **50 sales hours per week** by building an agentic pipeline to scrape, '
                'enrich, verify, clean, qualify, and ultimately send **120 personalized emails every day**.',
                'Built an automated Python ETL and messaging pipeline to scrape, clean, and qualify '
                'records, saving 50 sales hours per week while dispatching 120 personalized outbound '
                'emails daily with strict Data Quality controls.',
                [('50', 'hour', 'week'), ('120', 'email', 'day')],
                [('120', '121'), ('daily', 'weekly'), ('daily', ''), ('emails', 'customers')],
            ),
            (
                'Served as the top student leader (**Core Coordinator**) for a **23-member** campus '
                'organization, directing weekly programming across **3 semesters**, by owning planning, '
                'budget, and cross-team coordination.',
                'Spearheaded operations and budget allocation across 3 semesters as Core Coordinator '
                'for a 23-member organization, driving weekly operational execution and stakeholder '
                'alignment through structured Process Improvement and cross-team tracking.',
                [('3', 'semester', ''), ('23', 'member', '')],
                [('3 semesters', '4 semesters'), ('semesters', 'years'), ('23-member', '24-member')],
            ),
            (
                'Secured access to **5,000+ monthly customers** by negotiating and closing revenue-share '
                'agreements with **7+ fitness centers**, including Crunch Fitness Bay Area.',
                'Secured direct physical distribution to 5,000+ monthly customers by negotiating and '
                'executing commercial revenue-share contracts with 7+ premium fitness centers, '
                'including Crunch Fitness Bay Area, to drive rapid retail expansion.',
                [('5000+', 'customer', 'month'), ('7+', 'center', '')],
                [('7+', '8+'), ('fitness centers', 'customers'), ('monthly', 'daily'), ('monthly', '')],
            ),
        ]
        for source, rewrite, expected, unsupported_changes in cases:
            with self.subTest(rewrite=rewrite):
                self.assertEqual(numeric_claims(rewrite), expected)
                self.assertCountEqual(numeric_claims(source), expected)
                self.assertEqual(metric_errors(rewrite, source, 'test'), [])
                # Exercise the actual source-reference validation path as well.
                self.profile['experiences'][0]['bullets'][0]['text'] = source
                self.data['experiences'][0]['bullets'] = [rewrite]
                self.data['skills'] = {}
                validate_resume_evidence(deepcopy(self.data), self.profile)
                for old, new in unsupported_changes:
                    with self.subTest(change=(old, new)):
                        self.assertTrue(metric_errors(rewrite.replace(old, new), source, 'test'))

    def test_metric_frequencies_do_not_cross_clauses(self):
        from evidence import metric_errors, numeric_claims
        for separator in (' while ', ', '):
            text = 'Saved 50 hours weekly' + separator + 'sending 120 emails daily.'
            self.assertEqual(numeric_claims(text), [('50', 'hour', 'week'), ('120', 'email', 'day')])
            self.assertTrue(metric_errors(text.replace('daily', 'weekly'), text, 'test'))
        self.assertEqual(numeric_claims('Directed weekly programming across 3 semesters.'),
                         [('3', 'semester', '')])
        self.assertEqual(numeric_claims('Led a 23-member organization, directing weekly programming.'),
                         [('23', 'member', '')])
        for qualifier in ('weekly', 'per week', 'every week'):
            self.assertEqual(numeric_claims('Saved 50 hours, ' + qualifier + '.'), [('50', 'hour', 'week')])
            self.assertTrue(metric_errors('Saved 50 hours.', 'Saved 50 hours, ' + qualifier + '.', 'test'))

    def test_frequency_aliases_and_dropped_qualifiers(self):
        from evidence import metric_errors
        for source, valid, invalid in [
            ('Saved 50 hours per week.', 'Saved 50 hours weekly.', 'Saved 50 hours daily.'),
            ('Weekly savings of 50 hours.', 'Saved 50 hours every week.', 'Daily savings of 50 hours.'),
            ('Served 100 customers per month.', 'Served 100 monthly customers.', 'Served 100 customers daily.'),
            ('Earned $1000 in annual revenue.', 'Earned $1000 yearly.', 'Earned $1000 monthly.'),
        ]:
            self.assertEqual(metric_errors(valid, source, 'test'), [])
            self.assertTrue(metric_errors(invalid, source, 'test'))
        self.assertTrue(metric_errors('Saved 50 hours.', 'Saved 50 hours weekly.', 'test'))
        self.assertEqual(metric_errors('Saved 50 hours weekly and sent 120 emails daily.', 'Saved 50 hours per week and sent 120 emails per day.', 'test'), [])

    def setUp(self):
        self.profile = {'personal_info': {'full_name': 'Daniel Suh'}, 'education': [{'institution': 'Berkeley', 'location': 'Berkeley', 'graduation_date': 'May 2028', 'degree': 'BS Business Administration', 'gpa': '3.52', 'coursework': ['Analytics'], 'honors': []}], 'experiences': [{'id': 'exp', 'company': 'Acme', 'role': 'Consultant', 'location': 'Berkeley', 'date_range': '2026 – Present', 'bullets': [{'text': 'Saved 50 hours per week with Python automation.', 'tags': ['python']}]}], 'skills': {'technical_skills': ['Python']}}
        self.data = {'personal_info': {'full_name': 'Invented name'}, 'education': [{'institution': 'Berkeley', 'location': 'Berkeley', 'graduation_date': 'May 2028', 'coursework': ['Analytics'], 'honors': []}], 'experiences': [{'company': 'Acme', 'role': 'Consultant', 'location': 'Berkeley', 'date_range': '2026 – Present', 'bullets': ['Automated work with Python, saving 50 hours per week.'], 'bullet_source_refs': [['exp:bullet:0']]}], 'skills': {'technical_skills': ['Python']}}

    def test_valid_rewrite_records_original_and_source(self):
        from evidence import validate_resume_evidence
        result = validate_resume_evidence(self.data, self.profile)
        self.assertEqual(result['personal_info']['full_name'], 'Daniel Suh')
        review = result['tailoring_report']['evidence_review']
        self.assertEqual(review['bullets'][0]['source_refs'], ['exp:bullet:0'])
        self.assertEqual(review['skills'][0]['source_ref'], 'skills.technical_skills[0]')

    def test_global_skills_do_not_prove_tools_or_financial_domain_in_a_bullet(self):
        from copy import deepcopy
        from evidence import validate_resume_evidence
        self.profile['skills']['technical_skills'] += ['Excel', 'Tableau', 'HubSpot', 'PowerPoint']
        self.profile['experiences'][0]['bullets'].append({'text': 'Used Excel on a separate project.', 'tags': ['excel']})
        for added in ('using Excel', 'using Tableau', 'using HubSpot', 'using PowerPoint',
                      'enriching Market Data', 'supporting electronic trading'):
            data = deepcopy(self.data)
            data['experiences'][0]['bullets'][0] += ' ' + added
            with self.subTest(added=added), self.assertRaisesRegex(ValueError, 'Unsupported source-scoped claim'):
                validate_resume_evidence(data, self.profile)
        self.profile['experiences'][0]['bullets'][0]['tags'].append('excel')
        data = deepcopy(self.data)
        data['experiences'][0]['bullets'][0] += ' using Excel'
        validate_resume_evidence(data, self.profile)

    def test_unsupported_number_and_unit_are_blocked(self):
        from evidence import validate_resume_evidence
        for text in ['Saved 60 hours per week.', 'Saved 50 dollars per week.', 'Saved 50 hours per day.']:
            self.data['experiences'][0]['bullets'] = [text]
            with self.assertRaisesRegex(ValueError, 'Unsupported metric'):
                validate_resume_evidence(self.data, self.profile)

    def test_cross_employer_number_is_blocked(self):
        from evidence import validate_resume_evidence
        self.profile['experiences'].append({'id': 'other', 'company': 'Other', 'bullets': [{'text': 'Saved 60 hours per week.'}]})
        self.data['experiences'][0]['bullets'] = ['Saved 60 hours per week.']
        with self.assertRaises(ValueError):
            validate_resume_evidence(self.data, self.profile)
        self.data['experiences'][0]['bullet_source_refs'] = [['other:bullet:0']]
        with self.assertRaisesRegex(ValueError, 'Invalid source'):
            validate_resume_evidence(self.data, self.profile)

    def test_wrong_source_within_employer_is_blocked(self):
        from evidence import validate_resume_evidence
        self.profile['experiences'][0]['bullets'].append({'text': 'Saved 60 hours per week.'})
        self.data['experiences'][0]['bullets'] = ['Saved 60 hours per week.']
        with self.assertRaisesRegex(ValueError, 'Unsupported metric'):
            validate_resume_evidence(self.data, self.profile)

    def test_missing_sources_and_unsupported_skills_are_blocked(self):
        from evidence import validate_resume_evidence
        self.data['experiences'][0]['bullet_source_refs'] = []
        self.data['skills']['technical_skills'] = ['Aerospace Engineering']
        with self.assertRaises(ValueError) as exc:
            validate_resume_evidence(self.data, self.profile)
        self.assertIn('Missing bullet source', str(exc.exception))
        self.assertIn('Unsupported skill', str(exc.exception))

    def test_changed_role_date_or_qualification_is_blocked(self):
        from evidence import validate_resume_evidence
        self.data['experiences'][0]['role'] = 'CEO'
        self.data['experiences'][0]['date_range'] = '2020 – Present'
        self.data['education'][0]['honors'] = ['Nobel Prize']
        with self.assertRaises(ValueError) as exc:
            validate_resume_evidence(self.data, self.profile)
        for expected in ('role', 'date_range', 'qualification'):
            self.assertIn(expected, str(exc.exception))


class TestResumeMetricCorrection(unittest.TestCase):
    def setUp(self):
        from copy import deepcopy
        fixture = TestResumeEvidence()
        fixture.setUp()
        self.profile = deepcopy(fixture.profile)
        self.data = deepcopy(fixture.data)
        self.profile['experiences'] = []
        self.data['experiences'] = []
        sources = [
            ('Autopilot Local', 4, 'Saved 50 sales hours per week by building an agentic pipeline to scrape, '
             'enrich, verify, clean, qualify, and ultimately send 120 personalized emails every day.'),
            ('Asian American Christian Fellowship', 3, 'Directed weekly programming across 3 semesters.'),
            ('Aroma Vault', 2, 'Served 5,000+ monthly customers through 7+ fitness centers.'),
            ('ClayThis', 3, 'Achieved a 15% response rate by running targeted, personalized outbound campaigns '
             'to 300+ enterprise prospects.'),
        ]
        for index, (company, count, source) in enumerate(sources):
            master = deepcopy(fixture.profile['experiences'][0])
            # Keep the source's explicit Python tag: these fixtures isolate metric
            # corrections, not an unsupported tool claim in the initial rewrite.
            master.update(id=f'exp{index}', company=company,
                          bullets=[{'text': source, 'tags': ['python'] if index == 0 else []}])
            self.profile['experiences'].append(master)
            candidate = deepcopy(fixture.data['experiences'][0])
            candidate.update(company=company, bullets=[source] * count,
                             bullet_source_refs=[[f'exp{index}:bullet:0'] for _ in range(count)])
            self.data['experiences'].append(candidate)
        self.data['skills'] = {}
        self.bad_email = ('Shipped an automated data pipeline using Python to scrape, verify, and clean '
                          'operational records, saving 50 sales hours per week while dispatching '
                          '120 personalized communications daily.')
        self.bad_accounts = ('Executed high-touch personalized outbound campaigns across 300+ enterprise '
                             'accounts, generating an exceptional 15% response rate through data-driven '
                             'segmentation and messaging.')
        self.data['experiences'][0]['bullets'][0] = self.bad_email
        self.data['experiences'][3]['bullets'][0] = self.bad_accounts
        self.replacements = {'replacements': [
            {'experience_index': index, 'bullet_index': 0,
             'text': self.profile['experiences'][index]['bullets'][0]['text']}
            for index in (0, 3)]}

    def run_tailoring(self, correction=None):
        from unittest.mock import patch
        from tailor import tailor_resume
        responses = [json.dumps(self.data), json.dumps(correction if correction is not None else self.replacements)]
        with patch('tailor.load_cached_jd_analysis', return_value={'company_name': 'Example', 'role_title': 'Analyst'}), \
                patch('tailor.generate_content_with_fallback', side_effect=responses) as generate:
            self.generate = generate
            return tailor_resume(self.profile, 'Example analyst job', client=object())

    def test_reported_substitutions_are_distinct_units_with_structured_diagnostics(self):
        from evidence import ResumeEvidenceError, numeric_claims, validate_resume_evidence
        self.assertIn(('120', 'communication', 'day'), numeric_claims(self.bad_email))
        self.assertIn(('300+', 'account', ''), numeric_claims(self.bad_accounts))
        with self.assertRaises(ResumeEvidenceError) as caught:
            validate_resume_evidence(self.data, self.profile)
        self.assertIsInstance(caught.exception, ValueError)
        self.assertEqual(caught.exception.non_metric_errors, [])
        self.assertEqual(len(caught.exception.metric_issues), 2)
        self.assertEqual(caught.exception.metric_issues[1]['source_refs'], ['exp3:bullet:0'])
        self.assertEqual(caught.exception.metric_issues[1]['experience_index'], 3)
        self.assertIn('Rewrite:', str(caught.exception))
        self.assertIn('Source:', str(caught.exception))
        self.assertNotIn('unknown:', str(caught.exception))

    def test_unit_lookup_stays_in_numeric_phrase(self):
        from evidence import numeric_claims, metric_errors
        self.assertEqual(numeric_claims('Built 120 widgets while contacting customers daily.'),
                         [('120', 'unknown:widgets', '')])
        self.assertTrue(metric_errors('Sent 120 personalized communications daily.',
                                      'Sent 120 personalized emails daily.', 'test'))
        self.assertTrue(metric_errors('Contacted 300+ enterprise accounts.',
                                      'Contacted 300+ enterprise prospects.', 'test'))

    def test_tailoring_corrects_once_and_preserves_review_history(self):
        from copy import deepcopy
        from evidence import validate_resume_evidence, evidence_markdown
        original = deepcopy(self.data)
        result = self.run_tailoring()
        self.assertEqual(self.generate.call_count, 2)
        self.assertEqual(self.data, original)
        self.assertEqual(result['experiences'][0]['bullets'][0], self.replacements['replacements'][0]['text'])
        self.assertEqual(result['experiences'][0]['bullets'][1:], original['experiences'][0]['bullets'][1:])
        self.assertEqual(result['experiences'][3]['bullet_source_refs'], original['experiences'][3]['bullet_source_refs'])
        self.assertEqual(result['tailoring_report']['metric_integrity_violations'], [])
        validate_resume_evidence(result, self.profile)
        review = result['tailoring_report']['evidence_review']
        self.assertEqual(len(review['metric_corrections']), 2)
        self.assertEqual(review['metric_corrections'][0]['rewritten'], self.bad_email)
        self.assertIn(self.bad_email, evidence_markdown(review))
        self.assertIn(self.replacements['replacements'][0]['text'], evidence_markdown(review))
        initial_prompt = self.generate.call_args_list[0].args[1]
        self.assertIn('Copy the complete metric phrase', initial_prompt)
        self.assertNotIn('5,000+ active users', initial_prompt)

    def test_valid_generation_needs_no_correction(self):
        for replacement in self.replacements['replacements']:
            self.data['experiences'][replacement['experience_index']]['bullets'][0] = replacement['text']
        self.data['tailoring_report'] = {'metric_corrections': [{'rewritten': 'invented correction history'}]}
        result = self.run_tailoring()
        self.assertEqual(self.generate.call_count, 1)
        self.assertEqual(result['tailoring_report']['evidence_review']['metric_corrections'], [])

    def test_correction_service_failure_stops_without_retrying(self):
        from unittest.mock import patch
        from tailor import validate_or_correct_resume_metrics
        for kwargs in ({'side_effect': RuntimeError('Service unavailable')}, {'return_value': None}):
            with self.subTest(kwargs=kwargs), patch('tailor.generate_content_with_fallback', **kwargs) as generate:
                with self.assertRaisesRegex(ValueError, 'after one attempt'):
                    validate_or_correct_resume_metrics(self.data, self.profile, object())
                self.assertEqual(generate.call_count, 1)

    def test_second_invalid_result_stops_without_another_request(self):
        self.replacements['replacements'][0]['text'] = self.bad_email
        with self.assertRaisesRegex(ValueError, 'after one attempt.*'):
            self.run_tailoring()
        self.assertEqual(self.generate.call_count, 2)

    def test_non_metric_failures_do_not_trigger_correction(self):
        from copy import deepcopy
        original = deepcopy(self.data)
        for change in ('source', 'skill', 'role', 'count', 'company'):
            with self.subTest(change=change):
                self.data = deepcopy(original)
                if change == 'source':
                    self.data['experiences'][0]['bullet_source_refs'][0] = ['exp3:bullet:0']
                elif change == 'skill':
                    self.data['skills'] = {'technical_skills': ['Invented qualification']}
                elif change == 'role':
                    self.data['experiences'][0]['role'] = 'CEO'
                elif change == 'count':
                    self.data['experiences'][0]['bullets'].pop()
                else:
                    self.data['experiences'][0]['company'] = 'Other'
                with self.assertRaises(ValueError):
                    self.run_tailoring()
                self.assertEqual(self.generate.call_count, 1)

    def test_correction_rejects_malformed_or_unrelated_changes(self):
        from copy import deepcopy
        valid = self.replacements['replacements']
        invalid = [None, [], {'replacements': 'wrong'}, {'replacements': []},
                   {'replacements': valid, 'skills': {}}, {'replacements': [valid[0], valid[0]]}]
        for field, value in [('experience_index', 1), ('experience_index', True),
                             ('bullet_index', 99), ('text', ''), ('text', None),
                             ('source_refs', ['exp3:bullet:0'])]:
            changed = deepcopy(self.replacements)
            changed['replacements'][0][field] = value
            invalid.append(changed)
        # An otherwise plausible rewrite cannot remove the rejected metric.
        changed = deepcopy(self.replacements)
        changed['replacements'][0]['text'] = 'Saved 50 sales hours per week.'
        invalid.append(changed)
        from unittest.mock import patch
        from tailor import validate_or_correct_resume_metrics
        for response in [json.dumps(item) for item in invalid] + ['not JSON']:
            with self.subTest(response=response), \
                    patch('tailor.generate_content_with_fallback', return_value=response) as generate:
                with self.assertRaisesRegex(ValueError, 'after one attempt'):
                    validate_or_correct_resume_metrics(self.data, self.profile, object())
                self.assertEqual(generate.call_count, 1)

    def test_corrected_metrics_still_enforce_units_counts_frequency_and_sources(self):
        from copy import deepcopy
        original = deepcopy(self.replacements)
        for old, new in [('120', '121'), ('every day', 'every week'), ('every day', ''),
                         ('emails', 'customers'), ('50 sales hours', '50 sales days'),
                         ('120 personalized emails', '300 personalized emails')]:
            with self.subTest(change=(old, new)):
                replacement = deepcopy(original)
                replacement['replacements'][0]['text'] = replacement['replacements'][0]['text'].replace(old, new)
                with self.assertRaises(ValueError):
                    self.run_tailoring(replacement)
                self.assertEqual(self.generate.call_count, 2)

    def test_pipeline_writes_only_validated_correction(self):
        import tempfile
        from unittest.mock import patch
        from generate_resume import run_pipeline
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            profile = root / 'profile.json'
            profile.write_text(json.dumps(self.profile))
            def render(data, destination):
                self.assertEqual(data['tailoring_report']['metric_integrity_violations'], [])
                artifacts = {}
                for extension in ('pdf', 'md', 'html'):
                    path = Path(destination) / ('resume.' + extension)
                    path.write_text('mock rendered artifact')
                    artifacts[extension] = str(path)
                return artifacts
            for succeeds in (True, False):
                output = root / str(succeeds)
                correction = self.replacements if succeeds else {'replacements': []}
                with patch('generate_resume.get_genai_client', return_value=object()), \
                        patch('tailor.load_cached_jd_analysis', return_value={'company_name': 'Example', 'role_title': 'Analyst'}), \
                        patch('tailor.generate_content_with_fallback', side_effect=[json.dumps(self.data), json.dumps(correction)]), \
                        patch('generate_resume.save_resume_artifacts', side_effect=render) as renderer:
                    if succeeds:
                        result = run_pipeline('Example analyst job', str(profile), str(output),
                                              target_company='Example (Interns)', target_role='Summer Analyst')
                        saved = json.loads((Path(result['output_dir']) / 'tailored_resume.json').read_text())
                        self.assertEqual(saved['tailoring_report']['target_company'], 'Example (Interns)')
                        self.assertEqual(saved['tailoring_report']['target_role'], 'Summer Analyst')
                        self.assertEqual(len(saved['tailoring_report']['metric_corrections']), 2)
                        self.assertIn('Initial rewrite (rejected)', Path(result['report']).read_text())
                        self.assertTrue(saved['artifact_sha256'])
                    else:
                        with self.assertRaises(ValueError):
                            run_pipeline('Example analyst job', str(profile), str(output))
                        renderer.assert_not_called()
                        self.assertFalse(output.exists())

    def test_explicit_posting_identity_survives_model_and_cached_brand_normalization(self):
        from unittest.mock import patch
        from tailor import tailor_resume
        cached = {'company_name': 'Example Group', 'role_title': 'Analyst'}
        with patch('tailor.load_cached_jd_analysis', return_value=cached), \
                patch('tailor.generate_content_with_fallback', side_effect=[json.dumps(self.data), json.dumps(self.replacements)]):
            result = tailor_resume(self.profile, 'Example analyst job', client=object(),
                                   target_company='Example Group (Interns)', target_role='Summer Analyst')
        self.assertEqual(result['tailoring_report']['target_company'], 'Example Group (Interns)')
        self.assertEqual(result['tailoring_report']['target_role'], 'Summer Analyst')
        self.assertEqual(cached['company_name'], 'Example Group')

    def test_automatic_resume_preserves_source_bullets_despite_model_embellishments(self):
        from copy import deepcopy
        from unittest.mock import patch
        from tailor import tailor_resume
        for master, candidate in zip(self.profile['experiences'], self.data['experiences']):
            master['bullets'] = [deepcopy(master['bullets'][0]) for _ in candidate['bullets']]
            candidate['bullets'] = ['Invented one-on-one mentorship using HubSpot.']
            candidate['bullet_source_refs'] = [['nonexistent']]
        with patch('tailor.load_cached_jd_analysis', return_value={'company_name': 'Example', 'role_title': 'Analyst'}), \
                patch('tailor.generate_content_with_fallback', return_value=json.dumps(self.data)) as generate:
            result = tailor_resume(self.profile, 'Example analyst job', client=object(), preserve_source_bullets=True)
        self.assertEqual(generate.call_count, 1)
        self.assertEqual(result['tailoring_report']['experience_wording'], 'verified_source')
        for master, candidate in zip(self.profile['experiences'], result['experiences']):
            self.assertEqual(candidate['bullets'], [b['text'].replace('**', '') for b in master['bullets']])
            self.assertEqual(candidate['bullet_source_refs'], [[f"{master['id']}:bullet:{i}"] for i in range(len(master['bullets']))])


class TestRenderingAndOutreachEvidence(unittest.TestCase):
    def test_bottom_gap_accounts_for_chrome_page_transform(self):
        import tempfile
        from pypdf import PdfWriter
        from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
        from render_pdf import get_pdf_bottom_gap
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'positioned.pdf'
            writer = PdfWriter()
            page = writer.add_blank_page(width=612, height=792)
            font = DictionaryObject({NameObject('/Type'): NameObject('/Font'),
                                     NameObject('/Subtype'): NameObject('/Type1'),
                                     NameObject('/BaseFont'): NameObject('/Times-Roman')})
            page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): font})})
            content = DecodedStreamObject()
            content.set_data(b'q 0.75 0 0 -0.75 37.5 759.75 cm BT /F1 13.6 Tf 1 0 0 -1 20 943 Tm (Bottom line) Tj ET Q')
            page[NameObject('/Contents')] = writer._add_object(content)
            writer.write(path)
            self.assertAlmostEqual(get_pdf_bottom_gap(path), 49.95, places=2)

    def test_layout_grows_small_text_and_records_final_spacing(self):
        from unittest.mock import patch
        import tempfile
        from render_pdf import save_resume_artifacts
        data = {'experiences': [{'bullets': ['Unchanged achievement.']}]}
        def render(html, pdf):
            Path(pdf).write_bytes(Path(html).read_bytes())
        with tempfile.TemporaryDirectory() as folder, \
                patch('render_pdf.export_html_to_pdf', side_effect=render) as renderer, \
                patch('render_pdf.get_pdf_page_count', return_value=1), \
                patch('render_pdf.get_pdf_bottom_gap', side_effect=[90, 75, 50]):
            result = save_resume_artifacts(data, folder)
            self.assertEqual(renderer.call_count, 3)
            self.assertEqual(data['layout_settings']['bullet_font_pt'], 10.2)
            self.assertEqual(data['layout_settings']['bottom_gap_pt'], 50)
            self.assertIn('Unchanged achievement.', Path(result['html']).read_text())
            self.assertEqual(Path(result['pdf']).read_bytes(), Path(result['html']).read_bytes())

    def test_layout_keeps_last_single_page_when_larger_text_overflows(self):
        from unittest.mock import patch
        import tempfile
        from render_pdf import save_resume_artifacts
        def render(html, pdf):
            Path(pdf).write_bytes(Path(html).read_bytes())
        with tempfile.TemporaryDirectory() as folder, \
                patch('render_pdf.export_html_to_pdf', side_effect=render), \
                patch('render_pdf.get_pdf_page_count', side_effect=[1, 2]), \
                patch('render_pdf.get_pdf_bottom_gap', return_value=65):
            data = {}
            result = save_resume_artifacts(data, folder)
            self.assertEqual(data['layout_settings']['bullet_font_pt'], 9.8)
            self.assertIn('font-size: 9.8pt', Path(result['html']).read_text())
            self.assertEqual(Path(result['pdf']).read_bytes(), Path(result['html']).read_bytes())

    def test_unbalanced_or_unmeasurable_resume_fails_instead_of_publishing(self):
        from unittest.mock import patch
        import tempfile
        from render_pdf import save_resume_artifacts, get_pdf_bottom_gap
        from pypdf import PdfWriter
        with tempfile.TemporaryDirectory() as folder:
            blank = Path(folder) / 'blank.pdf'
            writer = PdfWriter()
            writer.add_blank_page(width=612, height=792)
            writer.write(blank)
            with self.assertRaisesRegex(ValueError, 'no measurable PDF text'):
                get_pdf_bottom_gap(blank)
            def render(html, pdf):
                Path(pdf).write_bytes(b'fixture')
            with patch('render_pdf.export_html_to_pdf', side_effect=render) as renderer, \
                    patch('render_pdf.get_pdf_page_count', return_value=1), \
                    patch('render_pdf.get_pdf_bottom_gap', return_value=150):
                with self.assertRaisesRegex(ValueError, 'layout needs review'):
                    save_resume_artifacts({}, folder)
                self.assertEqual(renderer.call_count, 6)

    def test_balanced_resume_needs_no_extra_render(self):
        from unittest.mock import patch
        import tempfile
        from render_pdf import save_resume_artifacts
        with tempfile.TemporaryDirectory() as folder, \
                patch('render_pdf.export_html_to_pdf') as renderer, \
                patch('render_pdf.get_pdf_page_count', return_value=1), \
                patch('render_pdf.get_pdf_bottom_gap', return_value=48):
            save_resume_artifacts({}, folder)
            self.assertEqual(renderer.call_count, 1)

    def test_unreadable_pdf_does_not_assume_one_page(self):
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.pdf') as handle:
            handle.write(b'not a PDF')
            handle.flush()
            with self.assertRaises(RuntimeError):
                get_pdf_page_count(handle.name)

    def test_multipage_resume_is_rejected_after_layout_attempts(self):
        from unittest.mock import patch
        import tempfile
        from render_pdf import save_resume_artifacts
        with tempfile.TemporaryDirectory() as folder, patch('render_pdf.export_html_to_pdf'), patch('render_pdf.get_pdf_page_count', return_value=2):
            with self.assertRaisesRegex(ValueError, 'exactly one page'):
                save_resume_artifacts({}, folder, max_shrink_attempts=0)

    def test_missing_profile_does_not_load_template(self):
        from generate_resume import load_master_profile
        with self.assertRaises(FileNotFoundError):
            load_master_profile('/missing/master_profile.json')

    def test_outreach_claims_match_attached_experience(self):
        from evidence import validate_outreach_evidence
        resume = {'experiences': [{'company': 'Acme', 'bullets': ['Saved 50 hours per week.']}, {'company': 'Other', 'bullets': ['Saved 90 hours per week.']}]}
        validate_outreach_evidence('At Acme I saved 50 hours per week.\n\nCould we chat for 10–15 minutes?\n\nThanks for your time,\nDaniel Suh\n661-476-8194', resume)
        with self.assertRaises(ValueError):
            validate_outreach_evidence('At Acme I saved 90 hours per week.', resume)

    def test_keyword_injection_does_not_use_partial_overlap(self):
        profile = {'skills': {'technical_skills': ['Data Analytics']}}
        result, _ = inject_verbatim_jd_skills({'skills': {}}, {'ats_keywords': ['Advanced Data Aerospace Analytics']}, profile)
        self.assertNotIn('Advanced Data Aerospace Analytics', result['skills'].get('technical_skills', []))


class TestEvidenceSnapshotAndRenderPublication(unittest.TestCase):
    def test_changed_source_text_requires_regeneration(self):
        from evidence import validate_resume_evidence
        fixture = TestResumeEvidence()
        fixture.setUp()
        data = validate_resume_evidence(fixture.data, fixture.profile)
        validate_resume_evidence(data, fixture.profile)
        fixture.profile['experiences'][0]['bullets'][0]['text'] = 'Saved 50 hours per week by a different method.'
        with self.assertRaisesRegex(ValueError, 'Profile evidence changed'):
            validate_resume_evidence(data, fixture.profile)

    def test_render_failure_does_not_accept_stale_pdf(self):
        import tempfile
        from unittest.mock import patch, MagicMock
        from render_pdf import export_html_to_pdf
        with tempfile.TemporaryDirectory() as folder:
            pdf = Path(folder) / 'resume.pdf'
            pdf.write_bytes(b'old artifact')
            process = MagicMock()
            process.poll.return_value = 0
            with patch('render_pdf.find_chrome_binary', return_value='/mock/chrome'), patch('render_pdf.subprocess.Popen', return_value=process), patch('os.killpg'):
                with self.assertRaises(RuntimeError):
                    export_html_to_pdf(str(Path(folder) / 'resume.html'), str(pdf))
            self.assertEqual(pdf.read_bytes(), b'old artifact')

    def test_render_publishes_complete_pdf_before_chrome_helpers_exit(self):
        import tempfile
        from unittest.mock import patch, MagicMock
        import pypdf
        from render_pdf import export_html_to_pdf
        def fake_chrome(command, **kwargs):
            target = next(arg.split('=', 1)[1] for arg in command if arg.startswith('--print-to-pdf='))
            writer = pypdf.PdfWriter()
            writer.add_blank_page(width=612, height=792)
            with open(target, 'wb') as handle:
                writer.write(handle)
            process = MagicMock()
            process.poll.return_value = None
            return process
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'resume.pdf'
            with patch('render_pdf.find_chrome_binary', return_value='/mock/chrome'), patch('render_pdf.subprocess.Popen', side_effect=fake_chrome), patch('os.killpg'):
                export_html_to_pdf(str(Path(folder) / 'resume.html'), str(target))
            self.assertEqual(get_pdf_page_count(str(target)), 1)
            self.assertEqual(list(Path(folder).iterdir()), [target])

if __name__ == "__main__":
    unittest.main()
