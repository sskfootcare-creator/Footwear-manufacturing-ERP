"""
CLI Helper to set up Gmail REST API OAuth 2.0 Credentials for SSK Footcare ERP.

Run this script on your machine to authorize your Google / Gmail account:
    python backend/scripts/setup_gmail_api.py

It will:
1. Load credentials from 'client_secret.json' (or prompt for Client ID & Secret).
2. Open your browser so you can grant permission to send emails from your @gmail.com address.
3. Save 'token.json' with your permanent refresh_token (and optionally save to MongoDB).
4. Verify connection via standard HTTPS (Port 443) which bypasses Render's firewall!
"""

import os
import sys
import json
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
]


def find_client_secret_file():
    candidates = [
        Path.cwd() / "client_secret.json",
        backend_dir / "client_secret.json",
        backend_dir.parent / "client_secret.json",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def main():
    print("=" * 70)
    print("  SSK FOOTCARE ERP — GMAIL REST API OAUTH 2.0 SETUP (PORT 443 HTTPS)")
    print("=" * 70)
    print("This setup allows your ERP to send payment reminders from your exact")
    print("@gmail.com address without getting blocked by cloud firewalls on Render.\n")

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError:
        print("ERROR: Google API packages are missing. Run:")
        print("    pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib")
        sys.exit(1)

    secret_file = find_client_secret_file()
    flow = None

    if secret_file:
        print(f"Found Google credentials file at: {secret_file}")
        try:
            flow = InstalledAppFlow.from_client_secrets_file(str(secret_file), SCOPES)
        except Exception as e:
            print(f"Failed to read {secret_file}: {e}")

    if not flow:
        print("\n'client_secret.json' was not found automatically.")
        print("Enter your credentials from Google Cloud Console (APIs & Services > Credentials):")
        client_id = input("Client ID: ").strip()
        client_secret = input("Client Secret: ").strip()

        if not client_id or not client_secret:
            print("Both Client ID and Client Secret are required. Exiting.")
            sys.exit(1)

        client_config = {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost", "http://127.0.0.1"],
            }
        }
        flow = InstalledAppFlow.from_client_config(client_config, SCOPES)

    print("\nLaunching browser for Google Authentication...")
    print("Please log into your company Gmail account and grant permission.")

    try:
        creds = flow.run_local_server(port=0, prompt="consent")
    except Exception as e:
        print(f"\nLocal server authorization failed ({e}). Trying console code...")
        try:
            creds = flow.run_console()
        except Exception as e2:
            print(f"Authorization failed: {e2}")
            sys.exit(1)

    # Verify credentials with Gmail API profile check
    print("\nVerifying connection over HTTPS Port 443 with Google...")
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    profile = service.users().getProfile(userId="me").execute()
    email_address = profile.get("emailAddress", "unknown")
    print(f"SUCCESS! Authenticated as: {email_address}")

    # Save token.json
    token_data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes,
        "email": email_address,
    }

    token_dest = backend_dir / "token.json"
    with open(token_dest, "w", encoding="utf-8") as f:
        json.dump(token_data, f, indent=2)

    print(f"\nCredentials saved to: {token_dest}")
    print("\n" + "-" * 70)
    print("CONFIG DETAILS (Copy & paste into ERP Settings or Render Env Vars):")
    print("-" * 70)
    print(f"Gmail User / Sender Email : {email_address}")
    print(f"Client ID                 : {creds.client_id}")
    print(f"Client Secret             : {creds.client_secret}")
    print(f"Refresh Token             : {creds.refresh_token}")
    print("-" * 70)
    print("In Render Dashboard > Environment, you can add:")
    print(f"  GMAIL_API_CLIENT_ID={creds.client_id}")
    print(f"  GMAIL_API_CLIENT_SECRET={creds.client_secret}")
    print(f"  GMAIL_API_REFRESH_TOKEN={creds.refresh_token}")
    print(f"  GMAIL_USER={email_address}")
    print("-" * 70)
    print("\nAll done! Your ERP can now send emails via Gmail REST API on Port 443.")


if __name__ == "__main__":
    main()
