import os
import re
import base64
import mimetypes
import json
import hashlib
import datetime
from email.utils import getaddresses
from reliability_store import store_lock, read_json, atomic_write
from typing import Optional, Dict, Any
from pathlib import Path
from email.message import EmailMessage
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
DRAFT_REGISTRY = BASE_DIR.parent / ".draft_registry.json"

# Load environment variables
load_dotenv(dotenv_path=BASE_DIR / ".env")
if not os.getenv("GEMINI_API_KEY") and (BASE_DIR.parent / ".env").exists():
    load_dotenv(dotenv_path=BASE_DIR.parent / ".env")

# modify scope allows creating drafts, sending emails, and inspecting threads/replies
SCOPES = ['https://www.googleapis.com/auth/gmail.modify']

def get_gmail_service():
    creds = None
    token_path = BASE_DIR / "token.json"
    client_secret_path = BASE_DIR / "client_secret.json"

    # token.json stores the user's access and refresh tokens
    if token_path.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_path))
        except Exception:
            creds = None
        
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"⚠️ Token refresh warning: {e}")
                creds = None
        
        if not creds or not creds.valid:
            if os.getenv("COPILOT_NONINTERACTIVE") == "1":
                raise RuntimeError("Gmail needs authorization. Run copilot.py --reauth-gmail interactively.")
            # Check for client_secret.json file first
            if client_secret_path.exists():
                flow = InstalledAppFlow.from_client_secrets_file(str(client_secret_path), SCOPES)
            else:
                # Build client config from environment variables
                client_id = os.getenv("GOOGLE_CLIENT_ID")
                client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
                
                if not client_id or not client_secret or "YOUR_" in client_secret:
                    raise ValueError(
                        f"Gmail auth failed: Please download 'client_secret.json' from your Google Cloud Console "
                        f"and place it at '{client_secret_path}', or specify GOOGLE_CLIENT_SECRET in your .env file."
                    )
                
                client_config = {
                    "installed": {
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token",
                        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                        "redirect_uris": ["http://localhost"]
                    }
                }
                flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
                
            creds = flow.run_local_server(port=0)
            
        with open(token_path, 'w') as token:
            token.write(creds.to_json())
            
    return build('gmail', 'v1', credentials=creds)

def verify_gmail_access() -> dict:
    """
    Actively checks and validates Gmail API connectivity, token validity, and account health.
    Returns:
      {
        'authenticated': bool,
        'email_address': str,
        'token_valid': bool,
        'error': Optional[str]
      }
    """
    token_path = BASE_DIR / "token.json"
    client_secret_path = BASE_DIR / "client_secret.json"

    if not token_path.exists() and not client_secret_path.exists() and not os.getenv("GOOGLE_CLIENT_SECRET"):
        return {
            'authenticated': False,
            'email_address': '',
            'token_valid': False,
            'error': 'Missing credentials. Please place client_secret.json in Emails/ or set GOOGLE_CLIENT_SECRET in .env'
        }

    try:
        service = get_gmail_service()
        profile = service.users().getProfile(userId='me').execute()
        email_addr = profile.get('emailAddress', '')
        return {
            'authenticated': True,
            'email_address': email_addr,
            'token_valid': True,
            'error': None
        }
    except Exception as e:
        return {
            'authenticated': False,
            'email_address': '',
            'token_valid': False,
            'error': str(e)
        }

def reauthorize_gmail() -> dict:
    """Forces re-authentication flow with updated SCOPES ('gmail.modify')."""
    token_path = BASE_DIR / "token.json"
    if token_path.exists():
        token_path.unlink()
    print("🌐 Launching Google OAuth browser authorization with 'gmail.modify' scope...")
    service = get_gmail_service()
    health = verify_gmail_access()
    if health.get("authenticated"):
        print(f"✅ Successfully authorized Gmail as: {health.get('email_address')} with full thread & reply inspection permissions!")
    return health

