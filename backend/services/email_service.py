"""Email service for SSK Footcare ERP.

Handles Gmail SMTP connection, authentication testing, transactional email dispatch,
and branded Payment Reminders with invoice PDF attachments.
"""

import os
import re
import base64
import smtplib
import socket
import logging
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from typing import Dict, Any, List, Optional, Tuple

log = logging.getLogger("email_service")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean_app_password(pwd: Optional[str]) -> str:
    """Strip spaces often inserted by Google when displaying 16-character App Passwords."""
    if not pwd:
        return ""
    return re.sub(r"\s+", "", pwd.strip())


async def get_email_config(db=None) -> Dict[str, Any]:
    """Retrieve email configuration from MongoDB settings or fallback to environment variables."""
    cfg = {
        "gmail_user": "",
        "gmail_app_password": "",
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
                if doc.get("gmail_user"):
                    cfg["gmail_user"] = str(doc.get("gmail_user", "")).strip()
                if doc.get("gmail_app_password"):
                    cfg["gmail_app_password"] = clean_app_password(doc.get("gmail_app_password", ""))
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
                if cfg["gmail_user"] and cfg["gmail_app_password"]:
                    cfg["is_configured"] = True
                    cfg["source"] = "database"
        except Exception as e:
            log.warning("Could not read email_config from db: %s", e)

    # 2. Fall back to environment variables if not configured via database
    if not cfg["is_configured"]:
        env_user = os.environ.get("GMAIL_USER", "").strip()
        env_pass = clean_app_password(os.environ.get("GMAIL_APP_PASSWORD", ""))
        env_from = os.environ.get("GMAIL_FROM_NAME", "").strip()
        env_reply_to = os.environ.get("GMAIL_REPLY_TO", "").strip()
        env_cc = os.environ.get("GMAIL_DEFAULT_CC", "").strip()

        if env_user:
            cfg["gmail_user"] = env_user
        if env_pass:
            cfg["gmail_app_password"] = env_pass
        if env_from:
            cfg["from_name"] = env_from
        if env_reply_to:
            cfg["reply_to"] = env_reply_to
        if env_cc:
            cfg["default_cc"] = env_cc

        if cfg["gmail_user"] and cfg["gmail_app_password"]:
            cfg["is_configured"] = True
            cfg["source"] = "environment"

    return cfg


def verify_smtp_credentials(
    smtp_host: str,
    smtp_port: int,
    user: str,
    password: str,
    timeout: int = 15
) -> Tuple[bool, str]:
    """Verify SMTP login credentials against the given host and port."""
    u = (user or "").strip()
    p = clean_app_password(password)
    host = (smtp_host or "smtp.gmail.com").strip()
    port = int(smtp_port or 465)

    if not u or not p:
        return (False, "Both Gmail address and Google App Password are required.")

    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=timeout) as smtp:
                smtp.login(u, p)
        else:
            with smtplib.SMTP(host, port, timeout=timeout) as smtp:
                smtp.ehlo()
                smtp.starttls()
                smtp.login(u, p)
        return (True, f"Successfully authenticated with {host}:{port} as {u}")
    except smtplib.SMTPAuthenticationError as e:
        log.warning("Gmail SMTP authentication failed: %s", e)
        return (
            False,
            "Gmail authentication failed. Please verify that 2-Step Verification is enabled on your "
            "Google Account and you are using a 16-character Google App Password (not your normal password)."
        )
    except (socket.timeout, TimeoutError):
        log.warning("Gmail SMTP connection timed out connecting to %s:%s", host, port)
        return (False, f"Connection to {host}:{port} timed out after {timeout} seconds.")
    except smtplib.SMTPConnectError as e:
        log.warning("Gmail SMTP connection error: %s", e)
        return (False, f"Could not establish connection to {host}:{port}: {e}")
    except Exception as e:
        log.exception("Unexpected error verifying Gmail credentials")
        return (False, f"Connection test failed: {e}")


