# LendFlow - GoDaddy Deployment Guide

**Application:** LendFlow (Loan Management System)
**Framework:** Flask 3.x, Python 3.9+
**Database:** SQLite (lendflow.db)
**Last Updated:** May 2026

---

## Table of Contents

1. [GoDaddy Hosting Options](#1-godaddy-hosting-options)
2. [Recommended Approach: cPanel Python Selector](#2-recommended-approach)
3. [Prepare Project for Production](#3-prepare-project-for-production)
4. [Step-by-Step Deployment](#4-step-by-step-deployment)
5. [Database Setup](#5-database-setup)
6. [Static Files & Uploads](#6-static-files--uploads)
7. [Domain & DNS Configuration](#7-domain--dns-configuration)
8. [SSL/HTTPS Setup](#8-sslhttps-setup)
9. [Post-Deployment Checklist](#9-post-deployment-checklist)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. GoDaddy Hosting Options

### Option A: cPanel Python Selector (Shared Hosting)

**How it works:** GoDaddy's cPanel includes a "Setup Python App" tool that uses Passenger (Phusion Passenger) to serve Python/Flask apps.

| Pros | Cons |
|------|------|
| Lower cost (~$6-12/month) | Python version may be limited (check available versions) |
| Built-in cPanel management | No root access (limited system-level control) |
| One-click app creation | SQLite file permissions can be tricky |
| Automatic app restarts | Performance limited by shared resources |
| SSL available via cPanel | Cannot install system packages (e.g., apt-get) |
| Good for low-medium traffic | Passenger can have cold-start delays |

### Option B: VPS (Virtual Private Server)

**How it works:** Full Linux server where you configure everything (Nginx, Gunicorn, Python, etc.).

| Pros | Cons |
|------|------|
| Full root access | Higher cost (~$15-50/month) |
| Any Python version | Requires Linux sysadmin knowledge |
| Better performance | Manual setup and maintenance |
| Full control over stack | You handle security updates |
| Better for high traffic | SSL setup is manual |

### Recommendation

**Use cPanel Python Selector** for LendFlow because:
- It's a Flask app with SQLite, which is lightweight
- Multi-role auth and loan management do not require heavy compute
- SMS notifications are external HTTP calls (BoxUganda API)
- File uploads are small (document images)
- Lower cost and easier maintenance
- cPanel handles SSL, restarts, and basic monitoring

**Only choose VPS if** you expect >100 concurrent users, need cron jobs beyond cPanel limits, or require custom system packages.

---

## 2. Recommended Approach: cPanel Python Selector

### Prerequisites

- GoDaddy cPanel hosting account (Linux-based)
- Domain pointed to GoDaddy nameservers
- SSH access enabled in cPanel (optional but recommended)
- Local copy of LendFlow project ready for deployment

---

## 3. Prepare Project for Production

### 3.1 Create Production Configuration

Create a `config.py` file in the project root:

```python
import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'generate-a-secure-random-key-here'
    DEBUG = False
    TESTING = False

class ProductionConfig(Config):
    DATABASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'lendflow.db')

class DevelopmentConfig(Config):
    DEBUG = True
```

### 3.2 Update app.py for Production

Ensure `app.py` has these production-ready changes:

```python
# Remove or guard this line:
# DO NOT leave this in production:
# app.run(debug=True, host='0.0.0.0', port=5000)

# Instead, use:
if __name__ == '__main__':
    app.run(debug=False)
```

### 3.3 Generate a Secure Secret Key

Run this in your Python terminal to generate a secret key:

```python
import secrets
print(secrets.token_hex(32))
```

Copy the output. You will set this as an environment variable during deployment.

### 3.4 Create Requirements File

Ensure `requirements.txt` is in the project root with pinned versions:

```
Flask==3.1.0
Werkzeug==3.1.3
gunicorn==23.0.0
```

Add any other dependencies your project uses (e.g., `requests` for BoxUganda API, `Pillow` for image uploads).

### 3.5 Create .htaccess for Passenger

Create `.htaccess` in the project root:

```apache
PassengerAppRoot "/home/USERNAME/lendflow"
PassengerAppType wsgi
PassengerStartupFile passenger_wsgi.py
PassengerPython /opt/alt/python39/bin/python3.9
PassengerAppEnv production
```

> **Note:** Adjust paths to match your cPanel home directory and available Python version.

### 3.6 Create passenger_wsgi.py

Create `passenger_wsgi.py` in the project root:

```python
import sys
import os

# Add project path
sys.path.insert(0, os.path.dirname(__file__))

# Set environment variable for secret key
os.environ['SECRET_KEY'] = 'YOUR_GENERATED_SECRET_KEY_HERE'

from app import app as application
```

### 3.7 Create .gitignore (if using Git)

```
__pycache__/
*.pyc
*.pyo
*.db
venv/
env/
.env
uploads/*
!uploads/.gitkeep
instance/
*.log
```

### 3.8 Production Checklist Before Upload

- [ ] `DEBUG = False` confirmed in app config
- [ ] Secret key is set via environment variable (not hardcoded in repo)
- [ ] `requirements.txt` is up to date
- [ ] `passenger_wsgi.py` is created
- [ ] No `app.run()` calls execute in production
- [ ] Error pages are customized (500.html, 404.html)
- [ ] Logging is configured for production

---

## 4. Step-by-Step Deployment

### Step 1: Access cPanel

1. Log in to your GoDaddy account
2. Navigate to **My Products** > **Web Hosting** > **Manage**
3. Click **cPanel Admin** to open cPanel

### Step 2: Create Python Application

1. In cPanel, scroll to **Software** section
2. Click **Setup Python App**
3. Click **+ CREATE APPLICATION**
4. Fill in the form:

   | Field | Value |
   |-------|-------|
   | Python version | 3.9 (or highest available) |
   | Application root | `lendflow` |
   | Application URL | Select your domain (e.g., `lendflow.example.com`) |
   | Application startup file | `passenger_wsgi.py` |
   | Application Entry Point | `application` |
   | Passenger log file | `passenger.log` (default) |

5. Click **CREATE**

### Step 3: Note the Virtual Environment Path

After creation, cPanel shows the **virtual environment path**. It looks like:

```
/home/USERNAME/virtualenv/lendflow/X.X/venv
```

**Copy this path.** You will need it in Step 5.

### Step 4: Upload Project Files

#### Option A: Via File Manager

1. In cPanel, go to **Files** > **File Manager**
2. Navigate to `/home/USERNAME/lendflow/` (the Application Root you set)
3. Upload all project files:
   - `app.py`
   - `config.py`
   - `passenger_wsgi.py`
   - `requirements.txt`
   - `templates/` directory (all .html files)
   - `static/` directory (all CSS, JS, images)
   - Any other Python modules (e.g., `models.py`, `routes.py`)

#### Option B: Via SSH/SCP (Recommended for Large Projects)

```bash
# Compress project locally (exclude venv, __pycache__, .db)
cd ~/Downloads/LendFlow/
tar -czf lendflow.tar.gz \
  --exclude='__pycache__' \
  --exclude='venv' \
  --exclude='*.db' \
  --exclude='.git' \
  .

# Upload via SCP
scp lendflow.tar.gz USERNAME@SERVER_IP:/home/USERNAME/

# SSH into server
ssh USERNAME@SERVER_IP

# Extract in the application root
cd /home/USERNAME/lendflow
tar -xzf ~/lendflow.tar.gz
rm ~/lendflow.tar.gz
```

### Step 5: Install Dependencies

1. Go back to **Setup Python App** in cPanel
2. Find your LendFlow app and click the **Edit** (pencil) icon
3. Scroll to the **pip** section
4. Upload or paste your `requirements.txt` content
5. Click **Install/Update**

**OR via SSH:**

```bash
# Activate the virtual environment
source /home/USERNAME/virtualenv/lendflow/X.X/venv/bin/activate

# Navigate to app directory
cd /home/USERNAME/lendflow

# Install dependencies
pip install -r requirements.txt
```

### Step 6: Set Environment Variables

In cPanel **Setup Python App** > Edit your app > **Environment Variables**:

| Variable | Value |
|----------|-------|
| `FLASK_ENV` | `production` |
| `SECRET_KEY` | Your generated secret key |
| `DATABASE_PATH` | `/home/USERNAME/lendflow/lendflow.db` |

Click **Save**.

### Step 7: Restart the Application

In **Setup Python App**, click the **Restart** button (circular arrow icon) next to your app.

### Step 8: Verify Deployment

Open your application URL in a browser:

```
https://lendflow.example.com
```

If you see a **500 error**, check the Passenger log:

```bash
# Via SSH
cat /home/USERNAME/lendflow/passenger.log

# Or in cPanel File Manager, navigate to:
# /home/USERNAME/lendflow/passenger.log
```

---

## 5. Database Setup

### 5.1 Create the SQLite Database

SQLite databases are single files. The database will be created automatically if your app has initialization code like this in `app.py`:

```python
import sqlite3
import os

DATABASE = os.environ.get('DATABASE_PATH', 'lendflow.db')

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db

def init_db():
    db = get_db()
    with open('schema.sql', 'r') as f:
        db.executescript(f.read())
```

### 5.2 Initialize the Database

Run this once via SSH after deployment:

```bash
source /home/USERNAME/virtualenv/lendflow/X.X/venv/bin/activate
cd /home/USERNAME/lendflow

# If you have a schema.sql file:
python -c "
from app import app, init_db
with app.app_context():
    init_db()
print('Database initialized successfully.')
"
```

### 5.3 Set Database Permissions

The database file must be writable by the web server:

```bash
cd /home/USERNAME/lendflow

# Create database if it doesn't exist
touch lendflow.db

# Set correct permissions
chmod 664 lendflow.db
chmod 775 .

# Ensure the directory is writable
ls -la lendflow.db
```

### 5.4 Seed Initial Data

If you need an admin user or default data:

```bash
python -c "
from app import app
from your_models import create_admin_user
with app.app_context():
    create_admin_user(username='admin', password='CHANGE_ME')
print('Admin user created.')
"
```

### 5.5 Database Backup Strategy

Set up a cron job in cPanel for daily backups:

1. Go to **cPanel** > **Advanced** > **Cron Jobs**
2. Add a new cron job:

```
# Run daily at 2:00 AM
0 2 * * * cp /home/USERNAME/lendflow/lendflow.db /home/USERNAME/backups/lendflow_$(date +\%Y\%m\%d).db
```

3. Create the backups directory:

```bash
mkdir -p /home/USERNAME/backups
chmod 750 /home/USERNAME/backups
```

---

## 6. Static Files & Uploads

### 6.1 Static Files Directory

Flask serves static files automatically from the `static/` directory. No additional configuration needed.

Structure:

```
lendflow/
├── static/
│   ├── css/
│   ├── js/
│   ├── images/
│   └── uploads/          <-- User uploaded files
```

### 6.2 Configure Upload Path

In `app.py`, ensure uploads go to the correct absolute path:

```python
import os

UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max

# Create directory if it doesn't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
```

### 6.3 Set Upload Directory Permissions

```bash
cd /home/USERNAME/lendflow/static

# Create uploads directory
mkdir -p uploads

# Set permissions (writable by web server)
chmod 775 uploads
chmod 664 uploads/* 2>/dev/null  # For existing files

# Verify
ls -la uploads/
```

### 6.4 Create .gitkeep for Uploads

If tracking uploads in version control (not recommended), add:

```bash
touch static/uploads/.gitkeep
```

### 6.5 Test File Upload

1. Log in to LendFlow
2. Navigate to any upload feature (e.g., document submission)
3. Upload a test file
4. Verify the file appears in `/home/USERNAME/lendflow/static/uploads/`
5. Verify the file is accessible via URL: `https://lendflow.example.com/static/uploads/filename.ext`

### 6.6 Upload Cleanup (Optional)

Add a cron job to clean old uploads:

```
# Run weekly on Sunday at 3:00 AM
0 3 * * 0 find /home/USERNAME/lendflow/static/uploads/ -type f -mtime +90 -delete
```

---

## 7. Domain & DNS Configuration

### 7.1 Choose Your URL Type

| Type | Example | Setup Complexity |
|------|---------|------------------|
| Root domain | `lendflow.com` | Simple |
| Subdomain | `app.lendflow.com` | Simple |
| Subdirectory | `lendflow.com/app` | Moderate |

**Recommended:** Use a subdomain (`app.lendflow.com` or `lendflow.yourdomain.com`).

### 7.2 Point Domain to GoDaddy

If your domain is registered with GoDaddy:

1. Go to **My Products** > **Domains**
2. Click **DNS** next to your domain
3. Ensure nameservers are set to GoDaddy defaults

If your domain is registered elsewhere, update nameservers:

```
ns1.godaddy.com
ns2.godaddy.com
```

### 7.3 Create Subdomain in cPanel

1. Go to **cPanel** > **Domains** > **Subdomains**
2. Subdomain: `app` (or `lendflow`)
3. Domain: `yourdomain.com`
4. Document Root: It will auto-fill (e.g., `public_html/app`)
5. Click **Create**

### 7.4 Link Subdomain to Python App

When creating the Python app in Step 2, select this subdomain as the **Application URL**.

### 7.5 DNS Propagation

DNS changes can take up to 48 hours to propagate. Check status:

```bash
# Check if subdomain resolves
dig app.lendflow.com +short
nslookup app.lendflow.com

# Or use online tools:
# https://dnschecker.org/
```

---

## 8. SSL/HTTPS Setup

### 8.1 Enable AutoSSL (Free via cPanel)

GoDaddy provides free Let's Encrypt SSL certificates:

1. Go to **cPanel** > **Security** > **SSL/TLS Status**
2. Find your domain/subdomain
3. Check the box next to it
4. Click **Run AutoSSL**
5. Wait for confirmation (usually 5-15 minutes)

### 8.2 Force HTTPS Redirect

Add this to `.htaccess` in your application root to force HTTPS:

```apache
RewriteEngine On
RewriteCond %{HTTPS} off
RewriteRule ^(.*)$ https://%{HTTP_HOST}%{REQUEST_URI} [L,R=301]
```

Or in Flask `app.py`:

```python
from flask import redirect, request

@app.before_request
def enforce_https():
    if not request.is_secure and not app.debug:
        url = request.url.replace('http://', 'https://', 1)
        return redirect(url, code=301)
```

### 8.3 Verify SSL

```bash
# Check SSL certificate
curl -I https://app.lendflow.com

# Or visit in browser and check for padlock icon
# https://www.sslshopper.com/ssl-checker.html
```

### 8.4 HSTS Header (Optional but Recommended)

Add to `app.py`:

```python
@app.after_request
def add_security_headers(response):
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    return response
```

---

## 9. Post-Deployment Checklist

### Core Functionality

- [ ] **Homepage loads** without errors at `https://your-domain.com`
- [ ] **User registration** works (if applicable)
- [ ] **Login works** for all roles (admin, loan officer, borrower)
- [ ] **Logout works** and clears session properly
- [ ] **Password reset** flow works (if implemented)

### Loan Management Features

- [ ] **Create loan application** - form submits and saves to database
- [ ] **View loan list** - displays correctly with pagination
- [ ] **Loan status updates** - admin can approve/reject loans
- [ ] **Loan details view** - shows correct borrower information

### SMS Notifications

- [ ] **BoxUganda API calls** succeed (check Passenger logs)
- [ ] **SMS sent on loan creation** - borrower receives confirmation
- [ ] **SMS sent on status change** - borrower gets approval/rejection notification
- [ ] **API errors are logged** and do not crash the app
- [ ] **API credentials** are stored securely (environment variables, not in code)

### File Uploads

- [ ] **Upload a test document** - file saves to `static/uploads/`
- [ ] **Uploaded file is accessible** via browser URL
- [ ] **File size limits** are enforced
- [ ] **File type validation** works (if implemented)

### Security

- [ ] **HTTPS is enforced** - HTTP redirects to HTTPS
- [ ] **DEBUG mode is OFF** - confirmed in environment
- [ ] **Secret key is set** - not using default value
- [ ] **Error pages are customized** - no stack traces shown to users
- [ ] **Database file is not web-accessible** - cannot download `lendflow.db` via URL

### Performance

- [ ] **Page load time** is under 3 seconds
- [ ] **Static files are loading** (CSS, JS, images)
- [ ] **No memory leaks** - app runs for hours without slowing down
- [ ] **Database queries are indexed** (check `schema.sql` for indexes)

### Monitoring & Maintenance

- [ ] **Passenger logs** are accessible and being monitored
- [ ] **Database backup cron** is configured and running
- [ ] **Error notifications** are set up (email on errors)
- [ ] **Uptime monitoring** configured (use UptimeRobot, Pingdom, etc.)

---

## 10. Troubleshooting

### App Shows 500 Internal Server Error

```bash
# Check Passenger logs
cat /home/USERNAME/lendflow/passenger.log

# Common causes:
# 1. Missing dependencies - reinstall via pip
# 2. Wrong Python path in passenger_wsgi.py
# 3. Database permission denied
# 4. Secret key not set
```

### App Shows 404 Not Found

- Verify `passenger_wsgi.py` exports `application`
- Check Application URL in cPanel matches your domain
- Restart the Python app in cPanel

### Database Locked Error

```bash
# Fix permissions
chmod 664 /home/USERNAME/lendflow/lendflow.db
chmod 775 /home/USERNAME/lendflow/

# If database is corrupted, restore from backup
cp /home/USERNAME/backups/lendflow_YYYYMMDD.db /home/USERNAME/lendflow/lendflow.db
```

### SMS Notifications Not Sending

```python
# Add logging to BoxUganda API calls
import logging
logging.basicConfig(filename='sms_errors.log', level=logging.ERROR)

try:
    response = requests.post(BOXUGANDA_API_URL, data=payload)
    response.raise_for_status()
except Exception as e:
    logging.error(f'SMS failed: {e}')
```

### File Upload Fails

```bash
# Check directory permissions
ls -la /home/USERNAME/lendflow/static/uploads/

# Should show: drwxrwxr-x (775)

# Check disk space
df -h

# Ensure MAX_CONTENT_LENGTH is set in app config
```

### App is Slow

- Check Passenger logs for cold-start warnings
- Add `PassengerMinInstances 1` to `.htaccess` to keep app warm
- Enable gzip compression in `.htaccess`:

```apache
AddOutputFilterByType DEFLATE text/html text/css application/javascript
```

---

## Quick Reference

### Important Paths

```
Application root:  /home/USERNAME/lendflow/
Virtual env:       /home/USERNAME/virtualenv/lendflow/X.X/venv
Database:          /home/USERNAME/lendflow/lendflow.db
Static files:      /home/USERNAME/lendflow/static/
Uploads:           /home/USERNAME/lendflow/static/uploads/
Passenger log:     /home/USERNAME/lendflow/passenger.log
Backups:           /home/USERNAME/backups/
```

### Useful Commands

```bash
# Activate virtual environment
source /home/USERNAME/virtualenv/lendflow/X.X/venv/bin/activate

# Restart app (touch passenger_wsgi.py triggers restart)
touch /home/USERNAME/lendflow/passenger_wsgi.py

# Check Python version
python --version

# List installed packages
pip list

# Test database connection
python -c "import sqlite3; db = sqlite3.connect('lendflow.db'); print('OK'); db.close()"
```

### Emergency Rollback

1. Stop the app in cPanel
2. Restore database from backup: `cp /home/USERNAME/backups/latest.db /home/USERNAME/lendflow/lendflow.db`
3. Restore files from previous backup if needed
4. Restart the app
