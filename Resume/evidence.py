"""Trace resume rewrites to profile evidence and reject unsupported factual claims.

These checks validate structure, numbers, units and listed skills. They do not
prove that arbitrary paraphrases preserve meaning: the report keeps sources
visible for human review.
"""
import copy
import hashlib
import json
import re


def normalize(text):
    return re.sub(r'[^a-z0-9]+', ' ', str(text).lower()).strip()


def source_catalog(profile):
    catalog = {}
    for exp in profile.get('experiences', []):
        identity = exp.get('id') or exp.get('company')
        for index, bullet in enumerate(exp.get('bullets', [])):
            catalog[f'{identity}:bullet:{index}'] = {
                'company': exp.get('company'),
                'text': bullet if isinstance(bullet, str) else bullet['text'],
                'tags': [] if isinstance(bullet, str) else bullet.get('tags', [])}
    return catalog


def skill_evidence(skill, profile):
    """Exact approved terms or full components; no partial-token inference."""
    aliases = {'process improvement': 'process optimization',
               'data reporting and analytics': 'dashboard development reporting'}
    # Punctuation carries skill identity (C, C++, C#, .NET, Node.js).
    skill_key = lambda value: re.sub(r'[^a-z0-9+#.]+', ' ', re.sub(r'(?<=[a-z0-9+#])\.(?=\s|$)', '', str(value).lower())).strip()
    needle = skill_key(skill)
    needle = aliases.get(needle, needle)
    if not needle:
        return None
    candidates = []
    for category, items in profile.get('skills', {}).items():
        if isinstance(items, list):
            candidates.extend((f'skills.{category}[{i}]', value) for i, value in enumerate(items))
    for ref, source in source_catalog(profile).items():
        candidates.append((ref, source['text']))
        candidates.extend((ref, tag.replace('_', ' ')) for tag in source['tags'])
    for ref, value in candidates:
        # Components explicitly listed in compound skills are supported as well.
        if f' {needle} ' in f' {skill_key(value)} ':
            return {'source_ref': ref, 'original': str(value), 'rewritten': skill}
    return None


def scoped_claim_errors(text, sources, label):
    """Reject known tool/domain transfers; this is not a semantic-equivalence proof.

    A global skill says the applicant knows a tool, not that they used it on the
    particular achievement being rewritten. Only cited bullet text/tags qualify.
    """
    groups = [('python',), ('sql',), ('excel',), ('tableau',), ('powerpoint',),
              ('hubspot', 'hub spot'), ('salesforce',), ('bloomberg terminal',),
              ('n8n',), ('google gemini', 'gemini'), ('kdb',),
              ('market data',), ('electronic trading',), ('order types',)]
    rewrite = ' ' + normalize(text) + ' '
    source = ' ' + normalize(' '.join(s['text'] + ' ' + ' '.join(s.get('tags', [])) for s in sources)) + ' '
    errors = []
    for terms in groups:
        if any(' ' + term + ' ' in rewrite for term in terms) and not any(' ' + term + ' ' in source for term in terms):
            errors.append(f'Unsupported source-scoped claim {terms[0]} in {label}.\nRewrite: {text}\nCited source: {source.strip()}')
    return errors


def numeric_claims(text):
    text = str(text).replace('**', '').lower()
    matches = list(re.finditer(r'(?<![a-z0-9])\$?\d[\d,]*(?:\.\d+)?(?:\+|%)?', text))
    # Keep qualifiers inside the numeric phrase they describe. In particular,
    # "weekly programming across 3 semesters" is a duration, not a weekly count.
    # A comma can introduce a new clause, but "50 hours, weekly" is still a rate.
    clause_boundary = (r'[;!?\n]|\.(?!\d)|'
                       r',(?!(?:\s*)(?:daily|weekly|monthly|yearly|annually|annual|per|every|each)\b)|'
                       r'\b(?:and|with|by|while|across)\b')
    claims = []
    for i, match in enumerate(matches):
        value = match.group().replace(',', '')
        following = text[match.end():matches[i + 1].start() if i + 1 < len(matches) else len(text)][:55]
        dimension = ''
        if '%' not in value and not value.startswith('$'):
            unit_context = re.split(clause_boundary, following)[0]
            unit_context = re.split(r'\b(?:per|every|each)\b|/', unit_context)[0]
            units = re.search(r'\b(seconds?|minutes?|hours?|days?|weeks?|users?|customers?|members?|clients?|emails?|communications?|accounts?|events?|people|persons?|dollars?|locations?|centers?|teams?|semesters?|organizations?|students?|prospects?|participants?|products?|units?|months?|years?|times?)\b', unit_context)
            if units:
                dimension = units.group().rstrip('s')
                dimension = {'people': 'person', 'persons': 'person', 'dollar': '$'}.get(dimension, dimension)
            else:
                noun = re.match(r'\s+([a-z]+)\b', unit_context)
                if noun and noun[1] not in {'daily', 'weekly', 'monthly', 'yearly', 'annually', 'annual', 'and', 'in', 'at', 'to', 'by', 'with', 'of', 'for', 'from', 'on', 'is', 'was', 'through', 'million', 'billion', 'thousand', 'k', 'm', 'b', 'x'}:
                    dimension = 'unknown:' + noun[1]
        aliases = {'daily': 'day', 'weekly': 'week', 'monthly': 'month',
                   'yearly': 'year', 'annually': 'year', 'annual': 'year'}
        pattern = r'(?:(?:per\s+|every\s+|each\s+|a\s+|/\s*)(day|week|month|year)\b|\b(daily|weekly|monthly|yearly|annually|annual)\b)'
        # A qualifier may precede the amount ("weekly savings of 50 hours").
        # Do not borrow a qualifier across another claim or a clause boundary.
        before = text[matches[i - 1].end() if i else 0:match.start()]
        before = re.split(clause_boundary, before)[-1][-55:]
        after = re.split(clause_boundary, following)[0]
        frequencies = {m.group(1) or aliases[m.group(2)] for fragment in (before, after)
                       for m in re.finditer(pattern, fragment)}
        frequency = '|'.join(sorted(frequencies))
        scale = re.match(r'\s*(million|billion|thousand|k|m|b|x|×)\b', following)
        if scale:
            dimension += ':' + {'k': 'thousand', 'm': 'million', 'b': 'billion', '×': 'x'}.get(scale.group(1), scale.group(1))
        claims.append((value, dimension, frequency))
    return claims


