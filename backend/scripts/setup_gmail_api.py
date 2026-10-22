"""
CLI Helper to set up Gmail REST API OAuth 2.0 Credentials for SSK Footcare ERP.

Run this script on your local computer to authorize your Google / Gmail account:
    python backend/scripts/setup_gmail_api.py

Workflow:
1. Loads credentials from 'client_secret.json'.
2. Spawns a temporary local web server (port=0) and opens your browser.
3. Automatically completes the OAuth flow upon your consent.
4. Saves permanent credentials to 'token.json' and updates MongoDB (if available).
5. Verifies the connection over HTTPS Port 443 with Google.
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


def ensure_environment():
    """If executed with system Python where google packages aren't installed, auto-switch to project venv."""
    try:
        import google_auth_oauthlib  # noqa: F401
        import googleapiclient       # noqa: F401
        return
    except ImportError:
        pass

    import subprocess
    candidates = [
        backend_dir / ".venv" / "Scripts" / "python.exe",
        backend_dir.parent / ".venv" / "Scripts" / "python.exe",
        backend_dir / ".venv" / "bin" / "python",
        backend_dir.parent / ".venv" / "bin" / "python",
    ]
    for py in candidates:
        if py.exists():
            print(f"Detected project virtual environment at: {py}")
            print("Switching execution to project venv Python automatically...\n")
            res = subprocess.run([str(py), str(Path(__file__).resolve())] + sys.argv[1:])
            sys.exit(res.returncode)


def main():
    ensure_environment()

    print("=" * 70)
    print("  SSK FOOTCARE ERP — GMAIL REST API OAUTH 2.0 SETUP (PORT 443 HTTPS)")
    print("=" * 70)
    print("This script runs a temporary local web server to authorize your Gmail")
    print("account over standard HTTPS (Port 443), bypassing all cloud firewalls.\n")

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError:
        print("ERROR: Google API packages are missing in this environment.")
        print("Run using the project virtualenv:")
        print(r"    .\backend\.venv\Scripts\python.exe backend\scripts\setup_gmail_api.py")
        print("Or install the packages:")
        print("    pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib")
        sys.exit(1)

    secret_file = find_client_secret_file()
    flow = None

    if secret_file:
        print(f"Found Google credentials file at: {secret_file}")
        try:
            with open(secret_file, "r", encoding="utf-8") as f:
                raw_data = json.load(f)

            # Normalize client config so run_local_server works regardless of web or installed type
            sub = raw_data.get("installed") or raw_data.get("web") or raw_data
            c_id = sub.get("client_id")
            c_sec = sub.get("client_secret")

            if c_id and c_sec:
                client_config = {
                    "installed": {
                        "client_id": c_id,
                        "client_secret": c_sec,
                        "auth_uri": sub.get("auth_uri", "https://accounts.google.com/o/oauth2/auth"),
                        "token_uri": sub.get("token_uri", "https://oauth2.googleapis.com/token"),
                        "redirect_uris": ["http://localhost", "http://127.0.0.1"],
                    }
                }
                flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
            else:
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

    print("\nStarting local web server and launching your browser for Google Authentication...")
    print("Please log into your company Gmail account and grant permission.\n")

    # Local web server method (port=0 lets the OS pick an open port dynamically)
    creds = flow.run_local_server(port=0)

    # Verify credentials with Gmail API profile check
    print("\nVerifying connection over HTTPS Port 443 with Google...")
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    profile = service.users().getProfile(userId="me").execute()
    email_address = profile.get("emailAddress", "unknown")
    print(f"SUCCESS! Authenticated as: {email_address}")

    # Build token payload
    token_data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes,
        "email": email_address,
    }

    # Save token.json to both backend/ and project root
    for target in [backend_dir / "token.json", Path.cwd() / "token.json"]:
        try:
            with open(target, "w", encoding="utf-8") as f:
                json.dump(token_data, f, indent=2)
            print(f"Credentials saved to: {target}")
        except Exception as e:
            print(f"Could not write {target}: {e}")

    # Optionally update MongoDB email_config if MONGO_URI is set
    mongo_uri = os.environ.get("MONGO_URI") or os.environ.get("MONGODB_URI") or os.environ.get("MONGODB_URL")
    if not mongo_uri:
        # Check backend/.env
        env_path = backend_dir / ".env"
        if env_path.exists():
            with open(env_path, "r", encoding="utf-8") as ef:
                for line in ef:
                    if line.startswith("MONGO_URI=") or line.startswith("MONGODB_URI=") or line.startswith("MONGODB_URL="):
                        mongo_uri = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break

    if mongo_uri:
        try:
            from pymongo import MongoClient
            import datetime
            client = MongoClient(mongo_uri)
            db_name = os.environ.get("DB_NAME", "ssk_erp")
            db = client[db_name]
            db.settings.update_one(
                {"_id": "email_config"},
                {
                    "$set": {
                        "provider": "gmail_api",
                        "gmail_user": email_address,
                        "gmail_client_id": creds.client_id,
                        "gmail_client_secret": creds.client_secret,
                        "gmail_refresh_token": creds.refresh_token,
                        "updated_at": datetime.datetime.utcnow().isoformat(),
                        "updated_by": "setup_gmail_api.py",
                    }
                },
                upsert=True,
            )
            print("Successfully updated email_config in MongoDB database!")
        except Exception as me:
            print(f"Notice: MongoDB direct update skipped ({me}).")

    print("\n" + "=" * 70)
    print("CONFIG DETAILS (For Render Environment Variables or ERP Settings):")
    print("=" * 70)
    print(f"GMAIL_USER              = {email_address}")
    print(f"GMAIL_API_CLIENT_ID     = {creds.client_id}")
    print(f"GMAIL_API_CLIENT_SECRET = {creds.client_secret}")
    print(f"GMAIL_API_REFRESH_TOKEN = {creds.refresh_token}")
    print("=" * 70)
    print("Deployment Note:")
    print("1. Upload 'token.json' alongside your backend code, OR")
    print("2. In your Render Dashboard > Environment Variables, set:")
    print(f"   GMAIL_API_REFRESH_TOKEN={creds.refresh_token}")
    print("=" * 70)
    print("\nAll done! Your ERP can now send emails silently via Gmail REST API on Port 443.")


if __name__ == "__main__":
    main()
