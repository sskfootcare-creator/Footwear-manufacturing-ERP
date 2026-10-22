"""Email service for SSK Footcare ERP.

Handles Gmail SMTP connection, Resend HTTP API fallback (Port 443 HTTPS),
authentication testing, non-blocking asynchronous email dispatch,
and branded Payment Reminders with invoice PDF attachments.
"""

import os
import re
import ssl
import json
import base64
import smtplib
import socket
import logging
import asyncio
from functools import partial
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.utils import formatdate
from typing import Dict, Any, List, Optional, Tuple, Union

log = logging.getLogger("email_service")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean_app_password(pwd: Optional[str]) -> str:
    """Strip spaces often inserted by Google when displaying 16-character App Passwords."""
    if not pwd:
        return ""
    return re.sub(r"\s+", "", pwd.strip())


def _safe_float(val: Any, default: float = 0.0) -> float:
    """Safely cast value to float, handling None, empty string '', invalid strings, and non-numerics without crashing."""
    if val is None:
        return default
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    if not s:
        return default
    try:
        return float(s)
    except (ValueError, TypeError):
        return default


async def get_email_config(db=None) -> Dict[str, Any]:
    """Retrieve email configuration from MongoDB settings, credentials files, or environment variables."""
    cfg = {
        "provider": "smtp",  # "gmail_api" (Port 443 HTTPS), "smtp" (Gmail Port 465/587), or "resend"
        "gmail_user": "",
        "gmail_app_password": "",
        "gmail_client_id": "",
        "gmail_client_secret": "",
        "gmail_refresh_token": "",
        "resend_api_key": "",
        "from_name": "SSK Footcare Manufacturing",
        "reply_to": "",
        "default_cc": "",
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 465,
        "is_configured": False,
        "source": "none",
        "updated_at": None,
    }

    # 1. Check MongoDB settings first if db is provided
    if db is not None:
        try:
            doc = await db.settings.find_one({"_id": "email_config"})
            if doc:
                if doc.get("provider"):
                    cfg["provider"] = str(doc.get("provider", "smtp")).strip()
                if doc.get("gmail_user"):
                    cfg["gmail_user"] = str(doc.get("gmail_user", "")).strip()
                if doc.get("gmail_app_password"):
                    cfg["gmail_app_password"] = clean_app_password(doc.get("gmail_app_password", ""))
                if doc.get("gmail_client_id"):
                    cfg["gmail_client_id"] = str(doc.get("gmail_client_id", "")).strip()
                if doc.get("gmail_client_secret"):
                    cfg["gmail_client_secret"] = str(doc.get("gmail_client_secret", "")).strip()
                if doc.get("gmail_refresh_token"):
                    cfg["gmail_refresh_token"] = str(doc.get("gmail_refresh_token", "")).strip()
                if doc.get("resend_api_key"):
                    cfg["resend_api_key"] = str(doc.get("resend_api_key", "")).strip()
                if doc.get("from_name"):
                    cfg["from_name"] = str(doc.get("from_name", "")).strip()
                if doc.get("reply_to"):
                    cfg["reply_to"] = str(doc.get("reply_to", "")).strip()
                if doc.get("default_cc"):
                    cfg["default_cc"] = str(doc.get("default_cc", "")).strip()
                if doc.get("smtp_host"):
                    cfg["smtp_host"] = str(doc.get("smtp_host", "smtp.gmail.com")).strip()
                if doc.get("smtp_port"):
                    try:
                        cfg["smtp_port"] = int(doc.get("smtp_port", 465))
                    except (ValueError, TypeError):
                        cfg["smtp_port"] = 465
                cfg["updated_at"] = doc.get("updated_at")
                if (
                    (cfg["gmail_client_id"] and cfg["gmail_refresh_token"])
                    or (cfg["gmail_user"] and cfg["gmail_app_password"])
                    or cfg["resend_api_key"]
                ):
                    cfg["is_configured"] = True
                    cfg["source"] = "database"
        except Exception as e:
            log.warning("Could not read email_config from db: %s", e)

    # 2. Check local client_secret.json / token.json credentials files if present
    for secret_path in [
        os.path.join(os.getcwd(), "client_secret.json"),
        os.path.join(os.getcwd(), "backend", "client_secret.json"),
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "client_secret.json"),
    ]:
        if os.path.exists(secret_path):
            try:
                with open(secret_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    c = data.get("installed") or data.get("web") or data
                    if c.get("client_id") and not cfg["gmail_client_id"]:
                        cfg["gmail_client_id"] = str(c.get("client_id")).strip()
                    if c.get("client_secret") and not cfg["gmail_client_secret"]:
                        cfg["gmail_client_secret"] = str(c.get("client_secret")).strip()
            except Exception as e:
                log.warning("Could not read client_secret.json at %s: %s", secret_path, e)
            break

    for token_path in [
        os.path.join(os.getcwd(), "token.json"),
        os.path.join(os.getcwd(), "backend", "token.json"),
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "token.json"),
    ]:
        if os.path.exists(token_path):
            try:
                with open(token_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if data.get("refresh_token") and not cfg["gmail_refresh_token"]:
                        cfg["gmail_refresh_token"] = str(data.get("refresh_token")).strip()
                    if data.get("client_id") and not cfg["gmail_client_id"]:
                        cfg["gmail_client_id"] = str(data.get("client_id")).strip()
                    if data.get("client_secret") and not cfg["gmail_client_secret"]:
                        cfg["gmail_client_secret"] = str(data.get("client_secret")).strip()
            except Exception as e:
                log.warning("Could not read token.json at %s: %s", token_path, e)
            break

    # 3. Fall back to environment variables
    env_client_id = os.environ.get("GMAIL_API_CLIENT_ID") or os.environ.get("GOOGLE_CLIENT_ID") or os.environ.get("GMAIL_CLIENT_ID", "")
    env_client_secret = os.environ.get("GMAIL_API_CLIENT_SECRET") or os.environ.get("GOOGLE_CLIENT_SECRET") or os.environ.get("GMAIL_CLIENT_SECRET", "")
    env_refresh_token = os.environ.get("GMAIL_API_REFRESH_TOKEN") or os.environ.get("GOOGLE_REFRESH_TOKEN") or os.environ.get("GMAIL_REFRESH_TOKEN", "")
    env_resend = os.environ.get("RESEND_API_KEY", "").strip()
    env_user = os.environ.get("GMAIL_USER", "").strip()
    env_pass = clean_app_password(os.environ.get("GMAIL_APP_PASSWORD", ""))
    env_from = os.environ.get("GMAIL_FROM_NAME", "").strip()
    env_reply_to = os.environ.get("GMAIL_REPLY_TO", "").strip()
    env_cc = os.environ.get("GMAIL_DEFAULT_CC", "").strip()

    if env_client_id and not cfg["gmail_client_id"]:
        cfg["gmail_client_id"] = env_client_id.strip()
    if env_client_secret and not cfg["gmail_client_secret"]:
        cfg["gmail_client_secret"] = env_client_secret.strip()
    if env_refresh_token and not cfg["gmail_refresh_token"]:
        cfg["gmail_refresh_token"] = env_refresh_token.strip()

    if env_resend and not cfg["resend_api_key"]:
        cfg["resend_api_key"] = env_resend
    if env_user and not cfg["gmail_user"]:
        cfg["gmail_user"] = env_user
    if env_pass and not cfg["gmail_app_password"]:
        cfg["gmail_app_password"] = env_pass
    if env_from and not cfg["from_name"]:
        cfg["from_name"] = env_from
    if env_reply_to and not cfg["reply_to"]:
        cfg["reply_to"] = env_reply_to
    if env_cc and not cfg["default_cc"]:
        cfg["default_cc"] = env_cc

    if not cfg["is_configured"]:
        if cfg["gmail_client_id"] and cfg["gmail_refresh_token"]:
            cfg["is_configured"] = True
            cfg["provider"] = "gmail_api"
            cfg["source"] = "environment"
        elif cfg["resend_api_key"]:
            cfg["is_configured"] = True
            cfg["provider"] = "resend"
            cfg["source"] = "environment"
        elif cfg["gmail_user"] and cfg["gmail_app_password"]:
            cfg["is_configured"] = True
            cfg["provider"] = "smtp"
            cfg["source"] = "environment"

    # Default provider resolution
    if cfg.get("provider") not in ("gmail_api", "smtp", "resend"):
        if cfg.get("gmail_client_id") and cfg.get("gmail_refresh_token"):
            cfg["provider"] = "gmail_api"
        elif cfg.get("resend_api_key"):
            cfg["provider"] = "resend"
        else:
            cfg["provider"] = "smtp"

    return cfg


def _connect_smtp_ssl_ipv4(host: str, port: int, timeout: int = 15) -> smtplib.SMTP_SSL:
    """Connect specifically using IPv4 (AF_INET) and wrap in SSL."""
    infos = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)
    last_err = None
    for res in infos:
        af, socktype, proto, canonname, sa = res
        s = socket.socket(af, socktype, proto)
        s.settimeout(timeout)
        try:
            s.connect(sa)
            ctx = ssl.create_default_context()
            wrapped = ctx.wrap_socket(s, server_hostname=host)
            smtp = smtplib.SMTP_SSL(timeout=timeout)
            smtp.sock = wrapped
            smtp.file = wrapped.makefile("rb")
            code, msg = smtp.getreply()
            if code != 220:
                smtp.close()
                raise smtplib.SMTPConnectError(code, msg)
            return smtp
        except (OSError, socket.timeout, TimeoutError) as err:
            last_err = err
            try:
                s.close()
            except Exception:
                pass
    raise last_err or OSError(101, f"Network is unreachable (IPv4 {host}:{port})")


