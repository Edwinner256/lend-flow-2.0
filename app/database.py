"""Database models for LendFlow - Enhanced"""

import os
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash

from app.db_adapter import (
    get_db, IS_POSTGRES, DB_PATH, _get_integrity_error,
    translate_ddl, translate_date, is_pragma
)

# Upload folder for profile pictures, collateral photos, etc.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPLOAD_FOLDER = os.path.join(_PROJECT_ROOT, 'static', 'uploads')


def init_db():
    """Initialize database tables — SQLite and PostgreSQL compatible."""
    # Ensure directories exist (SQLite needs DB dir; PG is managed externally)
    from app.db_adapter import init_db as _adapter_init
    _adapter_init()
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

    conn = get_db()
    cursor = conn.cursor()

    # For PostgreSQL: translate SQLite-specific DDL syntax
    _ddl = translate_ddl if IS_POSTGRES else lambda s: s

    # Users table (multi-role)
    cursor.execute(_ddl('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('admin', 'loan_officer', 'client')),
            full_name TEXT NOT NULL,
            phone TEXT,
            address TEXT,
            id_number TEXT,
            profile_picture TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    '''))

    # Add profile_picture column if it doesn't exist
    try:
        cursor.execute('ALTER TABLE users ADD COLUMN profile_picture TEXT')
    except:
        pass

    # Client profiles
    cursor.execute(_ddl('''
        CREATE TABLE IF NOT EXISTS client_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE NOT NULL,
            employer TEXT,
            monthly_income REAL,
            credit_score INTEGER,
            next_of_kin TEXT,
            next_of_kin_phone TEXT,
            bank_name TEXT,
            bank_account TEXT,
            mpesa_number TEXT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    '''))

    # Add missing columns to client_profiles if they don't exist (migration for older DBs)
    for col in ('mpesa_number', 'notes', 'bank_name', 'bank_account', 'credit_score', 'next_of_kin', 'next_of_kin_phone'):
        try:
            cursor.execute(f'ALTER TABLE client_profiles ADD COLUMN {col} TEXT')
        except:
            pass
    try:
        cursor.execute('ALTER TABLE client_profiles ADD COLUMN monthly_income REAL')
    except:
        pass

    # Loans - Enhanced
    cursor.execute(_ddl('''
        CREATE TABLE IF NOT EXISTS loans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            loan_number TEXT UNIQUE NOT NULL,
            client_id INTEGER NOT NULL,
            loan_officer_id INTEGER,
            principal REAL NOT NULL,
            interest_rate REAL NOT NULL,
            interest_type TEXT DEFAULT 'flat' CHECK(interest_type IN ('flat', 'reducing')),
            payment_schedule TEXT DEFAULT 'monthly' CHECK(payment_schedule IN ('daily', 'weekly', 'monthly')),
            total_amount REAL NOT NULL,
            amount_paid REAL DEFAULT 0,
            balance REAL NOT NULL,
            fine_amount REAL DEFAULT 0,
            fine_active INTEGER DEFAULT 0,
            default_count INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'approved', 'active', 'paid', 'defaulted', 'rejected')),
            purpose TEXT,
            guarantor_name TEXT,
            guarantor_phone TEXT,
            start_date DATE,
            loan_date DATE,
            loan_time TIME,
            due_date DATE,
            next_payment_date DATE,
            approved_by INTEGER,
            approved_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (client_id) REFERENCES users(id),
            FOREIGN KEY (loan_officer_id) REFERENCES users(id),
            FOREIGN KEY (approved_by) REFERENCES users(id)
        )
    '''))

    # Add new columns if they don't exist
    # IMPORTANT: ALTER TABLE ADD COLUMN requires a valid SQL type name
    for col, col_type, default in [
        ('loan_number', 'TEXT', 'NULL'),
        ('payment_schedule', 'TEXT', "'monthly'"),
        ('fine_amount', 'REAL', '0'),
        ('fine_active', 'INTEGER', '0'),
        ('default_count', 'INTEGER', '0'),
        ('fine_date', 'DATE', 'NULL'),
        ('next_payment_date', 'DATE', 'NULL'),
        ('processing_fee', 'REAL', '0'),
        ('collateral_photo', 'TEXT', 'NULL'),
        ('duration_months', 'INTEGER', '1'),
        ('loan_date', 'DATE', "date('now')"),
        ('loan_time', 'TEXT', "time('now')"),
    ]:
        try:
            cursor.execute(f'ALTER TABLE loans ADD COLUMN {col} {col_type} DEFAULT {default}')
        except:
            pass

    # Repayments
    cursor.execute(_ddl('''
        CREATE TABLE IF NOT EXISTS repayments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            loan_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            payment_type TEXT DEFAULT 'principal' CHECK(payment_type IN ('principal', 'fine')),
            payment_method TEXT CHECK(payment_method IN ('cash', 'mpesa', 'mtn', 'airtel', 'bank', 'cheque')),
            reference TEXT,
            received_by INTEGER,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (loan_id) REFERENCES loans(id) ON DELETE CASCADE,
            FOREIGN KEY (received_by) REFERENCES users(id)
        )
    '''))

    # Migration: add payment_type column to repayments
    try:
        cursor.execute("ALTER TABLE repayments ADD COLUMN payment_type TEXT DEFAULT 'principal'")
    except:
        pass

    # Migration: widen payment_method constraint
    if not IS_POSTGRES:  # SQLite-only migration (PG handles this at schema level)
        try:
            conn.execute("ALTER TABLE repayments RENAME TO repayments_old")
            cursor.execute(_ddl('''
                CREATE TABLE repayments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    loan_id INTEGER NOT NULL,
                    amount REAL NOT NULL,
                    payment_type TEXT DEFAULT 'principal' CHECK(payment_type IN ('principal', 'fine')),
                    payment_method TEXT CHECK(payment_method IN ('cash', 'mpesa', 'mtn', 'airtel', 'bank', 'cheque')),
                    reference TEXT,
                    received_by INTEGER,
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (loan_id) REFERENCES loans(id) ON DELETE CASCADE,
                    FOREIGN KEY (received_by) REFERENCES users(id)
                )
            '''))
            conn.execute("INSERT INTO repayments SELECT * FROM repayments_old")
            conn.execute("DROP TABLE repayments_old")
        except:
            pass

    # Notifications
    cursor.execute(_ddl('''
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            type TEXT NOT NULL CHECK(type IN ('reminder', 'alert', 'info', 'warning', 'success')),
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            channel TEXT DEFAULT 'in_app' CHECK(channel IN ('in_app', 'sms', 'email', 'whatsapp')),
            is_read INTEGER DEFAULT 0,
            sent_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    '''))

    # Migration: add entity_type + entity_id to notifications

    for col in ['entity_type', 'entity_id']:
        try:
            cursor.execute(f'ALTER TABLE notifications ADD COLUMN {col} TEXT')
        except:
            pass

    # Audit log
    cursor.execute(_ddl('''
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT NOT NULL,
            entity TEXT,
            entity_id INTEGER,
            details TEXT,
            ip_address TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    '''))

    # SMS logs
    cursor.execute(_ddl('''
        CREATE TABLE IF NOT EXISTS sms_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT NOT NULL,
            message TEXT NOT NULL,
            status TEXT DEFAULT 'sent',
            api_response TEXT,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    '''))

    # Login attempts tracking (for brute-force protection)
    cursor.execute(_ddl('''
        CREATE TABLE IF NOT EXISTS login_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            ip_address TEXT,
            attempted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            success INTEGER DEFAULT 0
        )
    '''))

    conn.commit()
    conn.close()

def generate_loan_number():
    """Generate loan number: VL-XXX-YYYY-MM"""
    conn = get_db()
    now = datetime.now()
    year = now.year
    month = now.strftime('%m')

    # Get max sequence number this month (handles deleted loans)
    row = conn.execute(
        "SELECT MAX(CAST(SUBSTR(loan_number, 4, 3) AS INTEGER)) FROM loans WHERE loan_number LIKE ?",
        (f'VL-%-{year}-{month}',)
    ).fetchone()

    seq = (row[0] or 0) + 1
    loan_number = f"VL-{seq:03d}-{year}-{month}"

    conn.close()
    return loan_number

def create_user(username, email, password, role, full_name, phone=None, address=None, id_number=None, profile_picture=None):
    """Create a new user"""
    conn = get_db()
    try:
        cursor = conn.execute(
            'INSERT INTO users (username, email, password_hash, role, full_name, phone, address, id_number, profile_picture) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id',
            (username, email, generate_password_hash(password, method='pbkdf2:sha256'), role, full_name, phone, address, id_number, profile_picture)
        )
        user_id = cursor.fetchone()[0]
        conn.commit()
        return user_id
    except _get_integrity_error():
        return None
    finally:
        conn.close()

def ensure_admin_exists(username='admin', password='admin123?Vaulta', email='admin@vaulta.local', full_name='System Admin'):
    """
    Ensure the superuser admin account exists with the specified credentials.
    Creates the admin if it doesn't exist, or updates the password if it does.
    This runs on every startup to guarantee admin access.
    """
    conn = get_db()
    try:
        existing = conn.execute('SELECT id, password_hash FROM users WHERE username = ?', (username,)).fetchone()
        if existing:
            # Admin exists — update password to ensure it matches
            new_hash = generate_password_hash(password, method='pbkdf2:sha256')
            conn.execute('UPDATE users SET password_hash = ?, role = ?, is_active = 1 WHERE id = ?',
                        (new_hash, 'admin', existing['id']))
            conn.commit()
            print(f"✅ Admin user '{username}' verified (password updated)")
        else:
            # Admin doesn't exist — create it
            password_hash = generate_password_hash(password, method='pbkdf2:sha256')
            conn.execute(
                'INSERT INTO users (username, email, password_hash, role, full_name, is_active) VALUES (?, ?, ?, ?, ?, 1)',
                (username, email, password_hash, 'admin', full_name)
            )
            conn.commit()
            print(f"✅ Admin user '{username}' created successfully")
    except Exception as e:
        print(f"⚠️  Admin setup warning: {e}")
    finally:
        conn.close()

def update_user_profile_picture(user_id, filename):
    """Update user profile picture"""
    conn = get_db()
    conn.execute('UPDATE users SET profile_picture = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?', (filename, user_id))
    conn.commit()
    conn.close()

def authenticate_user(username, password):
    """Authenticate user and return user data"""
    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE username = ? AND is_active = 1', (username,)).fetchone()
    conn.close()
    if user and check_password_hash(user['password_hash'], password):
        return dict(user)
    return None

def record_login_attempt(username, ip_address=None, success=False):
    """Record a login attempt for tracking/lockout"""
    conn = get_db()
    conn.execute(
        'INSERT INTO login_attempts (username, ip_address, success) VALUES (?, ?, ?)',
        (username, ip_address, 1 if success else 0)
    )
    conn.commit()
    conn.close()

def get_failed_attempts(username, within_minutes=15):
    """Get number of failed login attempts within a time window"""
    conn = get_db()
    # Use UTC to match SQLite CURRENT_TIMESTAMP
    cutoff = (datetime.utcnow() - timedelta(minutes=within_minutes)).strftime('%Y-%m-%d %H:%M:%S')
    count = conn.execute(
        "SELECT COUNT(*) FROM login_attempts WHERE username = ? AND success = 0 AND attempted_at >= ?",
        (username, cutoff)
    ).fetchone()[0]
    conn.close()
    return count

def is_account_locked(username, max_attempts=5, lockout_minutes=15):
    """Check if account is locked due to too many failed attempts"""
    failed = get_failed_attempts(username, within_minutes=lockout_minutes)
    return failed >= max_attempts

def change_password(user_id, new_password):
    """Update user password"""
    password_hash = generate_password_hash(new_password, method='pbkdf2:sha256')
    conn = get_db()
    conn.execute(
        'UPDATE users SET password_hash = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
        (password_hash, user_id)
    )
    conn.commit()
    conn.close()

def get_user_by_id(user_id):
    """Get user by ID"""
    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    conn.close()
    return dict(user) if user else None

def get_client_profile(user_id):
    """Get client profile"""
    conn = get_db()
    profile = conn.execute('SELECT * FROM client_profiles WHERE user_id = ?', (user_id,)).fetchone()
    conn.close()
    return dict(profile) if profile else None

def update_client_profile(user_id, **kwargs):
    """Update or create client profile"""
    conn = get_db()
    existing = conn.execute('SELECT id FROM client_profiles WHERE user_id = ?', (user_id,)).fetchone()
    if existing:
        fields = ', '.join([f'{k} = ?' for k in kwargs.keys()])
        values = list(kwargs.values()) + [user_id]
        conn.execute(f'UPDATE client_profiles SET {fields} WHERE user_id = ?', values)
    else:
        fields = ', '.join(['user_id'] + list(kwargs.keys()))
        placeholders = ', '.join(['?'] * (len(kwargs) + 1))
        values = [user_id] + list(kwargs.values())
        conn.execute(f'INSERT INTO client_profiles ({fields}) VALUES ({placeholders})', values)
    conn.commit()
    conn.close()

def create_loan(client_id, principal, interest_rate, interest_type, payment_schedule, duration_months, purpose, loan_officer_id=None, guarantor_name=None, guarantor_phone=None, processing_fee=0, collateral_photo=None, loan_date=None, loan_time=None):
    """Create a new loan with auto-generated loan number"""
    loan_number = generate_loan_number()

    # Calculate total amount
    if interest_type == 'flat':
        total_interest = principal * (interest_rate / 100) * duration_months
    else:
        total_interest = principal * (interest_rate / 100) * duration_months / 2

    total_amount = principal + total_interest
    balance = total_amount
    
    # Use provided date/time or default to now
    if loan_date:
        start_date = loan_date
    else:
        start_date = datetime.now().strftime('%Y-%m-%d')
    
    if not loan_time:
        loan_time = datetime.now().strftime('%H:%M:%S')
    
    due_date = (datetime.now() + timedelta(days=30 * duration_months)).strftime('%Y-%m-%d')

    # Calculate next payment date based on schedule
    if payment_schedule == 'daily':
        next_payment = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
    elif payment_schedule == 'weekly':
        next_payment = (datetime.now() + timedelta(weeks=1)).strftime('%Y-%m-%d')
    else:  # monthly
        next_payment = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')

    conn = get_db()
    cursor = conn.execute(
        '''INSERT INTO loans (loan_number, client_id, loan_officer_id, principal, interest_rate, interest_type,
           payment_schedule, total_amount, balance, fine_amount, fine_active, default_count,
           purpose, guarantor_name, guarantor_phone, start_date, loan_date, loan_time, due_date, next_payment_date, processing_fee, collateral_photo)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id''',
        (loan_number, client_id, loan_officer_id, principal, interest_rate, interest_type,
         payment_schedule, total_amount, balance, purpose, guarantor_name, guarantor_phone,
         start_date, loan_date or start_date, loan_time, due_date, next_payment, processing_fee, collateral_photo)
    )
    loan_id = cursor.fetchone()[0]
    conn.commit()
    conn.close()
    return loan_id, loan_number

def calculate_payment_schedule(loan):
    """Calculate full payment schedule breakdown for a loan.
    Returns dict with: installment_amount, total_payments, completion_date, schedule_table
    """
    if isinstance(loan, dict):
        principal = loan['principal']
        interest_rate = loan['interest_rate']
        interest_type = loan['interest_type']
        payment_schedule = loan['payment_schedule']
        duration_months = loan.get('duration_months') or _estimate_months(loan.get('due_date'), loan.get('start_date'))
        total_amount = loan['total_amount']
        start_date = loan['start_date']
        amount_paid = loan.get('amount_paid', 0)
    else:
        return None

    # Calculate installment amount
    if payment_schedule == 'daily':
        total_payments = duration_months * 30
        interval = timedelta(days=1)
        label = 'Daily'
    elif payment_schedule == 'weekly':
        total_payments = duration_months * 4
        interval = timedelta(weeks=1)
        label = 'Weekly'
    else:
        total_payments = duration_months
        interval = timedelta(days=30)
        label = 'Monthly'

    total_payments = max(1, int(total_payments))
    installment_amount = round(total_amount / total_payments, 2)

    # Build schedule table
    schedule = []
    current_date = datetime.strptime(start_date, '%Y-%m-%d') if isinstance(start_date, str) else start_date
    cumulative = 0
    today = datetime.now().strftime('%Y-%m-%d')

    for i in range(1, total_payments + 1):
        pay_date = current_date + interval * i
        pay_date_str = pay_date.strftime('%Y-%m-%d')
        cumulative += installment_amount
        remaining = round(total_amount - cumulative, 2)

        # Determine status
        if pay_date_str < today:
            status = 'overdue' if cumulative > amount_paid + installment_amount else 'paid'
        elif pay_date_str == today:
            status = 'due_today'
        else:
            status = 'upcoming'

        schedule.append({
            'number': i,
            'date': pay_date_str,
            'amount': installment_amount,
            'cumulative': round(cumulative, 2),
            'remaining': max(0, remaining),
            'status': status
        })

    completion_date = (current_date + interval * total_payments).strftime('%Y-%m-%d')

    return {
        'label': label,
        'installment_amount': installment_amount,
        'total_payments': total_payments,
        'completion_date': completion_date,
        'schedule': schedule
    }

def _estimate_months(due_date, start_date):
    """Estimate duration in months from dates"""
    if due_date and start_date:
        if isinstance(due_date, str):
            due = datetime.strptime(due_date, '%Y-%m-%d')
        else:
            due = due_date
        if isinstance(start_date, str):
            start = datetime.strptime(start_date, '%Y-%m-%d')
        else:
            start = start_date
        return max(1, round((due - start).days / 30))
    return 1

def approve_loan(loan_id, approved_by):
    """Approve a loan"""
    conn = get_db()
    conn.execute(
        'UPDATE loans SET status = ?, approved_by = ?, approved_at = CURRENT_TIMESTAMP WHERE id = ?',
        ('active', approved_by, loan_id)
    )
    conn.commit()
    conn.close()

def reject_loan(loan_id, approved_by):
    """Reject a loan"""
    conn = get_db()
    conn.execute(
        'UPDATE loans SET status = ?, approved_by = ?, approved_at = CURRENT_TIMESTAMP WHERE id = ?',
        ('rejected', approved_by, loan_id)
    )
    conn.commit()
    conn.close()

def check_and_apply_fine(loan_id):
    """Check if fine should be applied and apply it automatically.
    Fines applied when payment is 1+ day past due_date or next_payment_date.
    Fine is **2% of the total loan amount** (one-time fine per overdue event).

    Returns:
        dict with 'fine_applied' (bool), 'loan_id' (int), 'loan' (dict or None)
        or None if loan not found / not overdue.
        Callers should check result and result['fine_applied'].
    """
    conn = get_db()
    loan = conn.execute('SELECT * FROM loans WHERE id = ?', (loan_id,)).fetchone()
    if not loan:
        conn.close()
        return None

    today = datetime.now().strftime('%Y-%m-%d')

    # Determine if loan is overdue — check due_date or next_payment_date
    overdue = False
    if loan['due_date'] and loan['due_date'] < today:
        overdue = True
    elif loan['next_payment_date'] and loan['next_payment_date'] < today:
        overdue = True

    if not overdue:
        conn.close()
        return None

    # Loan is overdue — apply fine (only once, if not already applied)
    new_default_count = loan['default_count'] + 1
    fine_applied = False

    if not loan['fine_active']:
        # 2% of total loan amount — a one-time fine, not cumulative
        fine_amount = loan['total_amount'] * 0.02  # 2% of total loan
        fine_date = today
        conn.execute(
            'UPDATE loans SET default_count = ?, fine_amount = fine_amount + ?, fine_active = 1, '
            'fine_date = ?, balance = balance + ?, status = "defaulted", updated_at = CURRENT_TIMESTAMP WHERE id = ?',
            (new_default_count, fine_amount, fine_date, fine_amount, loan_id)
        )
        fine_applied = True

        # Notify client in-app
        conn.execute(
            'INSERT INTO notifications (user_id, type, title, message, channel) VALUES (?, ?, ?, ?, ?)',
            (loan['client_id'], 'warning', 'Fine Applied!',
             f'A fine of UGX {fine_amount:,.0f} (2% of total loan) has been applied to your loan {loan["loan_number"]} due to missed payment.', 'in_app')
        )
    else:
        conn.execute(
            'UPDATE loans SET default_count = ?, status = "defaulted", updated_at = CURRENT_TIMESTAMP WHERE id = ?',
            (new_default_count, loan_id)
        )

    conn.commit()
    conn.close()

    # Get fresh loan data for the caller to use (e.g., for SMS)
    fresh_loan = get_loan(loan_id)

    return {
        'fine_applied': fine_applied,
        'loan_id': loan_id,
        'loan': fresh_loan
    }


def apply_manual_fine(loan_id, fine_amount, fine_date, applied_by):
    """Admin manually applies a fine to a loan with a specific amount and date.

    This adds the fine to the existing fine_amount, marks fine as active,
    updates the balance, and logs the action.

    Args:
        loan_id: The loan ID
        fine_amount: The fine amount to apply (will be added to existing)
        fine_date: The date (YYYY-MM-DD) the fine is applied
        applied_by: User ID of the admin applying the fine

    Returns:
        dict with loan info, or None if loan not found
    """
    conn = get_db()
    loan = conn.execute('SELECT * FROM loans WHERE id = ?', (loan_id,)).fetchone()
    if not loan:
        conn.close()
        return None

    new_default_count = loan['default_count'] + 1

    conn.execute(
        'UPDATE loans SET default_count = ?, fine_amount = fine_amount + ?, fine_active = 1, '
        'fine_date = ?, balance = balance + ?, status = "defaulted", updated_at = CURRENT_TIMESTAMP WHERE id = ?',
        (new_default_count, fine_amount, fine_date, fine_amount, loan_id)
    )

    # Log audit entry
    from app.database import log_audit
    try:
        log_audit(applied_by, 'manual_fine', 'loan', loan_id,
                  f'Manual fine of UGX {fine_amount:,.0f} applied on {fine_date}')
    except Exception:
        pass  # non-critical

    # Notify client
    conn.execute(
        'INSERT INTO notifications (user_id, type, title, message, channel) VALUES (?, ?, ?, ?, ?)',
        (loan['client_id'], 'warning', 'Fine Applied (Manual)',
         f'A manual fine of UGX {fine_amount:,.0f} (2%) has been applied to your loan {loan["loan_number"]}.', 'in_app')
    )

    conn.commit()
    conn.close()

    fresh_loan = get_loan(loan_id)
    return fresh_loan

def toggle_fine(loan_id, action):
    """Pause or activate fine manually"""
    conn = get_db()
    if action == 'pause':
        conn.execute('UPDATE loans SET fine_active = 0, updated_at = CURRENT_TIMESTAMP WHERE id = ?', (loan_id,))
    elif action == 'activate':
        conn.execute('UPDATE loans SET fine_active = 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?', (loan_id,))
    conn.commit()
    conn.close()

def add_repayment(loan_id, amount, payment_method, reference, received_by, notes=None, payment_type='principal'):
    """Add a repayment (principal or fine)"""
    conn = get_db()

    loan = conn.execute('SELECT balance, total_amount, fine_amount, fine_active, fine_date FROM loans WHERE id = ?', (loan_id,)).fetchone()
    if not loan:
        conn.close()
        return False

    if payment_type == 'fine':
        # Fine-only payment — only reduce fine_amount
        new_fine = max(0, loan['fine_amount'] - amount)
        fine_paid = amount - (loan['fine_amount'] - new_fine)
        new_balance = loan['balance']
        # Deactivate fine if fully paid
        fine_active = 1 if new_fine > 0 else 0

        conn.execute(
            'INSERT INTO repayments (loan_id, amount, payment_type, payment_method, reference, received_by, notes) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (loan_id, amount, 'fine', payment_method, reference, received_by, notes)
        )

        conn.execute(
            'UPDATE loans SET fine_amount = ?, fine_active = ?, fine_date = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
            (new_fine, fine_active, None if fine_active == 0 else loan.get('fine_date'), loan_id)
        )
    else:
        # Principal payment — only reduce balance
        new_balance = max(0, loan['balance'] - amount)

        new_fine = loan['fine_amount']
        status = 'paid' if new_balance <= 0 else 'active'

        conn.execute(
            'INSERT INTO repayments (loan_id, amount, payment_type, payment_method, reference, received_by, notes) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (loan_id, amount, 'principal', payment_method, reference, received_by, notes)
        )

        conn.execute(
            'UPDATE loans SET balance = ?, amount_paid = ?, status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
            (new_balance, loan['total_amount'] - new_balance, status, loan_id)
        )

    conn.commit()

    # Send notification to client
    client = conn.execute('SELECT client_id FROM loans WHERE id = ?', (loan_id,)).fetchone()
    if client:
        pay_type_label = 'fine payment' if payment_type == 'fine' else 'payment'
        msg = f'Your {pay_type_label} of UGX {amount:,.0f} has been received.'
        if payment_type == 'principal':
            msg += f' New balance: UGX {new_balance:,.0f}.'
        elif new_fine > 0:
            msg += f' Remaining fine: UGX {new_fine:,.0f}.'
        else:
            msg += ' Your fine is fully paid!'
        conn.execute(
            'INSERT INTO notifications (user_id, type, title, message, channel) VALUES (?, ?, ?, ?, ?)',
            (client['client_id'], 'success', 'Payment Received', msg, 'in_app')
        )
        conn.commit()

    conn.close()
    return True

def get_loans(filters=None):
    """Get loans with optional filters"""
    conn = get_db()
    query = '''
        SELECT l.*, u.full_name as client_name, u.phone as client_phone, u.email as client_email,
               u.profile_picture as client_photo, lo.full_name as officer_name
        FROM loans l
        JOIN users u ON l.client_id = u.id
        LEFT JOIN users lo ON l.loan_officer_id = lo.id
    '''
    params = []

    if filters:
        conditions = []
        if filters.get('status'):
            conditions.append('l.status = ?')
            params.append(filters['status'])
        if filters.get('client_id'):
            conditions.append('l.client_id = ?')
            params.append(filters['client_id'])
        if filters.get('loan_officer_id'):
            conditions.append('l.loan_officer_id = ?')
            params.append(filters['loan_officer_id'])
        if filters.get('search'):
            conditions.append('(l.loan_number LIKE ? OR u.full_name LIKE ? OR u.phone LIKE ?)')
            search_term = f'%{filters["search"]}%'
            params.extend([search_term, search_term, search_term])
        if conditions:
            query += ' WHERE ' + ' AND '.join(conditions)

    query += ' ORDER BY l.created_at DESC'
    loans = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(l) for l in loans]

def get_loan(loan_id):
    """Get single loan by ID"""
    conn = get_db()
    loan = conn.execute('''
        SELECT l.*, u.full_name as client_name, u.phone as client_phone, u.email as client_email,
               u.profile_picture as client_photo, lo.full_name as officer_name
        FROM loans l
        JOIN users u ON l.client_id = u.id
        LEFT JOIN users lo ON l.loan_officer_id = lo.id
        WHERE l.id = ?
    ''', (loan_id,)).fetchone()
    conn.close()
    return dict(loan) if loan else None


def get_loan_by_number(loan_number):
    """Get single loan by loan number (for client loan-number login)"""
    conn = get_db()
    loan = conn.execute('''
        SELECT l.*, u.full_name as client_name, u.phone as client_phone, u.email as client_email,
               u.profile_picture as client_photo, lo.full_name as officer_name
        FROM loans l
        JOIN users u ON l.client_id = u.id
        LEFT JOIN users lo ON l.loan_officer_id = lo.id
        WHERE l.loan_number = ?
    ''', (loan_number,)).fetchone()
    conn.close()
    return dict(loan) if loan else None

def get_repayments(loan_id):
    """Get repayments for a loan"""
    conn = get_db()
    repayments = conn.execute('''
        SELECT r.*, u.full_name as received_by_name
        FROM repayments r
        LEFT JOIN users u ON r.received_by = u.id
        WHERE r.loan_id = ?
        ORDER BY r.created_at DESC
    ''', (loan_id,)).fetchall()
    conn.close()
    return [dict(r) for r in repayments]

def get_notifications(user_id, unread_only=False):
    """Get notifications for a user"""
    conn = get_db()
    query = 'SELECT * FROM notifications WHERE user_id = ?'
    params = [user_id]
    if unread_only:
        query += ' AND is_read = 0'
    query += ' ORDER BY created_at DESC LIMIT 50'
    notifications = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(n) for n in notifications]

def mark_notification_read(notification_id):
    """Mark notification as read"""
    conn = get_db()
    conn.execute('UPDATE notifications SET is_read = 1 WHERE id = ?', (notification_id,))
    conn.commit()
    conn.close()

def mark_all_notifications_read(user_id):
    """Mark all notifications as read"""
    conn = get_db()
    conn.execute('UPDATE notifications SET is_read = 1 WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

def send_notification(user_id, type, title, message, channel='in_app', entity_type=None, entity_id=None):
    """Send a notification"""
    conn = get_db()
    conn.execute(
        'INSERT INTO notifications (user_id, type, title, message, channel, entity_type, entity_id) VALUES (?, ?, ?, ?, ?, ?, ?)',
        (user_id, type, title, message, channel, entity_type, str(entity_id) if entity_id else None)
    )
    conn.commit()
    conn.close()

def get_dashboard_stats():
    """Get dashboard statistics"""
    conn = get_db()
    stats = {}

    stats['total_clients'] = conn.execute("SELECT COUNT(*) FROM users WHERE role = 'client'").fetchone()[0]
    stats['total_loans'] = conn.execute("SELECT COUNT(*) FROM loans").fetchone()[0]
    stats['active_loans'] = conn.execute("SELECT COUNT(*) FROM loans WHERE status = 'active'").fetchone()[0]
    stats['pending_loans'] = conn.execute("SELECT COUNT(*) FROM loans WHERE status = 'pending'").fetchone()[0]
    stats['total_disbursed'] = conn.execute("SELECT COALESCE(SUM(principal), 0) FROM loans WHERE status IN ('active', 'paid')").fetchone()[0]
    stats['total_collected'] = conn.execute("SELECT COALESCE(SUM(amount_paid), 0) FROM loans").fetchone()[0]
    stats['total_outstanding'] = conn.execute("SELECT COALESCE(SUM(balance), 0) FROM loans WHERE status = 'active'").fetchone()[0]
    stats['defaulted_loans'] = conn.execute("SELECT COUNT(*) FROM loans WHERE status = 'defaulted'").fetchone()[0]
    stats['total_fines'] = conn.execute("SELECT COALESCE(SUM(fine_amount), 0) FROM loans WHERE fine_active = 1").fetchone()[0]

    # Recent loans
    stats['recent_loans'] = [dict(l) for l in conn.execute('''
        SELECT l.id, l.loan_number, l.principal, l.status, l.payment_schedule, l.amount_paid, l.balance, l.fine_amount, l.default_count, l.created_at, u.full_name as client_name
        FROM loans l JOIN users u ON l.client_id = u.id
        ORDER BY l.created_at DESC LIMIT 10
    ''').fetchall()]

    # Overdue loans
    stats['overdue_loans'] = [dict(l) for l in conn.execute('''
        SELECT l.id, l.loan_number, l.balance, l.due_date, l.next_payment_date, l.fine_amount, l.fine_active,
               u.full_name as client_name, u.phone as client_phone
        FROM loans l JOIN users u ON l.client_id = u.id
        WHERE l.status IN ('active', 'defaulted') AND l.next_payment_date < CURRENT_DATE
        ORDER BY l.next_payment_date ASC
    ''').fetchall()]

    conn.close()
    return stats

def get_all_users(role=None, include_inactive=False):
    """Get all users, optionally filtered by role.

    Args:
        role: Filter by role ('admin', 'loan_officer', 'client')
        include_inactive: If False (default), only returns active users (is_active = 1)
    """
    conn = get_db()

    conditions = []
    params = []

    if not include_inactive:
        conditions.append('is_active = 1')

    if role:
        conditions.append('role = ?')
        params.append(role)

    where_clause = ''
    if conditions:
        where_clause = 'WHERE ' + ' AND '.join(conditions)

    sql = f'SELECT * FROM users {where_clause} ORDER BY created_at DESC'
    users = conn.execute(sql, params).fetchall() if params else conn.execute(sql).fetchall()

    conn.close()
    return [dict(u) for u in users]

def update_user(user_id, data):
    """Update user fields. data is a dict of column: value."""
    allowed = {'username', 'email', 'full_name', 'phone', 'address', 'id_number', 'role', 'is_active', 'profile_picture'}
    fields = {k: v for k, v in data.items() if k in allowed and v is not None}
    if not fields:
        return False
    conn = get_db()
    try:
        set_clause = ', '.join(f'{k} = ?' for k in fields)
        values = list(fields.values()) + [user_id]
        conn.execute(f'UPDATE users SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ?', values)
        conn.commit()
        return True
    except Exception as e:
        conn.close()
        raise e
    finally:
        conn.close()

def delete_user(user_id):
    """Soft-delete a user by setting is_active = 0.
    Returns False if user has active loans (for clients).
    """
    conn = get_db()
    try:
        # Check for active loans if user is a client
        user = conn.execute('SELECT role FROM users WHERE id = ?', (user_id,)).fetchone()
        if user and user['role'] == 'client':
            active = conn.execute(
                "SELECT COUNT(*) FROM loans WHERE client_id = ? AND status IN ('active', 'pending')",
                (user_id,)
            ).fetchone()[0]
            if active > 0:
                return False, f'Client has {active} active/pending loan(s). Cancel them first.'
        conn.execute('UPDATE users SET is_active = 0, updated_at = CURRENT_TIMESTAMP WHERE id = ?', (user_id,))
        conn.commit()
        return True, 'User deactivated'
    finally:
        conn.close()

def get_all_repayments(limit=100):
    """Get all repayments with loan + client info"""
    conn = get_db()
    rows = conn.execute('''
        SELECT r.*, l.loan_number, u.full_name AS client_name
        FROM repayments r
        JOIN loans l ON r.loan_id = l.id
        JOIN users u ON l.client_id = u.id
        ORDER BY r.created_at DESC LIMIT ?
    ''', (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def update_repayment(repayment_id, amount, payment_method, reference, notes):
    """Update a repayment record"""
    conn = get_db()
    try:
        conn.execute(
            'UPDATE repayments SET amount = ?, payment_method = ?, reference = ?, notes = ? WHERE id = ?',
            (amount, payment_method, reference, notes, repayment_id)
        )
        conn.commit()
        return True
    except Exception as e:
        raise e
    finally:
        conn.close()

def delete_repayment(repayment_id):
    """Delete a repayment record and recalculate loan balance.
    Admin-only operation with audit logging.
    """
    conn = get_db()
    try:
        # Get the loan_id and amount before deleting
        r = conn.execute('SELECT loan_id, amount FROM repayments WHERE id = ?', (repayment_id,)).fetchone()
        if not r:
            return False
        conn.execute('DELETE FROM repayments WHERE id = ?', (repayment_id,))
        conn.commit()
        # Recalculate loan balance
        total_paid = conn.execute(
            'SELECT COALESCE(SUM(amount), 0) FROM repayments WHERE loan_id = ?',
            (r['loan_id'],)
        ).fetchone()[0]
        loan = conn.execute('SELECT total_amount FROM loans WHERE id = ?', (r['loan_id'],)).fetchone()
        if loan:
            new_balance = loan['total_amount'] - total_paid
            new_status = 'active' if new_balance > 0 else 'paid'
            conn.execute(
                'UPDATE loans SET amount_paid = ?, balance = ?, status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
                (total_paid, new_balance, new_status, r['loan_id'])
            )
            conn.commit()
        return True
    except Exception as e:
        raise e
    finally:
        conn.close()

def get_audit_logs(limit=100):
    """Get recent audit log entries with user names"""
    conn = get_db()
    rows = conn.execute('''
        SELECT a.*, u.full_name AS user_name
        FROM audit_log a
        LEFT JOIN users u ON a.user_id = u.id
        ORDER BY a.created_at DESC LIMIT ?
    ''', (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def log_audit(user_id, action, entity=None, entity_id=None, details=None, ip_address=None):
    """Log an audit entry"""
    conn = get_db()
    conn.execute(
        'INSERT INTO audit_log (user_id, action, entity, entity_id, details, ip_address) VALUES (?, ?, ?, ?, ?, ?)',
        (user_id, action, entity, entity_id, details, ip_address)
    )
    conn.commit()
    conn.close()

def get_monthly_pnl(year=None, month=None):
    """Get Profit & Loss data for a specific month"""
    from datetime import date
    if not year:
        year = date.today().year
    if not month:
        month = date.today().month

    month_start = f"{year}-{month:02d}-01"
    if month == 12:
        month_end = f"{year+1}-01-01"
    else:
        month_end = f"{year}-{month+1:02d}-01"

    conn = get_db()

    # Processing fees from loans created this month
    processing_fees = conn.execute(
        "SELECT COALESCE(SUM(processing_fee), 0) FROM loans WHERE start_date >= ? AND start_date < ?",
        (month_start, month_end)
    ).fetchone()[0]

    # Interest earned (total_amount - principal) for loans created this month
    interest_earned = conn.execute(
        "SELECT COALESCE(SUM(total_amount - principal), 0) FROM loans WHERE start_date >= ? AND start_date < ?",
        (month_start, month_end)
    ).fetchone()[0]

    # Total repayments received this month
    repayments = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM repayments WHERE created_at >= ? AND created_at < ?",
        (month_start, month_end)
    ).fetchone()[0]

    # Loans created this month
    loans_created = conn.execute(
        "SELECT COUNT(*) FROM loans WHERE start_date >= ? AND start_date < ?",
        (month_start, month_end)
    ).fetchone()[0]

    # Loans paid off this month
    loans_paid = conn.execute(
        "SELECT COUNT(*) FROM loans WHERE status = 'paid' AND updated_at >= ? AND updated_at < ?",
        (month_start, month_end)
    ).fetchone()[0]

    # Fines collected this month (from repayments that include fines)
    fines_collected = conn.execute(
        "SELECT COALESCE(SUM(l.fine_amount), 0) FROM loans l JOIN repayments r ON l.id = r.loan_id WHERE r.created_at >= ? AND r.created_at < ? AND l.fine_active = 1",
        (month_start, month_end)
    ).fetchone()[0]

    # Outstanding balance at month end
    outstanding = conn.execute(
        "SELECT COALESCE(SUM(balance), 0) FROM loans WHERE status = 'active'"
    ).fetchone()[0]

    # Total disbursed this month
    disbursed = conn.execute(
        "SELECT COALESCE(SUM(principal), 0) FROM loans WHERE start_date >= ? AND start_date < ?",
        (month_start, month_end)
    ).fetchone()[0]

    # Loan details for the month
    loan_details = [dict(l) for l in conn.execute(
        '''SELECT l.loan_number, l.client_id, u.full_name as client_name, l.principal,
           l.processing_fee, l.total_amount - l.principal as interest, l.status, l.start_date
           FROM loans l JOIN users u ON l.client_id = u.id
           WHERE l.start_date >= ? AND l.start_date < ?
           ORDER BY l.start_date DESC''',
        (month_start, month_end)
    ).fetchall()]

    conn.close()

    return {
        'year': year,
        'month': month,
        'month_name': date(year, month, 1).strftime('%B %Y'),
        'processing_fees': processing_fees,
        'interest_earned': interest_earned,
        'repayments': repayments,
        'fines_collected': fines_collected,
        'total_revenue': processing_fees + interest_earned + fines_collected,
        'loans_created': loans_created,
        'loans_paid': loans_paid,
        'disbursed': disbursed,
        'outstanding': outstanding,
        'net_profit': (processing_fees + interest_earned + fines_collected) - disbursed,
        'loan_details': loan_details
    }

def get_balance_sheet(year=None, month=None):
    """Get full Balance Sheet + Income Statement for a specific month"""
    from datetime import date
    if not year:
        year = date.today().year
    if not month:
        month = date.today().month

    month_start = f"{year}-{month:02d}-01"
    if month == 12:
        month_end = f"{year+1}-01-01"
    else:
        month_end = f"{year}-{month+1:02d}-01"

    conn = get_db()

    # === INCOME STATEMENT ===
    # Revenue
    processing_fees = conn.execute(
        "SELECT COALESCE(SUM(processing_fee), 0) FROM loans WHERE start_date >= ? AND start_date < ?",
        (month_start, month_end)
    ).fetchone()[0]

    interest_earned = conn.execute(
        "SELECT COALESCE(SUM(total_amount - principal), 0) FROM loans WHERE start_date >= ? AND start_date < ?",
        (month_start, month_end)
    ).fetchone()[0]

    fines_collected = conn.execute(
        "SELECT COALESCE(SUM(l.fine_amount), 0) FROM loans l JOIN repayments r ON l.id = r.loan_id WHERE r.created_at >= ? AND r.created_at < ? AND l.fine_active = 1",
        (month_start, month_end)
    ).fetchone()[0]

    total_revenue = processing_fees + interest_earned + fines_collected

    # Expenses (disbursed principal = cost of funds)
    disbursed = conn.execute(
        "SELECT COALESCE(SUM(principal), 0) FROM loans WHERE start_date >= ? AND start_date < ?",
        (month_start, month_end)
    ).fetchone()[0]

    net_profit = total_revenue - disbursed

    # === BALANCE SHEET ===
    # ASSETS
    # Current Assets
    cash_on_hand = conn.execute(
        "SELECT COALESCE(SUM(r.amount), 0) FROM repayments r WHERE r.created_at < ?",
        (month_end,)
    ).fetchone()[0]

    accounts_receivable = conn.execute(
        "SELECT COALESCE(SUM(balance), 0) FROM loans WHERE status IN ('active', 'pending', 'approved')"
    ).fetchone()[0]

    fees_receivable = conn.execute(
        "SELECT COALESCE(SUM(processing_fee), 0) FROM loans WHERE status IN ('active', 'pending', 'approved')"
    ).fetchone()[0]

    total_current_assets = cash_on_hand + accounts_receivable + fees_receivable

    # Non-Current Assets (fines owed)
    fines_receivable = conn.execute(
        "SELECT COALESCE(SUM(fine_amount), 0) FROM loans WHERE fine_active = 1 AND status IN ('active', 'defaulted')"
    ).fetchone()[0]

    total_assets = total_current_assets + fines_receivable

    # LIABILITIES
    # For a simple lending business, liabilities could include:
    # - Payables (none tracked yet, so 0)
    # - Deferred revenue (unearned interest)
    unearned_interest = conn.execute(
        "SELECT COALESCE(SUM(total_amount - principal), 0) FROM loans WHERE status IN ('active', 'pending', 'approved')"
    ).fetchone()[0]

    total_liabilities = unearned_interest

    # EQUITY
    # Retained earnings = cumulative net profit
    cumulative_revenue = conn.execute(
        "SELECT COALESCE(SUM(processing_fee), 0) + COALESCE(SUM(total_amount - principal), 0) FROM loans"
    ).fetchone()[0]

    cumulative_disbursed = conn.execute(
        "SELECT COALESCE(SUM(principal), 0) FROM loans"
    ).fetchone()[0]

    retained_earnings = cumulative_revenue - cumulative_disbursed

    total_equity = retained_earnings

    # Verify: Assets = Liabilities + Equity
    total_liabilities_equity = total_liabilities + total_equity

    # Loan breakdown for the month
    loan_details = [dict(l) for l in conn.execute(
        '''SELECT l.loan_number, u.full_name as client_name, l.principal,
           l.processing_fee, l.total_amount - l.principal as interest,
           l.amount_paid, l.balance, l.fine_amount, l.status, l.start_date
           FROM loans l JOIN users u ON l.client_id = u.id
           WHERE l.start_date >= ? AND l.start_date < ?
           ORDER BY l.start_date DESC''',
        (month_start, month_end)
    ).fetchall()]

    # Repayment summary for the month
    repayments_summary = [dict(r) for r in conn.execute(
        '''SELECT r.amount, r.payment_method, r.reference, r.created_at,
           l.loan_number, u.full_name as client_name
           FROM repayments r
           JOIN loans l ON r.loan_id = l.id
           JOIN users u ON l.client_id = u.id
           WHERE r.created_at >= ? AND r.created_at < ?
           ORDER BY r.created_at DESC''',
        (month_start, month_end)
    ).fetchall()]

    conn.close()

    return {
        'year': year,
        'month': month,
        'month_name': date(year, month, 1).strftime('%B %Y'),
        # Income Statement
        'processing_fees': processing_fees,
        'interest_earned': interest_earned,
        'fines_collected': fines_collected,
        'total_revenue': total_revenue,
        'disbursed': disbursed,
        'net_profit': net_profit,
        # Balance Sheet - Assets
        'cash_on_hand': cash_on_hand,
        'accounts_receivable': accounts_receivable,
        'fees_receivable': fees_receivable,
        'total_current_assets': total_current_assets,
        'fines_receivable': fines_receivable,
        'total_assets': total_assets,
        # Balance Sheet - Liabilities
        'unearned_interest': unearned_interest,
        'total_liabilities': total_liabilities,
        # Balance Sheet - Equity
        'retained_earnings': retained_earnings,
        'total_equity': total_equity,
        'total_liabilities_equity': total_liabilities_equity,
        # Details
        'loan_details': loan_details,
        'repayments_summary': repayments_summary
    }

def run_daily_checks():
    """Run daily checks for overdue payments and apply fines.

    Returns:
        list of dicts for loans that had new fines applied (each with 'loan_id' and 'loan')
    """
    conn = get_db()
    active_loans = conn.execute('SELECT id FROM loans WHERE status IN ("active", "defaulted")').fetchall()
    conn.close()

    fined_loans = []
    for loan in active_loans:
        result = check_and_apply_fine(loan['id'])
        if result and result['fine_applied']:
            fined_loans.append(result)

    return fined_loans

def import_data_file(filepath, ext):
    """Import data from CSV or Excel file. Auto-detects entity type and imports."""
    import csv
    from werkzeug.security import generate_password_hash

    # Map friendly headers to database column names
    HEADER_MAP = {
        # Loan headers
        'loan id': 'loan_id',
        'loanid': 'loan_id',
        'loan_number': 'loan_number',
        'loan number': 'loan_number',
        'loan no': 'loan_number',
        'member id': 'client_id',
        'memberid': 'client_id',
        'client id': 'client_id',
        'clientid': 'client_id',
        'member name': 'client_name',
        'membername': 'client_name',
        'client name': 'client_name',
        'clientname': 'client_name',
        'member phone': 'client_phone',
        'memberphone': 'client_phone',
        'client phone': 'client_phone',
        'clientphone': 'client_phone',
        'principal (ugx)': 'principal',
        'principal': 'principal',
        'amount': 'principal',
        'loan amount': 'principal',
        'period (months)': 'duration_months',
        'period': 'duration_months',
        'period (months)': 'duration_months',
        'duration': 'duration_months',
        'duration (months)': 'duration_months',
        'term': 'duration_months',
        'monthly rate (%)': 'interest_rate',
        'monthly rate': 'interest_rate',
        'interest rate': 'interest_rate',
        'rate': 'interest_rate',
        'rate (%)': 'interest_rate',
        'payment mode': 'payment_schedule',
        'paymentmode': 'payment_schedule',
        'payment method': 'payment_method',
        'paymentmethod': 'payment_method',
        'schedule': 'payment_schedule',
        'processing fee (ugx)': 'processing_fee',
        'processing fee': 'processing_fee',
        'processingfee': 'processing_fee',
        'fee': 'processing_fee',
        'fee paid': 'fee_paid',
        'feepaid': 'fee_paid',
        'fee paid on': 'fee_paid_on',
        'feepaidon': 'fee_paid_on',
        'expected total (ugx)': 'total_amount',
        'expected total': 'total_amount',
        'expectedtotal': 'total_amount',
        'total amount': 'total_amount',
        'total': 'total_amount',
        'installment amount (ugx)': 'installment_amount',
        'installment amount': 'installment_amount',
        'installment': 'installment_amount',
        'installmentamount': 'installment_amount',
        'start date': 'start_date',
        'startdate': 'start_date',
        'date': 'start_date',
        'due date': 'due_date',
        'duedate': 'due_date',
        'days overdue': 'days_overdue',
        'daysoverdue': 'days_overdue',
        'overdue days': 'days_overdue',
        'status': 'status',
        'loan status': 'status',
        'amount paid (ugx)': 'amount_paid',
        'amount paid': 'amount_paid',
        'amountpaid': 'amount_paid',
        'paid': 'amount_paid',
        'balance (ugx)': 'balance',
        'balance': 'balance',
        'outstanding': 'balance',
        'created date': 'created_date',
        'createddate': 'created_date',
        'created': 'created_date',
        'note': 'note',
        'notes': 'note',
        'purpose': 'purpose',
        'loan purpose': 'purpose',
        'guarantor name': 'guarantor_name',
        'guarantorname': 'guarantor_name',
        'guarantor phone': 'guarantor_phone',
        'guarantorphone': 'guarantor_phone',
        # User headers
        'full name': 'full_name',
        'fullname': 'full_name',
        'name': 'full_name',
        'phone': 'phone',
        'mobile': 'phone',
        'address': 'address',
        'id number': 'id_number',
        'idnumber': 'id_number',
        'nin': 'id_number',
        'national id': 'id_number',
        # Client profile headers
        'employer': 'employer',
        'company': 'employer',
        'monthly income': 'monthly_income',
        'monthlyincome': 'monthly_income',
        'income': 'monthly_income',
        'salary': 'monthly_income',
        'credit score': 'credit_score',
        'creditscore': 'credit_score',
        'next of kin': 'next_of_kin',
        'nextofkin': 'next_of_kin',
        'next of kin phone': 'next_of_kin_phone',
        'nextofkinphone': 'next_of_kin_phone',
        'bank name': 'bank_name',
        'bankname': 'bank_name',
        'bank account': 'bank_account',
        'bankaccount': 'bank_account',
        'mpesa number': 'mpesa_number',
        'mpesanumber': 'mpesa_number',
        'mobile money': 'mpesa_number',
        # Repayment headers
        'loan id': 'loan_id',
        'loanid': 'loan_id',
        'reference': 'reference',
        'ref': 'reference',
        'receipt': 'reference',
        'receipt number': 'reference',
        'payment date': 'payment_date',
        'paymentdate': 'payment_date',
        'recorded by': 'recorded_by',
        'recordedby': 'recorded_by',
        'recorded at': 'recorded_at',
        'recordedat': 'recorded_at',
    }

    rows = []
    headers = []

    try:
        if ext == 'csv':
            with open(filepath, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                raw_headers = reader.fieldnames or []
                # Normalize: strip, lowercase, map to DB columns
                headers = []
                for h in raw_headers:
                    clean = h.strip().lower()
                    mapped = HEADER_MAP.get(clean, clean)
                    headers.append(mapped)
                rows = list(reader)
                # Normalize keys
                normalized_rows = []
                for row in rows:
                    norm_row = {}
                    for k, v in row.items():
                        clean = k.strip().lower()
                        mapped = HEADER_MAP.get(clean, clean)
                        norm_row[mapped] = v
                    normalized_rows.append(norm_row)
                rows = normalized_rows
        elif ext in ('xlsx', 'xls'):
            try:
                import openpyxl
                wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
                ws = wb.active
                raw_rows = list(ws.iter_rows(values_only=True))
                if not raw_rows:
                    return {'success': False, 'message': 'File is empty', 'errors': []}
                raw_headers = [str(h).strip().lower() for h in raw_rows[0] if h]
                headers = [HEADER_MAP.get(h, h) for h in raw_headers]
                for row in raw_rows[1:]:
                    row_dict = {}
                    for i, val in enumerate(row):
                        if i < len(raw_headers):
                            clean = raw_headers[i]
                            mapped = HEADER_MAP.get(clean, clean)
                            row_dict[mapped] = val if val is not None else ''
                    if any(row_dict.values()):
                        rows.append(row_dict)
                wb.close()
            except ImportError:
                return {'success': False, 'message': 'openpyxl not installed. Install with: pip install openpyxl', 'errors': []}
        else:
            return {'success': False, 'message': 'Unsupported file type', 'errors': []}
    except Exception as e:
        return {'success': False, 'message': f'Error reading file: {str(e)}', 'errors': []}

    if not rows:
        return {'success': False, 'message': 'No data rows found', 'errors': []}

    # Detect entity type from headers
    h_set = set(headers)

    # Check for users/clients
    if 'username' in h_set and 'email' in h_set:
        return _import_users(rows)
    # Check for client profiles
    elif 'user_id' in h_set and ('employer' in h_set or 'monthly_income' in h_set):
        return _import_client_profiles(rows)
    # Check for loans — accept client_id, or client_name, or client_phone
    elif 'principal' in h_set and ('client_id' in h_set or 'client_name' in h_set or 'client_phone' in h_set):
        return _import_loans(rows)
    # Check for repayments
    elif 'loan_number' in h_set and 'amount' in h_set:
        return _import_repayments(rows)
    else:
        return {'success': False, 'message': f'Could not detect data type. Headers found: {", ".join(headers)}', 'errors': []}

def _import_users(rows):
    """Import users/clients from rows"""
    from werkzeug.security import generate_password_hash
    conn = get_db()
    created = 0
    errors = []

    for i, row in enumerate(rows):
        try:
            username = row.get('username', '').strip()
            email = row.get('email', '').strip()
            password = row.get('password', 'changeme123').strip()
            role = row.get('role', 'client').strip()
            full_name = row.get('full_name', username).strip()
            phone = row.get('phone', '').strip()
            address = row.get('address', '').strip()
            id_number = row.get('id_number', '').strip()

            if not username or not email:
                errors.append(f'Row {i+1}: Missing username or email')
                continue

            # Check if user exists
            existing = conn.execute('SELECT id FROM users WHERE username = ? OR email = ?', (username, email)).fetchone()
            if existing:
                errors.append(f'Row {i+1}: User "{username}" already exists')
                continue

            conn.execute(
                'INSERT INTO users (username, email, password_hash, role, full_name, phone, address, id_number) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                (username, email, generate_password_hash(password, method='pbkdf2:sha256'), role, full_name, phone, address, id_number)
            )
            created += 1
        except Exception as e:
            errors.append(f'Row {i+1}: {str(e)}')

    conn.commit()
    conn.close()

    msg = f'Created {created} users'
    if errors:
        msg += f'. {len(errors)} error(s): {"; ".join(errors[:3])}'
    return {'success': created > 0, 'message': msg, 'errors': errors}

def _import_client_profiles(rows):
    """Import client profiles"""
    conn = get_db()
    created = 0
    errors = []

    for i, row in enumerate(rows):
        try:
            user_id = int(row.get('user_id', 0))
            if not user_id:
                errors.append(f'Row {i+1}: Missing user_id')
                continue

            existing = conn.execute('SELECT id FROM client_profiles WHERE user_id = ?', (user_id,)).fetchone()
            if existing:
                conn.execute(
                    'UPDATE client_profiles SET employer=?, monthly_income=?, credit_score=?, next_of_kin=?, next_of_kin_phone=?, bank_name=?, bank_account=?, mpesa_number=?, notes=? WHERE user_id=?',
                    (row.get('employer',''), float(row.get('monthly_income',0) or 0), int(row.get('credit_score',0) or 0),
                     row.get('next_of_kin',''), row.get('next_of_kin_phone',''), row.get('bank_name',''),
                     row.get('bank_account',''), row.get('mpesa_number',''), row.get('notes',''), user_id)
                )
            else:
                conn.execute(
                    'INSERT INTO client_profiles (user_id, employer, monthly_income, credit_score, next_of_kin, next_of_kin_phone, bank_name, bank_account, mpesa_number, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                    (user_id, row.get('employer',''), float(row.get('monthly_income',0) or 0), int(row.get('credit_score',0) or 0),
                     row.get('next_of_kin',''), row.get('next_of_kin_phone',''), row.get('bank_name',''),
                     row.get('bank_account',''), row.get('mpesa_number',''), row.get('notes',''))
                )
            created += 1
        except Exception as e:
            errors.append(f'Row {i+1}: {str(e)}')

    conn.commit()
    conn.close()

    msg = f'Imported {created} client profiles'
    if errors:
        msg += f'. {len(errors)} error(s)'
    return {'success': created > 0, 'message': msg, 'errors': errors}

def _get_client_id_range(conn):
    """Return a human-readable summary of available client IDs in the database"""
    try:
        rows = conn.execute('SELECT id, full_name FROM users WHERE role = ? ORDER BY id', ('client',)).fetchall()
        if not rows:
            return 'none — no clients exist yet'
        parts = [f'{r["id"]} ({r["full_name"]})' for r in rows[:10]]
        summary = ', '.join(parts)
        if len(rows) > 10:
            summary += f' and {len(rows) - 10} more'
        return summary
    except:
        return 'could not fetch client list'


def _import_loans(rows):
    """Import loans — accepts client_id (numeric) or client_name / client_phone (auto-lookup)"""
    conn = get_db()
    created = 0
    errors = []

    # Pre-compute starting loan number so each row gets a unique number
    # (generate_loan_number reads from DB each call, but within one batch
    #  uncommitted rows aren't visible, causing duplicates)
    now = datetime.now()
    year = now.year
    month = now.strftime('%m')
    max_seq = conn.execute(
        "SELECT COALESCE(MAX(CAST(SUBSTR(loan_number, 4, 3) AS INTEGER)), 0) FROM loans"
    ).fetchone()[0]
    seq_offset = 1  # will be incremented per row

    # Pre-fetch all clients for fast lookup
    all_clients = conn.execute(
        'SELECT id, full_name, phone FROM users WHERE role = ?', ('client',)
    ).fetchall()
    clients_by_name = {}
    clients_by_phone = {}
    for c in all_clients:
        key_name = c['full_name'].strip().lower()
        clients_by_name[key_name] = c['id']
        # Also index by partial name (first word / last word)
        for part in key_name.split():
            if part not in clients_by_name:
                clients_by_name[part] = c['id']
        # Index by phone (normalized)
        phone = (c['phone'] or '').strip()
        if phone:
            # Normalize: remove +, ensure 256 prefix
            clean = phone.lstrip('+')
            clients_by_phone[clean] = c['id']
            if clean.startswith('0'):
                clients_by_phone['256' + clean[1:]] = c['id']
            elif clean.startswith('256'):
                clients_by_phone['0' + clean[3:]] = c['id']

    for i, row in enumerate(rows):
        try:
            # ── Resolve client_id from row ──
            client_id = None
            client_label = None

            # Method 1: numeric client_id
            raw_cid = row.get('client_id', '')

            if raw_cid != '' and raw_cid is not None:
                try:
                    client_id = int(float(str(raw_cid)))
                    client_label = f'id={client_id}'
                    # Verify exists
                    found = conn.execute(
                        'SELECT id FROM users WHERE id = ? AND role = ?', (client_id, 'client')
                    ).fetchone()
                    if not found:
                        errors.append(
                            f'Row {i+1}: No client found with id={client_id}. '
                            f'{_get_client_id_range(conn)}'
                        )
                        continue
                except (ValueError, TypeError):
                    errors.append(
                        f'Row {i+1}: client_id "{raw_cid}" is not a number. '
                        f'Use client_name (full name) or client_phone instead.'
                    )
                    continue

            # Method 2: client_name — auto-lookup by full_name
            if client_id is None:
                raw_name = row.get('client_name', '').strip()
                if raw_name:
                    client_label = f'name="{raw_name}"'
                    key = raw_name.lower()
                    if key in clients_by_name:
                        client_id = clients_by_name[key]
                    else:
                        # Try fuzzy: match clients whose name starts with or contains the input
                        matches = [
                            c for c in all_clients
                            if raw_name.lower() in c['full_name'].lower()
                        ]
                        if len(matches) == 1:
                            client_id = matches[0]['id']
                        elif len(matches) > 1:
                            names = [f'{c["full_name"]} (id={c["id"]})' for c in matches]
                            errors.append(
                                f'Row {i+1}: Multiple clients match "{raw_name}": {", ".join(names)}. '
                                f'Use client_id or a more specific name.'
                            )
                            continue
                        else:
                            errors.append(
                                f'Row {i+1}: No client found with name "{raw_name}". '
                                f'Current clients: {_get_client_id_range(conn)}'
                            )
                            continue

            # Method 3: client_phone — auto-lookup by phone
            if client_id is None:
                raw_phone = row.get('client_phone', '').strip()
                if raw_phone:
                    client_label = f'phone="{raw_phone}"'
                    # Normalize phone
                    clean = raw_phone.lstrip('+')
                    if clean in clients_by_phone:
                        client_id = clients_by_phone[clean]
                    else:
                        # Try alternative formats
                        alt = None
                        if clean.startswith('0'):
                            alt = '256' + clean[1:]
                        elif clean.startswith('256'):
                            alt = '0' + clean[3:]
                        if alt and alt in clients_by_phone:
                            client_id = clients_by_phone[alt]
                        else:
                            errors.append(
                                f'Row {i+1}: No client found with phone "{raw_phone}". '
                                f'Current clients: {_get_client_id_range(conn)}'
                            )
                            continue

            if client_id is None:
                errors.append(
                    f'Row {i+1}: No client identified. '
                    f'Include one of: client_id (number), client_name (full name), or client_phone'
                )
                continue

            # ── Parse remaining fields ──
            principal = float(row.get('principal', 0) or 0)
            if not principal:
                errors.append(f'Row {i+1}: Missing principal amount')
                continue

            interest_rate = float(row.get('interest_rate', 10) or 10)
            # Normalize interest_type
            interest_type = row.get('interest_type', 'flat').strip().lower()
            if interest_type not in ('flat', 'reducing'):
                interest_type = 'flat'
            # Normalize payment_schedule
            payment_schedule = row.get('payment_schedule', 'monthly').strip().lower()
            if payment_schedule not in ('daily', 'weekly', 'monthly'):
                payment_schedule = 'monthly'
            duration_months = int(row.get('duration_months', 1) or 1)
            purpose = row.get('purpose', '').strip()
            guarantor_name = row.get('guarantor_name', '').strip()
            guarantor_phone = row.get('guarantor_phone', '').strip()
            processing_fee = float(row.get('processing_fee', 0) or 0)

            # Calculate total
            if interest_type == 'flat':
                total_interest = principal * (interest_rate / 100) * duration_months
            else:
                total_interest = principal * (interest_rate / 100) * duration_months / 2
            total_amount = principal + total_interest

            # Unique loan number per row (sequential offset)
            seq = max_seq + seq_offset
            seq_offset += 1
            loan_number = f"VL-{seq:03d}-{year}-{month}"

            start_date = now.strftime('%Y-%m-%d')
            due_date = (now + timedelta(days=30 * duration_months)).strftime('%Y-%m-%d')

            if payment_schedule == 'daily':
                next_payment = (now + timedelta(days=1)).strftime('%Y-%m-%d')
            elif payment_schedule == 'weekly':
                next_payment = (now + timedelta(weeks=1)).strftime('%Y-%m-%d')
            else:
                next_payment = (now + timedelta(days=30)).strftime('%Y-%m-%d')

            conn.execute(
                '''INSERT INTO loans (loan_number, client_id, principal, interest_rate, interest_type,
                   payment_schedule, total_amount, balance, fine_amount, fine_active, default_count,
                   purpose, guarantor_name, guarantor_phone, start_date, due_date, next_payment_date, processing_fee)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0, ?, ?, ?, ?, ?, ?, ?)''',
                (loan_number, client_id, principal, interest_rate, interest_type,
                 payment_schedule, total_amount, total_amount, purpose, guarantor_name, guarantor_phone,
                 start_date, due_date, next_payment, processing_fee)
            )
            created += 1
        except Exception as e:
            errors.append(f'Row {i+1}: {str(e)}')

    conn.commit()
    conn.close()

    msg = f'Created {created} loans'
    if errors:
        msg += f'. {len(errors)} error(s)'
    return {'success': created > 0, 'message': msg, 'errors': errors}

def _import_repayments(rows):
    """Import repayments"""
    conn = get_db()
    created = 0
    errors = []

    for i, row in enumerate(rows):
        try:
            loan_number = row.get('loan_number', '').strip()
            amount = float(row.get('amount', 0) or 0)
            if not loan_number or not amount:
                errors.append(f'Row {i+1}: Missing loan_number or amount')
                continue

            loan = conn.execute('SELECT id, balance FROM loans WHERE loan_number = ?', (loan_number,)).fetchone()
            if not loan:
                errors.append(f'Row {i+1}: Loan "{loan_number}" not found')
                continue

            payment_method = row.get('payment_method', 'cash').strip()
            reference = row.get('reference', '').strip()
            notes = row.get('notes', '').strip()

            conn.execute(
                'INSERT INTO repayments (loan_id, amount, payment_method, reference, notes) VALUES (?, ?, ?, ?, ?)',
                (loan['id'], amount, payment_method, reference, notes)
            )

            # Update loan balance
            new_balance = max(0, loan['balance'] - amount)
            new_paid = conn.execute('SELECT COALESCE(SUM(amount), 0) FROM repayments WHERE loan_id = ?', (loan['id'],)).fetchone()[0]
            status = 'paid' if new_balance <= 0 else 'active'

            conn.execute(
                'UPDATE loans SET balance = ?, amount_paid = ?, status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
                (new_balance, new_paid, status, loan['id'])
            )
            created += 1
        except Exception as e:
            errors.append(f'Row {i+1}: {str(e)}')

    conn.commit()
    conn.close()

    msg = f'Recorded {created} repayments'
    if errors:
        msg += f'. {len(errors)} error(s)'
    return {'success': created > 0, 'message': msg, 'errors': errors}

def clear_transactional_data():
    """
    Clear all transactional/activity data while keeping ALL users (admins, officers, clients).
    ADMIN-ONLY operation. Use this before importing new data.

    Returns:
        dict with counts of deleted records per table
    """
    conn = get_db()
    counts = {}

    try:
        # Order matters due to foreign key constraints
        counts['repayments'] = conn.execute('DELETE FROM repayments').rowcount
        counts['loans'] = conn.execute('DELETE FROM loans').rowcount
        counts['notifications'] = conn.execute('DELETE FROM notifications').rowcount
        counts['audit_log'] = conn.execute('DELETE FROM audit_log').rowcount
        counts['sms_logs'] = conn.execute('DELETE FROM sms_logs').rowcount
        counts['login_attempts'] = conn.execute('DELETE FROM login_attempts').rowcount
        counts['client_profiles'] = conn.execute('DELETE FROM client_profiles').rowcount

        conn.commit()
    except Exception as e:
        conn.rollback()
        conn.close()
        raise e

    conn.close()
    return counts


def clear_demo_data(keep_admin_ids=None):
    """
    Delete all demo/seed data from the system while preserving admin users
    AND all user-created users (non-demo).

    ADMIN-ONLY operation. Demo users are identified by their seed usernames:
      admin, officer, officer2, alice, brian, carol, david, faith, grace

    User-created users (any other usernames) are NEVER deleted by this function.

    Args:
        keep_admin_ids: list of user IDs to preserve (defaults to all admin-role users)

    Returns:
        dict with counts of deleted records per table
    """
    conn = get_db()

    # Determine which users to keep — all admins by default
    if keep_admin_ids is None:
        admins = conn.execute('SELECT id FROM users WHERE role = ?', ('admin',)).fetchall()
        keep_admin_ids = [a['id'] for a in admins]

    if not keep_admin_ids:
        keep_admin_ids = [1]  # safety fallback

    # DEMO USER SAFEGUARD: Only delete users with known demo usernames
    # This prevents accidental deletion of user-created accounts
    demo_usernames = ('admin', 'officer', 'officer2', 'alice', 'brian', 'carol',
                      'david', 'faith', 'grace')
    placeholders = ','.join('?' for _ in demo_usernames)

    # Get IDs of demo users that exist in the database
    demo_users = conn.execute(
        f'SELECT id FROM users WHERE username IN ({placeholders})',
        demo_usernames
    ).fetchall()
    demo_user_ids = [u['id'] for u in demo_users]

    # Combine admin IDs + demo user IDs to keep
    keep_ids = list(set(keep_admin_ids + demo_user_ids))
    ids_str = ','.join(str(i) for i in keep_ids)

    counts = {}

    try:
        # Order matters due to foreign key constraints

        # 1. SMS logs (no FK)
        counts['sms_logs'] = conn.execute('DELETE FROM sms_logs').rowcount

        # 2. Login attempts (no FK)
        counts['login_attempts'] = conn.execute('DELETE FROM login_attempts').rowcount

        # 3. Repayments (depends on loans via FK)
        counts['repayments'] = conn.execute('DELETE FROM repayments').rowcount

        # 4. Loans (depends on users via FK client_id, loan_officer_id, approved_by)
        counts['loans'] = conn.execute('DELETE FROM loans').rowcount

        # 5. Notifications (depends on users via FK)
        counts['notifications'] = conn.execute('DELETE FROM notifications').rowcount

        # 6. Audit log (references users)
        counts['audit_log'] = conn.execute('DELETE FROM audit_log').rowcount

        # 7. Client profiles (depends on users via FK)
        counts['client_profiles'] = conn.execute('DELETE FROM client_profiles').rowcount

        # 8. Only delete DEMO users (keep admins + user-created users)
        counts['demo_users_deleted'] = conn.execute(
            f'DELETE FROM users WHERE id NOT IN ({ids_str})'
        ).rowcount

        conn.commit()
    except Exception as e:
        conn.rollback()
        conn.close()
        raise e

    conn.close()
    return counts


# Initialize DB on import
init_db()