def metric_errors(text, source, label):
    allowed = numeric_claims(source)
    errors = []
    for value, unit, frequency in numeric_claims(text):
        if not any(value == v and unit == u and frequency == f for v, u, f in allowed):
            unit_label = ('unrecognized unit ' + unit.split(':', 1)[1]
                          if unit.startswith('unknown:') else unit)
            claim = ' '.join(part for part in (value, unit_label, 'per ' + frequency if frequency else '') if part)
            errors.append(f'Unsupported metric {claim} in {label}.\nRewrite: {text}\nSource: {source}')
    return errors


class ResumeEvidenceError(ValueError):
    """Keep machine-readable metric failures separate from other evidence errors."""
    def __init__(self, non_metric_errors, metric_issues):
        self.non_metric_errors = list(non_metric_errors)
        self.metric_issues = copy.deepcopy(metric_issues)
        errors = self.non_metric_errors + [error for issue in metric_issues for error in issue['errors']]
        super().__init__('Resume evidence validation failed:\n' + '\n'.join(errors))


def validate_resume_evidence(data, profile):
    """Enforce source references before rendering; enrich the review report."""
    catalog = source_catalog(profile)
    masters = {exp['company']: exp for exp in profile.get('experiences', [])}
    evidence = []
    errors = []
    metric_issues = []
    seen = set()
    for experience_index, exp in enumerate(data.get('experiences', [])):
        company = exp.get('company')
        master = masters.get(company)
        if not master or company in seen:
            errors.append(f'Unknown or duplicate employer: {company}')
            continue
        seen.add(company)
        for field in ('role', 'date_range', 'location'):
            if normalize(exp.get(field, '')) != normalize(master.get(field, '')):
                errors.append(f'Unsupported {field} for {company}: {exp.get(field)}')
        refs = exp.get('bullet_source_refs', [])
        bullets = exp.get('bullets', [])
        if len(refs) != len(bullets):
            errors.append(f'Missing bullet source references for {company}')
            continue
        for bullet_index, (bullet, source_refs) in enumerate(zip(bullets, refs)):
            text = bullet if isinstance(bullet, str) else bullet.get('text', '')
            if isinstance(source_refs, str):
                source_refs = [source_refs]
            if not isinstance(source_refs, list) or not source_refs or any(ref not in catalog or catalog[ref]['company'] != company for ref in source_refs):
                errors.append(f'Invalid source reference for {company}: {source_refs}')
                continue
            sources = [catalog[ref]['text'] for ref in source_refs]
            errors.extend(scoped_claim_errors(text, [catalog[ref] for ref in source_refs], company))
            failures = metric_errors(text, ' '.join(sources), company)
            if failures:
                metric_issues.append({'company': company, 'experience_index': experience_index,
                                      'bullet_index': bullet_index, 'source_refs': list(source_refs),
                                      'original': sources, 'rewritten': text, 'errors': failures})
            evidence.append({'company': company, 'source_refs': source_refs, 'original': sources, 'rewritten': text})
    skill_records = []
    for category, skills in data.get('skills', {}).items():
        if not isinstance(skills, list):
            errors.append(f'Invalid skills category {category}')
            continue
        for skill in skills:
            record = skill_evidence(skill, profile)
            if not record:
                errors.append(f'Unsupported skill: {skill}')
            else:
                skill_records.append(dict(record, category=category))
    # Identity/education are taken from the profile, never generated credentials.
    personal = copy.deepcopy(profile.get('personal_info', {}))
    if not personal.get('full_name') or not profile.get('education'):
        errors.append('Missing profile identity or education')
    education = []
    if len(data.get('education', [])) != len(profile.get('education', [])):
        errors.append('Education count differs from profile')
    for index, master in enumerate(profile.get('education', [])):
        generated = (data.get('education', []) + [{}] * len(profile['education']))[index]
        for field in ('institution', 'graduation_date', 'location'):
            if normalize(generated.get(field, '')) != normalize(master.get(field, '')):
                errors.append(f'Unsupported education {field}: {generated.get(field)}')
        coursework = generated.get('coursework', [])
        if any(course not in master.get('coursework', []) for course in coursework):
            errors.append('Unsupported coursework')
        honors = generated.get('honors', [])
        if any(normalize(h) not in {normalize(m) for m in master.get('honors', [])} for h in honors):
            errors.append('Unsupported honor or qualification')
        # The degree display is derived deterministically from verified profile fields.
        edu = copy.deepcopy(master)
        degree = master.get('degree', '')
        title, separator, major = degree.partition(' in ')
        edu['degree_title'] = master.get('degree_title') or title
        edu['major_minor_gpa'] = master.get('major_minor_gpa') or ((f"Major in {major} " if separator else '') + f"[GPA: {master.get('gpa', '')}]")
        edu['coursework'] = coursework
        edu['honors'] = honors
        edu['activities'] = master.get('activities', [])
        education.append(edu)
    provenance = {'bullets': [{'source_refs': item['source_refs'], 'original': item['original']} for item in evidence],
                  'skills': [{'source_ref': item['source_ref'], 'original': item['original']} for item in skill_records],
                  'personal_info': personal, 'education': education}
    source_hash = hashlib.sha256(json.dumps(provenance, sort_keys=True).encode()).hexdigest()
    if data.get('profile_evidence_sha256') and data['profile_evidence_sha256'] != source_hash:
        errors.append('Profile evidence changed since this packet was generated; regenerate the resume.')
    report = data.setdefault('tailoring_report', {})
    report['evidence_review'] = {'bullets': evidence, 'skills': skill_records,
                               'metric_corrections': copy.deepcopy(report.get('metric_corrections', [])),
                               'validation_errors': errors + [error for issue in metric_issues for error in issue['errors']],
                               'limitation': 'Checks cannot prove semantic equivalence. Review each rewrite against its source.'}
    if errors or metric_issues:
        raise ResumeEvidenceError(errors, metric_issues)
    data['personal_info'] = personal
    data['education'] = education
    data['evidence_version'] = 1
    data['profile_evidence_sha256'] = source_hash
    return data


