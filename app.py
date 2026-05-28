"""
LendFlow - Money Lending Management System
Main Application - Enhanced with profile pictures, loan IDs, fines
"""

import os
import traceback
import uuid
from datetime import datetime, timedelta, date
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_from_directory
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename
from app.database import (
    init_db, authenticate_user, get_user_by_id, create_user, update_user_profile_picture,
    get_client_profile, update_client_profile, create_loan, approve_loan,
    reject_loan, add_repayment, get_loans, get_loan, get_loan_by_number, get_repayments,
    get_notifications, mark_notification_read, mark_all_notifications_read,
    get_dashboard_stats, get_all_users, log_audit, send_notification,
    check_and_apply_fine, toggle_fine, apply_manual_fine, run_daily_checks,
    auto_apply_overdue_fines, UPLOAD_FOLDER,
    calculate_payment_schedule, get_monthly_pnl, get_balance_sheet, get_db,
    record_login_attempt, is_account_locked, change_password, get_failed_attempts,
    update_user, delete_user, get_all_repayments, update_repayment,
    delete_repayment, get_audit_logs, clear_demo_data
)
from app.notifications import (
    send_payment_reminder, send_loan_approved_notification,
    send_loan_rejected_notification, send_welcome_notification,
    send_payment_confirmation, run_daily_reminders, get_unread_count
)
from app.ai_service import (
    assess_credit_risk, generate_portfolio_insights,
    analyze_client, get_faq_response, get_dashboard_ai_data
)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'lendflow-secret-key-change-in-production')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5MB max
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

# Make datetime available in all templates
@app.context_processor
def inject_datetime():
    return {'datetime': datetime, 'date': date}

# Session security configuration
app.config['SESSION_COOKIE_HTTPONLY'] = True       # Prevent XSS access to session cookie
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'      # CSRF protection
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)  # Session expires after 8h
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('FLASK_ENV') == 'production'  # True in production with HTTPS
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

# Login security
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_DURATION = timedelta(minutes=15)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Initialize database
init_db()

# Ensure superuser admin account exists
from app.database import ensure_admin_exists
ensure_admin_exists(username='admin', password='admin123?Vaulta')

# ── Automatic overdue fine checker ──────────────────────────────
# Runs auto_apply_overdue_fines() before every request, but
# throttles to at most once every 30 minutes to avoid overhead.
_last_fine_check = None  # module-level timestamp

@app.before_request
def auto_check_overdue_fines():
    """Before every request, automatically apply fines for overdue loans.
    
    Throttled to run at most once every 30 minutes using a module-level
    timestamp. The database query is efficient — it only hits loans that
    are past due and have no active fine yet.
    """
    global _last_fine_check
    now = datetime.now()
    
    # Throttle: only run if 30+ minutes since last check
    if _last_fine_check and (now - _last_fine_check).total_seconds() < 1800:
        return
    
    _last_fine_check = now
    
    try:
        count = auto_apply_overdue_fines()
        if count:
            print(f"[Auto-Fine] Applied {count} fine(s) for overdue loans.")
    except Exception as e:
        print(f"[Auto-Fine] Error: {e}")

# ============ AUTH DECORATORS ============

def _greeting():
    """Return a time-aware greeting string."""
    hour = datetime.utcnow().hour
    if hour < 12:
        return 'Good morning'
    elif hour < 17:
        return 'Good afternoon'
    else:
        return 'Good evening'

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))
        
        # Check session timeout
        last_activity = session.get('last_activity')
        if last_activity:
            last = datetime.fromisoformat(last_activity)
            if datetime.utcnow() - last > app.config['PERMANENT_SESSION_LIFETIME']:
                session.clear()
                flash('Session expired. Please log in again.', 'warning')
                return redirect(url_for('login'))
        
        # Update last activity timestamp
        session['last_activity'] = datetime.utcnow().isoformat()
        return f(*args, **kwargs)
    return decorated

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if 'user_role' not in session or session['user_role'] not in roles:
                flash('You do not have permission to access this page.', 'danger')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated
    return decorator

# ============ HEALTH CHECK ============

@app.route('/health')
def health_check():
    """Health check endpoint — verifies database connectivity and persistence mode."""
    from app.db_adapter import IS_POSTGRES, DB_TYPE
    try:
        from app.database import get_db
        conn = get_db()
        user_count = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        loan_count = conn.execute('SELECT COUNT(*) FROM loans').fetchone()[0]
        conn.close()
        return {
            'status': 'healthy',
            'db_type': DB_TYPE,
            'postgres': IS_POSTGRES,
            'users': user_count,
            'loans': loan_count,
            'warning': 'SQLite on Vercel is NOT persistent — set DATABASE_URL for production'
                if not IS_POSTGRES else None
        }
    except Exception as e:
        return {'status': 'unhealthy', 'error': str(e)}, 500