def send_email(
    to_emails: List[str] | str,
    subject: str,
    text_body: str,
    html_body: str,
    cc_emails: Optional[List[str] | str] = None,
    bcc_emails: Optional[List[str] | str] = None,
    attachments: Optional[List[Dict[str, Any]]] = None,
    config: Optional[Dict[str, Any]] = None,
    timeout: int = 20,
) -> Tuple[bool, str]:
    """Dispatch an email via Gmail SMTP with optional PDF/file attachments."""
    if not config or not config.get("is_configured"):
        return (False, "Gmail is not configured in ERP settings or environment variables.")

    gmail_user = config["gmail_user"]
    gmail_pass = config["gmail_app_password"]
    from_name = config.get("from_name") or "SSK Footcare Manufacturing"
    reply_to = config.get("reply_to") or ""
    smtp_host = config.get("smtp_host") or "smtp.gmail.com"
    smtp_port = int(config.get("smtp_port") or 465)

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

    # Build root MIME container
    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = f"{from_name} <{gmail_user}>"
    msg["To"] = ", ".join(to_list)
    if cc_list:
        msg["Cc"] = ", ".join(cc_list)
    if reply_to:
        msg["Reply-To"] = reply_to
    msg["Date"] = smtplib.email.utils.formatdate(localtime=True)

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
        if smtp_port == 465:
            with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=timeout) as smtp:
                smtp.login(gmail_user, gmail_pass)
                smtp.sendmail(gmail_user, all_recipients, msg.as_string())
        else:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=timeout) as smtp:
                smtp.ehlo()
                smtp.starttls()
                smtp.login(gmail_user, gmail_pass)
                smtp.sendmail(gmail_user, all_recipients, msg.as_string())
        return (True, f"Email sent successfully to {', '.join(to_list)}")
    except smtplib.SMTPAuthenticationError:
        log.exception("Gmail SMTP auth failed during send")
        return (False, "Gmail authentication failed. Please check your Google App Password.")
    except Exception as e:
        log.exception("Gmail SMTP send failed")
        return (False, f"Failed to send email: {e}")


def format_inr(amount: float) -> str:
    """Format numeric amount into Indian Rupee style with commas (e.g. ₹1,23,456.00)."""
    try:
        val = float(amount or 0)
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