def validate_saved_resume(data, profile):
    """Validate persisted facts without repairing or replacing the exported data."""
    checked = copy.deepcopy(data)
    validate_resume_evidence(checked, profile)
    for key in ('personal_info', 'education'):
        if data.get(key) != checked.get(key):
            raise ValueError(f'Saved {key} differs from verified profile facts. Regenerate this packet.')
    return checked['tailoring_report']['evidence_review']


def evidence_markdown(review):
    lines = ['## Resume evidence review', '', review.get('limitation', ''), '']
    for item in review.get('bullets', []):
        lines.extend([f"### {item['company']} — {', '.join(item['source_refs'])}", '',
                      '**Original:** ' + ' | '.join(item['original']), '',
                      '**Rewritten:** ' + item['rewritten'], ''])
    lines.extend(['### Skills evidence', ''])
    for item in review.get('skills', []):
        lines.append(f"- {item['rewritten']} ← `{item['source_ref']}`: {item['original']}")
    if review.get('metric_corrections'):
        lines.extend(['', '### Automatic metric correction (one attempt)', ''])
        for item in review['metric_corrections']:
            lines.extend([f"**{item['company']} — bullet {item['bullet_index'] + 1}**", '',
                          '**Source:** ' + ' | '.join(item['original']), '',
                          '**Initial rewrite (rejected):** ' + item['rewritten'], '',
                          '**Corrected rewrite:** ' + item['corrected'], ''])
    return '\n'.join(lines)


def validate_outreach_evidence(body, data, role=''):
    """Check numeric achievement claims against the attached resume's evidence."""
    content = body.split('Thanks for your time,')[0]
    if role:
        content = content.replace(role, '')
    # Proposed chat lengths are requests, not career achievements.
    content = re.sub(r'\b\d+(?:\s*[–-]\s*\d+)?\s*minutes?\b', '', content, flags=re.I)
    experiences = data.get('experiences', [])
    all_text = ' '.join(b if isinstance(b, str) else b.get('text', '')
                        for exp in experiences for b in exp.get('bullets', []))
    errors = []
    for paragraph in content.split('\n\n'):
        cited = [exp for exp in experiences if exp.get('company', '').casefold() in paragraph.casefold()]
        source = ' '.join(b if isinstance(b, str) else b.get('text', '')
                          for exp in cited for b in exp.get('bullets', [])) if cited else all_text
        errors.extend(metric_errors(paragraph, source, 'outreach copy'))
    if errors:
        raise ValueError('Outreach evidence validation failed:\n' + '\n'.join(errors))
