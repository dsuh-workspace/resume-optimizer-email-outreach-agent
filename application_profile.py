"""Explicit application preferences and shared field policy. Never infer personal answers."""
import copy
import json
import re
from pathlib import Path

POLICY = json.loads((Path(__file__).parent / 'extension/field-policy.json').read_text())
MANUAL = re.compile(POLICY['manual'], re.I)
DISCLOSURE = re.compile(POLICY['disclosure'], re.I)
PERSONAL = re.compile(POLICY['personal'], re.I)
WRITTEN = re.compile(POLICY['written'], re.I)


def validate_profile(value):
    if not isinstance(value, dict) or set(value) - {'work', 'education', 'disclosures', 'automation', 'company_answers'}:
        raise ValueError('Unsupported application profile field.')
    result = copy.deepcopy(value)
    work = result.get('work', {})
    if not isinstance(work, dict) or set(work) - {'country', 'authorized', 'sponsorship_now', 'sponsorship_future'}:
        raise ValueError('Invalid work eligibility fields.')
    for key, answer in work.items():
        if key == 'country':
            if answer != 'US':
                raise ValueError('Structured work eligibility currently supports US only; save exact answers for other countries.')
        elif type(answer) is not bool:
            raise ValueError('Work eligibility answers must be explicitly Yes or No.')
    education = result.get('education', [])
    if not isinstance(education, list) or len(education) > 10:
        raise ValueError('Invalid application education entries.')
    for item in education:
        if not isinstance(item, dict) or set(item) - {'institution', 'aliases', 'degree', 'major', 'start', 'end', 'status'}:
            raise ValueError('Invalid education fields.')
        for key in ('institution', 'degree', 'major'):
            if not isinstance(item.get(key), str) or not 1 <= len(item[key].strip()) <= 300:
                raise ValueError('School, degree and major are required.')
        if item.get('status') not in ('expected', 'completed'):
            raise ValueError('Record whether the degree is expected or completed.')
        for key in ('start', 'end'):
            if item.get(key) and not re.fullmatch(r'\d{4}-(?:0[1-9]|1[0-2])', item[key]):
                raise ValueError('Education dates require YYYY-MM; no day is inferred.')
        if item.get('start') and item.get('end') and item['start'] > item['end']:
            raise ValueError('Education end precedes start.')
        aliases = item.get('aliases', [])
        if not isinstance(aliases, list) or len(aliases) > 10 or any(not isinstance(a, str) or not 1 <= len(a.strip()) <= 300 for a in aliases):
            raise ValueError('Invalid school aliases.')
    disclosures = result.get('disclosures', {})
    if not isinstance(disclosures, dict) or set(disclosures) - {'race', 'hispanic', 'gender', 'disability', 'protected_veteran', 'veteran', 'lgbtq', 'gender_identity', 'ethnicity', 'military_history'}:
        raise ValueError('Invalid disclosure fields.')
    if any(not isinstance(a, str) or not 1 <= len(a.strip()) <= 200 for a in disclosures.values()):
        raise ValueError('Disclosures require explicit nonempty answers; omit unanswered fields.')
    automation = result.get('automation', {})
    if not isinstance(automation, dict) or set(automation) - {'relationships_no', 'exhaustive_employment', 'recruitment_consent', 'demographic_consent'} or any(type(v) is not bool for v in automation.values()):
        raise ValueError('Automation settings require explicit boolean authorization.')
    answers = result.get('company_answers', [])
    if not isinstance(answers, list) or len(answers) > 100:
        raise ValueError('Invalid company answers.')
    seen = set()
    for item in answers:
        if not isinstance(item, dict) or set(item) != {'company', 'question', 'answer'}:
            raise ValueError('Company answers require company, exact question and answer.')
        if any(not isinstance(item.get(k), str) or not item[k].strip() or len(item[k]) > 4000 for k in ('company', 'question')):
            raise ValueError('Company and question must be nonempty text.')
        answers = item['answer'] if isinstance(item['answer'], list) else [item['answer']]
        if not 1 <= len(answers) <= 50 or any(not isinstance(v, str) or not v.strip() or len(v) > 4000 for v in answers) or len(set(answers)) != len(answers):
            raise ValueError('Provide a nonempty answer or distinct answer set.')
        key = (employer_key(item['company']), question_key(item['question']))
        if key in seen or MANUAL.search(item['question']) or WRITTEN.search(item['question']):
            raise ValueError('Duplicate or manual-only company answer.')
        seen.add(key)
    return result


def question_key(value):
    return re.sub(r"[ *:?!✱]+$", "", " ".join(value.casefold().split())).strip()


def employer_key(value):
    value = re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()
    return re.sub(r"(?: (?:inc|incorporated|llc|ltd|limited|corp|corporation))+$", "", value)


HISTORY = re.compile(r"\b(?:(?:have|had|did|do|are|were) you (?:(?:ever|previously|formerly|currently|before|been|a|an|former|current) )*(?:work(?:ed|ing)? (?:for|with|at|here)|employed\b|employee\b|contractor\b)|^(?:previous|prior|former|current) (?:employee|employment))", re.I)
RELATIONSHIP = re.compile(r"\b(?:relationships?|related to|relatives?|family(?: members?)?|friends?|spouse|familial|romantic|know anyone|know any(?:one| employees?))\b", re.I)
MIXED = re.compile(r"\b(?:government|investments?|business activities|intellectual property|ownership|certif\w*|attest\w*|background|criminal|financial|conflicts? of interest)\b", re.I)