def build_payment_reminder_template(
    invoice: Dict[str, Any],
    client: Dict[str, Any],
    company: Dict[str, Any],
    custom_message: Optional[str] = None,
    include_bank_details: bool = True,
) -> Tuple[str, str, str]:
    """
    Generate subject, plaintext body, and modern responsive HTML for a payment reminder.
    Returns: (subject, text_body, html_body)
    """
    inv_no = invoice.get("invoice_no") or "Invoice"
    client_name = client.get("company_name") or client.get("name") or invoice.get("client_name") or "Valued Customer"
    contact_person = client.get("contact_person") or ""
    po_no = invoice.get("po_number") or "N/A"
    inv_date = invoice.get("invoice_date") or invoice.get("date") or "N/A"
    due_date = invoice.get("due_date") or "Immediate"
    net_amount = float(invoice.get("net_amount") or 0)
    received_amount = float(invoice.get("received_amount") or 0)
    outstanding = float(invoice.get("outstanding") if invoice.get("outstanding") is not None else (net_amount - received_amount))

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
                f"overdue by {days_overdue} day(s). Kindly arrange the remittance of the outstanding balance "
                f"at your earliest convenience."
            )
        else:
            user_msg = (
                f"This is a gentle reminder regarding the outstanding balance for Invoice #{inv_no}. "
                f"Kindly review the invoice details below and arrange for payment on or before the due date."
            )
    else:
        user_msg = custom_message.strip()

    # Plaintext version
    text_parts = [
        f"PAYMENT REMINDER — {company_name.upper()}",
        "=" * 50,
        f"\nDear {greeting_name},",
        f"\n{user_msg}\n",
        "-" * 50,
        "INVOICE SUMMARY:",
        f"  Invoice Number  : {inv_no}",
        f"  Invoice Date    : {inv_date}",
        f"  Due Date        : {due_date} {'(OVERDUE by ' + str(days_overdue) + ' days)' if is_overdue else ''}",
        f"  Purchase Order  : {po_no}",
        f"  Total Amount    : {format_inr(net_amount)}",
        f"  Amount Received : {format_inr(received_amount)}",
        f"  OUTSTANDING DUE : {format_inr(outstanding)}",
        "-" * 50,
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
    badge_text = f"OVERDUE · {days_overdue} DAYS" if is_overdue else "PAYMENT DUE"

    bank_html = ""
    if include_bank_details and bank_acc:
        bank_html = f"""
        <div style="margin-top: 24px; padding: 18px; background: #F8FAFC; border: 1px solid #CBD5E1; border-left: 4px solid #0F172A;">
          <div style="font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 1.5px; color: #475569; margin-bottom: 10px;">
            Bank Remittance Information
          </div>
          <table style="width: 100%; font-size: 13px; border-collapse: collapse; line-height: 1.6;">
            <tr>
              <td style="color: #64748B; width: 140px; padding: 3px 0;">Beneficiary:</td>
              <td style="color: #0F172A; font-weight: 600; padding: 3px 0;">{company_name}</td>
            </tr>
            <tr>
              <td style="color: #64748B; padding: 3px 0;">Bank Name:</td>
              <td style="color: #0F172A; font-weight: 600; padding: 3px 0;">{bank_name}</td>
            </tr>
            <tr>
              <td style="color: #64748B; padding: 3px 0;">Account Number:</td>
              <td style="color: #0F172A; font-family: 'Courier New', monospace; font-size: 14px; font-weight: 700; padding: 3px 0;">{bank_acc}</td>
            </tr>
            <tr>
              <td style="color: #64748B; padding: 3px 0;">IFSC Code:</td>
              <td style="color: #0F172A; font-family: 'Courier New', monospace; font-size: 14px; font-weight: 700; padding: 3px 0;">{bank_ifsc}</td>
            </tr>
            {f'<tr><td style="color: #64748B; padding: 3px 0;">UPI ID:</td><td style="color: #0F172A; font-weight: 600; padding: 3px 0;">{upi_id}</td></tr>' if upi_id else ''}
          </table>
          <div style="margin-top: 10px; font-size: 11px; color: #64748B;">
            * Kindly send the UTR / transaction receipt to this email once transferred for prompt ledger credit.
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
  <div style="max-width: 620px; margin: 0 auto; background: #FFFFFF; border: 2px solid #0F172A; box-shadow: 4px 4px 0px #0F172A;">
    
    <!-- Header -->
    <div style="background: #0F172A; padding: 24px 28px; color: #FFFFFF;">
      <table style="width: 100%;">
        <tr>
          <td>
            <div style="font-size: 10px; letter-spacing: 2px; text-transform: uppercase; color: #94A3B8; font-weight: 700;">
              SSK Footcare ERP · Accounts Department
            </div>
            <div style="font-size: 20px; font-weight: 800; letter-spacing: 0.5px; margin-top: 4px;">
              {company_name}
            </div>
          </td>
          <td style="text-align: right; vertical-align: top;">
            <span style="display: inline-block; padding: 4px 10px; font-size: 10px; font-weight: 800; letter-spacing: 1.5px; text-transform: uppercase; background: {badge_bg}; color: {badge_color}; border: 1px solid {badge_border}; border-radius: 2px;">
              {badge_text}
            </span>
          </td>
        </tr>
      </table>
    </div>

    <!-- Body -->
    <div style="padding: 28px;">
      <p style="font-size: 15px; margin: 0 0 16px; color: #0F172A;">
        Dear <strong>{greeting_name}</strong>,
      </p>
      
      <p style="font-size: 14px; line-height: 1.6; margin: 0 0 20px; color: #334155;">
        {user_msg}
      </p>

      <!-- Invoice Breakdown Card -->
      <div style="background: #F8FAFC; border: 1px solid #E2E8F0; padding: 16px 20px; margin-bottom: 20px;">
        <div style="font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 1.5px; color: #64748B; margin-bottom: 12px; border-bottom: 1px solid #E2E8F0; padding-bottom: 6px;">
          Invoice Details & Balance Breakdown
        </div>
        <table style="width: 100%; font-size: 13px; border-collapse: collapse;">
          <tr>
            <td style="padding: 5px 0; color: #64748B;">Invoice Number:</td>
            <td style="padding: 5px 0; font-family: 'Courier New', monospace; font-weight: 700; text-align: right; color: #0F172A;">{inv_no}</td>
          </tr>
          <tr>
            <td style="padding: 5px 0; color: #64748B;">Invoice Date:</td>
            <td style="padding: 5px 0; font-weight: 600; text-align: right; color: #0F172A;">{inv_date}</td>
          </tr>
          <tr>
            <td style="padding: 5px 0; color: #64748B;">Due Date:</td>
            <td style="padding: 5px 0; font-weight: 700; text-align: right; color: {'#DC2626' if is_overdue else '#0F172A'};">
              {due_date} {f'({days_overdue} days overdue)' if is_overdue else ''}
            </td>
          </tr>
          <tr>
            <td style="padding: 5px 0; color: #64748B;">Purchase Order (PO):</td>
            <td style="padding: 5px 0; text-align: right; color: #0F172A;">{po_no}</td>
          </tr>
          <tr style="border-top: 1px dashed #CBD5E1;">
            <td style="padding: 8px 0 4px; color: #64748B;">Total Invoice Amount:</td>
            <td style="padding: 8px 0 4px; font-family: 'Courier New', monospace; text-align: right; color: #0F172A;">{format_inr(net_amount)}</td>
          </tr>
          <tr>
            <td style="padding: 4px 0; color: #64748B;">Amount Received:</td>
            <td style="padding: 4px 0; font-family: 'Courier New', monospace; text-align: right; color: #16A34A;">{format_inr(received_amount)}</td>
          </tr>
          <tr style="border-top: 2px solid #0F172A;">
            <td style="padding: 10px 0 4px; font-size: 14px; font-weight: 800; color: #0F172A; text-transform: uppercase; letter-spacing: 0.5px;">
              Outstanding Balance Due:
            </td>
            <td style="padding: 10px 0 4px; font-family: 'Courier New', monospace; font-size: 18px; font-weight: 800; text-align: right; color: #DC2626;">
              {format_inr(outstanding)}
            </td>
          </tr>
        </table>
      </div>

      <!-- Attachment notice -->
      <div style="font-size: 12px; color: #64748B; background: #F1F5F9; padding: 10px 14px; border-left: 3px solid #64748B; margin-bottom: 20px;">
        📎 <strong>Invoice Copy Attached:</strong> The complete tax invoice PDF (<b>{inv_no}.pdf</b>) is attached to this email for your accounts reconciliation.
      </div>

      {bank_html}

      <div style="margin-top: 28px; border-top: 1px solid #E2E8F0; padding-top: 18px; font-size: 13px; color: #64748B;">
        <p style="margin: 0 0 4px;">With regards,</p>
        <p style="margin: 0; font-weight: 700; color: #0F172A;">Finance & Accounts Team</p>
        <p style="margin: 0; color: #475569;">{company_name}</p>
        {f'<p style="margin: 4px 0 0; font-size: 12px;">Contact: {company_phone} | {company_email}</p>' if (company_phone or company_email) else ''}
      </div>
    </div>

    <!-- Footer -->
    <div style="background: #F8FAFC; border-top: 1px solid #E2E8F0; padding: 14px 28px; text-align: center; font-size: 11px; color: #94A3B8;">
      This is an automated payment advisory generated by SSK Footcare Manufacturing ERP.
    </div>
  </div>
</body>
</html>"""

    return (subject, text_body, html_body)


async def send_invoice_payment_reminder(
    db,
    invoice_id: str,
    to_email: str,
    cc_emails: Optional[List[str] | str] = None,
    subject: Optional[str] = None,
    custom_message: Optional[str] = None,
    attach_pdf: bool = True,
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
            "error": "Gmail connection is not configured in ERP settings. Please navigate to Settings to connect your company Gmail address and App Password."
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

    # 7. Send email
    ok, msg_or_err = send_email(
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