def build_email_message(
    to_email: str,
    subject: str,
    body_text: str,
    attachment_path: Optional[str] = None,
    in_reply_to: Optional[str] = None
) -> EmailMessage:
    """
    Constructs an EmailMessage with:
      - Plain text body
      - Rich HTML alternative with clickable URLs
      - RFC 2822 In-Reply-To / References headers
      - Clean attachment naming (always 'Daniel_Suh_Resume.pdf' for resumes)
    """
    import html
    message = EmailMessage()
    message.set_content(body_text)
    message['To'] = to_email
    message['Subject'] = subject

    if in_reply_to:
        message['In-Reply-To'] = in_reply_to
        message['References'] = in_reply_to

    # Add rich HTML alternative
    escaped_text = html.escape(body_text)
    html_body = re.sub(
        r'(https?://[^\s<]+|linkedin\.com/[^\s<]+|github\.com/[^\s<]+)',
        lambda m: f'<a href="{"https://" if not m.group(0).startswith("http") else ""}{m.group(0)}" target="_blank">{m.group(0)}</a>',
        escaped_text
    )
    html_body = html_body.replace('\n', '<br>\n')
    message.add_alternative(
        f"<div style='font-family: -apple-system, BlinkMacSystemFont, \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif; font-size: 14px; line-height: 1.5; color: #111;'>{html_body}</div>",
        subtype='html'
    )

    if attachment_path and not os.path.isfile(attachment_path):
        raise FileNotFoundError(f"Resume attachment missing: {attachment_path}")
    if attachment_path:
        ctype, encoding = mimetypes.guess_type(attachment_path)
        if ctype is None or encoding is not None:
            ctype = 'application/octet-stream'
        maintype, subtype = ctype.split('/', 1)
        with open(attachment_path, 'rb') as fp:
            file_data = fp.read()
            raw_filename = os.path.basename(attachment_path)
            display_filename = "Daniel_Suh_Resume.pdf" if "resume" in raw_filename.lower() else raw_filename
            message.add_attachment(file_data, maintype=maintype, subtype=subtype, filename=display_filename)
        print(f"Attached file: {display_filename}")

    return message

def create_gmail_draft(
    to_email: str, subject: str, body_text: str,
    attachment_path: Optional[str] = None, thread_id: Optional[str] = None,
    in_reply_to: Optional[str] = None, idempotency_key: Optional[str] = None
) -> Optional[dict]:
    """Create at most one draft per account/operation; uncertain results halt retries."""
    from email_validator import validate_email_syntax
    valid, reason = validate_email_syntax(to_email)
    if not valid:
        raise ValueError(f'Invalid draft recipient: {reason}')
    message = build_email_message(to_email, subject, body_text, attachment_path, in_reply_to)
    service = get_gmail_service()
    account = service.users().getProfile(userId='me').execute()['emailAddress'].lower()
    # Explicit operation keys are stable even when AI wording or PDF bytes change.
    operation = idempotency_key or json.dumps([to_email.lower(), subject, thread_id or '', in_reply_to or ''])
    key = hashlib.sha256(f'{account}:{operation}'.encode()).hexdigest()
    # Gmail replaces its resource ID on send. Correlate only preserved headers
    # observed on a SENT message; missing headers leave the outcome unconfirmed.
    rfc_id = f'<applypilot.{key}@{account.split("@")[-1]}>'
    message['Message-ID'] = rfc_id
    message['X-ApplyPilot-Operation'] = key
    with store_lock(DRAFT_REGISTRY):
        registry = read_json(DRAFT_REGISTRY, {})
        if not isinstance(registry, dict):
            raise RuntimeError('Draft registry is invalid; refusing to create another draft.')
        previous = registry.get(key)
        if previous:
            if previous.get('state') != 'created':
                raise RuntimeError(f"Draft result is uncertain for {to_email}. Inspect Gmail and reconcile operation {key} before retrying.")
            print('Reusing the existing Gmail draft record; review its current state in Gmail.')
            return dict(previous['draft'], reused=True, review_snapshot=previous.get('review_snapshot'))
        snapshot = {'recipient': to_email, 'subject': subject, 'body': body_text,
                    'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    'attachment_path': str(attachment_path) if attachment_path else None,
                    'attachment_sha256': hashlib.sha256(Path(attachment_path).read_bytes()).hexdigest() if attachment_path else None}
        registry[key] = {'state': 'pending', 'recipient': to_email, 'subject': subject,
                         'operation': operation, 'review_snapshot': snapshot}
        atomic_write(DRAFT_REGISTRY, json.dumps(registry, indent=2))
        request = {'message': {'raw': base64.urlsafe_b64encode(message.as_bytes()).decode()}}
        if thread_id:
            request['message']['threadId'] = thread_id
        # Pending stays on disk if the response is lost: retrying cannot duplicate outreach.
        draft = service.users().drafts().create(userId='me', body=request).execute()
        draft = dict(draft, rfc_message_id=rfc_id, operation_id=key)
        registry[key].update(state='created', draft=draft)
        atomic_write(DRAFT_REGISTRY, json.dumps(registry, indent=2))
        print(f"Draft created. Review and send in Gmail. Draft ID: {draft['id']}")
        return dict(draft, review_snapshot=snapshot)


