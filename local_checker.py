#!/usr/bin/env python3
"""
CBSE Class X 2026 Result Checker — LOCAL version
Run this on your own Mac. Checks every 3 minutes.
Plays a sound + prints alert when result goes live.

Usage:
    pip install requests beautifulsoup4 playwright
    playwright install chromium
    python local_checker.py
"""

import os, sys, time, requests
from bs4 import BeautifulSoup
from datetime import datetime

NIC_URL      = "https://results.cbse.nic.in/"
NIC2_URL     = "https://cbseresults.nic.in/"
CBSE_GOV_URL = "https://www.cbse.gov.in/cbsenew/CBSE_Main_Site/main/announcements.html"
DIGILOCKER   = "https://results.digilocker.gov.in/"
FLAG_FILE    = "notified_local.flag"
INTERVAL     = 180   # seconds between checks
HEADERS      = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
CLASS_X_KEYS    = ["class x", "class 10", "secondary", "x result", "10th", "class-x", "10 result"]
CLASS_X_EXCLUDE = ["class xii", "class 12", "12th", "senior secondary", "aissce", "xii result"]


# ── Source 1: DigiLocker (works on residential IPs, blocked on cloud) ─────────
import re as _re
_STATE_BOARD_RE = _re.compile(r'^[A-Z]{2}20\d{2}', _re.IGNORECASE)  # e.g. MP2026..., UP2026...

def check_digilocker():
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(DIGILOCKER, timeout=60000, wait_until="networkidle")
            page.wait_for_timeout(2000)
            html = page.content()
            browser.close()

        soup = BeautifulSoup(html, "html.parser")

        # Find the CBSE-specific card div
        cbse_card = (
            soup.find("div", class_=lambda c: c and ("CISCE" in c or "CBSE" in c))
            or soup.find("div", class_=lambda c: c and "cbse" in c.lower())
        )
        if cbse_card:
            # Search ONLY inside the CBSE card — never in its parent (other boards live there)
            btn = cbse_card.find("a", href=True)
            if btn:
                href = btn.get("href", "").strip()
                text = btn.get_text(strip=True)
                print(f"  [DigiLocker CBSE card] text='{text}' href='{href}'")

                # Reject if href looks like another state board file (MP2026..., UP2026...)
                if _STATE_BOARD_RE.match(href):
                    return False, f"State-board link ignored: {href}"

                is_coming_soon = "coming soon" in text.lower()
                # A real CBSE result link points to an http URL or a non-empty non-# path
                is_real_link = href.startswith("http") or (
                    href and href not in ("#", "javascript:void(0)", "")
                    and not _STATE_BOARD_RE.match(href)
                )
                if not is_coming_soon and is_real_link:
                    return True, f"'{text}' -> {href}"
                return False, f"Coming Soon or no valid link ({text} | {href})"
            return False, "CBSE card visible but no link yet"

        return False, "CBSE card not found on DigiLocker page"
    except Exception as e:
        return None, f"DigiLocker error: {e}"


# ── Source 2: results.cbse.nic.in ─────────────────────────────────────────────
def check_nic():
    try:
        soup = BeautifulSoup(requests.get(NIC_URL, headers=HEADERS, timeout=15).text, "html.parser")
        for a in soup.find_all("a", href=True):
            t = a.get_text(strip=True)
            t_lower = t.lower()
            if (
                "2026" in t
                and any(k in t_lower for k in CLASS_X_KEYS)
                and "cbse" in t_lower
                and not any(ex in t_lower for ex in CLASS_X_EXCLUDE)
            ):
                return True, f"'{t}' -> {a['href']}"
        links = [a.get_text(strip=True) for a in soup.find_all("a", href=True)
                 if "cbse" in a.get_text(strip=True).lower()][:4]
        return False, f"CBSE links found: {links}"
    except Exception as e:
        return None, f"NIC error: {e}"


