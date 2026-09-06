import os
import base64
import mimetypes
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

def create_gmail_draft(
    to_email: str,
    subject: str,
    body_text: str,
    attachment_path: Optional[str] = None,
    thread_id: Optional[str] = None,
    in_reply_to: Optional[str] = None
) -> Optional[dict]:
    """Creates a draft email in the user's Gmail account with optional thread chaining and attachments."""
    try:
        service = get_gmail_service()
        message = EmailMessage()
        message.set_content(body_text)
        message['To'] = to_email
        message['Subject'] = subject

        # Threading headers for RFC 2822 standard email clients (Gmail, Outlook, Apple Mail)
        if in_reply_to:
            message['In-Reply-To'] = in_reply_to
            message['References'] = in_reply_to

        if attachment_path and os.path.exists(attachment_path):
            ctype, encoding = mimetypes.guess_type(attachment_path)
            if ctype is None or encoding is not None:
                ctype = 'application/octet-stream'
            maintype, subtype = ctype.split('/', 1)
            with open(attachment_path, 'rb') as fp:
                file_data = fp.read()
                filename = os.path.basename(attachment_path)
                message.add_attachment(file_data, maintype=maintype, subtype=subtype, filename=filename)
            print(f"Attached file: {filename}")

        # Encode message
        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        create_message = {
            'message': {
                'raw': encoded_message
            }
        }
        
        # Link to existing Gmail threadId so Touch 2 appears in the exact same conversation
        if thread_id:
            create_message['message']['threadId'] = thread_id
            print(f"🔗 Chaining draft to conversation thread: {thread_id}")

        draft = service.users().drafts().create(userId="me", body=create_message).execute()
        print(f"Draft created successfully. Draft ID: {draft['id']} (Thread ID: {draft.get('message', {}).get('threadId')})")
        return draft
    except HttpError as error:
        print(f"An error occurred in Gmail API: {error}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred during Gmail drafting: {e}")
        return None

def send_gmail_message(
    to_email: str,
    subject: str,
    body_text: str,
    attachment_path: Optional[str] = None,
    thread_id: Optional[str] = None,
    in_reply_to: Optional[str] = None
) -> Optional[dict]:
    """
    Directly sends an email via Gmail API without user intervention (used for automated Touch 2 follow-ups).
    """
    try:
        service = get_gmail_service()
        message = EmailMessage()
        message.set_content(body_text)
        message['To'] = to_email
        message['Subject'] = subject

        if in_reply_to:
            message['In-Reply-To'] = in_reply_to
            message['References'] = in_reply_to

        if attachment_path and os.path.exists(attachment_path):
            ctype, encoding = mimetypes.guess_type(attachment_path)
            if ctype is None or encoding is not None:
                ctype = 'application/octet-stream'
            maintype, subtype = ctype.split('/', 1)
            with open(attachment_path, 'rb') as fp:
                file_data = fp.read()
                filename = os.path.basename(attachment_path)
                message.add_attachment(file_data, maintype=maintype, subtype=subtype, filename=filename)
            print(f"Attached file: {filename}")

        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        send_body = {'raw': encoded_message}
        if thread_id:
            send_body['threadId'] = thread_id
            print(f"🔗 Sending directly in thread: {thread_id}")

        sent = service.users().messages().send(userId="me", body=send_body).execute()
        print(f"🚀 SUCCESS: Sent Touch 2 follow-up! Message ID: {sent['id']} (Thread ID: {sent.get('threadId')})")
        return sent
    except HttpError as error:
        print(f"An error occurred in Gmail API send: {error}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred during Gmail send: {e}")
        return None

def check_thread_for_replies(thread_id: str, recipient_email: str = "") -> dict:
    """
    Inspects a Gmail conversation thread to determine if:
      1. Touch 1 was actually sent/dispatched.
      2. The recipient has replied.
      3. Retrieves the RFC 2822 Message-ID for thread chaining.
    """
    if not thread_id:
        return {'has_reply': False, 'touch1_sent': False, 'message_count': 0, 'status': 'NO_THREAD_ID', 'snippet': '', 'first_message_id': None}

    try:
        service = get_gmail_service()
        thread = service.users().threads().get(userId='me', id=thread_id).execute()
        messages = thread.get('messages', [])
        
        if not messages:
            return {'has_reply': False, 'touch1_sent': False, 'message_count': 0, 'status': 'DRAFT_NOT_SENT', 'snippet': '', 'first_message_id': None}

        # Check if first message was sent/scheduled
        first_msg = messages[0]
        labels = first_msg.get('labelIds', [])
        is_sent = ('SENT' in labels) or ('SCHEDULED' in labels) or (len(messages) > 1) or ('DRAFT' not in labels)
        
        headers = first_msg.get('payload', {}).get('headers', [])
        first_msg_id = next((h['value'] for h in headers if h['name'].lower() == 'message-id'), None)

        # If thread has more than 1 message, inspect senders for replies
        if len(messages) > 1:
            for msg in messages[1:]:
                payload = msg.get('payload', {})
                msg_headers = payload.get('headers', [])
                from_header = next((h['value'] for h in msg_headers if h['name'].lower() == 'from'), '')
                
                clean_recip = recipient_email.lower().strip()
                if clean_recip and clean_recip in from_header.lower():
                    return {
                        'has_reply': True,
                        'touch1_sent': is_sent,
                        'message_count': len(messages),
                        'status': 'REPLIED_TERMINATE',
                        'snippet': msg.get('snippet', ''),
                        'sender': from_header,
                        'first_message_id': first_msg_id
                    }
            
            return {
                'has_reply': True,
                'touch1_sent': is_sent,
                'message_count': len(messages),
                'status': 'REPLIED_TERMINATE',
                'snippet': messages[-1].get('snippet', ''),
                'sender': 'Recipient',
                'first_message_id': first_msg_id
            }

        return {
            'has_reply': False,
            'touch1_sent': is_sent,
            'message_count': len(messages),
            'status': 'NO_REPLY_ACTIVE',
            'snippet': messages[0].get('snippet', '') if messages else '',
            'first_message_id': first_msg_id
        }

    except Exception as e:
        return {
            'has_reply': False,
            'touch1_sent': True,
            'message_count': 0,
            'status': f'ERROR: {e}',
            'snippet': '',
            'first_message_id': None
        }
