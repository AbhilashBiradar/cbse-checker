#!/usr/bin/env python3
"""
CBSE Class X 2026 Result Checker — GitHub Actions cloud version
Sources: results.cbse.nic.in  +  cbseresults.nic.in  +  cbse.gov.in
DigiLocker (results.digilocker.gov.in) is behind CloudFront and blocks all
cloud/datacenter IPs — skipped.
"""

import os, sys, smtplib, requests
from bs4 import BeautifulSoup
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

NIC_URL      = "https://results.cbse.nic.in/"
NIC2_URL     = "https://cbseresults.nic.in/"
CBSE_GOV_URL = "https://www.cbse.gov.in/cbsenew/CBSE_Main_Site/main/announcements.html"
FLAG_FILE    = "notified.flag"
HEADERS      = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
CLASS_X_KEYS = ["class x", "class 10", "secondary", "x result", "10th", "class-x", "10 result"]

# ── Already notified? ─────────────────────────────────────────────────────────
if os.path.exists(FLAG_FILE):
    print("Already notified. Skipping.")
    sys.exit(0)


# ── Source 1: results.cbse.nic.in ─────────────────────────────────────────────
def check_nic():
    try:
        resp = requests.get(NIC_URL, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        # Look for 2026 results section
        section = next((h2.parent for h2 in soup.find_all("h2")
                        if "2026" in h2.get_text() and "result" in h2.get_text().lower()), None)
        if not section:
            # Fallback: scan all links on the page
            section = soup
        for a in section.find_all("a", href=True):
            t = a.get_text(strip=True).lower()
            h = a.get("href", "").strip()
            if any(k in t for k in CLASS_X_KEYS) and "2026" in a.get_text():
                return True, f"'{a.get_text(strip=True)}' -> {h}"
        links = [a.get_text(strip=True) for a in section.find_all("a")][:5]
        return False, f"No Class X 2026 link. Recent: {links}"
    except Exception as e:
        return None, str(e)


# ── Source 2: cbseresults.nic.in (goes live when results release) ──────────────
def check_nic2():
    """
    When results are live this page shows a result-entry form.
    When not live it shows a 'Results not available' message or redirects.
    We treat any page that contains a roll-number input as LIVE.
    """
    try:
        resp = requests.get(NIC2_URL, headers=HEADERS, timeout=15, allow_redirects=True)
        text_lower = resp.text.lower()
        soup = BeautifulSoup(resp.text, "html.parser")
        page_text = " ".join(soup.get_text(" ").split())[:300]
        print(f"  [cbseresults.nic.in preview]: {page_text}")

        # Roll-number input present → results entry form is live
        has_roll_input = bool(soup.find("input", {"name": lambda n: n and "roll" in n.lower()}))
        if has_roll_input:
            return True, f"Result entry form detected at {NIC2_URL}"

        # Explicit "not available" / "coming soon" text
        not_live_phrases = ["not available", "coming soon", "will be declared", "await"]
        if any(p in text_lower for p in not_live_phrases):
            snippet = next((p for p in not_live_phrases if p in text_lower), "")
            return False, f"Not live yet ('{snippet}' found)"

        # Page loaded with no form and no explicit wait message — inconclusive
        return None, f"Unexpected response (status {resp.status_code}, len={len(resp.text)})"
    except Exception as e:
        return None, str(e)


# ── Source 3: cbse.gov.in announcements ───────────────────────────────────────
def check_cbse_gov():
    try:
        resp = requests.get(CBSE_GOV_URL, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        for a in soup.find_all("a", href=True):
            t = a.get_text(strip=True)
            t_lower = t.lower()
            h = a.get("href", "").strip()
            if "2026" in t and any(k in t_lower for k in CLASS_X_KEYS):
                if any(w in t_lower for w in ["result", "declared", "available", "announce"]):
                    return True, f"'{t}' -> {h}"
        return False, "No Class X 2026 result announcement yet"
    except Exception as e:
        return None, str(e)


# ── Send Email via Gmail ───────────────────────────────────────────────────────
def send_email(subject, body):
    gmail_user     = os.environ.get("GMAIL_USER", "")
    gmail_password = os.environ.get("GMAIL_APP_PASSWORD", "")
    to_email       = os.environ.get("NOTIFY_EMAIL", gmail_user)

    if not gmail_user or not gmail_password:
        print("Email skipped — GMAIL_USER or GMAIL_APP_PASSWORD not set")
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = gmail_user
        msg["To"]      = to_email
        msg.attach(MIMEText(body, "plain"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail_user, gmail_password)
            server.sendmail(gmail_user, to_email, msg.as_string())
        print(f"Email sent to {to_email}")
        return True
    except Exception as e:
        print(f"Email error: {e}")
        return False


# ── Main ──────────────────────────────────────────────────────────────────────
ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
print(f"[{ts}] Checking sources...")

nic_avail,  nic_detail  = check_nic()
nic2_avail, nic2_detail = check_nic2()
gov_avail,  gov_detail  = check_cbse_gov()

print(f"  results.cbse.nic.in   : {'LIVE — ' + nic_detail  if nic_avail  else nic_detail}")
print(f"  cbseresults.nic.in    : {'LIVE — ' + nic2_detail if nic2_avail else nic2_detail}")
print(f"  cbse.gov.in           : {'LIVE — ' + gov_detail  if gov_avail  else gov_detail}")

found, summary, link = False, "", ""
for avail, detail, url in [
    (nic_avail,  nic_detail,  NIC_URL),
    (nic2_avail, nic2_detail, NIC2_URL),
    (gov_avail,  gov_detail,  CBSE_GOV_URL),
]:
    if avail:
        found, summary, link = True, detail, url
        break

if found:
    subject = "CBSE Class X 2026 Results are LIVE!"
    body = f"""CBSE Class X 2026 results are now available!

Detail  : {summary}
Check   : {link}

Detected at {ts}
"""
    print("\n*** RESULT IS LIVE ***")
    send_email(subject, body)
    with open(FLAG_FILE, "w") as f:
        f.write(f"Notified at {ts}\n{summary}\n")
    print("Flag written — no more notifications will be sent.")
else:
    print("Not live yet.")

sys.exit(0)
