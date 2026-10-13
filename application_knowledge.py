"""Grounded application facts. Model output selects evidence, never supplies facts."""
import hashlib
import json
import re
import calendar
from datetime import date
from pathlib import Path

from application_profile import MANUAL, DISCLOSURE, PERSONAL, HISTORY, RELATIONSHIP

PREPARATION_VERSION = 2
ENGINE_REVISION = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
CONTEXT_KEYS = ('label', 'helper', 'type', 'options', 'required', 'limit', 'wordLimit',
                'group', 'condition', 'occurrence', 'multiple', 'section', 'subject', 'contextVersion')
FACT_KEYS = {'first_name', 'last_name', 'full_name', 'email', 'phone', 'linkedin', 'github',
             'current_city', 'address', 'state', 'postal_code', 'country', 'school', 'degree',
             'major', 'minor', 'gpa', 'graduation_month', 'graduation_year', 'graduation_date', 'education_summary',
             'gender_identity', 'ethnicity', 'military_history'}


ENROLLMENT = re.compile(r'\b(enroll\w*|attend\w*|pursu\w*)\b|\b(current|currently|present)\b.*\b(school|university|college|student|degree|education)\b|\b(school|university|college|degree|education)\b.*\b(current|currently|present)\b', re.I)
THIRD_PARTY = re.compile(r'\b(references?|referees?|emergency|next of kin|third.party|parent|guardian|spouse)\b', re.I)

LABEL_THIRD_PARTY = re.compile(r"\b(emergency contact|next of kin|third.party|parent|guardian|spouse|referee)\b|\breference(?:['’]s|\s+(?:name|email|phone|contact|relationship))\b|\b(?:of|for) (?:your |a |the )?reference\b|^\s*references?\s*[*:]*$", re.I)

def subject_reason(field):
    if field.get('subject', 'applicant') != 'applicant' or THIRD_PARTY.search(str(field.get('section', ''))) or LABEL_THIRD_PARTY.search(field.get('label', '')):
        return {'reason': 'Third-party or uncertain subject: complete this field manually.', 'category': 'needs_input'}
    return None

def contextual_question(field):
    text = field['label'] + ('\n' + field['helper'] if field.get('helper') else '')
    return ('[' + field['section'] + ' | ' + field.get('subject', 'applicant') + ']\n' if field.get('section') else '') + text


def field_context(field):
    return {k: field[k] for k in CONTEXT_KEYS if k in field}


def context_digest(payload, field, preferences, profile):
    data = [PREPARATION_VERSION, ENGINE_REVISION, payload.get('url'), payload.get('company'),
            field_context(field), preferences, profile]
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def validate_knowledge(records):
    if not isinstance(records, list) or len(records) > 300:
        raise ValueError('Invalid reusable facts.')
    seen = set()
    for record in records:
        if not isinstance(record, dict) or set(record) - {'key', 'answer', 'scope', 'question', 'company', 'posting', 'confirmed_at', 'valid_until'}:
            raise ValueError('Invalid fact metadata.')
        if record.get('key') == 'school' and ENROLLMENT.search(record.get('question', '')):
            raise ValueError('Current enrollment requires an exact question answer, not a global school fact.')
        if record.get('key') not in FACT_KEYS or record.get('scope') not in ('global', 'company', 'posting'):
            raise ValueError('Choose a supported fact and reuse scope.')
        for key in ('answer', 'question', 'confirmed_at'):
            if not isinstance(record.get(key), str) or not 1 <= len(record[key]) <= 2000:
                raise ValueError('Reusable facts require an answer, source question and confirmation date.')
        for key in ('confirmed_at', 'valid_until'):
            if record.get(key):
                date.fromisoformat(record[key])
        if record['scope'] != 'global' and not record.get('company' if record['scope'] == 'company' else 'posting'):
            raise ValueError('Scoped facts need a company or posting.')
        identity = (record['key'], record['scope'], record.get('company'), record.get('posting'))
        if identity in seen:
            raise ValueError('Duplicate reusable fact.')
        seen.add(identity)
    return records