def _connect_smtp_starttls_ipv4(host: str, port: int, timeout: int = 15) -> smtplib.SMTP:
    """Connect specifically using IPv4 (AF_INET) and upgrade via STARTTLS."""
    infos = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)
    last_err = None
    for res in infos:
        af, socktype, proto, canonname, sa = res
        s = socket.socket(af, socktype, proto)
        s.settimeout(timeout)
        try:
            s.connect(sa)
            smtp = smtplib.SMTP(timeout=timeout)
            smtp._host = host
            smtp.sock = s
            smtp.file = s.makefile("rb")
            code, msg = smtp.getreply()
            if code != 220:
                smtp.close()
                raise smtplib.SMTPConnectError(code, msg)
            smtp.ehlo()
            smtp.starttls()
            return smtp
        except (OSError, socket.timeout, TimeoutError) as err:
            last_err = err
            try:
                s.close()
            except Exception:
                pass
    raise last_err or OSError(101, f"Network is unreachable (IPv4 {host}:{port})")


def create_smtp_connection(
    smtp_host: str = "smtp.gmail.com",
    smtp_port: int = 465,
    timeout: int = 15,
):
    """
    Establish an SMTP connection with automatic IPv4 fallback if dual-stack DNS
    returns [Errno 101] Network is unreachable or IPv6 connection times out (common in
    Linux/Docker/WSL/cloud VPS environments with incomplete IPv6 routing).
    """
    host = (smtp_host or "smtp.gmail.com").strip()
    port = int(smtp_port or 465)

    if port == 465:
        try:
            return smtplib.SMTP_SSL(host, port, timeout=timeout)
        except (OSError, socket.timeout, TimeoutError) as e:
            log.info(
                "Standard SMTP_SSL connect to %s:%s failed with %s; falling back to direct IPv4 socket",
                host,
                port,
                e,
            )
            return _connect_smtp_ssl_ipv4(host, port, timeout=timeout)
    else:
        try:
            smtp = smtplib.SMTP(host, port, timeout=timeout)
            smtp.ehlo()
            smtp.starttls()
            return smtp
        except (OSError, socket.timeout, TimeoutError) as e:
            log.info(
                "Standard SMTP connect to %s:%s failed with %s; falling back to direct IPv4 socket",
                host,
                port,
                e,
            )
            return _connect_smtp_starttls_ipv4(host, port, timeout=timeout)


def verify_smtp_credentials(
    smtp_host: str,
    smtp_port: int,
    user: str,
    password: str,
    timeout: int = 15,
) -> Tuple[bool, str]:
    """Verify SMTP login credentials against the given host and port."""
    u = (user or "").strip()
    p = clean_app_password(password)
    host = (smtp_host or "smtp.gmail.com").strip()
    port = int(smtp_port or 465)

    if not u or not p:
        return (False, "Both Gmail address and Google App Password are required.")

    try:
        with create_smtp_connection(host, port, timeout=timeout) as smtp:
            smtp.login(u, p)
        return (True, f"Successfully authenticated with {host}:{port} as {u}")
    except smtplib.SMTPAuthenticationError as e:
        log.warning("Gmail SMTP authentication failed: %s", e)
        return (
            False,
            "Gmail authentication failed. Please verify that 2-Step Verification is enabled on your "
            "Google Account and you are using a 16-character Google App Password (not your normal password).",
        )
    except (socket.timeout, TimeoutError):
        log.warning("Gmail SMTP connection timed out connecting to %s:%s", host, port)
        alt_port = 587 if port == 465 else 465
        return (
            False,
            f"Connection to {host}:{port} timed out after {timeout} seconds. "
            f"Port {port} may be blocked by your hosting provider or network firewall. "
            f"If both Port 465 and Port 587 time out, your cloud host (e.g. Render, AWS EC2, DigitalOcean) blocks outbound SMTP ports 25, 465, and 587. "
            f"Solution: Switch to HTTP Email Delivery (Resend API on HTTPS Port 443) in Settings or request your host to unblock port 587.",
        )
    except smtplib.SMTPConnectError as e:
        log.warning("Gmail SMTP connection error: %s", e)
        return (False, f"Could not establish connection to {host}:{port}: {e}")
    except OSError as e:
        err_msg = str(e)
        if getattr(e, "errno", None) in (101, 10051) or "unreachable" in err_msg.lower():
            alt_port = 587 if port == 465 else 465
            log.warning("Network unreachable connecting to %s:%s: %s", host, port, e)
            alt_hint = f"Try switching SMTP Port to {alt_port} in Settings."
            # Check if alternate port is reachable
            try:
                with create_smtp_connection(host, alt_port, timeout=4):
                    alt_hint = f"Notice: Port {alt_port} is reachable! Switch your SMTP Port setting from {port} to {alt_port} in Settings."
            except Exception:
                pass
            return (
                False,
                f"Connection test failed: [Errno 101] Network is unreachable ({host}:{port}). "
                f"Outbound SMTP traffic appears blocked by your hosting provider/firewall (common on cloud VPS like AWS/DigitalOcean). {alt_hint}",
            )
        log.exception("Unexpected socket error verifying Gmail credentials")
        return (False, f"Connection test failed: {e}")
    except Exception as e:
        log.exception("Unexpected error verifying Gmail credentials")
        return (False, f"Connection test failed: {e}")


def _verify_resend_api_key(api_key: str, timeout: int = 10) -> Tuple[bool, str]:
    """Verify Resend API Key against Resend API via HTTPS (Port 443)."""
    k = (api_key or "").strip()
    if not k:
        return (False, "Resend API key is required.")
    import httpx
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(
                "https://api.resend.com/api-keys",
                headers={"Authorization": f"Bearer {k}"},
            )
            if resp.status_code == 200:
                return (True, "Successfully authenticated with Resend HTTP API (Port 443 HTTPS). Ready to send emails without SMTP port restrictions.")
            return (False, f"Resend API Key verification failed ({resp.status_code}): {resp.text}")
    except Exception as e:
        return (False, f"Resend API connection failed: {e}")


def _verify_gmail_api_credentials(config: Dict[str, Any], timeout: int = 15) -> Tuple[bool, str]:
    """Verify Gmail REST API OAuth credentials over HTTPS (Port 443)."""
    client_id = (config.get("gmail_client_id") or os.environ.get("GMAIL_API_CLIENT_ID") or os.environ.get("GOOGLE_CLIENT_ID") or "").strip()
    client_secret = (config.get("gmail_client_secret") or os.environ.get("GMAIL_API_CLIENT_SECRET") or os.environ.get("GOOGLE_CLIENT_SECRET") or "").strip()
    refresh_token = (config.get("gmail_refresh_token") or os.environ.get("GMAIL_API_REFRESH_TOKEN") or os.environ.get("GOOGLE_REFRESH_TOKEN") or "").strip()

    if not client_id or not client_secret:
        return (False, "Google Cloud OAuth Client ID and Client Secret are required for Gmail REST API.")
    if not refresh_token:
        return (False, "Google OAuth Refresh Token is required. Please authorize your Google account first.")

    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request as GoogleAuthRequest
        from googleapiclient.discovery import build

        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
            scopes=["https://www.googleapis.com/auth/gmail.send", "https://www.googleapis.com/auth/gmail.readonly"],
        )
        creds.refresh(GoogleAuthRequest())

        service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        profile = service.users().getProfile(userId="me").execute()
        email_addr = profile.get("emailAddress", config.get("gmail_user", ""))
        return (
            True,
            f"Successfully authenticated with Gmail REST API (Port 443 HTTPS) as {email_addr}. "
            f"Cloud firewall-immune delivery is active.",
        )
    except Exception as e:
        log.warning("Gmail REST API verification failed: %s", e)
        return (False, f"Gmail REST API verification failed: {e}")


def generate_google_auth_url(client_id: str, redirect_uri: str = "urn:ietf:wg:oauth:2.0:oob") -> str:
    """Generate the Google OAuth 2.0 authorization URL for Gmail API."""
    from urllib.parse import urlencode
    params = {
        "client_id": client_id.strip(),
        "redirect_uri": redirect_uri.strip(),
        "response_type": "code",
        "scope": "https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/gmail.readonly",
        "access_type": "offline",
        "prompt": "consent",
    }
    return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"


def exchange_google_auth_code(
    client_id: str,
    client_secret: str,
    auth_code: str,
    redirect_uri: str = "urn:ietf:wg:oauth:2.0:oob",
    timeout: int = 15,
) -> Dict[str, Any]:
    """Exchange an authorization code for permanent Google OAuth tokens (access_token + refresh_token)."""
    import httpx
    resp = httpx.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": auth_code.strip(),
            "client_id": client_id.strip(),
            "client_secret": client_secret.strip(),
            "redirect_uri": redirect_uri.strip(),
            "grant_type": "authorization_code",
        },
        timeout=timeout,
    )
    if resp.status_code != 200:
        raise ValueError(f"Google OAuth token exchange failed ({resp.status_code}): {resp.text}")
    return resp.json()


