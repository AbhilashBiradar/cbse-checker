#!/usr/bin/env python3
"""
CBSE Class X Result Checker — GitHub Actions cloud version
Monitors DigiLocker + results.cbse.nic.in every 5 min.
Sends email (Gmail) when result goes live. Writes a flag to stop repeat alerts.
"""

import os, sys, smtplib, requests
from bs4 import BeautifulSoup
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

NIC_URL = "https://results.cbse.nic.in/"
FLAG_FILE      = "notified.flag"

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

# ── Already notified? ─────────────────────────────────────────────────────────
if os.path.exists(FLAG_FILE):
    print("Already notified. Skipping.")
    sys.exit(0)


# ── Source 1: DigiLocker (playwright — real browser) ──────────────────────────
def check_digilocker():
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            # Wait until network is idle so JS-rendered cards are present
            page.goto("https://results.digilocker.gov.in/", timeout=60000,
                      wait_until="networkidle")
            # Extra buffer for slow cloud runners
            page.wait_for_timeout(3000)
            html = page.content()
            browser.close()

        soup = BeautifulSoup(html, "html.parser")

        # Dump a short preview for debugging (first 2000 chars stripped of tags)
        text_preview = " ".join(soup.get_text(" ").split())[:500]
        print(f"  [DigiLocker page text preview]: {text_preview}")

        # Strategy 1: look for div with class containing "CISCE" or "CBSE"
        cbse_card = (soup.find("div", class_=lambda c: c and ("CISCE" in c or "CBSE" in c))
                     or soup.find("div", class_=lambda c: c and "cbse" in c.lower()))

        if cbse_card:
            btn = (cbse_card.parent.find("a", class_=lambda c: c and "btn" in c)
                   or cbse_card.find("a", href=True))
            if btn:
                href = btn.get("href", "").strip()
                text = btn.get_text(strip=True)
                if "coming soon" not in text.lower() or href not in ("", "#"):
                    return True, f"'{text}' -> {href or 'https://results.digilocker.gov.in/'}"
                return False, f"CBSE card found — {text}"
            return False, "CBSE card found but no link yet"

        # Strategy 2: scan all <a> tags for CBSE + Class X
        page_lower = html.lower()
        if "cbse" in page_lower:
            for a in soup.find_all("a", href=True):
                t = a.get_text(strip=True)
                h = a.get("href", "").strip()
                if "cbse" in t.lower() and "class x" in t.lower():
                    if "coming soon" not in t.lower() and h not in ("", "#"):
                        return True, f"Link scan: '{t}' -> {h}"
            return False, "CBSE mentioned on page but no Class X result link yet"

        return None, f"CBSE not found on DigiLocker page (len={len(html)})"
    except Exception as e:
        return None, str(e)


# ── Source 2: results.cbse.nic.in ─────────────────────────────────────────────
def check_nic():
    try:
        soup = BeautifulSoup(requests.get(NIC_URL, headers=HEADERS, timeout=15).text, "html.parser")
        section = next((h2.parent for h2 in soup.find_all("h2")
                        if "2026" in h2.get_text() and "result" in h2.get_text().lower()), None)
        if not section:
            return None, "2026 Results section not found"
        for a in section.find_all("a", href=True):
            t = a.get_text(strip=True).lower()
            if any(k in t for k in ["class x", "class 10", "secondary", "x result", "10th"]):
                return True, f"'{a.get_text(strip=True)}' -> {a['href']}"
        return False, str([a.get_text(strip=True) for a in section.find_all("a")])
    except Exception as e:
        return None, str(e)

# ── Send Email via Gmail ───────────────────────────────────────────────────────
def send_email(subject, body):
    gmail_user     = os.environ.get("GMAIL_USER", "")      # your Gmail address
    gmail_password = os.environ.get("GMAIL_APP_PASSWORD", "")  # Gmail App Password
    to_email       = os.environ.get("NOTIFY_EMAIL", gmail_user) # who to notify

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
print(f"[{ts}] Checking both sources...")

dl_avail,  dl_detail  = check_digilocker()
nic_avail, nic_detail = check_nic()
print(f"  DigiLocker  : {'LIVE — ' + dl_detail if dl_avail else dl_detail}")
print(f"  cbse.nic.in : {'LIVE — ' + nic_detail if nic_avail else nic_detail}")

found, summary, link = False, "", ""
if dl_avail:
    found, summary, link = True, dl_detail, "https://results.digilocker.gov.in/"
elif nic_avail:
    found, summary, link = True, nic_detail, NIC_URL

if found:
    subject = "🎉 CBSE Class X 2026 Results are LIVE!"
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
