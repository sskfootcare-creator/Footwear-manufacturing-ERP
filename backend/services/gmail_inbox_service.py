"""Gmail Inbox Reader Service for SSK Footcare ERP.

Connects to Gmail exclusively via Google REST API over HTTPS (Port 443) using OAuth 2.0 credentials
(from email_config in MongoDB, token.json, client_secret.json, or environment variables).
Bypasses all outbound SMTP (465/587) and IMAP (993) firewall blocks.

Fetches unread/recent emails related to Goods Receipt Notes (GRN) and Payment Alerts.
"""

import os
import json
import base64
from email.header import decode_header
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("gmail_inbox_service")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def decode_mime_words(raw_header: Optional[str]) -> str:
    """Decode RFC 2047 MIME-encoded email headers into unicode string."""
    if not raw_header:
        return ""
    try:
        decoded_fragments = decode_header(raw_header)
        result = []
        for frag, encoding in decoded_fragments:
            if isinstance(frag, bytes):
                encoding = encoding or "utf-8"
                try:
                    result.append(frag.decode(encoding, errors="replace"))
                except Exception:
                    result.append(frag.decode("latin-1", errors="replace"))
            else:
                result.append(str(frag))
        return "".join(result).strip()
    except Exception:
        return str(raw_header).strip()