def verify_email_credentials(
    config: Dict[str, Any],
    timeout: int = 15,
) -> Tuple[bool, str]:
    """Verify credentials for Gmail REST API (Port 443 HTTPS), Resend HTTP API, or Gmail SMTP."""
    provider = config.get("provider", "smtp")
    if provider == "gmail_api" or (config.get("gmail_refresh_token") and config.get("gmail_client_id") and not config.get("gmail_app_password")):
        return _verify_gmail_api_credentials(config, timeout=timeout)
    elif provider == "resend" or (config.get("resend_api_key") and not config.get("gmail_app_password")):
        api_key = config.get("resend_api_key", "").strip()
        return _verify_resend_api_key(api_key, timeout=timeout)
    else:
        return verify_smtp_credentials(
            smtp_host=config.get("smtp_host", "smtp.gmail.com"),
            smtp_port=int(config.get("smtp_port") or 465),
            user=config.get("gmail_user", ""),
            password=config.get("gmail_app_password", ""),
            timeout=timeout,
        )


async def async_verify_smtp_credentials(smtp_host: str, smtp_port: int, user: str, password: str, timeout: int = 15) -> Tuple[bool, str]:
    """Execute synchronous verify_smtp_credentials in a threadpool executor without blocking the asyncio loop."""
    loop = asyncio.get_running_loop()
    func = partial(verify_smtp_credentials, smtp_host, smtp_port, user, password, timeout=timeout)
    return await loop.run_in_executor(None, func)


async def async_verify_email_credentials(config: Dict[str, Any], timeout: int = 15) -> Tuple[bool, str]:
    """Execute synchronous verify_email_credentials in a threadpool executor without blocking the asyncio loop."""
    loop = asyncio.get_running_loop()
    func = partial(verify_email_credentials, config, timeout=timeout)
    return await loop.run_in_executor(None, func)


def _send_via_resend_api(
    config: Dict[str, Any],
    to_list: List[str],
    subject: str,
    text_body: str,
    html_body: str,
    cc_list: Optional[List[str]] = None,
    bcc_list: Optional[List[str]] = None,
    attachments: Optional[List[Dict[str, Any]]] = None,
    timeout: int = 20,
) -> Tuple[bool, str]:
    """Dispatch an email via Resend HTTP API over standard HTTPS (Port 443)."""
    api_key = (config.get("resend_api_key") or os.environ.get("RESEND_API_KEY") or "").strip()
    if not api_key:
        return (False, "Resend API Key is not configured. Please add your Resend API Key in Settings.")

    from_name = config.get("from_name") or "SSK Footcare"
    sender_email = config.get("from_email") or config.get("gmail_user") or ""
    # If not using a custom verified domain on Resend, Resend requires onboarding@resend.dev
    if not sender_email or "@" not in sender_email or sender_email.endswith("@gmail.com"):
        from_header = f"{from_name} <onboarding@resend.dev>"
    else:
        from_header = f"{from_name} <{sender_email}>"

    payload: Dict[str, Any] = {
        "from": from_header,
        "to": to_list,
        "subject": subject,
        "html": html_body,
        "text": text_body,
    }
    if cc_list:
        payload["cc"] = cc_list
    if bcc_list:
        payload["bcc"] = bcc_list
    if config.get("reply_to"):
        payload["reply_to"] = config["reply_to"]
    elif config.get("gmail_user"):
        payload["reply_to"] = config["gmail_user"]

    if attachments:
        resend_atts = []
        for att in attachments:
            fname = att.get("filename", "attachment.pdf")
            content = att.get("content")
            if isinstance(content, bytes):
                b64_content = base64.b64encode(content).decode("utf-8")
            elif isinstance(content, str):
                b64_content = content
            else:
                continue
            resend_atts.append({
                "filename": fname,
                "content": b64_content,
            })
        if resend_atts:
            payload["attachments"] = resend_atts

    import httpx
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            if resp.status_code in (200, 201):
                data = resp.json()
                email_id = data.get("id", "")
                return (True, f"Email delivered via Resend API (ID: {email_id})")
            else:
                err_text = resp.text
                try:
                    err_json = resp.json()
                    err_text = err_json.get("message") or err_text
                except Exception:
                    pass
                return (False, f"Resend API error ({resp.status_code}): {err_text}")
    except Exception as e:
        log.exception("Resend API request failed")
        return (False, f"Resend API request failed: {e}")


def _send_via_gmail_api(
    config: Dict[str, Any],
    to_list: List[str],
    subject: str,
    text_body: str,
    html_body: Optional[str] = None,
    cc_list: Optional[List[str]] = None,
    bcc_list: Optional[List[str]] = None,
    attachments: Optional[List[Dict[str, Any]]] = None,
    timeout: int = 20,
) -> Tuple[bool, str]:
    """Dispatch an email via Gmail REST API over standard HTTPS (Port 443)."""
    client_id = (config.get("gmail_client_id") or os.environ.get("GMAIL_API_CLIENT_ID") or os.environ.get("GOOGLE_CLIENT_ID") or "").strip()
    client_secret = (config.get("gmail_client_secret") or os.environ.get("GMAIL_API_CLIENT_SECRET") or os.environ.get("GOOGLE_CLIENT_SECRET") or "").strip()
    refresh_token = (config.get("gmail_refresh_token") or os.environ.get("GMAIL_API_REFRESH_TOKEN") or os.environ.get("GOOGLE_REFRESH_TOKEN") or "").strip()

    if not client_id or not client_secret or not refresh_token:
        return (False, "Gmail REST API credentials incomplete. Client ID, Client Secret, and Refresh Token are required.")

    from_name = config.get("from_name") or "SSK Footcare Manufacturing"
    sender_email = config.get("gmail_user") or ""
    reply_to = config.get("reply_to") or ""

    # Build root MIME container
    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    if sender_email:
        msg["From"] = f"{from_name} <{sender_email}>"
    else:
        msg["From"] = from_name
    msg["To"] = ", ".join(to_list)
    if cc_list:
        msg["Cc"] = ", ".join(cc_list)
    if reply_to:
        msg["Reply-To"] = reply_to
    msg["Date"] = formatdate(localtime=True)

    alt = MIMEMultipart("alternative")
    if text_body:
        alt.attach(MIMEText(text_body, "plain", "utf-8"))
    if html_body:
        alt.attach(MIMEText(html_body, "html", "utf-8"))
    msg.attach(alt)

    if attachments:
        for att in attachments:
            fname = att.get("filename", "attachment.pdf")
            content = att.get("content")
            if isinstance(content, str):
                try:
                    payload = base64.b64decode(content)
                except Exception:
                    payload = content.encode("utf-8")
            elif isinstance(content, bytes):
                payload = content
            else:
                continue
            part = MIMEApplication(payload)
            part.add_header("Content-Disposition", "attachment", filename=fname)
            msg.attach(part)

    raw_bytes = msg.as_bytes()
    raw_b64 = base64.urlsafe_b64encode(raw_bytes).decode("ascii")

    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request as GoogleAuthRequest
        from googleapiclient.discovery import build

        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
            scopes=["https://www.googleapis.com/auth/gmail.send"],
        )
        creds.refresh(GoogleAuthRequest())

        service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        res = service.users().messages().send(userId="me", body={"raw": raw_b64}).execute()
        msg_id = res.get("id", "")
        log.info("Email sent successfully via Gmail REST API (id: %s)", msg_id)
        return (True, f"Email delivered via Gmail REST API (HTTPS Port 443, ID: {msg_id})")
    except Exception as e:
        log.exception("Gmail REST API dispatch error")
        return (False, f"Gmail REST API dispatch failed: {e}")