def fact_catalog(profile, prefs, company='', url=''):
    result = {}
    def add(key, value, source):
        if value is not None and str(value).strip():
            if key in ('linkedin', 'github') and not str(value).startswith(('https://', 'http://')):
                value = 'https://' + str(value)
            result[key] = {'value': str(value), 'source': source, 'fact_key': key, 'category': 'fact'}
    personal = (profile or {}).get('personal_info', {})
    for key in ('full_name', 'email', 'phone', 'linkedin', 'github'):
        add(key, personal.get(key), 'Verified master profile: ' + key)
    for key, value in prefs.get('facts', {}).items():
        add('current_city' if key == 'city' else key, value, 'Explicit profile fact: ' + key)
    app = prefs.get('application_profile', {})
    for key in ('gender_identity', 'ethnicity', 'military_history'):
        add(key, app.get('disclosures', {}).get(key), 'Explicit disclosure: ' + key)
    schools = app.get('education', [])
    if len(schools) == 1:
        school = schools[0]
        for key, attr in [('school', 'institution'), ('degree', 'degree'), ('major', 'major')]:
            add(key, school.get(attr), 'Explicit education: ' + attr)
        if re.fullmatch(r'\d{4}-\d{2}', school.get('end', '')):
            add('graduation_year', school['end'][:4], 'Explicit education: expected/completed end year')
            add('graduation_month', school['end'][5:], 'Explicit education: expected/completed end month')
            add('graduation_date', calendar.month_name[int(school['end'][5:])] + ' ' + school['end'][:4], 'Explicit education: month and year')
        school_key = lambda value: re.sub(r'[^a-z0-9]+', '', value.casefold())
        identities = [school_key(school['institution']), *[school_key(a) for a in school.get('aliases', [])]]
        matches = [s for s in (profile or {}).get('education', [])
                   if any(len(identity) >= 8 and school_key(s.get('institution', '')).startswith(identity) for identity in identities)]
        if len(matches) == 1:
            add('education_summary', matches[0].get('degree'), 'Verified master education: recorded degree, major and minor')
            for key in ('gpa', 'minor'):
                add(key, matches[0].get(key), 'Verified master education: ' + key)
            minor = re.search(r'\bMinor in ([^;]+)', matches[0].get('degree', ''), re.I)
            if minor and 'minor' not in result:
                add('minor', minor[1], 'Verified master education: explicitly named minor')
    for record in prefs.get('knowledge', []):
        if record.get('valid_until', '9999-12-31') < date.today().isoformat():
            continue
        if record['scope'] == 'company' and record.get('company', '').casefold() != company.casefold():
            continue
        if record['scope'] == 'posting' and record.get('posting') != url:
            continue
        key = record['key']
        # Conflict is terminal for this catalog build: another applicable scope
        # cannot restore a value just by agreeing with one conflicting source.
        if key in result and ('value' not in result[key] or result[key]['value'] != record['answer']):
            result[key] = {'reason': 'Confirmed sources conflict; resolve this fact before filling.', 'fact_key': key}
        else:
            add(key, record['answer'], 'Explicit reusable fact confirmed ' + record['confirmed_at'])
    return result


def resolve_fact(key, catalog):
    return catalog.get(key, {'reason': 'No confirmed fact is available.', 'fact_key': key})


def direct_resolution(field, catalog):
    """Only complete, closed ordinary labels qualify without interpretation."""
    if subject_reason(field) or ENROLLMENT.search(field.get('label', '') + ' ' + field.get('helper', '')):
        return {'reason': 'This question needs your explicit answer.'}
    if field.get('helper') or field.get('group'):
        return None
    label = re.sub(r'[ *:?!✱]+$', '', field['label'].lower()).strip()
    aliases = {'current city': 'current_city', 'city': 'current_city', 'location (city)': 'current_city',
               'current location': 'current_city', 'gpa': 'gpa', 'grade point average': 'gpa', 'minor': 'minor',
               'what is your cumulative gpa': 'gpa', 'what is your family name': 'last_name', 'family name': 'last_name',
               'what is your given name': 'first_name', 'given name': 'first_name'}
    key = aliases.get(label)
    if key in catalog:
        result = dict(catalog[key])
        if key == 'gpa' and 'value' in result:
            result['matchRule'] = {'kind': 'numeric_interval'}
        return result
    graduation = re.fullmatch(r'is your expected graduation date in (\d{4}) or (later|earlier)', label)
    if graduation and 'value' in catalog.get('graduation_year', {}):
        year = int(catalog['graduation_year']['value'])
        eligible = year >= int(graduation[1]) if graduation[2] == 'later' else year <= int(graduation[1])
        return {'value': 'Yes' if eligible else 'No', 'source': 'Derived from confirmed graduation year ' + str(year), 'category': 'derived'}
    return None


