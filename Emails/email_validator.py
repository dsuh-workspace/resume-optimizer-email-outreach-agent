#!/usr/bin/env python3
"""
Email Deliverability & Syntax Validation Engine
Author: Daniel Suh & Antigravity

Provides multi-layer validation for emails discovered via Hunter.io, AI pattern synthesis,
or user inputs:
  1. RFC 5322 Syntax & Format Checking (local-part, domain labels, TLD length, dot rules)
  2. Placeholder & Disposable Email Screening (example.com, test.com, tempmail, dummy names)
  3. Optional DNS Host Resolution (verifies domain exists on internet)
  4. Hunter.io Email Verifier API Integration (live mailbox deliverability and bounce checking)
"""

import os
import re
import socket
from typing import Tuple, Optional, Dict, Any
import requests

# Strict RFC 5322-compliant regex for local part (disallows consecutive dots, leading/trailing dots)
LOCAL_PART_REGEX = re.compile(r"^[a-zA-Z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[a-zA-Z0-9!#$%&'*+/=?^_`{|}~-]+)*$")

# Domain label regex (1-63 chars per label, alphanumeric, hyphens not at start/end)
DOMAIN_LABEL_REGEX = re.compile(r"^[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$")

# Known placeholder, dummy, or blacklisted domains that must never be used in outreach
DISPOSABLE_OR_DUMMY_DOMAINS = {
    "example.com", "example.org", "example.net",
    "test.com", "testing.com", "fake.com", "placeholder.com",
    "invalid.com", "localhost", "localdomain",
    "mailinator.com", "10minutemail.com", "tempmail.com",
    "guerrillamail.com", "trashmail.com", "sharklasers.com",
    "yopmail.com", "dispostable.com"
}

# Known placeholder local parts
DUMMY_LOCAL_PARTS = {
    "placeholder", "your-email", "your_email", "yourname",
    "username", "null", "undefined", "none",
    "todo", "fake", "dummy"
}

def clean_email(email: Optional[str]) -> str:
    """Strips whitespace, surrounding angle brackets, and converts to lower case."""
    if not email:
        return ""
    cleaned = email.strip()
    # Remove surrounding angle brackets e.g. <john@domain.com>
    if cleaned.startswith("<") and cleaned.endswith(">"):
        cleaned = cleaned[1:-1].strip()
    return cleaned.lower()

def validate_email_syntax(email: str) -> Tuple[bool, str]:
    """
    Validates the syntax and structure of an email address based on RFC 5322.
    Returns:
      (is_valid, reason_or_cleaned_email)
    """
    if not email or not isinstance(email, str):
        return False, "Email is empty or not a string"

    email = clean_email(email)

    # Check overall length: RFC specifies max 254 characters
    if len(email) < 5 or len(email) > 254:
        return False, f"Email length ({len(email)}) is outside RFC limits (5-254 characters)"

    # Exactly one @ symbol separating local part and domain
    parts = email.split("@")
    if len(parts) != 2:
        return False, f"Email must contain exactly one '@' symbol (found {len(parts)-1})"

    local_part, domain = parts[0], parts[1]

    # Validate local part length: max 64 characters
    if not local_part or len(local_part) > 64:
        return False, f"Local part length ({len(local_part)}) is outside valid range (1-64 characters)"

    # Validate local part characters and format
    if not LOCAL_PART_REGEX.match(local_part):
        return False, f"Local part '{local_part}' contains invalid characters or consecutive/leading/trailing dots"

    # Validate domain length: max 253 characters
    if not domain or len(domain) > 253:
        return False, f"Domain length ({len(domain)}) is outside valid range (1-253 characters)"

    # Domain must contain at least one dot separating name and TLD
    domain_labels = domain.split(".")
    if len(domain_labels) < 2:
        return False, f"Domain '{domain}' must have at least one period separating the name and TLD"

    # Validate each domain label
    for label in domain_labels:
        if not label or not DOMAIN_LABEL_REGEX.match(label):
            return False, f"Domain label '{label}' contains invalid characters, hyphens at boundaries, or exceeds 63 characters"

    # Validate top-level domain (TLD): must be at least 2 alphabetic characters
    tld = domain_labels[-1]
    if not tld.isalpha() or len(tld) < 2:
        return False, f"Top-level domain '{tld}' must be at least 2 alphabetic characters"

    return True, "Valid syntax"