def send_email(
    to_emails: Union[List[str], str],
    subject: str,
    text_body: str,
    html_body: Optional[str] = None,
    cc_emails: Optional[Union[List[str], str]] = None,
    bcc_emails: Optional[Union[List[str], str]] = None,
    attachments: Optional[List[Dict[str, Any]]] = None,
    config: Optional[Dict[str, Any]] = None,
    timeout: int = 20,
) -> Tuple[bool, str]:
    """Dispatch an email via Gmail REST API, Gmail SMTP, or Resend HTTP API with optional attachments."""
    if not config or (
        not config.get("is_configured")
        and not (config.get("gmail_user") and config.get("gmail_app_password"))
        and not (config.get("gmail_client_id") and config.get("gmail_refresh_token"))
        and not config.get("resend_api_key")
    ):
        return (False, "Email is not configured in ERP settings or environment variables.")

    # Normalize recipient lists
    def _normalize_list(val) -> List[str]:
        if not val:
            return []
        if isinstance(val, str):
            parts = [x.strip() for x in re.split(r"[,;]+", val) if x.strip()]
            return parts
        return [str(x).strip() for x in val if str(x).strip()]

    to_list = _normalize_list(to_emails)
    cc_list = _normalize_list(cc_emails)
    bcc_list = _normalize_list(bcc_emails)

    if not to_list:
        return (False, "Recipient email address ('to') is required.")

    # Validate email syntax
    email_regex = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    for addr in to_list + cc_list + bcc_list:
        if not email_regex.match(addr):
            return (False, f"Invalid email format: '{addr}'")

    provider = config.get("provider", "smtp")
    if provider == "gmail_api" or (config.get("gmail_refresh_token") and config.get("gmail_client_id") and not config.get("gmail_app_password")):
        return _send_via_gmail_api(
            config=config,
            to_list=to_list,
            subject=subject,
            text_body=text_body,
            html_body=html_body,
            cc_list=cc_list,
            bcc_list=bcc_list,
            attachments=attachments,
            timeout=timeout,
        )
    elif provider == "resend" or (config.get("resend_api_key") and not config.get("gmail_app_password")):
        return _send_via_resend_api(
            config=config,
            to_list=to_list,
            subject=subject,
            text_body=text_body,
            html_body=html_body,
            cc_list=cc_list,
            bcc_list=bcc_list,
            attachments=attachments,
            timeout=timeout,
        )

    gmail_user = config.get("gmail_user", "")
    gmail_pass = config.get("gmail_app_password", "")
    from_name = config.get("from_name") or "SSK Footcare Manufacturing"
    reply_to = config.get("reply_to") or ""
    smtp_host = config.get("smtp_host") or "smtp.gmail.com"
    smtp_port = int(config.get("smtp_port") or 465)

    if not gmail_user or not gmail_pass:
        return (False, "Gmail address or Google App Password missing.")

    # Build root MIME container
    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = f"{from_name} <{gmail_user}>"
    msg["To"] = ", ".join(to_list)
    if cc_list:
        msg["Cc"] = ", ".join(cc_list)
    if reply_to:
        msg["Reply-To"] = reply_to
    msg["Date"] = formatdate(localtime=True)

    # Alternative body (plain + HTML)
    alt = MIMEMultipart("alternative")
    if text_body:
        alt.attach(MIMEText(text_body, "plain", "utf-8"))
    if html_body:
        alt.attach(MIMEText(html_body, "html", "utf-8"))
    msg.attach(alt)

    # Attachments
    if attachments:
        for att in attachments:
            fname = att.get("filename", "attachment")
            content = att.get("content")
            if isinstance(content, str):
                # could be base64
                try:
                    content = base64.b64decode(content)
                except Exception:
                    content = content.encode("utf-8")
            if not isinstance(content, bytes):
                continue
            part = MIMEApplication(content, Name=fname)
            part["Content-Disposition"] = f'attachment; filename="{fname}"'
            msg.attach(part)

    all_recipients = list(set(to_list + cc_list + bcc_list))

    try:
        with create_smtp_connection(smtp_host, smtp_port, timeout=timeout) as smtp:
            smtp.login(gmail_user, gmail_pass)
            smtp.sendmail(gmail_user, all_recipients, msg.as_string())
        return (True, f"Email sent successfully to {', '.join(to_list)}")
    except smtplib.SMTPAuthenticationError:
        log.exception("Gmail SMTP auth failed during send")
        return (False, "Gmail authentication failed. Please check your Google App Password.")
    except (socket.timeout, TimeoutError):
        log.warning("Gmail SMTP connection timed out connecting to %s:%s during send", smtp_host, smtp_port)
        alt_port = 587 if smtp_port == 465 else 465
        return (
            False,
            f"Connection to {smtp_host}:{smtp_port} timed out after {timeout} seconds. "
            f"If both Port 465 and Port 587 time out, your cloud host (e.g. Render, AWS EC2, DigitalOcean) blocks outbound SMTP ports 25, 465, and 587. "
            f"Solution: Switch to HTTP Email Delivery (Resend API on HTTPS Port 443) in Settings or request your cloud provider to unblock port 587.",
        )
    except OSError as e:
        err_msg = str(e)
        if getattr(e, "errno", None) in (101, 10051) or "unreachable" in err_msg.lower():
            alt_port = 587 if smtp_port == 465 else 465
            return (
                False,
                f"Network is unreachable on {smtp_host}:{smtp_port} ([Errno 101]). "
                f"Outbound SMTP port {smtp_port} may be blocked by your hosting provider or firewall. "
                f"Try switching SMTP Port to {alt_port} in Settings.",
            )
        log.exception("Gmail SMTP network error during send")
        return (False, f"Failed to send email: {e}")
    except Exception as e:
        log.exception("Gmail SMTP send failed")
        return (False, f"Failed to send email: {e}")


async def async_send_email(*args, **kwargs) -> Tuple[bool, str]:
    """Execute synchronous send_email in a threadpool executor without blocking the asyncio loop."""
    loop = asyncio.get_running_loop()
    func = partial(send_email, *args, **kwargs)
    return await loop.run_in_executor(None, func)


def format_inr(amount: Any) -> str:
    """Format numeric amount into Indian Rupee style with commas (e.g. ₹1,23,456.00)."""
    try:
        val = _safe_float(amount, 0.0)
        s = f"{val:.2f}"
        parts = s.split(".")
        integer_part = parts[0]
        dec_part = parts[1]
        if len(integer_part) > 3:
            last3 = integer_part[-3:]
            remaining = integer_part[:-3]
            # split remaining in pairs of 2 from right to left
            chunks = []
            while remaining:
                chunks.append(remaining[-2:])
                remaining = remaining[:-2]
            chunks.reverse()
            formatted_int = ",".join(chunks) + "," + last3
        else:
            formatted_int = integer_part
        return f"₹{formatted_int}.{dec_part}"
    except Exception:
        return f"₹{amount}"


def _format_date_clean(val: Any) -> str:
    """Format an ISO date string (YYYY-MM-DD) into readable DD-MMM-YYYY or return as string."""
    if not val:
        return "—"
    s = str(val).strip()
    if not s or s in ("—", "-", "None", "null", "N/A"):
        return "—"
    if s == "Immediate":
        return "Immediate"
    try:
        dt = datetime.strptime(s[:10], "%Y-%m-%d")
        return dt.strftime("%d-%b-%Y")
    except Exception:
        return s


