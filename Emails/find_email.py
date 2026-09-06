import sys
import os
import requests
from pathlib import Path
from dotenv import load_dotenv
from agent import get_company_domain

BASE_DIR = Path(__file__).resolve().parent

load_dotenv(dotenv_path=BASE_DIR / ".env")
if not os.getenv("HUNTER_API_KEY") and (BASE_DIR.parent / ".env").exists():
    load_dotenv(dotenv_path=BASE_DIR.parent / ".env")

HUNTER_API_KEY = os.getenv("HUNTER_API_KEY")

def main():
    if len(sys.argv) < 4:
        print("Usage: python find_email.py <first_name> <last_name> <company_name>")
        sys.exit(1)
        
    first_name = sys.argv[1]
    last_name = sys.argv[2]
    company_name = sys.argv[3]
    
    if not HUNTER_API_KEY or "YOUR_" in HUNTER_API_KEY:
        print("Error: HUNTER_API_KEY not configured in .env")
        sys.exit(1)
        
    domain = get_company_domain(company_name)
    url = "https://api.hunter.io/v2/email-finder"
    params = {
        "domain": domain,
        "first_name": first_name,
        "last_name": last_name,
        "api_key": HUNTER_API_KEY
    }
    
    try:
        response = requests.get(url, params=params, timeout=15)
        if response.status_code == 200:
            data = response.json()
            email = data.get("data", {}).get("email")
            score = data.get("data", {}).get("score")
            if email:
                print(f"EMAIL_FOUND:{email}:{score}")
            else:
                print(f"EMAIL_NOT_FOUND: Could not find email for {first_name} {last_name} at {domain}")
        elif response.status_code == 401:
            print("ERROR: Hunter.io returned status 401 (Unauthorized: Invalid API key)")
        elif response.status_code == 402:
            print("ERROR: Hunter.io returned status 402 (Payment Required: Out of credits)")
        elif response.status_code == 429:
            print("ERROR: Hunter.io returned status 429 (Rate Limit Exceeded)")
        else:
            print(f"ERROR: Hunter.io returned status {response.status_code}: {response.text}")
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    main()