def create_scheduled_send(to_email, subject, body_text, send_at_datetime,
                          attachment_path=None, thread_id=None, in_reply_to=None,
                          idempotency_key=None):
    """Compatibility wrapper: creates a draft, never schedules or sends it."""
    draft = create_gmail_draft(to_email, subject, body_text, attachment_path,
                              thread_id, in_reply_to, idempotency_key)
    return dict(draft, threadId=draft.get('message', {}).get('threadId'))


def send_gmail_message(*args, **kwargs):
    """Legacy interface deliberately disabled under the draft-only policy."""
    raise RuntimeError('Draft-only policy: review and send messages yourself in Gmail.')


def check_thread_for_replies(thread_id: str, recipient_email: str = "", not_before: Optional[str] = None) -> dict:
    """Use SENT labels and exact sender addresses; errors never imply a send."""
    result = {'has_reply': False, 'touch1_sent': False, 'sent_at': None,
              'message_count': 0, 'first_message_id': None, 'error': None,
              'status': 'NO_THREAD_ID'}
    if not thread_id:
        return result
    try:
        service = get_gmail_service()
        messages = service.users().threads().get(userId='me', id=thread_id).execute().get('messages', [])
        result['message_count'] = len(messages)
        expected = recipient_email.strip().casefold()
        minimum_time = datetime.datetime.fromisoformat(not_before).timestamp() * 1000 if not_before else 0
        sent = []
        for message in messages:
            labels = message.get('labelIds', [])
            headers = {h['name'].lower(): h['value'] for h in message.get('payload', {}).get('headers', [])}
            recipients = {address.casefold() for _, address in getaddresses([headers.get('to', ''), headers.get('cc', '')])}
            if 'SENT' in labels and 'DRAFT' not in labels and int(message.get('internalDate', 0)) >= minimum_time and (not expected or expected in recipients):
                sent.append(message)
        sent.sort(key=lambda message: int(message.get('internalDate', 0)))
        if not sent:
            result['status'] = 'DRAFT_NOT_SENT'
            return result
        first = sent[0]
        timestamp = int(first['internalDate'])
        if timestamp <= 0:
            raise ValueError('Sent message has no valid Gmail timestamp')
        result['touch1_sent'] = True
        result['sent_at'] = datetime.datetime.fromtimestamp(timestamp / 1000, datetime.timezone.utc).isoformat()
        headers = {h['name'].lower(): h['value'] for h in first.get('payload', {}).get('headers', [])}
        result['first_message_id'] = headers.get('message-id')
        result['subject'] = headers.get('subject')
        result['sent_messages'] = [{'id': message.get('id'),
            'rfc_message_id': next((h['value'].strip() for h in message.get('payload', {}).get('headers', []) if h['name'].lower() == 'message-id'), None),
            'operation_id': next((h['value'].strip() for h in message.get('payload', {}).get('headers', []) if h['name'].lower() == 'x-applypilot-operation'), None),
            'sent_at': datetime.datetime.fromtimestamp(int(message['internalDate']) / 1000, datetime.timezone.utc).isoformat()}
            for message in sent]
        expected = recipient_email.strip().casefold()
        for msg in messages:
            labels = msg.get('labelIds', [])
            if 'SENT' in labels or 'DRAFT' in labels or int(msg.get('internalDate', 0)) < timestamp:
                continue
            headers = {h['name'].lower(): h['value'] for h in msg.get('payload', {}).get('headers', [])}
            senders = {address.casefold() for _, address in getaddresses([headers.get('from', '')])}
            if expected and expected in senders:
                result.update(has_reply=True, sender=headers.get('from'), snippet=msg.get('snippet', ''))
                break
        result['status'] = 'REPLIED_TERMINATE' if result['has_reply'] else 'NO_REPLY_ACTIVE'
        return result
    except Exception as exc:
        result.update(touch1_sent=False, sent_at=None, error=str(exc), status=f'ERROR: {exc}')
        return result
