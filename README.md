# CBSE Class X Result Checker

Monitors DigiLocker + results.cbse.nic.in every 5 min via GitHub Actions.
Sends an email the moment CBSE Class X 2026 results go live.

## Setup (5 steps)

### 1. Create a GitHub repo
- Go to github.com → New repository → name it `cbse-checker` → Public or Private → Create

### 2. Push this folder
```bash
cd ~/Desktop/cbse_result_checker
git init
git add .
git commit -m "init"
git remote add origin https://github.com/YOUR_USERNAME/cbse-checker.git
git push -u origin main
```

### 3. Get Gmail App Password
- Go to myaccount.google.com → Security → 2-Step Verification (enable if not done)
- Then → App passwords → Select app: Mail → Generate
- Copy the 16-character password

### 4. Add GitHub Secrets
Go to your repo → Settings → Secrets and variables → Actions → New repository secret

| Secret Name        | Value                        |
|--------------------|------------------------------|
| GMAIL_USER         | your.email@gmail.com         |
| GMAIL_APP_PASSWORD | xxxx xxxx xxxx xxxx          |
| NOTIFY_EMAIL       | email to receive alert (can be same) |

### 5. Enable Actions
Go to Actions tab in your repo → Enable workflows

That's it! Checker runs every 5 minutes automatically.
