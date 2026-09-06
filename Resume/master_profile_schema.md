# Master Profile Guide & Schema

The `master_profile.json` file is your **single source of truth** for all your career accomplishments, roles, projects, skills, and coursework. 

The AI tailoring engine reads this file and selects, re-orders, and highlights the exact experiences and keywords that match each job description you apply to.

---

## Structure Overview

```json
{
  "personal_info": {
    "full_name": "Your Name",
    "headline": "Target headline",
    "email": "your.email@example.com",
    "phone": "123-456-7890",
    "location": "City, State",
    "linkedin": "linkedin.com/in/your-profile",
    "github": "github.com/your-username",
    "portfolio": "your-portfolio.com"
  },
  "education": [
    {
      "institution": "University / College",
      "degree": "Degree and Majors",
      "location": "City, State",
      "graduation_date": "Month Year (or Expected)",
      "gpa": "3.8/4.0",
      "honors": ["Dean's List", "Scholarship"],
      "coursework": ["Course 1", "Course 2"]
    }
  ],
  "experiences": [
    {
      "id": "unique_id",
      "company": "Company Name",
      "role": "Job Title",
      "location": "City, State",
      "date_range": "Month Year - Month Year",
      "description": "Brief context on what the company/team does",
      "bullets": [
        {
          "text": "Accomplished [X] as measured by [Y], by doing [Z]...",
          "tags": ["python", "leadership", "analytics"],
          "impact": "high"
        }
      ]
    }
  ],
  "projects": [
    {
      "id": "proj_id",
      "name": "Project Name",
      "role": "Creator / Developer",
      "date_range": "2025",
      "tech_stack": ["Python", "FastAPI", "PostgreSQL"],
      "link": "github.com/username/project",
      "bullets": [
        {
          "text": "Built [System] to solve [Problem], handling [Metric]...",
          "tags": ["python", "api"]
        }
      ]
    }
  ],
  "skills": {
    "programming_languages": ["Python", "SQL", "JavaScript", "HTML/CSS"],
    "frameworks_and_libraries": ["Pandas", "NumPy", "Pydantic", "FastAPI"],
    "ai_and_automation": ["Google Antigravity SDK", "Gemini API", "Prompt Engineering"],
    "tools_and_platforms": ["Git", "GitHub", "Excel", "Notion", "HubSpot"],
    "business_and_analytical": ["Product Strategy", "Market Research", "Financial Modeling"]
  },
  "certifications_and_activities": [
    {
      "title": "Role / Award",
      "organization": "Club / Organization / Issuer",
      "date": "Year"
    }
  ]
}
```

---

## Tips for Best Results

1. **Add as many bullet points as you want**: Include 5-10 bullets per job in `master_profile.json`. The AI will select the top 3-4 best bullets for each specific job posting.
2. **Quantify your impact**: Use numbers, percentages, dollar amounts, and team sizes (e.g. `20% ARR increase`, `100+ contacts`, `5-person team`).
3. **Keep tags updated**: Tags (like `"python"`, `"product_management"`, `"financial_modeling"`) help semantic keyword alignment.
