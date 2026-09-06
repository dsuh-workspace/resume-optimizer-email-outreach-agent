# {{ personal_info.full_name }}
{% if target_title %}### {{ target_title }}{% endif %}

{{ personal_info.location }} | {{ personal_info.phone }} | [{{ personal_info.email }}](mailto:{{ personal_info.email }}) | [LinkedIn](https://{{ personal_info.linkedin }}) | [GitHub](https://{{ personal_info.github }})

---

{% if summary %}
## Professional Summary
{{ summary }}

---
{% endif %}

## Education
{% for edu in education %}
**{{ edu.institution }}** — {{ edu.degree }}  
*{{ edu.graduation_date }} | {{ edu.location }}*  
{% if edu.gpa %}**GPA:** {{ edu.gpa }} {% endif %}{% if edu.honors %}| **Honors:** {{ edu.honors|join(', ') }}{% endif %}  
{% if edu.coursework %}**Relevant Coursework:** {{ edu.coursework|join(', ') }}{% endif %}

{% endfor %}

---

## Experience
{% for exp in experiences %}
### {{ exp.role }} — **{{ exp.company }}**
*{{ exp.date_range }} | {{ exp.location }}*
{% for bullet in exp.bullets %}
- {{ bullet }}
{% endfor %}

{% endfor %}

---

## Projects
{% for proj in projects %}
### {{ proj.name }} | *{{ proj.tech_stack|join(', ') }}*
*{{ proj.date_range }}{% if proj.link %} | [{{ proj.link }}](https://{{ proj.link }}){% endif %}*
{% for bullet in proj.bullets %}
- {{ bullet }}
{% endfor %}

{% endfor %}

---

## Skills
{% for cat_name, skill_list in skills.items() %}
- **{{ cat_name }}:** {{ skill_list|join(', ') }}
{% endfor %}

{% if certifications_and_activities and certifications_and_activities|length > 0 %}
---

## Leadership & Activities
{% for act in certifications_and_activities %}
- **{{ act.title }}** — {{ act.organization }} (*{{ act.date }}*)
{% endfor %}
{% endif %}