def interpreted_resolution(field, interpretation, catalog):
    """A conservative gate around semantic interpretation of ordinary factual fields."""
    text = (field.get('label', '') + ' ' + field.get('helper', '')).strip()
    unknown = {'reason': 'This question needs an explicit answer or clearer scope.', 'category': 'needs_input'}
    if subject_reason(field) or ENROLLMENT.search(text):
        return unknown
    policy_text = re.sub(r'\bfamily name\b', 'surname', text, flags=re.I)
    if any(pattern.search(policy_text) for pattern in (MANUAL, DISCLOSURE, PERSONAL, HISTORY, RELATIONSHIP)):
        return unknown
    # Changed time, location, qualification, comparison, or compound conditions
    # cannot be erased by the model selecting a familiar fact key.
    if re.search(r'\b(?:summer|would|willing|during|since|between|minimum|at least|at most|higher|completed|earned|awarded|highest|citizen|subsidiar\w*|affiliat\w*)\b', text, re.I):
        return unknown
    if interpretation.get('kind') == 'written':
        if field.get('type') in ('text', 'textarea', 'search'):
            return {'written': True, 'category': 'written', 'reason': 'Required writing can be drafted from verified evidence.'}
        return unknown
    if interpretation.get('kind') != 'fact':
        return unknown
    key = interpretation.get('fact_key')
    if re.search(r'\b(?:will|future)\b', text, re.I) and key not in ('graduation_date', 'graduation_year', 'graduation_month'):
        return unknown
    qualifiers = interpretation.get('qualifiers', [])
    if not isinstance(qualifiers, list) or any(not isinstance(q, str) for q in qualifiers):
        return unknown
    intrinsic = {'current_city': {'current', 'currently', 'present'}, 'school': set(),
                 'graduation_year': {'expected'}, 'graduation_month': {'expected'},
                 'graduation_date': {'expected', 'month and year'},
                 'education_summary': set()}
    if any(q.lower() not in intrinsic.get(key, set()) for q in qualifiers):
        return unknown
    # These families must be resolved by explicit policy, never a model mapping.
    if key not in FACT_KEYS - {'gender_identity', 'ethnicity', 'military_history'}:
        return unknown
    anchors = {
        'current_city': r'\b(city|location|live|reside|residence|based)\b',
        'school': r'\b(school|university|college|institution)\b',
        'degree': r'\bdegree\b', 'major': r'\b(major|discipline|field of study)\b',
        'minor': r'\bminor\b', 'gpa': r'\b(gpa|grade point average)\b',
        'graduation_year': r'\b(graduat\w*|completion)\b.*\byear\b|\byear\b.*\bgraduat\w*\b',
        'graduation_month': r'\bgraduat\w*\b.*\bmonth\b|\bmonth\b.*\bgraduat\w*\b',
        'graduation_date': r'\b(graduat\w*|completion date)\b',
        'education_summary': r'\bdegree\b.*\b(?:major|minor)',
        'full_name': r'\b(full name|your name)\b', 'first_name': r'\b(first|given) name\b',
        'last_name': r'\b(last|family|sur) ?name\b', 'email': r'\be-?mail\b',
        'phone': r'\b(phone|mobile|telephone)\b', 'linkedin': r'\blinkedin\b',
        'github': r'\bgithub\b', 'address': r'\b(street|mailing|address)\b',
        'state': r'\b(state|province)\b', 'postal_code': r'\b(zip|postal)\b', 'country': r'\bcountry\b',
    }
    if not re.search(anchors[key], text, re.I):
        return unknown
    # A compound request cannot be answered with only one of its facts.
    if key not in ('education_summary', 'graduation_date') and re.search(r'\b(?:and|plus)\b|\bmajor\b.*\bminor\b', text, re.I):
        return unknown
    if key == 'graduation_date' and re.search(r'\b(?:day|dd|exact)\b', text, re.I):
        return {'reason': 'Only the graduation month and year are confirmed; the exact day is unknown.'}
    result = dict(resolve_fact(key, catalog))
    if 'value' in result and field.get('limit') and len(result['value']) > field['limit']:
        return {'reason': 'Confirmed answer exceeds this field’s character limit.', 'fact_key': key}
    return result