def resolve_question(question, company, app, profile):
    """Use explicit instructions and the FULL profile; never a selected resume."""
    q = question_key(question)
    company_id = employer_key(company)
    history_question = bool(HISTORY.search(q) or re.match(r'(?:do|have|are) you (?:ever |currently )?(?:have |had |in )?(?:any |an? )?(?:employment|professional|working|business) relationship', q))
    for item in app.get('company_answers', []):
        if not history_question and company_id and employer_key(item['company']) == company_id and question_key(item['question']) == q:
            return {'value': item['answer'], 'source': 'Explicit company answer (exact wording)'}
    auto = app.get('automation', {})
    if MANUAL.search(q):
        return None
    if history_question:
        if not auto.get('exhaustive_employment'):
            return {'reason': 'Authorize checking your exhaustive master employment list in Settings.'}
        if MIXED.search(q) or re.search(r"\b(?:and|or) (?:do|have|are|will) you|\b(?:subsidiar|affiliat|parent compan|acquir|applied|interview|since|between)|(?:last|past) \d+ years", q):
            return {'reason': 'This question includes additional history or entities not established by the profile.'}
        target = re.search(r"(?:work(?:ed|ing)? (?:for|with|at)|employed (?:by|with|at)|employee (?:of|at)|contractor (?:for|at)) (.+?)(?=\?|[.;]| as (?:an? |the )| (?:before|previously|in the past|at any time|either|in any capacity)\b|$)", q)
        name = target.group(1).strip() if target else ''
        name = re.sub(r"^(?:the company|company)\s+", '', name)
        if name in ('us', 'our company', 'this company', 'here', 'the company', ''):
            name = company
        target_id = employer_key(name)
        if not target_id or target_id in ('us', 'our company', 'this company', 'here') or re.search(r"\b(?:or|and|any|a|an)\b|[/]", name):
            return {'reason': 'Cannot identify a single employer for this work-history question.'}
        if not isinstance(profile, dict) or not isinstance(profile.get('experiences'), list) or not profile['experiences'] or any(not isinstance(e, dict) or not isinstance(e.get('company'), str) or not e['company'].strip() for e in profile['experiences']):
            return {'reason': 'Full master profile is unavailable or incomplete; employment history cannot be checked.'}
        matches = [e for e in profile['experiences'] if target_id in [employer_key(e['company']), *[employer_key(a) for a in e.get('aliases', [])]]]
        if matches:
            if re.search(r'\b(?:currently|current employee|still)\b', q):
                if any(re.search(r'\b(?:present|current)\b', e.get('date_range', ''), re.I) for e in matches):
                    pass
                elif all(re.search(r'\d{4}\s*$', e.get('date_range', '')) for e in matches):
                    return {'value': 'No', 'source': 'Full master profile: matching employment has ended'}
                else:
                    return {'reason': 'Matching employer found, but current employment status is not established.'}
            # A company entry establishes work with/for it; narrower employment types need evidence.
            qualifier = re.search(r'\b(full.time|part.time|permanent)\b', q)
            if qualifier and not re.search(r'employee.{0,20}intern.{0,20}contractor', q):
                kind = re.sub(r'[- ]', '', qualifier[1])
                if not any(kind in re.sub(r'[- ]', '', str(e.get('employment_type', '')).lower()) for e in matches):
                    return {'reason': 'Employer found, but the requested employment type is not established.'}
            if re.search(r"\b(?:full.time|permanent|employee|contractor|intern)\b", q) and not re.search(r"employee.{0,20}intern.{0,20}contractor", q):
                requested = re.search(r"\b(employee|contractor|intern)\b", q)
                if requested and not any(requested[1] in str(e.get('employment_type', '')).lower() or requested[1] == 'intern' and 'intern' in e.get('role', '').lower() for e in matches):
                    return {'reason': 'Employer found, but the requested employment type is not established.'}
            return {'value': 'Yes', 'source': 'Full master profile: matching employer'}
        if any(target_id in employer_key(e['company']) or employer_key(e['company']) in target_id or target_id.replace(' ', '') == ''.join(w[0] for w in employer_key(e['company']).split()) for e in profile['experiences']):
            return {'reason': 'Employer identity is ambiguous; confirm the company name or alias.'}
        # This alternative is evidence of never working there, not merely current status.
        display_name = company.strip() if target_id == company_id else name
        return {'value': 'No', 'alternatives': [f'I have never worked at {display_name}'],
                'source': 'Full master profile checked; user confirmed the experience list is exhaustive'}
    if RELATIONSHIP.search(q) and not re.fullmatch(r'(?:what is your |your )?family name', q):
        if MIXED.search(q) or re.search(r"\b(?:and|or) (?:do|have|are|will) you|outside (?:work|activities)|referr(?:al|ed)|recommend|own(?:ing)? shares", q):
            return {'reason': 'Combined relationship question requires an exact saved answer.'}
        if auto.get('relationships_no') and re.match(r"(?:do|have|are|is)\b", q):
            return {'value': 'No', 'source': 'Explicit cross-company relationship answer'}
        return {'reason': 'No authorized relationship answer is saved.'}
    return None