def resolve_gmail_oauth_credentials(config: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    """Resolve Google OAuth credentials over HTTPS Port 443 from all available local and DB sources."""
    cfg = config or {}
    creds = {
        "client_id": str(cfg.get("gmail_client_id") or "").strip(),
        "client_secret": str(cfg.get("gmail_client_secret") or "").strip(),
        "refresh_token": str(cfg.get("gmail_refresh_token") or "").strip(),
        "user_email": str(cfg.get("gmail_user") or "").strip(),
    }

    # 1. Check token.json files
    for token_path in [
        Path.cwd() / "token.json",
        Path.cwd() / "backend" / "token.json",
        Path(__file__).resolve().parent.parent / "token.json",
    ]:
        if token_path.exists():
            try:
                with open(token_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if data.get("refresh_token") and not creds["refresh_token"]:
                        creds["refresh_token"] = str(data["refresh_token"]).strip()
                    if data.get("client_id") and not creds["client_id"]:
                        creds["client_id"] = str(data["client_id"]).strip()
                    if data.get("client_secret") and not creds["client_secret"]:
                        creds["client_secret"] = str(data["client_secret"]).strip()
                    if data.get("email") and not creds["user_email"]:
                        creds["user_email"] = str(data["email"]).strip()
            except Exception as e:
                log.warning("Could not read token.json at %s: %s", token_path, e)
            break

    # 2. Check client_secret.json files
    for secret_path in [
        Path.cwd() / "client_secret.json",
        Path.cwd() / "backend" / "client_secret.json",
        Path(__file__).resolve().parent.parent / "client_secret.json",
    ]:
        if secret_path.exists():
            try:
                with open(secret_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    sub = data.get("web") or data.get("installed") or data
                    if sub.get("client_id") and not creds["client_id"]:
                        creds["client_id"] = str(sub["client_id"]).strip()
                    if sub.get("client_secret") and not creds["client_secret"]:
                        creds["client_secret"] = str(sub["client_secret"]).strip()
            except Exception as e:
                log.warning("Could not read client_secret.json at %s: %s", secret_path, e)
            break

    # 3. Check environment variables
    env_cid = os.environ.get("GMAIL_API_CLIENT_ID") or os.environ.get("GOOGLE_CLIENT_ID") or ""
    env_sec = os.environ.get("GMAIL_API_CLIENT_SECRET") or os.environ.get("GOOGLE_CLIENT_SECRET") or ""
    env_rt = os.environ.get("GMAIL_API_REFRESH_TOKEN") or os.environ.get("GOOGLE_REFRESH_TOKEN") or ""
    env_usr = os.environ.get("GMAIL_USER") or ""

    if env_cid and not creds["client_id"]:
        creds["client_id"] = env_cid.strip()
    if env_sec and not creds["client_secret"]:
        creds["client_secret"] = env_sec.strip()
    if env_rt and not creds["refresh_token"]:
        creds["refresh_token"] = env_rt.strip()
    if env_usr and not creds["user_email"]:
        creds["user_email"] = env_usr.strip()

    return creds


def get_gmail_service(config: Optional[Dict[str, Any]] = None):
    """Build and return an authorized googleapiclient Gmail service instance over HTTPS (Port 443)."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request as GoogleAuthRequest
    from googleapiclient.discovery import build

    creds_dict = resolve_gmail_oauth_credentials(config)
    client_id = creds_dict["client_id"]
    client_secret = creds_dict["client_secret"]
    refresh_token = creds_dict["refresh_token"]

    if not client_id or not client_secret:
        raise ValueError(
            "Google Cloud OAuth Client ID and Secret are missing. "
            "Please verify client_secret.json or configure GMAIL_API_CLIENT_ID / GMAIL_API_CLIENT_SECRET."
        )

    if not refresh_token:
        raise ValueError(
            "Gmail is not authorized yet over HTTPS Port 443. "
            "Please click 'Connect with Google' in Settings (or run setup_gmail_api.py) to complete authorization."
        )

    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=[
            "https://www.googleapis.com/auth/gmail.send",
            "https://www.googleapis.com/auth/gmail.readonly",
        ],
    )
    creds.refresh(GoogleAuthRequest())
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _extract_body_and_attachments(
    payload: Dict[str, Any], service=None, user_id="me", message_id=""
) -> Tuple[str, List[Dict[str, Any]]]:
    """Recursively parse Gmail message payload to extract plain text/HTML body and attachment metadata."""
    body_parts = []
    attachments = []

    def _walk(part: Dict[str, Any]):
        mime_type = part.get("mimeType", "")
        filename = part.get("filename", "")
        body = part.get("body", {})
        data_b64 = body.get("data")
        att_id = body.get("attachmentId")
        size = body.get("size", 0)

        # Body text
        if mime_type == "text/plain" and data_b64 and not filename:
            try:
                decoded = base64.urlsafe_b64decode(data_b64).decode("utf-8", errors="replace")
                body_parts.append(decoded)
            except Exception:
                pass
        elif mime_type == "text/html" and data_b64 and not filename:
            if not body_parts:
                try:
                    decoded = base64.urlsafe_b64decode(data_b64).decode("utf-8", errors="replace")
                    body_parts.append(decoded)
                except Exception:
                    pass

        # Attachment
        if filename:
            att_info = {
                "filename": filename,
                "mime_type": mime_type,
                "size_bytes": size,
                "attachment_id": att_id,
                "data_bytes": None,
            }
            # If attachment data is embedded inline
            if data_b64:
                try:
                    att_info["data_bytes"] = base64.urlsafe_b64decode(data_b64)
                except Exception:
                    pass
            # Or fetch on demand over HTTPS (Port 443)
            elif service and att_id and message_id and size < 10 * 1024 * 1024:
                try:
                    att_obj = service.users().messages().attachments().get(
                        userId=user_id, messageId=message_id, id=att_id
                    ).execute()
                    if att_obj.get("data"):
                        att_info["data_bytes"] = base64.urlsafe_b64decode(att_obj["data"])
                except Exception as ae:
                    log.warning("Could not download attachment %s for %s over Port 443: %s", filename, message_id, ae)

            attachments.append(att_info)

        # Recurse into nested multipart parts
        for subpart in part.get("parts", []):
            _walk(subpart)

    _walk(payload)
    full_text = "\n\n".join(body_parts).strip()
    return full_text, attachments


async def fetch_recent_emails(
    config: Optional[Dict[str, Any]] = None,
    max_results: int = 30,
    search_query: Optional[str] = None,
    since_date: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Fetch recent emails from Gmail exclusively via Google REST API on Port 443 HTTPS.

    Filters look for:
    - GRN keywords: "GRN", "Goods Receipt", "Delivery Receipt", "Receiving", "Goods Acceptance", "Challan"
    - Payment keywords: "credited", "NEFT", "RTGS", "IMPS", "remittance", "payment advice", "UTR", "payment received"
    """
    service = get_gmail_service(config)

    # Build smart search query
    default_query = (
        '("GRN" OR "Goods Receipt" OR "Delivery Receipt" OR "Receiving" OR "Goods Acceptance" OR "Inspection" OR '
        '"credited" OR "NEFT" OR "RTGS" OR "IMPS" OR "remittance" OR "payment advice" OR "payment received" OR "UTR")'
    )
    q = search_query.strip() if search_query else default_query

    if since_date:
        d_clean = since_date[:10].replace("-", "/")
        q += f" after:{d_clean}"

    log.info("Querying Gmail REST API (Port 443 HTTPS) messages with filter: %s", q)
    response = service.users().messages().list(userId="me", q=q, maxResults=max_results).execute()
    messages = response.get("messages", [])

    results = []
    for m in messages:
        mid = m["id"]
        try:
            msg_obj = service.users().messages().get(userId="me", id=mid, format="full").execute()
            payload = msg_obj.get("payload", {})
            headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}

            subject = decode_mime_words(headers.get("subject", ""))
            from_header = decode_mime_words(headers.get("from", ""))
            to_header = decode_mime_words(headers.get("to", ""))
            date_header = headers.get("date", "")

            # Parse sender email
            from_email = ""
            sender_name = from_header
            if "<" in from_header and ">" in from_header:
                sender_name = from_header.split("<")[0].strip().strip('"').strip("'")
                from_email = from_header.split("<")[1].split(">")[0].strip()
            else:
                from_email = from_header.strip()

            body_text, attachments = _extract_body_and_attachments(
                payload, service=service, user_id="me", message_id=mid
            )

            # Parse ISO date from internalDate or Date header
            internal_date_ms = int(msg_obj.get("internalDate") or 0)
            if internal_date_ms > 0:
                received_iso = datetime.fromtimestamp(internal_date_ms / 1000.0, tz=timezone.utc).isoformat()
            else:
                received_iso = now_iso()

            results.append({
                "message_id": mid,
                "thread_id": msg_obj.get("threadId", ""),
                "subject": subject,
                "from_header": from_header,
                "from_email": from_email,
                "sender_name": sender_name,
                "to_header": to_header,
                "date_header": date_header,
                "received_iso": received_iso,
                "snippet": msg_obj.get("snippet", ""),
                "body_text": body_text,
                "attachments": attachments,
                "labels": msg_obj.get("labelIds", []),
            })
        except Exception as me:
            log.warning("Could not fetch details for Gmail message %s: %s", mid, me)

    log.info("Retrieved %d relevant messages from Gmail REST API over Port 443", len(results))
    return results