def build_payment_reminder_template(
    invoice: Dict[str, Any],
    client: Dict[str, Any],
    company: Dict[str, Any],
    custom_message: Optional[str] = None,
    include_bank_details: bool = True,
) -> Tuple[str, str, str]:
    """
    Generate subject, plaintext body, and modern responsive HTML table of details for an invoice payment reminder.
    Returns: (subject, text_body, html_body)
    """
    inv_no = invoice.get("invoice_no") or "Invoice"
    client_name = client.get("company_name") or client.get("name") or invoice.get("client_name") or "Valued Customer"
    contact_person = client.get("contact_person") or ""
    po_no = invoice.get("po_number") or "—"
    inv_date = invoice.get("invoice_date") or invoice.get("date") or "—"
    inv_date_clean = _format_date_clean(inv_date)
    grn_date = invoice.get("grn_date")
    grn_date_clean = _format_date_clean(grn_date)
    due_date = invoice.get("due_date") or "Immediate"
    due_date_clean = _format_date_clean(due_date)

    net_amount = _safe_float(invoice.get("net_amount"), 0.0)
    received_amount = _safe_float(invoice.get("received_amount"), 0.0)
    raw_out = invoice.get("outstanding")
    if raw_out is not None and str(raw_out).strip() != "":
        outstanding = _safe_float(raw_out, net_amount - received_amount)
    else:
        outstanding = max(0.0, net_amount - received_amount)

    # Calculate status & overdue days
    is_overdue = False
    days_overdue = 0
    if due_date and due_date != "Immediate":
        try:
            d_due = datetime.strptime(due_date[:10], "%Y-%m-%d").date()
            today = datetime.now(timezone.utc).date()
            if today > d_due:
                is_overdue = True
                days_overdue = (today - d_due).days
        except Exception:
            pass

    company_name = company.get("name") or "SSK FOOTCARE MANUFACTURING LLP"
    bank_name = company.get("bank_name") or "HDFC BANK"
    bank_acc = company.get("bank_acc") or ""
    bank_ifsc = company.get("bank_ifsc") or ""
    upi_id = company.get("upi_id") or ""
    company_phone = company.get("phone") or ""
    company_email = company.get("email") or ""

    greeting_name = contact_person or client_name

    # Subject line
    if is_overdue:
        subject = f"OVERDUE PAYMENT REMINDER: Invoice #{inv_no} ({client_name}) - {format_inr(outstanding)}"
    else:
        subject = f"Payment Reminder: Invoice #{inv_no} ({client_name}) - {format_inr(outstanding)}"

    # Default message if none supplied
    if not custom_message:
        if is_overdue:
            user_msg = (
                f"We would like to bring to your attention that payment for Invoice #{inv_no} is currently "
                f"overdue by {days_overdue} day(s). Kindly review the itemized particulars below and arrange "
                f"the remittance of the outstanding balance at your earliest convenience."
            )
        else:
            user_msg = (
                f"This is a gentle reminder regarding the upcoming balance for Invoice #{inv_no}. "
                f"Kindly review the invoice details below and arrange for payment on or before the due date."
            )
    else:
        user_msg = custom_message.strip()

    overdue_period_str = f"{days_overdue} Days Overdue" if is_overdue else "Due on schedule"

    # Plaintext version with clean tabular layout
    text_parts = [
        f"PAYMENT REMINDER & STATEMENT — {company_name.upper()}",
        "=" * 70,
        f"\nDear {greeting_name},",
        f"\n{user_msg}\n",
        "-" * 70,
        "INVOICE PARTICULARS & BALANCE DETAILS:",
        f"  • Invoice Number  : {inv_no}",
        f"  • Invoice Date    : {inv_date_clean}",
        f"  • GRN Date        : {grn_date_clean}",
        f"  • PO Number       : {po_no}",
        f"  • Total Amount    : {format_inr(net_amount)}",
        f"  • Due Date        : {due_date_clean}",
        f"  • Overdue Period  : {overdue_period_str}",
        f"  • OUTSTANDING DUE : {format_inr(outstanding)}",
        "-" * 70,
    ]

    if include_bank_details and bank_acc:
        text_parts.extend([
            "\nREMITTANCE / BANK TRANSFER DETAILS:",
            f"  Beneficiary : {company_name}",
            f"  Bank Name   : {bank_name}",
            f"  Account No  : {bank_acc}",
            f"  IFSC Code   : {bank_ifsc}",
        ])
        if upi_id:
            text_parts.append(f"  UPI ID      : {upi_id}")
        text_parts.append("\nPlease reply with the UTR / transaction reference once payment is initiated.\n")

    text_parts.extend([
        f"\nWarm regards,",
        f"Accounts & Finance Team",
        f"{company_name}",
        f"Phone: {company_phone}" if company_phone else "",
        f"Email: {company_email}" if company_email else "",
    ])
    text_body = "\n".join([p for p in text_parts if p is not None])

    # HTML Version
    badge_bg = "#FEE2E2" if is_overdue else "#FEF3C7"
    badge_color = "#991B1B" if is_overdue else "#92400E"
    badge_border = "#FCA5A5" if is_overdue else "#FCD34D"
    badge_text = f"OVERDUE · {days_overdue} DAYS" if is_overdue else "PAYMENT SCHEDULED"

    grn_badge = (
        f'<span style="display: inline-block; padding: 2px 7px; background: #EFF6FF; color: #1D4ED8; border: 1px solid #BFDBFE; border-radius: 4px; font-size: 11px; font-weight: 600;">{grn_date_clean}</span>'
        if grn_date
        else '<span style="color: #94A3B8; font-size: 11px;">Not Recorded</span>'
    )

    overdue_badge = (
        f'<span style="display: inline-block; padding: 3px 8px; background: #FEE2E2; color: #991B1B; border: 1px solid #FCA5A5; border-radius: 12px; font-weight: 700; font-size: 11px;">{days_overdue}d Overdue</span>'
        if is_overdue
        else '<span style="display: inline-block; padding: 3px 8px; background: #ECFDF5; color: #047857; border: 1px solid #A7F3D0; border-radius: 12px; font-weight: 600; font-size: 11px;">Current</span>'
    )

    bank_html = ""
    if include_bank_details and bank_acc:
        bank_html = f"""
        <div style="margin-top: 24px; padding: 18px 20px; background: #F8FAFC; border: 1px solid #E2E8F0; border-left: 4px solid #0F172A; border-radius: 6px;">
          <div style="font-size: 11px; font-weight: 800; text-transform: uppercase; letter-spacing: 1.5px; color: #0F172A; margin-bottom: 12px; display: flex; align-items: center; gap: 6px;">
            🏦 Bank Remittance & Settlement Details
          </div>
          <table style="width: 100%; font-size: 13px; border-collapse: collapse; line-height: 1.7;">
            <tr>
              <td style="color: #64748B; width: 140px; padding: 3px 0;">Beneficiary:</td>
              <td style="color: #0F172A; font-weight: 700; padding: 3px 0;">{company_name}</td>
            </tr>
            <tr>
              <td style="color: #64748B; padding: 3px 0;">Bank Name:</td>
              <td style="color: #0F172A; font-weight: 600; padding: 3px 0;">{bank_name}</td>
            </tr>
            <tr>
              <td style="color: #64748B; padding: 3px 0;">Account Number:</td>
              <td style="color: #0F172A; font-family: 'Consolas', 'Courier New', monospace; font-size: 14px; font-weight: 700; padding: 3px 0;">{bank_acc}</td>
            </tr>
            <tr>
              <td style="color: #64748B; padding: 3px 0;">IFSC Code:</td>
              <td style="color: #0F172A; font-family: 'Consolas', 'Courier New', monospace; font-size: 14px; font-weight: 700; padding: 3px 0;">{bank_ifsc}</td>
            </tr>
            {f'<tr><td style="color: #64748B; padding: 3px 0;">UPI ID:</td><td style="color: #0F172A; font-weight: 600; padding: 3px 0;">{upi_id}</td></tr>' if upi_id else ''}
          </table>
          <div style="margin-top: 10px; font-size: 11px; color: #64748B; border-top: 1px dashed #CBD5E1; padding-top: 8px;">
            * Kindly reply to this email with the UTR / transaction receipt once transferred for instant ledger credit.
          </div>
        </div>
        """

    html_body = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{subject}</title>
</head>
<body style="margin: 0; padding: 24px; background-color: #F1F5F9; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1E293B;">
  <div style="max-width: 680px; margin: 0 auto; background: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 16px rgba(15, 23, 42, 0.08);">
    
    <!-- Top Accent Bar -->
    <div style="height: 4px; background: #C27842;"></div>

    <!-- Header -->
    <div style="background: linear-gradient(135deg, #0F172A 0%, #1E293B 100%); padding: 24px 28px; color: #FFFFFF;">
      <table style="width: 100%; border-collapse: collapse;">
        <tr>
          <td>
            <div style="font-size: 10px; letter-spacing: 2px; text-transform: uppercase; color: #94A3B8; font-weight: 700;">
              SSK Footcare ERP · Accounts & Receivables
            </div>
            <div style="font-size: 20px; font-weight: 800; letter-spacing: 0.5px; margin-top: 4px; color: #FFFFFF;">
              {company_name}
            </div>
          </td>
          <td style="text-align: right; vertical-align: top;">
            <span style="display: inline-block; padding: 5px 12px; font-size: 10px; font-weight: 800; letter-spacing: 1.5px; text-transform: uppercase; background: {badge_bg}; color: {badge_color}; border: 1px solid {badge_border}; border-radius: 20px;">
              {badge_text}
            </span>
          </td>
        </tr>
      </table>
    </div>

    <!-- Body -->
    <div style="padding: 28px;">
      
      <!-- Greeting -->
      <p style="font-size: 15px; margin: 0 0 14px; color: #0F172A;">
        Dear <strong>{greeting_name}</strong>,
      </p>
      
      <p style="font-size: 14px; line-height: 1.6; margin: 0 0 20px; color: #334155;">
        {user_msg}
      </p>

      <!-- Executive KPI Cards -->
      <table style="width: 100%; border-collapse: collapse; margin-bottom: 22px;">
        <tr>
          <td style="width: 50%; padding-right: 6px;">
            <div style="background: #FEF2F2; border: 1px solid #FECACA; border-radius: 6px; padding: 14px 16px;">
              <div style="font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; color: #991B1B;">
                Outstanding Balance Due
              </div>
              <div style="font-size: 22px; font-weight: 800; color: #DC2626; font-family: 'Consolas', 'Courier New', monospace; margin-top: 4px;">
                {format_inr(outstanding)}
              </div>
            </div>
          </td>
          <td style="width: 50%; padding-left: 6px;">
            <div style="background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px; padding: 14px 16px;">
              <div style="font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; color: #64748B;">
                Invoice Status
              </div>
              <div style="font-size: 16px; font-weight: 700; color: #0F172A; margin-top: 6px;">
                {f'<span style="color: #DC2626;">{days_overdue} Days Overdue</span>' if is_overdue else '<span style="color: #16A34A;">Payment Pending</span>'}
              </div>
            </div>
          </td>
        </tr>
      </table>

      <!-- TABLE OF DETAILS (Hero Element) -->
      <div style="border: 1px solid #CBD5E1; border-radius: 6px; overflow: hidden; margin-bottom: 20px;">
        <div style="background: #F8FAFC; border-bottom: 1px solid #CBD5E1; padding: 10px 14px; font-size: 11px; font-weight: 800; text-transform: uppercase; letter-spacing: 1px; color: #475569;">
          Itemized Invoice & Delivery Particulars
        </div>
        <table style="width: 100%; font-size: 12px; border-collapse: collapse; text-align: left;">
          <thead>
            <tr style="background: #F1F5F9; border-bottom: 2px solid #CBD5E1; color: #334155; font-size: 11px; font-weight: 700; text-transform: uppercase;">
              <th style="padding: 10px 12px;">Invoice #</th>
              <th style="padding: 10px 8px;">Invoice Date</th>
              <th style="padding: 10px 8px;">GRN Date</th>
              <th style="padding: 10px 8px;">PO #</th>
              <th style="padding: 10px 8px; text-align: right;">Amount</th>
              <th style="padding: 10px 8px;">Due Date</th>
              <th style="padding: 10px 8px; text-align: center;">Overdue Period</th>
              <th style="padding: 10px 12px; text-align: right;">Balance Due</th>
            </tr>
          </thead>
          <tbody>
            <tr style="background: #FFFFFF;">
              <td style="padding: 12px; font-family: 'Consolas', 'Courier New', monospace; font-weight: 700; color: #0F172A;">{inv_no}</td>
              <td style="padding: 12px 8px; color: #475569;">{inv_date_clean}</td>
              <td style="padding: 12px 8px;">{grn_badge}</td>
              <td style="padding: 12px 8px; color: #475569;">{po_no}</td>
              <td style="padding: 12px 8px; text-align: right; font-family: 'Consolas', 'Courier New', monospace; color: #475569;">{format_inr(net_amount)}</td>
              <td style="padding: 12px 8px; color: {'#DC2626' if is_overdue else '#0F172A'}; font-weight: 600;">{due_date_clean}</td>
              <td style="padding: 12px 8px; text-align: center;">{overdue_badge}</td>
              <td style="padding: 12px; text-align: right; font-family: 'Consolas', 'Courier New', monospace; font-weight: 800; color: #DC2626;">{format_inr(outstanding)}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Statement Notice (No PDF Required) -->
      <div style="font-size: 12px; color: #475569; background: #F8FAFC; border: 1px solid #E2E8F0; border-left: 4px solid #C27842; padding: 12px 16px; margin-bottom: 22px; border-radius: 4px; line-height: 1.5;">
        📋 <strong>Statement Notice:</strong> All invoice numbers, GRN delivery records, PO references, and overdue terms are itemized directly in the table above for immediate reconciliation. No file downloads required.
      </div>

      {bank_html}

      <!-- Signoff -->
      <div style="margin-top: 28px; border-top: 1px solid #E2E8F0; padding-top: 18px; font-size: 13px; color: #64748B;">
        <p style="margin: 0 0 4px;">With regards,</p>
        <p style="margin: 0; font-weight: 700; color: #0F172A;">Finance & Accounts Team</p>
        <p style="margin: 0; color: #475569;">{company_name}</p>
        {f'<p style="margin: 4px 0 0; font-size: 12px;">Contact: {company_phone} | {company_email}</p>' if (company_phone or company_email) else ''}
      </div>
    </div>

    <!-- Footer -->
    <div style="background: #F8FAFC; border-top: 1px solid #E2E8F0; padding: 14px 28px; text-align: center; font-size: 11px; color: #94A3B8;">
      This is an automated payment advisory and statement generated by SSK Footcare Manufacturing ERP.
    </div>
  </div>