# ── Source 3: cbseresults.nic.in (result entry form goes live on result day) ──
def check_nic2():
    try:
        resp = requests.get(NIC2_URL, headers=HEADERS, timeout=15, allow_redirects=True)
        soup = BeautifulSoup(resp.text, "html.parser")
        text_lower = resp.text.lower()
        # Roll-number input = some result entry form is live — verify it's CBSE Class X
        if soup.find("input", {"name": lambda n: n and "roll" in n.lower()}):
            is_cbse   = "cbse" in text_lower
            is_class_x = any(k in text_lower for k in CLASS_X_KEYS)
            is_not_xii = not any(ex in text_lower for ex in ["class xii", "class 12", "senior secondary", "aissce"])
            if is_cbse and is_class_x and is_not_xii:
                return True, f"CBSE Class X result entry form is live at {NIC2_URL}"
            else:
                return False, f"Roll input found but not CBSE Class X (cbse={is_cbse}, classX={is_class_x})"
        if any(p in text_lower for p in ["not available", "coming soon", "will be declared"]):
            return False, "Not live yet"
        return None, f"Unexpected response (status {resp.status_code})"
    except Exception as e:
        return None, f"cbseresults error: {e}"


# ── Source 4: cbse.gov.in announcements ───────────────────────────────────────
def check_cbse_gov():
    try:
        soup = BeautifulSoup(requests.get(CBSE_GOV_URL, headers=HEADERS, timeout=15).text, "html.parser")
        for a in soup.find_all("a", href=True):
            t = a.get_text(strip=True)
            t_lower = t.lower()
            if (
                "2026" in t
                and any(k in t_lower for k in CLASS_X_KEYS)
                and any(w in t_lower for w in ["result", "declared", "available", "announce"])
                and not any(ex in t_lower for ex in CLASS_X_EXCLUDE)
            ):
                return True, f"'{t}' -> {a['href']}"
        return False, "No announcement yet"
    except Exception as e:
        return None, f"cbse.gov error: {e}"


# ── Alert ─────────────────────────────────────────────────────────────────────
def alert(summary, link):
    # macOS notification + sound
    os.system(f'osascript -e \'display notification "CBSE Class X result is LIVE! Check {link}" with title "RESULT IS LIVE"\' ')
    os.system("afplay /System/Library/Sounds/Glass.aiff")
    print("\n" + "="*60)
    print("  *** CBSE CLASS X 2026 RESULT IS LIVE ***")
    print(f"  {summary}")
    print(f"  Open: {link}")
    print("="*60 + "\n")


# ── Main loop ─────────────────────────────────────────────────────────────────
print("CBSE Class X 2026 Result Checker — LOCAL")
print(f"Checking every {INTERVAL//60} minutes. Press Ctrl+C to stop.\n")

if os.path.exists(FLAG_FILE):
    print("notified_local.flag exists — already alerted once.")
    print("Delete the file 'notified_local.flag' if you want to re-run.\n")

run = 0
while True:
    run += 1
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] Run #{run}")

    results = {
        "DigiLocker         ": check_digilocker(),
        "results.cbse.nic.in": check_nic(),
        "cbseresults.nic.in ": check_nic2(),
        "cbse.gov.in        ": check_cbse_gov(),
    }

    found, summary, link = False, "", ""
    for source, (avail, detail) in results.items():
        status = "LIVE — " + detail if avail else detail
        print(f"  {source}: {status}")
        if avail and not found:
            found, summary, link = True, detail, source.strip()

    if found and not os.path.exists(FLAG_FILE):
        alert(summary, link)
        with open(FLAG_FILE, "w") as f:
            f.write(f"Alerted at {ts}\n{summary}\n")
        print("Flag written. Will not alert again unless you delete 'notified_local.flag'.")
    elif not found:
        print(f"  → Not live yet. Next check in {INTERVAL//60} min...\n")

    time.sleep(INTERVAL)