def is_placeholder_or_dummy_email(email: str, target_company: str = "") -> Tuple[bool, str]:
    """
    Checks whether an email address is a dummy, test, or generic placeholder.
    """
    email = clean_email(email)
    if not email or "@" not in email:
        return True, "Invalid email structure"

    local_part, domain = email.split("@", 1)

    if domain in DISPOSABLE_OR_DUMMY_DOMAINS:
        return True, f"Domain '{domain}' is a known dummy or disposable domain"

    if local_part in DUMMY_LOCAL_PARTS:
        return True, f"Local part '{local_part}' is a placeholder"

    # Disallow generic fallback 'company.com' if target company is not literally 'Company'
    if domain == "company.com" and target_company and target_company.strip().lower() not in ["company", "the company"]:
        return True, "Generic 'company.com' domain placeholder detected"

    return False, "Not a placeholder"

def check_domain_dns(domain: str) -> Tuple[bool, str]:
    """
    Verifies that the email's domain actually exists and has an active DNS host.
    """
    try:
        # Check standard host address resolution
        socket.getaddrinfo(domain, 25, socket.AF_INET, socket.SOCK_STREAM)
        return True, f"Domain '{domain}' successfully resolved via DNS"
    except socket.gaierror:
        # Try fallback port 80/443
        try:
            socket.gethostbyname(domain)
            return True, f"Domain '{domain}' resolved via gethostbyname"
        except Exception as e:
            return False, f"Domain '{domain}' failed DNS host resolution: {e}"
    except Exception as e:
        return False, f"DNS check error for '{domain}': {e}"

def verify_email_with_hunter(email: str, api_key: Optional[str] = None) -> Dict[str, Any]:
    """
    Calls Hunter.io Email Verifier API (v2/email-verifier) to check live deliverability and bounce risk.
    """
    key = api_key or os.getenv("HUNTER_API_KEY")
    if not key or "YOUR_" in key:
        return {
            "checked": False,
            "is_valid": False,  # Unverified mailboxes cannot be accepted
            "reason": "Hunter.io API key not configured or is placeholder",
            "score": None,
            "status": "unverified",
            "result": "unknown"
        }

    email = clean_email(email)
    url = "https://api.hunter.io/v2/email-verifier"
    params = {"email": email, "api_key": key}

    try:
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json().get("data", {})
            status = data.get("status", "unknown")  # valid, invalid, accept_all, webmail, disposable, unknown
            result = data.get("result", "unknown")  # deliverable, undeliverable, risky, unknown
            score = data.get("score", 0)

            # Hunter marks explicitly invalid/undeliverable addresses
            is_valid = status == "valid" and result == "deliverable" and score >= 50
            reason = "Hunter.io marked email as deliverable/valid" if is_valid else f"Hunter.io flagged email as {status} / {result}"

            return {
                "checked": True,
                "is_valid": is_valid,
                "status": status,
                "result": result,
                "score": score,
                "reason": reason,
                "raw": data
            }
        elif resp.status_code in [401, 402, 429]:
            return {
                "checked": False,
                "is_valid": False,
                "reason": f"Hunter.io API rate limit or credit exhaustion ({resp.status_code})",
                "score": None,
                "status": "rate_limited",
                "result": "unknown"
            }
        else:
            return {
                "checked": False,
                "is_valid": False,
                "reason": f"Hunter.io API error ({resp.status_code}): {resp.text[:100]}",
                "score": None,
                "status": "error",
                "result": "unknown"
            }
    except Exception as e:
        return {
            "checked": False,
            "is_valid": False,
            "reason": f"Hunter.io verifier request exception: {e}",
            "score": None,
            "status": "error",
            "result": "unknown"
        }