</body>
</html>"""

    return (subject, text_body, html_body)


async def send_invoice_payment_reminder(
    db,
    invoice_id: str,
    to_email: str,
    cc_emails: Optional[Union[List[str], str]] = None,
    subject: Optional[str] = None,
    custom_message: Optional[str] = None,
    attach_pdf: bool = False,
    include_bank_details: bool = True,
    user_email: str = "system",
) -> Dict[str, Any]:
    """
    Prepare and send a formal payment reminder email for an invoice,
    persisting audit and reminder metadata in MongoDB.
    """
    from bson import ObjectId

    # 1. Resolve invoice
    try:
        inv_oid = ObjectId(invoice_id)
    except Exception:
        inv_oid = invoice_id

    inv = await db.invoices.find_one({"_id": inv_oid})
    if not inv:
        return {"ok": False, "error": f"Invoice '{invoice_id}' not found"}

    # 2. Get email configuration
    cfg = await get_email_config(db)
    if not cfg["is_configured"]:
        return {
            "ok": False,
            "error": "Email is not configured in ERP settings. Please navigate to Settings to connect your company Gmail address or Resend API Key."
        }

    # 3. Lookup client master for name/person
    client_name = inv.get("client_name") or ""
    client_doc = {}
    if client_name:
        client_doc = await db.clients.find_one({
            "$or": [
                {"company_name": {"$regex": f"^{re.escape(client_name)}$", "$options": "i"}},
                {"name": {"$regex": f"^{re.escape(client_name)}$", "$options": "i"}},
            ]
        }) or {}

    # 4. Resolve company profile
    company_profile = await db.settings.find_one({"_id": "company_profile"})
    if not company_profile:
        from pdf_docs import COMPANY
        company_profile = dict(COMPANY)

    # 5. Build template
    tmpl_subj, tmpl_txt, tmpl_html = build_payment_reminder_template(
        invoice=inv,
        client=client_doc,
        company=company_profile,
        custom_message=custom_message,
        include_bank_details=include_bank_details,
    )

    final_subject = subject.strip() if subject else tmpl_subj

    # 6. Prepare attachments
    attachments = []
    if attach_pdf:
        pdf_raw = None
        # Check direct invoice file_b64
        if inv.get("file_b64"):
            try:
                pdf_raw = base64.b64decode(inv["file_b64"])
            except Exception as e:
                log.warning("Failed to b64decode invoice file_b64: %s", e)

        # Check dispatch_records invoice_file_b64 if not found
        if not pdf_raw and inv.get("dispatch_record_id"):
            try:
                dr = await db.dispatch_records.find_one({"_id": ObjectId(inv["dispatch_record_id"])})
                if dr and dr.get("invoice_file_b64"):
                    pdf_raw = base64.b64decode(dr["invoice_file_b64"])
            except Exception:
                pass

        if pdf_raw:
            fname = f"{inv.get('invoice_no', 'invoice')}.pdf"
            attachments.append({
                "filename": fname,
                "content": pdf_raw,
                "mime_type": "application/pdf"
            })
        else:
            log.info("No stored PDF found for invoice %s; sending reminder without attachment", inv.get("invoice_no"))

    # Merge default CC from config if none supplied
    final_cc = cc_emails
    if not final_cc and cfg.get("default_cc"):
        final_cc = cfg["default_cc"]

    # 7. Send email in background thread executor to prevent blocking the async loop
    ok, msg_or_err = await async_send_email(
        to_emails=to_email,
        subject=final_subject,
        text_body=tmpl_txt,
        html_body=tmpl_html,
        cc_emails=final_cc,
        attachments=attachments,
        config=cfg,
    )

    if not ok:
        return {"ok": False, "error": msg_or_err}

    # 8. Persist reminder event in invoice document & audit logs
    reminder_event = {
        "sent_at": now_iso(),
        "sent_to": to_email,
        "sent_cc": final_cc or "",
        "sent_by": user_email,
        "subject": final_subject,
        "outstanding_at_send": float(inv.get("outstanding") or 0),
        "attached_pdf": bool(len(attachments) > 0),
    }

    try:
        await db.invoices.update_one(
            {"_id": inv_oid},
            {
                "$push": {"reminder_history": reminder_event},
                "$set": {
                    "last_reminder_sent_at": reminder_event["sent_at"],
                    "last_reminder_sent_to": to_email,
                },
                "$inc": {"reminder_count": 1},
            }
        )
    except Exception as e:
        log.warning("Could not persist reminder_history on invoice %s: %s", invoice_id, e)

    # Audit log
    try:
        await db.audit_logs.insert_one({
            "action": "send_payment_reminder",
            "category": "invoices",
            "details": f"Sent payment reminder for {inv.get('invoice_no')} to {to_email} (Due: ₹{inv.get('outstanding')})",
            "by": user_email,
            "created_at": now_iso(),
        })
    except Exception:
        pass

    return {
        "ok": True,
        "message": f"Payment reminder successfully sent to {to_email}",
        "reminder": reminder_event,
    }


def build_multi_invoice_reminder_template(
    invoices: List[Dict[str, Any]],
    client: Dict[str, Any],
    company: Dict[str, Any],
    custom_message: Optional[str] = None,
    include_bank_details: bool = True,
) -> Tuple[str, str, str]:
    """
    Generate subject, plaintext body, and modern responsive HTML for a consolidated multi-invoice payment reminder.
    Returns: (subject, text_body, html_body)
    """
    if len(invoices) == 1:
        return build_payment_reminder_template(
            invoice=invoices[0],
            client=client,
            company=company,
            custom_message=custom_message,
            include_bank_details=include_bank_details,
        )

    client_name = client.get("company_name") or client.get("name") or (invoices[0].get("client_name") if invoices else "Valued Client")
    contact_person = client.get("contact_person") or ""
    greeting_name = contact_person or client_name

    company_name = company.get("name") or "SSK FOOTCARE MANUFACTURING LLP"
    bank_name = company.get("bank_name") or "HDFC BANK"
    bank_acc = company.get("bank_acc") or ""
    bank_ifsc = company.get("bank_ifsc") or ""
    upi_id = company.get("upi_id") or ""
    company_phone = company.get("phone") or ""
    company_email = company.get("email") or ""

    inv_count = len(invoices)
    total_net = sum(_safe_float(inv.get("net_amount")) for inv in invoices)
    total_received = sum(_safe_float(inv.get("received_amount")) for inv in invoices)
    total_outstanding = sum(
        _safe_float(inv.get("outstanding"))
        if (inv.get("outstanding") is not None and str(inv.get("outstanding")).strip() != "")
        else (_safe_float(inv.get("net_amount")) - _safe_float(inv.get("received_amount")))
        for inv in invoices
    )

    subject = f"OVERDUE STATEMENT: {inv_count} Overdue Invoices ({client_name}) - {format_inr(total_outstanding)}"

    if not custom_message:
        user_msg = (
            f"We would like to bring to your attention that there are {inv_count} overdue invoices "
            f"pending on your account with an aggregate outstanding balance of {format_inr(total_outstanding)}. "
            f"Please review the itemized breakdown below and arrange for payment at your earliest convenience."
        )
    else:
        user_msg = custom_message.strip()

    # Plaintext version with clean tabular layout
    text_rows = []
    for inv in invoices:
        no = inv.get("invoice_no") or "N/A"
        dt = _format_date_clean(inv.get("invoice_date") or inv.get("date"))
        grn_d = _format_date_clean(inv.get("grn_date"))
        due = _format_date_clean(inv.get("due_date") or "Immediate")
        po = inv.get("po_number") or "-"
        net_val = _safe_float(inv.get("net_amount"))
        rec_val = _safe_float(inv.get("received_amount"))
        raw_out = inv.get("outstanding")
        out_val = _safe_float(raw_out, net_val - rec_val) if (raw_out is not None and str(raw_out).strip() != "") else (net_val - rec_val)
        bal = format_inr(out_val)
        tot = format_inr(net_val)
        days = abs(inv.get("days_to_due", 0)) if (inv.get("days_to_due") is not None and inv.get("days_to_due") < 0) else 0
        od_str = f"{days}d overdue" if days > 0 else "current"
        text_rows.append(f"  • Inv #{no} | Inv Date: {dt} | GRN: {grn_d} | Due: {due} ({od_str}) | PO: {po} | Total: {tot} | Balance Due: {bal}")

    text_parts = [
        f"OVERDUE STATEMENT & PAYMENT REMINDER — {company_name.upper()}",
        "=" * 70,
        f"\nDear {greeting_name},",
        f"\n{user_msg}\n",
        "-" * 70,
        f"OVERDUE INVOICES ITEMIZED BREAKDOWN ({inv_count} INVOICES):",
        *text_rows,
        "-" * 70,
        f"TOTAL INVOICE VALUE   : {format_inr(total_net)}",
        f"TOTAL RECEIVED TO DATE: {format_inr(total_received)}",
        f"TOTAL OVERDUE BALANCE : {format_inr(total_outstanding)}",
        "=" * 70,
    ]

    if include_bank_details and bank_acc:
        text_parts.extend([
            "\nREMITTANCE / BANK TRANSFER DETAILS:",
            f"  Beneficiary : {company_name}",
            f"  Bank Name   : {bank_name}",
            f"  Account No  : {bank_acc}",
            f"  IFSC Code   : {bank_ifsc}",
        ])
        if upi_id:
            text_parts.append(f"  UPI ID      : {upi_id}")
        text_parts.append("\nPlease reply with the UTR / transaction reference once payment is initiated.\n")

    text_parts.extend([
        f"\nWarm regards,",
        f"Accounts & Finance Team",
        f"{company_name}",
        f"Phone: {company_phone}" if company_phone else "",
        f"Email: {company_email}" if company_email else "",
    ])
    text_body = "\n".join([p for p in text_parts if p is not None])

    # HTML Table Rows
    table_rows_html = []
    max_days_od = 0
    for idx, inv in enumerate(invoices):
        no = inv.get("invoice_no") or "N/A"
        dt = _format_date_clean(inv.get("invoice_date") or inv.get("date"))
        grn_d = _format_date_clean(inv.get("grn_date"))
        due = _format_date_clean(inv.get("due_date") or "Immediate")
        po = inv.get("po_number") or "—"
        net_val = _safe_float(inv.get("net_amount"))
        rec_val = _safe_float(inv.get("received_amount"))
        raw_out = inv.get("outstanding")
        out_val = _safe_float(raw_out, net_val - rec_val) if (raw_out is not None and str(raw_out).strip() != "") else (net_val - rec_val)
        bal = format_inr(out_val)
        tot = format_inr(net_val)
        days = abs(inv.get("days_to_due", 0)) if (inv.get("days_to_due") is not None and inv.get("days_to_due") < 0) else 0
        if days > max_days_od:
            max_days_od = days

        grn_badge = (
            f'<span style="display: inline-block; padding: 2px 7px; background: #EFF6FF; color: #1D4ED8; border: 1px solid #BFDBFE; border-radius: 4px; font-size: 11px; font-weight: 600;">{grn_d}</span>'
            if inv.get("grn_date")
            else '<span style="color: #94A3B8; font-size: 11px;">Not Recorded</span>'
        )

        overdue_badge = (
            f'<span style="display: inline-block; padding: 3px 8px; background: #FEE2E2; color: #991B1B; border: 1px solid #FCA5A5; border-radius: 12px; font-weight: 700; font-size: 11px;">{days}d Overdue</span>'
            if days > 0
            else '<span style="display: inline-block; padding: 3px 8px; background: #ECFDF5; color: #047857; border: 1px solid #A7F3D0; border-radius: 12px; font-weight: 600; font-size: 11px;">Current</span>'
        )

        row_bg = "#FFFFFF" if idx % 2 == 0 else "#F8FAFC"

        table_rows_html.append(f"""
          <tr style="background: {row_bg}; border-bottom: 1px solid #E2E8F0;">
            <td style="padding: 10px 12px; font-family: 'Consolas', 'Courier New', monospace; font-weight: 700; color: #0F172A;">{no}</td>
            <td style="padding: 10px 8px; color: #475569;">{dt}</td>
            <td style="padding: 10px 8px;">{grn_badge}</td>
            <td style="padding: 10px 8px; color: #475569;">{po}</td>
            <td style="padding: 10px 8px; text-align: right; color: #475569; font-family: 'Consolas', 'Courier New', monospace;">{tot}</td>
            <td style="padding: 10px 8px; color: #0F172A; font-weight: 600;">{due}</td>
            <td style="padding: 10px 8px; text-align: center;">{overdue_badge}</td>
            <td style="padding: 10px 12px; text-align: right; font-weight: 800; color: #DC2626; font-family: 'Consolas', 'Courier New', monospace;">{bal}</td>
          </tr>
        """)

    bank_html = ""
    if include_bank_details and bank_acc:
        bank_html = f"""
        <div style="margin-top: 24px; padding: 18px 20px; background: #F8FAFC; border: 1px solid #E2E8F0; border-left: 4px solid #0F172A; border-radius: 6px;">
          <div style="font-size: 11px; font-weight: 800; text-transform: uppercase; letter-spacing: 1.5px; color: #0F172A; margin-bottom: 12px;">
            🏦 Bank Remittance & Settlement Details
          </div>
          <table style="width: 100%; font-size: 13px; border-collapse: collapse; line-height: 1.7;">
            <tr>
              <td style="color: #64748B; width: 140px; padding: 3px 0;">Beneficiary:</td>
              <td style="color: #0F172A; font-weight: 700; padding: 3px 0;">{company_name}</td>
            </tr>
            <tr>
              <td style="color: #64748B; padding: 3px 0;">Bank Name:</td>
              <td style="color: #0F172A; font-weight: 600; padding: 3px 0;">{bank_name}</td>
            </tr>
            <tr>
              <td style="color: #64748B; padding: 3px 0;">Account Number:</td>
              <td style="color: #0F172A; font-family: 'Consolas', 'Courier New', monospace; font-size: 14px; font-weight: 700; padding: 3px 0;">{bank_acc}</td>
            </tr>
            <tr>
              <td style="color: #64748B; padding: 3px 0;">IFSC Code:</td>
              <td style="color: #0F172A; font-family: 'Consolas', 'Courier New', monospace; font-size: 14px; font-weight: 700; padding: 3px 0;">{bank_ifsc}</td>
            </tr>
            {f'<tr><td style="color: #64748B; padding: 3px 0;">UPI ID:</td><td style="color: #0F172A; font-weight: 600; padding: 3px 0;">{upi_id}</td></tr>' if upi_id else ''}
          </table>
          <div style="margin-top: 10px; font-size: 11px; color: #64748B; border-top: 1px dashed #CBD5E1; padding-top: 8px;">
            * Kindly reply to this email with the UTR / transaction receipt once transferred for instant ledger credit.
          </div>
        </div>
        """

    html_body = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{subject}</title>
</head>
<body style="margin: 0; padding: 24px; background-color: #F1F5F9; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1E293B;">
  <div style="max-width: 720px; margin: 0 auto; background: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 16px rgba(15, 23, 42, 0.08);">
    
    <!-- Top Accent Bar -->
    <div style="height: 4px; background: #C27842;"></div>

    <!-- Header -->
    <div style="background: linear-gradient(135deg, #0F172A 0%, #1E293B 100%); padding: 24px 28px; color: #FFFFFF;">
      <table style="width: 100%; border-collapse: collapse;">
        <tr>
          <td>
            <div style="font-size: 10px; letter-spacing: 2px; text-transform: uppercase; color: #94A3B8; font-weight: 700;">
              SSK Footcare ERP · Accounts & Receivables
            </div>
            <div style="font-size: 20px; font-weight: 800; letter-spacing: 0.5px; margin-top: 4px; color: #FFFFFF;">
              {company_name}
            </div>
          </td>
          <td style="text-align: right; vertical-align: top;">
            <span style="display: inline-block; padding: 5px 12px; font-size: 10px; font-weight: 800; letter-spacing: 1.5px; text-transform: uppercase; background: #FEE2E2; color: #991B1B; border: 1px solid #FCA5A5; border-radius: 20px;">
              OVERDUE · {inv_count} INVOICES
            </span>
          </td>
        </tr>
      </table>
    </div>

    <!-- Body -->
    <div style="padding: 28px;">
      
      <!-- Greeting -->
      <p style="font-size: 15px; margin: 0 0 14px; color: #0F172A;">
        Dear <strong>{greeting_name}</strong>,
      </p>
      
      <p style="font-size: 14px; line-height: 1.6; margin: 0 0 20px; color: #334155;">
        {user_msg}
      </p>

      <!-- Executive KPI Cards -->
      <table style="width: 100%; border-collapse: collapse; margin-bottom: 22px;">
        <tr>
          <td style="width: 50%; padding-right: 6px;">
            <div style="background: #FEF2F2; border: 1px solid #FECACA; border-radius: 6px; padding: 14px 16px;">
              <div style="font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; color: #991B1B;">
                Total Overdue Balance Due
              </div>
              <div style="font-size: 22px; font-weight: 800; color: #DC2626; font-family: 'Consolas', 'Courier New', monospace; margin-top: 4px;">
                {format_inr(total_outstanding)}
              </div>
            </div>
          </td>
          <td style="width: 50%; padding-left: 6px;">
            <div style="background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px; padding: 14px 16px;">
              <div style="font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; color: #64748B;">
                Aging Summary
              </div>
              <div style="font-size: 15px; font-weight: 700; color: #0F172A; margin-top: 6px;">
                <span style="color: #DC2626;">{inv_count} Invoices Overdue</span> · Up to {max_days_od}d
              </div>
            </div>
          </td>
        </tr>
      </table>

      <!-- TABLE OF DETAILS (Hero Element) -->
      <div style="border: 1px solid #CBD5E1; border-radius: 6px; overflow: hidden; margin-bottom: 20px;">
        <div style="background: #F8FAFC; border-bottom: 1px solid #CBD5E1; padding: 10px 14px; font-size: 11px; font-weight: 800; text-transform: uppercase; letter-spacing: 1px; color: #475569;">
          Itemized Overdue Invoices Breakdown
        </div>
        <table style="width: 100%; font-size: 12px; border-collapse: collapse; text-align: left;">
          <thead>
            <tr style="background: #F1F5F9; border-bottom: 2px solid #CBD5E1; color: #334155; font-size: 11px; font-weight: 700; text-transform: uppercase;">
              <th style="padding: 10px 12px;">Invoice #</th>
              <th style="padding: 10px 8px;">Invoice Date</th>
              <th style="padding: 10px 8px;">GRN Date</th>
              <th style="padding: 10px 8px;">PO #</th>
              <th style="padding: 10px 8px; text-align: right;">Amount</th>
              <th style="padding: 10px 8px;">Due Date</th>
              <th style="padding: 10px 8px; text-align: center;">Overdue Period</th>
              <th style="padding: 10px 12px; text-align: right;">Balance Due</th>
            </tr>
          </thead>
          <tbody>
            {''.join(table_rows_html)}
            <tr style="background: #FEF2F2; border-top: 2px solid #0F172A;">
              <td colspan="4" style="padding: 12px; font-size: 12px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.5px; color: #0F172A;">
                Consolidated Balance Due:
              </td>
              <td style="padding: 12px 8px; text-align: right; font-family: 'Consolas', 'Courier New', monospace; font-size: 12px; color: #64748B; font-weight: 600;">
                {format_inr(total_net)}
              </td>
              <td colspan="2"></td>
              <td style="padding: 12px; text-align: right; font-family: 'Consolas', 'Courier New', monospace; font-size: 17px; font-weight: 800; color: #DC2626;">
                {format_inr(total_outstanding)}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Statement Notice (No PDF Required) -->
      <div style="font-size: 12px; color: #475569; background: #F8FAFC; border: 1px solid #E2E8F0; border-left: 4px solid #C27842; padding: 12px 16px; margin-bottom: 22px; border-radius: 4px; line-height: 1.5;">
        📋 <strong>Consolidated Account Statement:</strong> All invoice particulars, delivery GRN receipts, PO references, and overdue terms are itemized directly in the breakdown table above for direct settlement without downloading attachments.
      </div>

      {bank_html}

      <!-- Signoff -->
      <div style="margin-top: 28px; border-top: 1px solid #E2E8F0; padding-top: 18px; font-size: 13px; color: #64748B;">
        <p style="margin: 0 0 4px;">With regards,</p>
        <p style="margin: 0; font-weight: 700; color: #0F172A;">Finance & Accounts Team</p>
        <p style="margin: 0; color: #475569;">{company_name}</p>
        {f'<p style="margin: 4px 0 0; font-size: 12px;">Contact: {company_phone} | {company_email}</p>' if (company_phone or company_email) else ''}
      </div>
    </div>

    <!-- Footer -->
    <div style="background: #F8FAFC; border-top: 1px solid #E2E8F0; padding: 14px 28px; text-align: center; font-size: 11px; color: #94A3B8;">
      This is an automated consolidated overdue payment statement generated by SSK Footcare Manufacturing ERP.
    </div>
  </div>
</body>
</html>"""

    return (subject, text_body, html_body)