# ============ AUTH ROUTES ============

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        ip_address = request.remote_addr

        # Check if account is locked
        lockout_minutes = int(LOCKOUT_DURATION.total_seconds() // 60)
        if is_account_locked(username, MAX_LOGIN_ATTEMPTS, lockout_minutes):
            flash(f'🔒 Account locked after too many failed attempts. Please try again in {lockout_minutes} minutes.', 'danger')
            return render_template('login.html')

        user = authenticate_user(username, password)

        if user:
            record_login_attempt(username, ip_address, success=True)
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['user_role'] = user['role']
            session['full_name'] = user['full_name']
            session.permanent = True
            session['last_activity'] = datetime.utcnow().isoformat()

            # Role-specific welcome message
            role = user['role']
            name = user['full_name']

            if role == 'admin':
                flash(f'Welcome back, {name}! You have full system access.', 'success')
            elif role == 'loan_officer':
                flash(f'Welcome back, {name}! Ready to manage clients and loans?', 'success')
            else:
                flash(f'Welcome back, {name}!', 'success')

            return redirect(url_for('dashboard'))
        else:
            record_login_attempt(username, ip_address, success=False)
            failed = get_failed_attempts(username, within_minutes=lockout_minutes)
            remaining = MAX_LOGIN_ATTEMPTS - failed
            if remaining > 0:
                flash(f'Incorrect username or password. {remaining} attempt(s) remaining before account lockout.', 'danger')
            else:
                flash(f'🔒 Account locked after {MAX_LOGIN_ATTEMPTS} failed attempts. Please wait {lockout_minutes} minutes and try again.', 'danger')

    return render_template('login.html')

@app.route('/logout')
def logout():
    name = session.get('full_name', 'User')
    session.clear()
    flash(f'Goodbye, {name}! You have been signed out securely. See you next time.', 'info')
    return redirect(url_for('login'))

# ============ CLIENT LOAN ACCESS (VIEW-ONLY) ============

def loan_view_required(f):
    """Decorator: require an active loan view session (client entered loan number)."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('loan_view') or not session.get('loan_id'):
            flash('Please enter your loan number to access your account.', 'warning')
            return redirect(url_for('client_loan_access'))
        return f(*args, **kwargs)
    return decorated


@app.route('/client/access', methods=['GET', 'POST'])
def client_loan_access():
    """Client logs in with a loan number (no password) — view-only."""
    # If already logged in as staff, redirect away
    if session.get('user_role') in ('admin', 'loan_officer'):
        flash('You are already logged in as staff. Please log out first to use client access.', 'warning')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        loan_number = request.form.get('loan_number', '').strip().upper()
        if not loan_number:
            flash('Please enter your loan number.', 'warning')
            return render_template('client_access.html')

        loan = get_loan_by_number(loan_number)
        if not loan:
            flash(f'No loan found with number "{loan_number}". Please check and try again.', 'danger')
            return render_template('client_access.html')

        # Set session for view-only loan access
        session['loan_view'] = True
        session['loan_id'] = loan['id']
        session['user_id'] = loan['client_id']
        session['full_name'] = loan['client_name']
        session['user_role'] = 'loan_viewer'
        session.permanent = True
        session['last_activity'] = datetime.utcnow().isoformat()

        flash(f'Welcome, {loan["client_name"]}! You are viewing loan {loan_number}.', 'success')
        return redirect(url_for('client_my_loan'))

    return render_template('client_access.html')


@app.route('/client/my-loan')
@login_required
@loan_view_required
def client_my_loan():
    """View-only loan dashboard for a client who entered their loan number."""
    loan_id = session['loan_id']
    loan = get_loan(loan_id)
    if not loan:
        flash('Loan not found.', 'danger')
        return redirect(url_for('client_loan_access'))

    repayments = get_repayments(loan_id)
    schedule = calculate_payment_schedule(loan)
    return render_template('loan_detail.html', loan=loan, repayments=repayments, schedule=schedule)


@app.route('/client/logout')
def client_loan_logout():
    """Clear loan view session and redirect to client access page."""
    name = session.get('full_name', 'Client')
    for key in ['loan_view', 'loan_id', 'user_id', 'full_name', 'user_role', 'last_activity']:
        session.pop(key, None)
    flash(f'You have been signed out, {name}.', 'info')
    return redirect(url_for('client_loan_access'))


# ============ PASSWORD CHANGE ============

@app.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password_route():
    if request.method == 'POST':
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')

        # Verify current password
        user = get_user_by_id(session['user_id'])
        if not user or not check_password_hash(user['password_hash'], current_password):
            flash('Current password is incorrect.', 'danger')
            return render_template('change_password.html')

        # Validate new password
        if new_password != confirm_password:
            flash('New passwords do not match.', 'danger')
            return render_template('change_password.html')

        is_valid, error_msg = validate_password_strength(new_password)
        if not is_valid:
            flash(error_msg, 'danger')
            return render_template('change_password.html')

        if current_password == new_password:
            flash('New password must be different from current password.', 'warning')
            return render_template('change_password.html')

        # Update password
        change_password(session['user_id'], new_password)
        log_audit(session['user_id'], 'change_password', 'user', session['user_id'])
        flash('Password changed successfully!', 'success')
        return redirect(url_for('dashboard'))

    return render_template('change_password.html')

@app.route('/register', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'loan_officer')
def register():
    generated_creds = None  # track auto-generated credentials to display

    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role')
        full_name = request.form.get('full_name')
        phone = request.form.get('phone')
        address = request.form.get('address')
        id_number = request.form.get('id_number')

        # Auto-generate credentials for clients (fields are disabled in the form)
        if role == 'client' and (not username or not email or not password):
            import secrets, re
            # Extract first name from full_name for username
            first_name = (full_name or 'client').strip().split()[0].lower()
            first_name = re.sub(r'[^a-z0-9]', '', first_name) or 'client'

            # Generate unique username: first_name, first_name2, first_name3, etc.
            if not username:
                from app.database import get_db
                conn = get_db()
                base_username = first_name
                username = base_username
                counter = 2
                while conn.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone():
                    username = f"{base_username}{counter}"
                    counter += 1
                conn.close()

            if not email:
                email = f"{username}@vaulta.local"
            if not password:
                password = secrets.token_urlsafe(12)  # 16 chars, meets strength reqs
            generated_creds = {'username': username, 'password': password}

        # Validate password strength (skip for auto-generated client passwords)
        if not generated_creds:
            is_valid, error_msg = validate_password_strength(password)
            if not is_valid:
                flash(error_msg, 'danger')
                return render_template('register.html')

        # Handle profile picture upload
        profile_picture = None
        if 'profile_picture' in request.files:
            file = request.files['profile_picture']
            if file and file.filename and allowed_file(file.filename):
                ext = file.filename.rsplit('.', 1)[1].lower()
                filename = f"profile_{uuid.uuid4().hex[:8]}.{ext}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                profile_picture = filename

        user_id = create_user(username, email, password, role, full_name, phone, address, id_number, profile_picture)
        if user_id:
            log_audit(session['user_id'], 'create_user', 'user', user_id, f'Created user: {username}')
            if role == 'client':
                send_welcome_notification(user_id, full_name)
            # Show generated credentials if any (so admin can share them with the user)
            if generated_creds:
                flash(
                    f'Client "{full_name}" created! '
                    f'<br><strong>Username:</strong> {generated_creds["username"]}'
                    f'<br><strong>Password:</strong> {generated_creds["password"]}'
                    f'<br><small class="text-muted">Share these credentials securely with the client.</small>',
                    'success'
                )
            else:
                flash(f'User "{username}" created successfully!', 'success')
            return redirect(url_for('admin_users'))
        else:
            flash('Username or email already exists.', 'danger')

    return render_template('register.html')

# ============ PASSWORD HELPERS ============

def validate_password_strength(password):
    """Validate password meets minimum strength requirements.
    Returns (is_valid, error_message) tuple.
    """
    if len(password) < 8:
        return False, 'Password must be at least 8 characters long.'
    if not any(c.isupper() for c in password):
        return False, 'Password must contain at least one uppercase letter.'
    if not any(c.islower() for c in password):
        return False, 'Password must contain at least one lowercase letter.'
    if not any(c.isdigit() for c in password):
        return False, 'Password must contain at least one number.'
    return True, None

# ============ PROFILE PICTURE UPLOAD ============

@app.route('/upload-photo/<int:user_id>', methods=['POST'])
@login_required
def upload_photo(user_id):
    if 'profile_picture' not in request.files:
        flash('No file selected.', 'warning')
        return redirect(request.referrer or url_for('dashboard'))

    file = request.files['profile_picture']
    if file and file.filename and allowed_file(file.filename):
        ext = file.filename.rsplit('.', 1)[1].lower()
        filename = f"profile_{uuid.uuid4().hex[:8]}.{ext}"
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        update_user_profile_picture(user_id, filename)
        flash('Profile picture updated!', 'success')
    else:
        flash('Invalid file type. Use PNG, JPG, or GIF.', 'danger')

    return redirect(request.referrer or url_for('client_profile', client_id=user_id))

@app.route('/uploads/<filename>')
@login_required
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# ============ DASHBOARD ============

@app.route('/dashboard')
@login_required
def dashboard():
    # Loan viewers should only see their own loan page
    if session.get('loan_view'):
        return redirect(url_for('client_my_loan'))
    stats = get_dashboard_stats()
    unread = get_unread_count(session['user_id'])

    # AI portfolio insights
    ai_data = get_dashboard_ai_data(stats)

    return render_template(
        'dashboard.html',
        stats=stats,
        unread=unread,
        greeting=_greeting(),
        ai_insights=ai_data['insights'],
        ai_enabled=ai_data['ai_enabled'],
    )

@app.route('/reports/profit-loss')
@login_required
@role_required('admin', 'loan_officer')
def profit_loss_report():
    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)
    report = get_balance_sheet(year, month)
    return render_template('profit_loss.html', report=report)

@app.route('/reports/profit-loss/pdf')
@login_required
@role_required('admin', 'loan_officer')
def profit_loss_pdf():
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch, mm
    from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
    from reportlab.platypus import (
        SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
        PageBreak, KeepTogether
    )
    from reportlab.lib.colors import HexColor
    from io import BytesIO

    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)
    report = get_balance_sheet(year, month)

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40
    )

    styles = getSampleStyleSheet()
    gold = HexColor('#b8860b')
    navy = HexColor('#0f172a')
    light_gold = HexColor('#fef9e7')
    green = HexColor('#16a34a')
    red = HexColor('#dc2626')

    styles.add(ParagraphStyle(
        'VTitle', fontName='Helvetica-Bold', fontSize=18, textColor=navy,
        alignment=TA_CENTER, spaceAfter=2
    ))
    styles.add(ParagraphStyle(
        'VSubtitle', fontName='Helvetica', fontSize=11, textColor=colors.grey,
        alignment=TA_CENTER, spaceAfter=12
    ))
    styles.add(ParagraphStyle(
        'SectionHeader', fontName='Helvetica-Bold', fontSize=12, textColor=gold,
        spaceBefore=10, spaceAfter=4
    ))
    styles.add(ParagraphStyle(
        'SubHeader', fontName='Helvetica-Bold', fontSize=10, textColor=navy,
        spaceBefore=6, spaceAfter=2
    ))
    styles.add(ParagraphStyle(
        'BodyRight', fontName='Helvetica', fontSize=10, textColor=colors.black,
        alignment=TA_RIGHT, spaceAfter=1
    ))
    styles.add(ParagraphStyle(
        'BodyLeft', fontName='Helvetica', fontSize=10, textColor=colors.black,
        alignment=TA_LEFT, spaceAfter=1
    ))
    styles.add(ParagraphStyle(
        'BoldRight', fontName='Helvetica-Bold', fontSize=10, textColor=navy,
        alignment=TA_RIGHT, spaceAfter=1
    ))
    styles.add(ParagraphStyle(
        'BoldLeft', fontName='Helvetica-Bold', fontSize=10, textColor=navy,
        alignment=TA_LEFT, spaceAfter=1
    ))
    styles.add(ParagraphStyle(
        'TotalRow', fontName='Helvetica-Bold', fontSize=10, textColor=gold,
        alignment=TA_RIGHT, spaceAfter=2
    ))
    styles.add(ParagraphStyle(
        'GreenRight', fontName='Helvetica-Bold', fontSize=10, textColor=green,
        alignment=TA_RIGHT, spaceAfter=1
    ))
    styles.add(ParagraphStyle(
        'RedRight', fontName='Helvetica-Bold', fontSize=10, textColor=red,
        alignment=TA_RIGHT, spaceAfter=1
    ))

    def fmt(amount):
        return f"UGX {amount:,.0f}"

    def row(label, amount, bold=False, color=None):
        style = styles['BoldRight'] if bold else styles['BodyRight']
        if color == 'green':
            style = styles['GreenRight']
        elif color == 'red':
            style = styles['RedRight']
        return [Paragraph(label, styles['BodyLeft']), Paragraph(fmt(amount), style)]

    elements = []

    # Header
    elements.append(Paragraph("Vaulta", styles['VTitle']))
    elements.append(Paragraph("Financial Statement", styles['VSubtitle']))
    elements.append(Paragraph(f"For the Month of {report['month_name']}", styles['VSubtitle']))
    elements.append(Spacer(1, 8))

    # === INCOME STATEMENT ===
    elements.append(Paragraph("INCOME STATEMENT", styles['SectionHeader']))
    elements.append(Spacer(1, 4))

    data = []
    data.append([Paragraph("Revenue", styles['SubHeader']), Paragraph("", styles['BodyRight'])])
    data.append(row("  Processing Fees", report['processing_fees']))
    data.append(row("  Interest Earned", report['interest_earned']))
    data.append(row("  Fines Collected", report['fines_collected']))
    data.append(row("Total Revenue", report['total_revenue'], bold=True))
    data.append(row("Less: Funds Disbursed", report['disbursed'], bold=True, color='red'))
    net_color = 'green' if report['net_profit'] >= 0 else 'red'
    data.append(row("Net Profit / (Loss)", report['net_profit'], bold=True, color=net_color))

    t = Table(data, colWidths=[4*inch, 2*inch])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), light_gold),
        ('BACKGROUND', (0, 4), (-1, 4), light_gold),
        ('BACKGROUND', (0, 5), (-1, 5), light_gold),
        ('BACKGROUND', (0, 6), (-1, 6), light_gold),
        ('LINEBELOW', (0, 4), (-1, 4), 1, gold),
        ('LINEBELOW', (0, 5), (-1, 5), 1, navy),
        ('LINEBELOW', (0, 6), (-1, 6), 2, gold),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    elements.append(t)

    # === BALANCE SHEET ===
    elements.append(Spacer(1, 12))
    elements.append(Paragraph("BALANCE SHEET", styles['SectionHeader']))
    elements.append(Spacer(1, 4))

    # Assets
    elements.append(Paragraph("ASSETS", styles['SubHeader']))
    data = []
    data.append([Paragraph("Current Assets", styles['BodyLeft']), Paragraph("", styles['BodyRight'])])
    data.append(row("  Cash on Hand (Total Repayments)", report['cash_on_hand']))
    data.append(row("  Accounts Receivable (Outstanding Loans)", report['accounts_receivable']))
    data.append(row("  Fees Receivable", report['fees_receivable']))
    data.append(row("Total Current Assets", report['total_current_assets'], bold=True))
    data.append([Paragraph("Non-Current Assets", styles['BodyLeft']), Paragraph("", styles['BodyRight'])])
    data.append(row("  Fines Receivable", report['fines_receivable']))
    data.append(row("Total Assets", report['total_assets'], bold=True))

    t = Table(data, colWidths=[4*inch, 2*inch])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 4), (-1, 4), light_gold),
        ('BACKGROUND', (0, 7), (-1, 7), light_gold),
        ('LINEBELOW', (0, 4), (-1, 4), 1, gold),
        ('LINEBELOW', (0, 7), (-1, 7), 2, gold),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    elements.append(t)

    # Liabilities & Equity
    elements.append(Spacer(1, 8))
    elements.append(Paragraph("LIABILITIES & EQUITY", styles['SubHeader']))
    data = []
    data.append([Paragraph("Liabilities", styles['BodyLeft']), Paragraph("", styles['BodyRight'])])
    data.append(row("  Unearned Interest (Deferred Revenue)", report['unearned_interest']))
    data.append(row("Total Liabilities", report['total_liabilities'], bold=True))
    data.append([Paragraph("Equity", styles['BodyLeft']), Paragraph("", styles['BodyRight'])])
    data.append(row("  Retained Earnings", report['retained_earnings']))
    data.append(row("Total Equity", report['total_equity'], bold=True))
    data.append(row("Total Liabilities + Equity", report['total_liabilities_equity'], bold=True))

    t = Table(data, colWidths=[4*inch, 2*inch])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 2), (-1, 2), light_gold),
        ('BACKGROUND', (0, 4), (-1, 4), light_gold),
        ('BACKGROUND', (0, 6), (-1, 6), light_gold),
        ('BACKGROUND', (0, 7), (-1, 7), light_gold),
        ('LINEBELOW', (0, 2), (-1, 2), 1, gold),
        ('LINEBELOW', (0, 6), (-1, 6), 1, gold),
        ('LINEBELOW', (0, 7), (-1, 7), 2, gold),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    elements.append(t)

    # Loan Details
    if report['loan_details']:
        elements.append(Spacer(1, 12))
        elements.append(Paragraph("LOAN BREAKDOWN", styles['SectionHeader']))
        data = [[
            Paragraph("Loan #", styles['BodyLeft']),
            Paragraph("Client", styles['BodyLeft']),
            Paragraph("Principal", ParagraphStyle('tr', alignment=TA_RIGHT, fontSize=9)),
            Paragraph("Fee", ParagraphStyle('tr', alignment=TA_RIGHT, fontSize=9)),
            Paragraph("Interest", ParagraphStyle('tr', alignment=TA_RIGHT, fontSize=9)),
            Paragraph("Status", ParagraphStyle('tr', alignment=TA_CENTER, fontSize=9)),
        ]]
        for loan in report['loan_details']:
            data.append([
                Paragraph(loan['loan_number'], ParagraphStyle('s', fontSize=8)),
                Paragraph(loan['client_name'], ParagraphStyle('s', fontSize=8)),
                Paragraph(fmt(loan['principal']), ParagraphStyle('s', fontSize=8, alignment=TA_RIGHT)),
                Paragraph(fmt(loan['processing_fee']), ParagraphStyle('s', fontSize=8, alignment=TA_RIGHT)),
                Paragraph(fmt(loan['interest']), ParagraphStyle('s', fontSize=8, alignment=TA_RIGHT)),
                Paragraph(loan['status'].upper(), ParagraphStyle('s', fontSize=8, alignment=TA_CENTER)),
            ])

        t = Table(data, colWidths=[1.1*inch, 1.5*inch, 1.1*inch, 0.8*inch, 1*inch, 0.8*inch])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), navy),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, HexColor('#f8f9fa')]),
            ('LINEBELOW', (0, 0), (-1, 0), 1, navy),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ]))
        elements.append(t)

    # Footer
    elements.append(Spacer(1, 20))
    elements.append(Paragraph(
        f"Generated on {datetime.now().strftime('%d %B %Y, %H:%M')} | Vaulta Loan Management",
        ParagraphStyle('Footer', fontName='Helvetica', fontSize=8, textColor=colors.grey, alignment=TA_CENTER)
    ))

    doc.build(elements)
    buffer.seek(0)

    from flask import send_file
    return send_file(
        buffer,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f"Vaulta_BalanceSheet_{report['month_name'].replace(' ', '_')}.pdf"
    )

# ============ CLIENT MANAGEMENT ============

@app.route('/clients')
@login_required
@role_required('admin', 'loan_officer')
def manage_clients():
    clients = get_all_users('client')
    return render_template('clients.html', clients=clients)

@app.route('/clients/<int:client_id>')
@login_required
def client_profile(client_id):
    user = get_user_by_id(client_id)
    if not user:
        flash('Client not found.', 'danger')
        return redirect(url_for('manage_clients'))

    profile = get_client_profile(client_id)
    loans = get_loans({'client_id': client_id})
    return render_template('client_profile.html', user=user, profile=profile, loans=loans)

@app.route('/clients/<int:client_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'loan_officer')
def edit_client(client_id):
    user = get_user_by_id(client_id)
    if not user:
        flash('Client not found.', 'danger')
        return redirect(url_for('manage_clients'))

    if user['role'] != 'client':
        flash('This user is not a client.', 'danger')
        return redirect(url_for('manage_clients'))

    profile = get_client_profile(client_id)

    if request.method == 'POST':
        try:
            update_client_profile(client_id,
                employer=request.form.get('employer'),
                monthly_income=float(request.form.get('monthly_income', 0) or 0),
                credit_score=int(request.form.get('credit_score', 0) or 0),
                next_of_kin=request.form.get('next_of_kin'),
                next_of_kin_phone=request.form.get('next_of_kin_phone'),
                bank_name=request.form.get('bank_name'),
                bank_account=request.form.get('bank_account'),
                mpesa_number=request.form.get('mpesa_number'),
                notes=request.form.get('notes')
            )
            log_audit(session['user_id'], 'update_profile', 'client', client_id)
            flash('Client profile updated!', 'success')
            return redirect(url_for('client_profile', client_id=client_id))
        except Exception as e:
            flash(f'Error updating profile: {str(e)}', 'danger')

    return render_template('edit_client.html', user=user, profile=profile)

# ============ LOAN MANAGEMENT ============

@app.route('/loans')
@login_required
def manage_loans():
    status_filter = request.args.get('status')
    search_query = request.args.get('search', '').strip()
    filters = {}
    if status_filter:
        filters['status'] = status_filter
    if search_query:
        filters['search'] = search_query

    if session['user_role'] == 'client':
        filters['client_id'] = session['user_id']

    loans = get_loans(filters)
    return render_template('loans.html', loans=loans, search_query=search_query)

@app.route('/loans/new', methods=['GET', 'POST'])
@login_required
def new_loan():
    if request.method == 'POST':
        try:
            client_id = int(request.form.get('client_id', session['user_id']))
            principal = float(request.form.get('principal'))
            interest_rate = float(request.form.get('interest_rate'))
            interest_type = request.form.get('interest_type', 'reducing')
            payment_schedule = request.form.get('payment_schedule', 'monthly')
            duration_months = int(request.form.get('duration_months'))
            processing_fee = float(request.form.get('processing_fee', 0) or 0)
            purpose = request.form.get('purpose')
            guarantor_name = request.form.get('guarantor_name')
            guarantor_phone = request.form.get('guarantor_phone')

            # Capture loan date and time from form (auto-filled from device — read-only)
            loan_date = request.form.get('loan_date') or datetime.now().strftime('%Y-%m-%d')
            loan_time = request.form.get('loan_time') or datetime.now().strftime('%H:%M:%S')

            # Disbursement date — manually selected from calendar (defaults to loan_date)
            disbursement_date = request.form.get('disbursement_date') or loan_date

            # Handle collateral photo upload
            collateral_photo = None
            if 'collateral_photo' in request.files:
                file = request.files['collateral_photo']
                if file and file.filename and allowed_file(file.filename):
                    ext = file.filename.rsplit('.', 1)[1].lower()
                    filename = f"collateral_{uuid.uuid4().hex[:8]}.{ext}"
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                    collateral_photo = filename

            loan_officer_id = session['user_id'] if session['user_role'] == 'loan_officer' else None

            loan_id, loan_number = create_loan(client_id, principal, interest_rate, interest_type,
                                payment_schedule, duration_months, purpose, loan_officer_id,
                                guarantor_name, guarantor_phone, processing_fee, collateral_photo,
                                loan_date=loan_date, loan_time=loan_time,
                                disbursement_date=disbursement_date)

            # Auto-approve loans below UGX 3,000,000
            if principal < 3000000:
                approve_loan(loan_id, session['user_id'])
                loan = get_loan(loan_id)
                send_loan_approved_notification(loan_id, loan['client_id'])
                log_audit(session['user_id'], 'approve_loan', 'loan', loan_id)
                flash(f'Loan {loan_number} approved automatically (under UGX 3,000,000)!', 'success')
            else:
                log_audit(session['user_id'], 'create_loan', 'loan', loan_id, f'{loan_number}: Principal {principal}, Fee {processing_fee}')
                # Notify all admins about pending large loan
                created_by = session.get('full_name', 'A user')
                admins = get_all_users('admin')
                for admin in admins:
                    send_notification(admin['id'], 'warning', 'Loan Needs Approval',
                        f'Loan {loan_number} of UGX {principal:,.0f} from {created_by} needs your approval.',
                        'in_app', entity_type='loan', entity_id=loan_id)
                flash(f'Loan application {loan_number} submitted! Awaiting admin approval (UGX 3,000,000+).', 'success')

            return redirect(url_for('manage_loans'))

        except Exception as e:
            traceback.print_exc()
            flash(f'Could not create loan. Please check your entries and try again. ({type(e).__name__})', 'danger')
            # Re-render the form so the user sees the error
            clients = get_all_users('client') if session['user_role'] in ('admin', 'loan_officer') else None
            return render_template('new_loan.html', clients=clients)

    clients = get_all_users('client') if session['user_role'] in ('admin', 'loan_officer') else None
    return render_template('new_loan.html', clients=clients)

@app.route('/api/calculate-loan', methods=['POST'])
@login_required
def api_calculate_loan():
    """Live preview of loan calculations"""
    data = request.get_json()
    principal = float(data.get('principal', 0))
    interest_rate = float(data.get('interest_rate', 0))
    interest_type = data.get('interest_type', 'flat')
    payment_schedule = data.get('payment_schedule', 'monthly')
    duration_months = int(data.get('duration_months', 1))

    if interest_type == 'flat':
        total_interest = principal * (interest_rate / 100) * duration_months
    else:
        total_interest = principal * (interest_rate / 100) * duration_months / 2

    total_amount = principal + total_interest

    if payment_schedule == 'daily':
        total_payments = duration_months * 30
        label = 'Daily'
    elif payment_schedule == 'weekly':
        total_payments = duration_months * 4
        label = 'Weekly'
    else:
        total_payments = duration_months
        label = 'Monthly'

    installment = round(total_amount / max(1, total_payments), 2)
    completion = (datetime.now() + timedelta(days=30 * duration_months)).strftime('%Y-%m-%d')

    return jsonify({
        'total_interest': round(total_interest, 2),
        'total_amount': round(total_amount, 2),
        'installment_amount': installment,
        'total_payments': total_payments,
        'schedule_label': label,
        'completion_date': completion
    })

@app.route('/loans/<int:loan_id>')
@login_required
def loan_detail(loan_id):
    loan = get_loan(loan_id)
    if not loan:
        flash('Loan not found.', 'danger')
        return redirect(url_for('manage_loans'))

    repayments = get_repayments(loan_id)
    schedule = calculate_payment_schedule(loan)
    return render_template('loan_detail.html', loan=loan, repayments=repayments, schedule=schedule)

@app.route('/loans/<int:loan_id>/approve', methods=['POST'])
@login_required
@role_required('admin', 'loan_officer')
def approve_loan_route(loan_id):
    loan = get_loan(loan_id)
    if not loan:
        flash('Loan not found.', 'danger')
        return redirect(url_for('manage_loans'))

    # Loan officers cannot approve loans ≥ UGX 3,000,000
    if session['user_role'] == 'loan_officer' and loan['principal'] >= 3000000:
        flash('Only an admin can approve loans of UGX 3,000,000 and above.', 'danger')
        return redirect(url_for('loan_detail', loan_id=loan_id))

    approve_loan(loan_id, session['user_id'])
    send_loan_approved_notification(loan_id, loan['client_id'])
    log_audit(session['user_id'], 'approve_loan', 'loan', loan_id)
    flash('Loan approved!', 'success')
    return redirect(url_for('loan_detail', loan_id=loan_id))

@app.route('/loans/<int:loan_id>/reject', methods=['POST'])
@login_required
@role_required('admin', 'loan_officer')
def reject_loan_route(loan_id):
    loan = get_loan(loan_id)
    if not loan:
        flash('Loan not found.', 'danger')
        return redirect(url_for('manage_loans'))

    # Loan officers cannot reject loans ≥ UGX 3,000,000
    if session['user_role'] == 'loan_officer' and loan['principal'] >= 3000000:
        flash('Only an admin can reject loans of UGX 3,000,000 and above.', 'danger')
        return redirect(url_for('loan_detail', loan_id=loan_id))

    reject_loan(loan_id, session['user_id'])
    send_loan_rejected_notification(loan['client_id'], loan_id)
    log_audit(session['user_id'], 'reject_loan', 'loan', loan_id)
    flash('Loan rejected.', 'warning')
    return redirect(url_for('loan_detail', loan_id=loan_id))

@app.route('/loans/<int:loan_id>/repay', methods=['GET', 'POST'])
@login_required
def repay_loan(loan_id):
    loan = get_loan(loan_id)
    if not loan:
        flash('Loan not found.', 'danger')
        return redirect(url_for('manage_loans'))

    if request.method == 'POST':
        amount = float(request.form.get('amount'))
        payment_method = request.form.get('payment_method')
        payment_type = request.form.get('payment_type', 'principal')
        reference = request.form.get('reference')
        notes = request.form.get('notes')

        # Validate amount against the correct maximum
        if payment_type == 'fine':
            max_allowed = loan['fine_amount']
        else:
            max_allowed = loan['balance']
        if amount > max_allowed:
            label = 'fine' if payment_type == 'fine' else 'balance'
            flash(f'Payment amount exceeds {label} (UGX {max_allowed:,.0f}).', 'danger')
            return redirect(url_for('repay_loan', loan_id=loan_id))

        # Auto-generate reference if empty
        if not reference:
            import secrets
            reference = f"PAY-{datetime.now().strftime('%Y%m%d')}-{secrets.token_hex(3).upper()}"

        add_repayment(loan_id, amount, payment_method, reference, session['user_id'], notes, payment_type)
        if payment_type == 'principal':
            send_payment_confirmation(loan['client_id'], amount, loan['balance'] - amount)
        pay_label = 'fine payment' if payment_type == 'fine' else 'payment'
        log_audit(session['user_id'], 'repayment', 'loan', loan_id, f'{pay_label}: {amount}')
        flash(f'{pay_label.title()} of UGX {amount:,.0f} recorded!', 'success')
        return redirect(url_for('loan_detail', loan_id=loan_id))

    return render_template('repay_loan.html', loan=loan)

@app.route('/loans/<int:loan_id>/toggle-fine', methods=['POST'])
@login_required
@role_required('admin', 'loan_officer')
def toggle_fine_route(loan_id):
    from app.sms_service import send_fine_status_sms
    action = request.form.get('action')
    if action in ('pause', 'activate'):
        toggle_fine(loan_id, action)
        loan = get_loan(loan_id)
        status = 'paused' if action == 'pause' else 'activated'
        flash(f'Fine {status} for loan {loan["loan_number"]}.', 'info')
        log_audit(session['user_id'], f'{action}_fine', 'loan', loan_id)
        # Send SMS notification to client about fine status change
        if loan.get('client_phone'):
            sms_result = send_fine_status_sms(loan, action)
            if sms_result['success']:
                flash(f'SMS fine status notification sent to {loan["client_name"]}.', 'info')
            else:
                flash(f'SMS notification failed: {sms_result["error"]}', 'warning')
    return redirect(url_for('loan_detail', loan_id=loan_id))

@app.route('/loans/<int:loan_id>/check-fine', methods=['POST'])
@login_required
@role_required('admin', 'loan_officer')
def check_fine_route(loan_id):
    from app.sms_service import send_fine_applied_sms
    result = check_and_apply_fine(loan_id)
    if result and result['fine_applied']:
        loan = result['loan']
        flash(f'Fine of UGX {loan["fine_amount"]:,.0f} applied to {loan["loan_number"]} (2% of total loan).', 'warning')
        # Send SMS notification to client
        sms_result = send_fine_applied_sms(loan)
        if sms_result['success']:
            flash(f'SMS fine notification sent to {loan["client_name"]}.', 'info')
        else:
            flash(f'SMS notification failed: {sms_result["error"]}', 'warning')
    else:
        flash('No fine applied. Payment is not overdue or fine already active.', 'info')
    return redirect(url_for('loan_detail', loan_id=loan_id))


@app.route('/loans/<int:loan_id>/apply-manual-fine', methods=['POST'])
@login_required
@role_required('admin', 'loan_officer')
def apply_manual_fine_route(loan_id):
    """Admin manually applies a fine with a specific amount and date."""
    loan = get_loan(loan_id)
    if not loan:
        flash('Loan not found.', 'danger')
        return redirect(url_for('manage_loans'))

    try:
        fine_amount = float(request.form.get('fine_amount', 0))
        fine_date = request.form.get('fine_date', '').strip()

        if fine_amount <= 0:
            flash('Fine amount must be greater than zero.', 'danger')
            return redirect(url_for('loan_detail', loan_id=loan_id))

        if not fine_date:
            fine_date = datetime.now().strftime('%Y-%m-%d')

        result = apply_manual_fine(loan_id, fine_amount, fine_date, session['user_id'])
        if result:
            from app.sms_service import send_fine_applied_sms
            flash(f'Manual fine of UGX {fine_amount:,.0f} applied to {loan["loan_number"]}.', 'success')
            log_audit(session['user_id'], 'manual_fine', 'loan', loan_id,
                     f'Applied fine UGX {fine_amount:,.0f} on {fine_date}')
            # Send SMS
            try:
                sms_result = send_fine_applied_sms(result)
                if sms_result['success']:
                    flash(f'SMS fine notification sent to {result["client_name"]}.', 'info')
                else:
                    flash(f'SMS notification failed: {sms_result["error"]}', 'warning')
            except Exception:
                pass
        else:
            flash('Could not apply fine. Loan not found.', 'danger')
    except Exception as e:
        flash(f'Error applying fine: {str(e)}', 'danger')

    return redirect(url_for('loan_detail', loan_id=loan_id))


@app.route('/api/run-fine-checks', methods=['POST'])
@login_required
@role_required('admin')
def run_fine_checks_api():
    """Trigger overdue fine checks for all loans (admin-only).

    Useful for external cron jobs or manual admin triggers.
    Returns JSON with the number of fines applied.
    """
    try:
        count = auto_apply_overdue_fines()
        return jsonify({'success': True, 'fines_applied': count})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/loans/<int:loan_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'loan_officer')
def edit_loan(loan_id):
    loan = get_loan(loan_id)
    if not loan:
        flash('Loan not found.', 'danger')
        return redirect(url_for('manage_loans'))

    if request.method == 'POST':
        principal = float(request.form.get('principal', loan['principal']))
        interest_rate = float(request.form.get('interest_rate', loan['interest_rate']))
        interest_type = request.form.get('interest_type', loan['interest_type'])
        payment_schedule = request.form.get('payment_schedule', loan['payment_schedule'])
        duration_months = int(request.form.get('duration_months', 1))
        purpose = request.form.get('purpose', loan['purpose'] or '')
        guarantor_name = request.form.get('guarantor_name', loan['guarantor_name'] or '')
        guarantor_phone = request.form.get('guarantor_phone', loan['guarantor_phone'] or '')
        processing_fee = float(request.form.get('processing_fee', loan.get('processing_fee', 0) or 0))
        disbursement_date = request.form.get('disbursement_date', loan.get('disbursement_date') or loan.get('start_date') or '').strip()
        status = request.form.get('status', loan['status'])

        # Recalculate total amount
        if interest_type == 'flat':
            total_interest = principal * (interest_rate / 100) * duration_months
        else:
            total_interest = principal * (interest_rate / 100) * duration_months / 2
        total_amount = principal + total_interest

        # Calculate due date from disbursement date
        start_date = disbursement_date or loan['start_date'] or datetime.now().strftime('%Y-%m-%d')
        due_date = (datetime.strptime(start_date, '%Y-%m-%d') + timedelta(days=30 * duration_months)).strftime('%Y-%m-%d')

        # Calculate next payment date
        if payment_schedule == 'daily':
            next_payment = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        elif payment_schedule == 'weekly':
            next_payment = (datetime.now() + timedelta(weeks=1)).strftime('%Y-%m-%d')
        else:
            next_payment = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')

        conn = get_db()
        conn.execute(
            '''UPDATE loans SET principal=?, interest_rate=?, interest_type=?, payment_schedule=?,
               total_amount=?, balance=?, purpose=?, guarantor_name=?, guarantor_phone=?,
               start_date=?, due_date=?, next_payment_date=?, processing_fee=?, status=?,
               disbursement_date=?, updated_at=CURRENT_TIMESTAMP WHERE id=?''',
            (principal, interest_rate, interest_type, payment_schedule,
             total_amount, total_amount - loan['amount_paid'], purpose, guarantor_name, guarantor_phone,
             start_date, due_date, next_payment, processing_fee, status, disbursement_date or start_date, loan_id)
        )
        conn.commit()
        conn.close()

        log_audit(session['user_id'], 'edit_loan', 'loan', loan_id, f'Updated loan {loan["loan_number"]}')
        flash(f'Loan {loan["loan_number"]} updated successfully!', 'success')
        return redirect(url_for('loan_detail', loan_id=loan_id))

    return render_template('edit_loan.html', loan=loan)

@app.route('/loans/<int:loan_id>/delete', methods=['POST'])
@login_required
@role_required('admin')
def delete_loan(loan_id):
    """Delete a loan — ADMIN ONLY. Requires confirmation and audit logging."""
    loan = get_loan(loan_id)
    if not loan:
        flash('Loan not found.', 'danger')
        return redirect(url_for('manage_loans'))

    # Check if loan has repayments
    repayments = get_repayments(loan_id)
    if repayments:
        flash('Cannot delete loan with existing repayments. Please delete repayments first.', 'danger')
        return redirect(url_for('loan_detail', loan_id=loan_id))

    conn = get_db()
    conn.execute('DELETE FROM loans WHERE id = ?', (loan_id,))
    conn.commit()
    conn.close()

    log_audit(session['user_id'], 'delete_loan', 'loan', loan_id, f'Deleted loan {loan["loan_number"]}')
    flash(f'Loan {loan["loan_number"]} deleted successfully!', 'success')
    return redirect(url_for('manage_loans'))

# ============ NOTIFICATIONS ============

@app.route('/notifications')
@login_required
def notifications():
    unread_only = request.args.get('unread') == '1'
    notifs = get_notifications(session['user_id'], unread_only)
    return render_template('notifications.html', notifications=notifs)

@app.route('/notifications/<int:notif_id>/read')
@login_required
def read_notification(notif_id):
    mark_notification_read(notif_id)
    return redirect(url_for('notifications'))

@app.route('/notifications/read-all', methods=['POST'])
@login_required
def read_all_notifications():
    mark_all_notifications_read(session['user_id'])
    flash('All notifications marked as read.', 'info')
    return redirect(url_for('notifications'))

@app.route('/notifications/send-reminder/<int:loan_id>', methods=['POST'])
@login_required
@role_required('admin', 'loan_officer')
def send_reminder(loan_id):
    send_payment_reminder(loan_id)
    flash('Reminder sent!', 'success')
    return redirect(url_for('loan_detail', loan_id=loan_id))

# ============ ADMIN DATA IMPORT ============

@app.route('/admin/upload', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_upload():
    result = None
    if request.method == 'POST':
        if 'data_file' not in request.files:
            flash('No file selected.', 'warning')
            return redirect(url_for('admin_upload'))

        file = request.files['data_file']
        if file.filename == '':
            flash('No file selected.', 'warning')
            return redirect(url_for('admin_upload'))

        filename = secure_filename(file.filename)
        ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''

        if ext not in ('csv', 'xlsx', 'xls'):
            flash('Invalid file type. Please upload CSV or Excel file.', 'danger')
            return redirect(url_for('admin_upload'))

        # Save uploaded file
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)

        # Optionally replace all existing data before import
        replace_data = request.form.get('replace_data') == '1'
        cleared_counts = None
        if replace_data:
            from app.database import clear_transactional_data
            cleared_counts = clear_transactional_data()
            flash(f'Existing loans, repayments, and activity cleared ({sum(cleared_counts.values())} records removed). Users preserved.', 'info')

        # Process the file
        from app.database import import_data_file
        result = import_data_file(filepath, ext)

        # Clean up uploaded file
        os.remove(filepath)

        if result['success']:
            msg = result['message']
            if cleared_counts:
                parts = [f'{v} {k}' for k, v in cleared_counts.items() if v > 0]
                msg += f' (replaced {sum(cleared_counts.values())} old records)'
            flash(f"Import successful! {msg}", 'success')
            log_audit(session['user_id'], 'data_import', 'file',
                      details=f"Imported {filename}: {result['message']}" +
                              (f' (replaced {sum(cleared_counts.values())} old records)' if cleared_counts else ''))
        else:
            flash(f"Import failed: {result['message']}", 'danger')

        return render_template('admin_upload.html', import_result=result)

    return render_template('admin_upload.html', import_result=result)

@app.route('/admin/download-template/<template_type>')
@login_required
@role_required('admin')
def download_template(template_type):
    """Download CSV template for data import"""
    templates = {
        'clients': 'username,email,password,role,full_name,phone,address,id_number\nalice,alice@email.com,pass123,client,Alice Wanjiku,0711111111,Nairobi,CF123456\nbob,bob@email.com,pass123,client,Bob Ochieng,0722222222,Mombasa,CF789012',
        'loans': 'client_name,principal,interest_rate,interest_type,payment_schedule,duration_months,purpose,guarantor_name,guarantor_phone,processing_fee\nAlice Wanjiku,50000,10,flat,monthly,3,Business expansion,Peter Wanjiku,0711111112,1000\nBrian Ochieng,30000,12,flat,monthly,2,School fees,,0,5000',
        'repayments': 'loan_number,amount,payment_method,reference,notes\nVL-001-2026-01,15000,mtn,MTN-REF-001,First installment\nVL-002-2026-01,10000,cash,CASH-001,Second payment'
    }

    if template_type not in templates:
        flash('Unknown template type.', 'danger')
        return redirect(url_for('admin_upload'))

    from flask import Response
    return Response(
        templates[template_type],
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename=vaulta_{template_type}_template.csv'}
    )

# ============ CLEAR DEMO DATA ============

@app.route('/admin/clear-demo-data', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_clear_demo_data():
    """Clear all demo/seed data from the system — ADMIN ONLY."""
    if request.method == 'POST':
        confirm = request.form.get('confirm', '').strip()
        if confirm != 'CLEAR':
            flash('Please type CLEAR to confirm.', 'danger')
            return redirect(url_for('admin_clear_demo_data'))

        try:
            counts = clear_demo_data()
            total = sum(counts.values())
            parts = [f'{v} {k}' for k, v in counts.items() if v > 0]
            flash(f'Demo data cleared successfully! Removed: {", ".join(parts)} ({total} total records).', 'success')
            log_audit(session['user_id'], 'clear_demo_data', 'system',
                      details=f'Deleted: {", ".join(parts)} ({total} total)')
        except Exception as e:
            flash(f'Error clearing demo data: {str(e)}', 'danger')

        return redirect(url_for('dashboard'))

    # GET: show confirmation page
    return render_template('admin_clear_demo.html')


# ============ SMS ROUTES ============

@app.route('/admin/sms')
@login_required
@role_required('admin')
def admin_sms():
    from app.sms_service import get_sms_stats, get_sms_logs
    stats = get_sms_stats()
    logs = get_sms_logs(100)
    return render_template('admin_sms.html', stats=stats, logs=logs)

@app.route('/admin/sms/send-reminder/<int:loan_id>', methods=['POST'])
@login_required
@role_required('admin', 'loan_officer')
def sms_send_reminder(loan_id):
    from app.sms_service import send_payment_reminder_sms
    from app.database import get_loan
    
    loan = get_loan(loan_id)
    if not loan:
        flash('Loan not found.', 'danger')
        return redirect(url_for('loan_detail', loan_id=loan_id))
    
    result = send_payment_reminder_sms(loan)
    if result['success']:
        flash(f'SMS reminder sent to {loan["client_name"]}!', 'success')
        log_audit(session['user_id'], 'sms_reminder', 'loan', loan_id, f'SMS sent to {loan["client_phone"]}')
    else:
        flash(f'Failed to send SMS: {result["error"]}', 'danger')
    
    return redirect(url_for('loan_detail', loan_id=loan_id))

@app.route('/admin/sms/send-overdue/<int:loan_id>', methods=['POST'])
@login_required
@role_required('admin', 'loan_officer')
def sms_send_overdue(loan_id):
    from app.sms_service import send_overdue_alert_sms
    from app.database import get_loan
    
    loan = get_loan(loan_id)
    if not loan:
        flash('Loan not found.', 'danger')
        return redirect(url_for('loan_detail', loan_id=loan_id))
    
    result = send_overdue_alert_sms(loan)
    if result['success']:
        flash(f'Overdue alert sent to {loan["client_name"]}!', 'success')
        log_audit(session['user_id'], 'sms_overdue', 'loan', loan_id, f'SMS sent to {loan["client_phone"]}')
    else:
        flash(f'Failed to send SMS: {result["error"]}', 'danger')
    
    return redirect(url_for('loan_detail', loan_id=loan_id))

@app.route('/admin/sms/send-bulk-overdue', methods=['POST'])
@login_required
@role_required('admin')
def sms_send_bulk_overdue():
    from app.sms_service import send_bulk_overdue_reminders
    from app.database import get_dashboard_stats
    
    stats = get_dashboard_stats()
    overdue_loans = stats.get('overdue_loans', [])
    
    if not overdue_loans:
        flash('No overdue loans to send reminders to.', 'info')
        return redirect(url_for('admin_sms'))
    
    result = send_bulk_overdue_reminders(overdue_loans)
    
    if result['sent'] > 0:
        flash(f'Sent {result["sent"]} SMS reminders. {result["failed"]} failed.', 'success')
        log_audit(session['user_id'], 'sms_bulk_overdue', 'loans', details=f'Sent {result["sent"]} reminders')
    else:
        flash(f'Failed to send SMS reminders: {", ".join(result["errors"][:3])}', 'danger')
    
    return redirect(url_for('admin_sms'))

@app.route('/admin/sms/test', methods=['POST'])
@login_required
@role_required('admin')
def sms_test():
    from app.sms_service import send_sms
    
    phone = request.form.get('phone', '').strip()
    if not phone:
        flash('Please enter a phone number.', 'warning')
        return redirect(url_for('admin_sms'))
    
    message = request.form.get('message', 'Test message from Vaulta Cash').strip()
    result = send_sms(phone, message)
    
    if result['success']:
        flash(f'Test SMS sent successfully to {phone}!', 'success')
    else:
        flash(f'Failed to send SMS: {result["error"]}', 'danger')
    
    return redirect(url_for('admin_sms'))

# ============ ADMIN CRUD ============

# ── User Management ──

@app.route('/admin/users')
@login_required
@role_required('admin')
def admin_users():
    role_filter = request.args.get('role')
    # Admin page shows ALL users (active + inactive) for full management
    users = get_all_users(role=role_filter, include_inactive=True) if role_filter else get_all_users(include_inactive=True)
    return render_template('admin_users.html', users=users, role_filter=role_filter)

@app.route('/admin/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_edit_user(user_id):
    user = get_user_by_id(user_id)
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('admin_users'))

    if request.method == 'POST':
        # ── Handle password reset (standalone form) ──
        new_password = request.form.get('new_password', '').strip()
        if new_password:
            is_valid, error_msg = validate_password_strength(new_password)
            if not is_valid:
                flash(f'Password reset failed: {error_msg}', 'danger')
                return render_template('edit_user.html', user=user)
            change_password(user_id, new_password)
            log_audit(session['user_id'], 'reset_password', 'user', user_id,
                      f'Password reset by admin for user: {user["username"]}')
            flash(f'Password for "{user["username"]}" has been reset.', 'success')
            return redirect(url_for('admin_users'))

        # ── Handle profile update (only if profile fields present) ──
        data = {}
        for field in ('username', 'email', 'full_name', 'phone', 'address', 'id_number', 'role'):
            val = request.form.get(field)
            if val is not None:
                data[field] = val
        # Only set is_active if the checkbox was submitted (checked → '1', unchecked → absent)
        if 'is_active' in request.form:
            data['is_active'] = 1
        else:
            data['is_active'] = 0

        if data:
            try:
                update_user(user_id, data)
                log_audit(session['user_id'], 'update_user', 'user', user_id,
                          f'Updated user: {data.get("username", user["username"])}')
                flash(f'User "{data.get("username", user["username"])}" updated successfully.', 'success')
                return redirect(url_for('admin_users'))
            except Exception as e:
                if 'UNIQUE' in str(e):
                    flash('Username or email already exists.', 'danger')
                else:
                    flash(f'Error updating user: {e}', 'danger')
        else:
            flash('No changes submitted.', 'info')

    return render_template('edit_user.html', user=user)

@app.route('/admin/users/<int:user_id>/delete', methods=['POST'])
@login_required
@role_required('admin')
def admin_delete_user(user_id):
    user = get_user_by_id(user_id)
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('admin_users'))

    success, msg = delete_user(user_id)
    if success:
        log_audit(session['user_id'], 'delete_user', 'user', user_id, f'Deactivated user: {user["username"]}')
        flash(f'User {user["username"]} deactivated successfully.', 'success')
    else:
        flash(msg, 'danger')
    return redirect(url_for('admin_users'))

# ── Repayment Management ──

@app.route('/admin/repayments')
@login_required
@role_required('admin')
def admin_repayments():
    repayments = get_all_repayments()
    return render_template('admin_repayments.html', repayments=repayments)

@app.route('/admin/repayments/<int:repayment_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_edit_repayment(repayment_id):
    conn = get_db()
    repayment = conn.execute('''
        SELECT r.*, l.loan_number, u.full_name AS client_name
        FROM repayments r
        JOIN loans l ON r.loan_id = l.id
        JOIN users u ON l.client_id = u.id
        WHERE r.id = ?
    ''', (repayment_id,)).fetchone()
    conn.close()

    if not repayment:
        flash('Repayment not found.', 'danger')
        return redirect(url_for('admin_repayments'))

    if request.method == 'POST':
        amount = float(request.form.get('amount', 0))
        method = request.form.get('payment_method', 'cash')
        reference = request.form.get('reference', '')
        notes = request.form.get('notes', '')

        try:
            update_repayment(repayment_id, amount, method, reference, notes)
            log_audit(session['user_id'], 'update_repayment', 'repayment', repayment_id,
                      f'Updated repayment for {repayment["loan_number"]}: UGX {amount}')
            flash('Repayment updated successfully.', 'success')
            return redirect(url_for('admin_repayments'))
        except Exception as e:
            flash(f'Error updating repayment: {e}', 'danger')

    return render_template('edit_repayment.html', repayment=dict(repayment))

@app.route('/admin/repayments/<int:repayment_id>/delete', methods=['POST'])
@login_required
@role_required('admin')
def admin_delete_repayment(repayment_id):
    """Delete a repayment — ADMIN ONLY. Requires confirmation and audit logging."""
    try:
        success = delete_repayment(repayment_id)
        if success:
            log_audit(session['user_id'], 'delete_repayment', 'repayment', repayment_id, 'Deleted repayment')
            flash('Repayment deleted and loan balance recalculated.', 'success')
        else:
            flash('Repayment not found.', 'danger')
    except Exception as e:
        flash(f'Error deleting repayment: {e}', 'danger')
    return redirect(url_for('admin_repayments'))

# ── Accept Payment ──

@app.route('/admin/accept-payment', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'loan_officer')
def accept_payment():
    if request.method == 'POST':
        loan_id = int(request.form.get('loan_id'))
        amount = float(request.form.get('amount'))
        payment_method = request.form.get('payment_method')
        payment_type = request.form.get('payment_type', 'principal')
        reference = request.form.get('reference')
        notes = request.form.get('notes')

        loan = get_loan(loan_id)
        if not loan:
            flash('Loan not found.', 'danger')
            return redirect(url_for('accept_payment'))

        if amount > loan['balance']:
            flash(f'Payment amount exceeds balance (UGX {loan["balance"]:,.0f}).', 'danger')
            return redirect(url_for('accept_payment'))

        # Auto-generate reference if empty
        if not reference:
            import secrets
            reference = f"PAY-{datetime.now().strftime('%Y%m%d')}-{secrets.token_hex(3).upper()}"

        add_repayment(loan_id, amount, payment_method, reference, session['user_id'], notes, payment_type)
        if payment_type == 'principal':
            send_payment_confirmation(loan['client_id'], amount, loan['balance'] - amount)
        pay_label = 'fine payment' if payment_type == 'fine' else 'payment'
        log_audit(session['user_id'], 'repayment', 'loan', loan_id,
                  f'{pay_label}: {amount}, Method: {payment_method}')
        flash(f'{pay_label.title()} of UGX {amount:,.0f} recorded for {loan["loan_number"]}!', 'success')
        return redirect(url_for('accept_payment'))

    # Show active/approved loans with balance > 0
    loans = [l for l in get_loans() if l['status'] in ('active', 'approved') and l['balance'] > 0]
    return render_template('accept_payment.html', loans=loans)

# ── Audit Log Viewer ──

@app.route('/admin/audit-logs')
@login_required
@role_required('admin')
def admin_audit_logs():
    logs = get_audit_logs()
    return render_template('audit_logs.html', logs=logs)

# ============ API ROUTES ============

@app.route('/api/stats')
@login_required
def api_stats():
    return jsonify(get_dashboard_stats())

@app.route('/api/notifications/unread')
@login_required
def api_unread():
    return jsonify({'count': get_unread_count(session['user_id'])})

# ============ ERROR HANDLERS ============

@app.errorhandler(404)
def not_found(e):
    return render_template('error.html', code=404, message='Page not found'), 404

@app.errorhandler(403)
def forbidden(e):
    return render_template('error.html', code=403, message='Access denied'), 403

# ============ AI FEATURES ============

@app.route('/api/ai/insights')
@login_required
def ai_insights():
    """Return AI portfolio insights for the dashboard."""
    if session.get('loan_view'):
        return jsonify({'error': 'Not available in view-only mode'}), 403
    stats = get_dashboard_stats()
    data = get_dashboard_ai_data(stats)
    return jsonify(data)


@app.route('/api/ai/risk-score/<int:client_id>')
@login_required
def ai_risk_score(client_id):
    """Return AI credit risk assessment for a client."""
    if session.get('loan_view'):
        return jsonify({'error': 'Not available in view-only mode'}), 403
    conn = get_db()
    profile = conn.execute(
        'SELECT * FROM client_profiles WHERE user_id = ?', (client_id,)
    ).fetchone()
    user = conn.execute(
        'SELECT id, full_name, phone FROM users WHERE id = ?', (client_id,)
    ).fetchone()
    if not user:
        conn.close()
        return jsonify({'error': 'Client not found'}), 404

    # Gather repayment history
    loans = conn.execute(
        'SELECT id, status, principal FROM loans WHERE client_id = ?', (client_id,)
    ).fetchall()
    active_loans = sum(1 for l in loans if l['status'] == 'active')
    late_payments = 0
    repayments = []
    for loan in loans:
        rs = conn.execute(
            'SELECT * FROM repayments WHERE loan_id = ?', (loan['id'],)
        ).fetchall()
        for r in rs:
            repayments.append({
                'amount': r['amount'],
                'date': r['created_at'],
                'on_time': True,  # default — would need due-date comparison
            })
        # Count total
        late_payments += conn.execute(
            'SELECT COUNT(*) as cnt FROM repayments WHERE loan_id = ?',
            (loan['id'],)
        ).fetchone()['cnt']
    conn.close()

    client_data = dict(profile) if profile else {}
    client_data['active_loans'] = active_loans
    client_data['late_payments'] = 0  # simplified
    client_data['full_name'] = user['full_name']

    result = assess_credit_risk(client_data, repayments)
    result['client_name'] = user['full_name']
    return jsonify(result)


@app.route('/api/ai/faq', methods=['POST'])
def ai_faq():
    """Handle FAQ questions from the client view-only portal."""
    data = request.get_json() or {}
    question = data.get('question', '').strip()
    if not question:
        return jsonify({'answer': 'Please ask a question.', 'source': 'ai'})

    # If user is in loan_view, provide loan context
    loan_data = None
    if session.get('loan_view') and session.get('loan_id'):
        from app.database import get_loan
        loan_data = get_loan(session['loan_id'])

    answer = get_faq_response(question, loan_data)
    return jsonify({'answer': answer, 'source': 'ai (rule engine)'})


@app.route('/api/ai/client-analysis/<int:client_id>')
@login_required
def ai_client_analysis(client_id):
    """Return AI analysis of a client."""
    if session.get('loan_view'):
        return jsonify({'error': 'Not available in view-only mode'}), 403
    conn = get_db()
    profile = conn.execute(
        'SELECT * FROM client_profiles WHERE user_id = ?', (client_id,)
    ).fetchone()
    user = conn.execute(
        'SELECT * FROM users WHERE id = ?', (client_id,)
    ).fetchone()
    if not user:
        conn.close()
        return jsonify({'error': 'Client not found'}), 404

    loans = conn.execute(
        'SELECT * FROM loans WHERE client_id = ? ORDER BY created_at DESC',
        (client_id,)
    ).fetchall()
    repayments = []
    for loan in loans:
        rs = conn.execute(
            'SELECT * FROM repayments WHERE loan_id = ? ORDER BY created_at ASC',
            (loan['id'],)
        ).fetchall()
        for r in rs:
            repayments.append({
                'amount': r['amount'],
                'date': r['created_at'],
                'on_time': True,
                'loan': loan['loan_number'],
            })
    conn.close()

    client_data = dict(user)
    if profile:
        client_data.update(dict(profile))

    result = analyze_client(
        client_data,
        [dict(l) for l in loans],
        repayments,
    )
    result['client_name'] = user['full_name']
    return jsonify(result)


if __name__ == '__main__':
    # Railway provides the PORT env var automatically
    port = int(os.environ.get('PORT', 5000))
    host = os.environ.get('HOST', '127.0.0.1')
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    print("\n" + "="*50)
    print("  LendFlow - Money Lending Management System")
    print(f"  http://{host}:{port}")
    print("="*50 + "\n")
    app.run(debug=debug, host=host, port=port)