def validate_email(
    email: str,
    check_dns: bool = False,
    hunter_api_key: Optional[str] = None,
    target_company: str = "",
    allow_placeholders: bool = False
) -> Tuple[bool, str]:
    """
    Comprehensive multi-stage email validation:
      1. RFC 5322 Syntax & Format
      2. Dummy & Placeholder screening
      3. Hunter.io deliverability verification (if API key available)
      4. DNS host check (optional)
    """
    if not email:
        return False, "Email address is missing or empty"

    cleaned = clean_email(email)

    # 1. Syntax check
    valid_syntax, syntax_msg = validate_email_syntax(cleaned)
    if not valid_syntax:
        return False, f"Syntax Error: {syntax_msg}"

    # 2. Placeholder check
    if not allow_placeholders:
        is_dummy, dummy_msg = is_placeholder_or_dummy_email(cleaned, target_company=target_company)
        if is_dummy:
            return False, f"Placeholder Detected: {dummy_msg}"

    # 3. Hunter.io Email Verifier API (only when key is explicitly provided)
    if hunter_api_key:
        hunter_res = verify_email_with_hunter(cleaned, api_key=hunter_api_key)
        if not hunter_res.get("checked") or not hunter_res.get("is_valid") or (hunter_res.get("score") or 0) < 50:
            return False, f"Hunter.io Deliverability Check Failed: {hunter_res.get('reason')} (Score: {hunter_res.get('score')}%)"

    # 4. Optional DNS check
    if check_dns:
        domain = cleaned.split("@")[1]
        dns_ok, dns_msg = check_domain_dns(domain)
        if not dns_ok:
            return False, f"DNS Verification Failed: {dns_msg}"

    return True, "Email is valid"

def is_valid_email(
    email: Optional[str],
    check_dns: bool = False,
    hunter_api_key: Optional[str] = None,
    target_company: str = "",
    allow_placeholders: bool = False
) -> bool:
    """Convenience boolean helper to verify if an email is deliverable and valid."""
    if not email:
        return False
    valid, _ = validate_email(
        email,
        check_dns=check_dns,
        hunter_api_key=hunter_api_key,
        target_company=target_company,
        allow_placeholders=allow_placeholders
    )
    return valid

def sanitize_and_validate_email(
    email: Optional[str],
    check_dns: bool = False,
    hunter_api_key: Optional[str] = None,
    target_company: str = "",
    allow_placeholders: bool = False
) -> Tuple[Optional[str], Optional[str]]:
    """
    Sanitizes email (trims, lowers) and validates it.
    Returns:
      (cleaned_email, None) if valid
      (None, error_message) if invalid
    """
    if not email:
        return None, "Email address is required"
    cleaned = clean_email(email)
    valid, reason = validate_email(
        cleaned,
        check_dns=check_dns,
        hunter_api_key=hunter_api_key,
        target_company=target_company,
        allow_placeholders=allow_placeholders
    )
    if valid:
        return cleaned, None
    return None, reason


def contact_verification(email: str, user_provided: bool = False, target_company: str = '') -> dict:
    """Return explicit provenance; syntax and DNS never count as mailbox proof."""
    from datetime import datetime, timezone
    cleaned = clean_email(email)
    valid, reason = validate_email(cleaned, target_company=target_company)
    if not valid:
        raise ValueError(reason)
    checked_at = datetime.now(timezone.utc).isoformat()
    if user_provided:
        return {'email': cleaned, 'source': 'user-provided', 'status': 'user-provided; mailbox not independently verified', 'score': None, 'checked_at': checked_at}
    verification = verify_email_with_hunter(cleaned)
    if not verification.get('checked') or not verification.get('is_valid') or (verification.get('score') or 0) < 50:
        raise ValueError(f"Mailbox verification required for {cleaned}: {verification.get('reason')}")
    return {'email': cleaned, 'source': 'Hunter.io email-verifier', 'status': verification['status'], 'score': verification['score'], 'checked_at': checked_at}