async def send_multi_invoice_payment_reminder(
    db,
    invoice_ids: List[str],
    to_email: str,
    cc_emails: Optional[Union[List[str], str]] = None,
    subject: Optional[str] = None,
    custom_message: Optional[str] = None,
    attach_pdfs: bool = False,
    include_bank_details: bool = True,
    user_email: str = "system",
) -> Dict[str, Any]:
    """
    Send a consolidated payment reminder email covering multiple overdue invoices,
    attaching all available PDFs and updating reminder history on each invoice.
    """
    from bson import ObjectId
    import routes.invoice_packing as ip_routes

    if not invoice_ids:
        return {"ok": False, "error": "No invoice IDs provided"}

    # 1. Fetch email config
    cfg = await get_email_config(db)
    if not cfg["is_configured"]:
        return {
            "ok": False,
            "error": "Gmail connection is not configured in ERP settings. Please navigate to Settings to connect your company Gmail address and App Password."
        }

    clean_oids = []
    for x in invoice_ids:
        try:
            clean_oids.append(ObjectId(x))
        except Exception:
            clean_oids.append(x)

    docs = await db.invoices.find({"_id": {"$in": clean_oids}}).to_list(100)
    if not docs:
        return {"ok": False, "error": "No matching invoices found"}

    str_ids = [str(d["_id"]) for d in docs]
    pay_map = await ip_routes._aggregate_payments_for_invoices(str_ids, db=db)
    grn_map = await ip_routes._aggregate_grn_adjustments(str_ids, db=db)
    decorated_invoices = [ip_routes._decorate_invoice(d, pay_map, grn_map) for d in docs]

    # Resolve client doc
    client_name = decorated_invoices[0].get("client_name") or ""
    client_doc = {}
    if client_name:
        client_doc = await db.clients.find_one({
            "$or": [
                {"company_name": {"$regex": f"^{re.escape(client_name)}$", "$options": "i"}},
                {"name": {"$regex": f"^{re.escape(client_name)}$", "$options": "i"}},
            ]
        }) or {}

    company_profile = await db.settings.find_one({"_id": "company_profile"})
    if not company_profile:
        from pdf_docs import COMPANY
        company_profile = dict(COMPANY)

    # 2. Build template
    tmpl_subj, tmpl_txt, tmpl_html = build_multi_invoice_reminder_template(
        invoices=decorated_invoices,
        client=client_doc,
        company=company_profile,
        custom_message=custom_message,
        include_bank_details=include_bank_details,
    )
    final_subject = subject.strip() if subject else tmpl_subj

    # 3. Attachments
    attachments = []
    if attach_pdfs:
        for doc in docs:
            inv_no = doc.get("invoice_no", "invoice")
            pdf_raw = None
            if doc.get("file_b64"):
                try:
                    pdf_raw = base64.b64decode(doc["file_b64"])
                except Exception:
                    pass
            if not pdf_raw and doc.get("dispatch_record_id"):
                try:
                    dr = await db.dispatch_records.find_one({"_id": ObjectId(doc["dispatch_record_id"])})
                    if dr and dr.get("invoice_file_b64"):
                        pdf_raw = base64.b64decode(dr["invoice_file_b64"])
                except Exception:
                    pass
            if pdf_raw:
                attachments.append({
                    "filename": f"{inv_no}.pdf",
                    "content": pdf_raw,
                    "mime_type": "application/pdf"
                })

    final_cc = cc_emails or cfg.get("default_cc")

    # 4. Send email in threadpool executor without blocking the asyncio loop
    ok, msg_or_err = await async_send_email(
        to_emails=to_email,
        subject=final_subject,
        text_body=tmpl_txt,
        html_body=tmpl_html,
        cc_emails=final_cc,
        attachments=attachments,
        config=cfg,
    )
    if not ok:
        return {"ok": False, "error": msg_or_err}

    # 5. Update reminder history on all invoices
    total_due = sum(inv.get("outstanding", 0) for inv in decorated_invoices)
    all_nos = [inv.get("invoice_no") for inv in decorated_invoices if inv.get("invoice_no")]
    reminder_event = {
        "sent_at": now_iso(),
        "sent_to": to_email,
        "sent_cc": final_cc or "",
        "sent_by": user_email,
        "subject": final_subject,
        "batch_invoices": all_nos,
        "batch_count": len(decorated_invoices),
        "total_outstanding_at_send": total_due,
        "attached_pdfs_count": len(attachments),
    }

    try:
        await db.invoices.update_many(
            {"_id": {"$in": clean_oids}},
            {
                "$push": {"reminder_history": reminder_event},
                "$set": {
                    "last_reminder_sent_at": reminder_event["sent_at"],
                    "last_reminder_sent_to": to_email,
                },
                "$inc": {"reminder_count": 1},
            }
        )
    except Exception as e:
        log.warning("Could not persist reminder_history for batch invoices: %s", e)

    # 6. Audit log
    try:
        await db.audit_logs.insert_one({
            "action": "send_multi_invoice_payment_reminder",
            "category": "invoices",
            "details": f"Sent consolidated overdue payment reminder for {len(decorated_invoices)} invoices ({', '.join(all_nos)}) to {to_email} (Total Due: ₹{total_due})",
            "by": user_email,
            "created_at": now_iso(),
        })
    except Exception:
        pass

    return {
        "ok": True,
        "message": f"Consolidated overdue reminder for {len(decorated_invoices)} invoices sent to {to_email}",
        "invoices_count": len(decorated_invoices),
        "total_outstanding": total_due,
        "reminder": reminder_event,
    }
