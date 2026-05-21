"""
LendFlow API Server — Backend for Hybrid Architecture
Deploy on Render (free tier)
Exposes JSON endpoints for the PHP frontend on GoDaddy
"""

import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import Flask, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

from app.database import (
    init_db, authenticate_user, get_user_by_id, create_user, update_user_profile_picture,
    get_client_profile, update_client_profile, create_loan, approve_loan,
    reject_loan, add_repayment, get_loans, get_loan, get_loan_by_number, get_repayments,
    get_notifications, mark_notification_read, mark_all_notifications_read,
    get_dashboard_stats, get_all_users, log_audit, send_notification,
    check_and_apply_fine, toggle_fine, run_daily_checks, UPLOAD_FOLDER,
    calculate_payment_schedule, get_monthly_pnl, get_balance_sheet, get_db,
    record_login_attempt, is_account_locked, change_password, get_failed_attempts,
    update_user, delete_user, get_all_repayments, update_repayment,
    delete_repayment, get_audit_logs, clear_demo_data, ensure_admin_exists
)
from app.ai_service import (
    assess_credit_risk, generate_portfolio_insights,
    analyze_client, get_faq_response, get_dashboard_ai_data
)

# ── App Setup ──────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'lendflow-api-secret-change-in-production')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5MB max

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ── Initialize Database ───────────────────────────────────────
init_db()
ensure_admin_exists(username='admin', password='admin123?Vaulta')

# ── API Token Store (in-memory for simplicity; use Redis in production) ──
API_TOKENS = {}  # token -> {user_id, role, created_at}

def generate_api_token(user_id, role):
    """Generate a unique API token for the user."""
    token = secrets.token_hex(32)
    API_TOKENS[token] = {
        'user_id': user_id,
        'role': role,
        'created_at': datetime.utcnow().isoformat()
    }
    return token

def revoke_api_token(token):
    """Revoke an API token."""
    if token in API_TOKENS:
        del API_TOKENS[token]

# ── Auth Decorators ───────────────────────────────────────────
def api_required(f):
    """Decorator: require valid API token in Authorization header."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'success': False, 'error': 'Missing or invalid Authorization header'}), 401
        
        token = auth_header[7:]  # Remove 'Bearer ' prefix
        if token not in API_TOKENS:
            return jsonify({'success': False, 'error': 'Invalid or expired token'}), 401
        
        # Attach user info to request
        request.api_user = API_TOKENS[token]
        request.api_token = token
        return f(*args, **kwargs)
    return decorated

def role_required(*roles):
    """Decorator: require specific role(s)."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            user_role = request.api_user.get('role')
            if user_role not in roles:
                return jsonify({'success': False, 'error': 'Insufficient permissions'}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator

# ── CORS Middleware ────────────────────────────────────────────
@app.after_request
def add_cors_headers(response):
    """Allow requests from any origin (PHP frontend on GoDaddy)."""
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    return response

@app.route('/', methods=['OPTIONS'])
@app.route('/<path:path>', methods=['OPTIONS'])
def handle_options(path=None):
    """Handle preflight OPTIONS requests."""
    return '', 200

# ── Health Check ──────────────────────────────────────────────
@app.route('/api/health')
def health():
    """Health check endpoint."""
    try:
        conn = get_db()
        user_count = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        loan_count = conn.execute('SELECT COUNT(*) FROM loans').fetchone()[0]
        conn.close()
        return jsonify({
            'success': True,
            'status': 'healthy',
            'users': user_count,
            'loans': loan_count
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ═══════════════════════════════════════════════════════════════
#  AUTH ENDPOINTS
# ═══════════════════════════════════════════════════════════════

@app.route('/api/auth/login', methods=['POST'])
def api_login():
    """Authenticate user and return API token."""
    data = request.get_json() or {}
    identifier = data.get('username') or data.get('loan_number', '')
    password = data.get('password', '')
    
    if not identifier:
        return jsonify({'success': False, 'error': 'Username or loan number required'}), 400
    
    # Check if account is locked
    if is_account_locked(identifier):
        failed = get_failed_attempts(identifier)
        return jsonify({
            'success': False, 
            'error': f'Account locked. Too many failed attempts ({failed}). Try again later.'
        }), 429
    
    user = authenticate_user(identifier, password)
    
    if not user:
        record_login_attempt(identifier, success=False)
        failed = get_failed_attempts(identifier)
        remaining = 5 - failed
        return jsonify({
            'success': False, 
            'error': f'Invalid credentials. {remaining} attempts remaining.' if remaining > 0 else 'Account locked.'
        }), 401
    
    # Login successful — clear failed attempts
    record_login_attempt(identifier, success=True)
    
    # Generate API token
    token = generate_api_token(user['id'], user['role'])
    
    return jsonify({
        'success': True,
        'message': 'Login successful',
        'token': token,
        'user': {
            'id': user['id'],
            'username': user['username'],
            'full_name': user['full_name'],
            'email': user['email'],
            'role': user['role'],
            'phone': user.get('phone'),
            'profile_picture': user.get('profile_picture')
        }
    })

@app.route('/api/auth/logout', methods=['POST'])
@api_required
def api_logout():
    """Revoke API token."""
    revoke_api_token(request.api_token)
    return jsonify({'success': True, 'message': 'Logged out successfully'})

@app.route('/api/auth/me', methods=['GET'])
@api_required
def api_get_me():
    """Get current user info."""
    user = get_user_by_id(request.api_user['user_id'])
    if not user:
        return jsonify({'success': False, 'error': 'User not found'}), 404
    return jsonify({'success': True, 'user': dict(user)})

@app.route('/api/auth/change-password', methods=['POST'])
@api_required
def api_change_password():
    """Change user password."""
    data = request.get_json() or {}
    current_password = data.get('current_password', '')
    new_password = data.get('new_password', '')
    
    if not current_password or not new_password:
        return jsonify({'success': False, 'error': 'Current and new password required'}), 400
    
    success, error = change_password(request.api_user['user_id'], current_password, new_password)
    if success:
        return jsonify({'success': True, 'message': 'Password changed successfully'})
    return jsonify({'success': False, 'error': error}), 400

# ═══════════════════════════════════════════════════════════════
#  DASHBOARD ENDPOINTS
# ═══════════════════════════════════════════════════════════════

@app.route('/api/dashboard/stats', methods=['GET'])
@api_required
def api_dashboard_stats():
    """Get dashboard statistics."""
    user_id = request.api_user['user_id']
    role = request.api_user['role']
    
    stats = get_dashboard_stats()
    
    # AI insights
    ai_data = get_dashboard_ai_data(stats)
    
    return jsonify({
        'success': True,
        'stats': stats,
        'ai_insights': ai_data.get('insights', []),
        'ai_enabled': ai_data.get('ai_enabled', False)
    })

# ═══════════════════════════════════════════════════════════════
#  USER MANAGEMENT ENDPOINTS (Admin/Loan Officer)
# ═══════════════════════════════════════════════════════════════

@app.route('/api/users', methods=['GET'])
@api_required
@role_required('admin', 'loan_officer')
def api_get_users():
    """Get all users."""
    users = get_all_users()
    return jsonify({'success': True, 'users': [dict(u) for u in users]})

@app.route('/api/users', methods=['POST'])
@api_required
@role_required('admin', 'loan_officer')
def api_create_user():
    """Create a new user."""
    data = request.get_json() or {}
    
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')
    role = data.get('role', 'client')
    full_name = data.get('full_name')
    phone = data.get('phone')
    address = data.get('address')
    id_number = data.get('id_number')
    
    # Auto-generate credentials for clients
    generated_creds = None
    if role == 'client' and (not username or not email or not password):
        import re
        first_name = (full_name or 'client').strip().split()[0].lower()
        first_name = re.sub(r'[^a-z0-9]', '', first_name) or 'client'
        
        conn = get_db()
        base_username = first_name
        username = base_username
        counter = 2
        while conn.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone():
            username = f"{base_username}{counter}"
            counter += 1
        conn.close()
        
        email = f"{username}@vaulta.local"
        password = secrets.token_urlsafe(12)
        generated_creds = {'username': username, 'password': password}
    
    user_id = create_user(username, email, password, role, full_name, phone, address, id_number)
    
    if user_id:
        log_audit(request.api_user['user_id'], 'create_user', 'user', user_id, f'Created user: {username}')
        if role == 'client':
            send_notification(user_id, 'Welcome', f'Welcome to LendFlow, {full_name}!')
        
        result = {'success': True, 'message': f'User "{username}" created', 'user_id': user_id}
        if generated_creds:
            result['generated_credentials'] = generated_creds
        return jsonify(result), 201
    
    return jsonify({'success': False, 'error': 'Username or email already exists'}), 409

@app.route('/api/users/<int:user_id>', methods=['GET'])
@api_required
@role_required('admin', 'loan_officer')
def api_get_user(user_id):
    """Get user by ID."""
    user = get_user_by_id(user_id)
    if not user:
        return jsonify({'success': False, 'error': 'User not found'}), 404
    return jsonify({'success': True, 'user': dict(user)})

@app.route('/api/users/<int:user_id>', methods=['PUT'])
@api_required
@role_required('admin')
def api_update_user(user_id):
    """Update user profile."""
    data = request.get_json() or {}
    
    user = get_user_by_id(user_id)
    if not user:
        return jsonify({'success': False, 'error': 'User not found'}), 404
    
    try:
        success, error = update_user(user_id, **data)
        if success:
            log_audit(request.api_user['user_id'], 'update_user', 'user', user_id, f'Updated user: {user["username"]}')
            return jsonify({'success': True, 'message': 'User updated'})
        return jsonify({'success': False, 'error': error}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/users/<int:user_id>', methods=['DELETE'])
@api_required
@role_required('admin')
def api_delete_user(user_id):
    """Soft-delete (deactivate) a user."""
    user = get_user_by_id(user_id)
    if not user:
        return jsonify({'success': False, 'error': 'User not found'}), 404
    
    success, msg = delete_user(user_id)
    if success:
        log_audit(request.api_user['user_id'], 'delete_user', 'user', user_id, f'Deactivated user: {user["username"]}')
        return jsonify({'success': True, 'message': msg})
    return jsonify({'success': False, 'error': msg}), 400

# ═══════════════════════════════════════════════════════════════
#  LOAN ENDPOINTS
# ═══════════════════════════════════════════════════════════════

@app.route('/api/loans', methods=['GET'])
@api_required
def api_get_loans():
    """Get loans (filtered by role)."""
    user_id = request.api_user['user_id']
    role = request.api_user['role']
    
    if role == 'client':
        loans = get_loans(client_id=user_id)
    else:
        loans = get_loans()
    
    return jsonify({'success': True, 'loans': [dict(l) for l in loans]})

@app.route('/api/loans', methods=['POST'])
@api_required
@role_required('client')
def api_create_loan():
    """Create a new loan application."""
    data = request.get_json() or {}
    
    client_id = request.api_user['user_id']
    principal = float(data.get('principal', 0))
    interest_rate = float(data.get('interest_rate', 0))
    interest_type = data.get('interest_type', 'flat')
    payment_schedule = data.get('payment_schedule', 'monthly')
    purpose = data.get('purpose', '')
    duration_months = int(data.get('duration_months', 1))
    
    if principal <= 0:
        return jsonify({'success': False, 'error': 'Principal must be greater than 0'}), 400
    
    loan_id = create_loan(client_id, principal, interest_rate, interest_type, payment_schedule, purpose, duration_months)
    
    if loan_id:
        log_audit(client_id, 'create_loan', 'loan', loan_id, f'Applied for loan: UGX {principal}')
        return jsonify({'success': True, 'message': 'Loan application submitted', 'loan_id': loan_id}), 201
    
    return jsonify({'success': False, 'error': 'Failed to create loan'}), 500

@app.route('/api/loans/<int:loan_id>', methods=['GET'])
@api_required
def api_get_loan(loan_id):
    """Get loan details."""
    loan = get_loan(loan_id)
    if not loan:
        return jsonify({'success': False, 'error': 'Loan not found'}), 404
    
    # Check access permission
    if request.api_user['role'] == 'client' and loan['client_id'] != request.api_user['user_id']:
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    
    repayments = get_repayments(loan_id)
    
    return jsonify({
        'success': True,
        'loan': dict(loan),
        'repayments': [dict(r) for r in repayments]
    })

@app.route('/api/loans/<int:loan_id>/approve', methods=['POST'])
@api_required
@role_required('admin', 'loan_officer')
def api_approve_loan(loan_id):
    """Approve a loan."""
    loan = get_loan(loan_id)
    if not loan:
        return jsonify({'success': False, 'error': 'Loan not found'}), 404
    
    data = request.get_json() or {}
    notes = data.get('notes', '')
    
    success = approve_loan(loan_id, request.api_user['user_id'], notes)
    if success:
        log_audit(request.api_user['user_id'], 'approve_loan', 'loan', loan_id, f'Approved loan {loan["loan_number"]}')
        return jsonify({'success': True, 'message': 'Loan approved'})
    return jsonify({'success': False, 'error': 'Failed to approve loan'}), 500

@app.route('/api/loans/<int:loan_id>/reject', methods=['POST'])
@api_required
@role_required('admin', 'loan_officer')
def api_reject_loan(loan_id):
    """Reject a loan."""
    loan = get_loan(loan_id)
    if not loan:
        return jsonify({'success': False, 'error': 'Loan not found'}), 404
    
    data = request.get_json() or {}
    reason = data.get('reason', 'No reason provided')
    
    success = reject_loan(loan_id, request.api_user['user_id'], reason)
    if success:
        log_audit(request.api_user['user_id'], 'reject_loan', 'loan', loan_id, f'Rejected loan {loan["loan_number"]}: {reason}')
        return jsonify({'success': True, 'message': 'Loan rejected'})
    return jsonify({'success': False, 'error': 'Failed to reject loan'}), 500

@app.route('/api/loans/<int:loan_id>/fine', methods=['POST'])
@api_required
@role_required('admin', 'loan_officer')
def api_toggle_fine(loan_id):
    """Toggle fine on a loan."""
    loan = get_loan(loan_id)
    if not loan:
        return jsonify({'success': False, 'error': 'Loan not found'}), 404
    
    new_status = toggle_fine(loan_id)
    log_audit(request.api_user['user_id'], 'toggle_fine', 'loan', loan_id, f'Toggled fine on {loan["loan_number"]}')
    
    return jsonify({'success': True, 'fine_active': new_status})

@app.route('/api/loans/<int:loan_id>', methods=['DELETE'])
@api_required
@role_required('admin')
def api_delete_loan(loan_id):
    """Delete a loan (admin only)."""
    loan = get_loan(loan_id)
    if not loan:
        return jsonify({'success': False, 'error': 'Loan not found'}), 404
    
    repayments = get_repayments(loan_id)
    if repayments:
        return jsonify({'success': False, 'error': 'Cannot delete loan with existing repayments'}), 400
    
    conn = get_db()
    conn.execute('DELETE FROM loans WHERE id = ?', (loan_id,))
    conn.commit()
    conn.close()
    
    log_audit(request.api_user['user_id'], 'delete_loan', 'loan', loan_id, f'Deleted loan {loan["loan_number"]}')
    return jsonify({'success': True, 'message': f'Loan {loan["loan_number"]} deleted'})

# ═══════════════════════════════════════════════════════════════
#  REPAYMENT ENDPOINTS
# ═══════════════════════════════════════════════════════════════

@app.route('/api/loans/<int:loan_id>/repayments', methods=['POST'])
@api_required
@role_required('admin', 'loan_officer')
def api_add_repayment(loan_id):
    """Record a repayment."""
    loan = get_loan(loan_id)
    if not loan:
        return jsonify({'success': False, 'error': 'Loan not found'}), 404
    
    data = request.get_json() or {}
    amount = float(data.get('amount', 0))
    payment_method = data.get('payment_method', 'cash')
    notes = data.get('notes', '')
    payment_type = data.get('payment_type', 'principal')
    
    if amount <= 0:
        return jsonify({'success': False, 'error': 'Amount must be greater than 0'}), 400
    
    # Auto-generate reference
    reference = f"PAY-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{secrets.token_hex(3).upper()}"
    
    add_repayment(loan_id, amount, payment_method, reference, request.api_user['user_id'], notes, payment_type)
    
    log_audit(request.api_user['user_id'], 'add_repayment', 'loan', loan_id, f'Repayment: UGX {amount} for {loan["loan_number"]}')
    
    return jsonify({
        'success': True,
        'message': 'Payment recorded',
        'reference': reference
    }), 201

@app.route('/api/repayments/<int:repayment_id>', methods=['PUT'])
@api_required
@role_required('admin')
def api_update_repayment(repayment_id):
    """Update a repayment record."""
    data = request.get_json() or {}
    amount = float(data.get('amount', 0))
    method = data.get('payment_method', 'cash')
    reference = data.get('reference', '')
    notes = data.get('notes', '')
    
    try:
        update_repayment(repayment_id, amount, method, reference, notes)
        log_audit(request.api_user['user_id'], 'update_repayment', 'repayment', repayment_id, f'Updated repayment')
        return jsonify({'success': True, 'message': 'Repayment updated'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/repayments/<int:repayment_id>', methods=['DELETE'])
@api_required
@role_required('admin')
def api_delete_repayment(repayment_id):
    """Delete a repayment record."""
    success = delete_repayment(repayment_id)
    if success:
        log_audit(request.api_user['user_id'], 'delete_repayment', 'repayment', repayment_id, 'Deleted repayment')
        return jsonify({'success': True, 'message': 'Repayment deleted and loan balance recalculated'})
    return jsonify({'success': False, 'error': 'Repayment not found'}), 404

@app.route('/api/repayments', methods=['GET'])
@api_required
@role_required('admin')
def api_get_all_repayments():
    """Get all repayments."""
    repayments = get_all_repayments()
    return jsonify({'success': True, 'repayments': [dict(r) for r in repayments]})

# ═══════════════════════════════════════════════════════════════
#  REPORTS & ANALYTICS
# ═══════════════════════════════════════════════════════════════

@app.route('/api/reports/profit-loss', methods=['GET'])
@api_required
@role_required('admin', 'loan_officer')
def api_profit_loss():
    """Get profit and loss report."""
    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)
    report = get_balance_sheet(year, month)
    return jsonify({'success': True, 'report': report})

@app.route('/api/reports/audit-log', methods=['GET'])
@api_required
@role_required('admin')
def api_audit_log():
    """Get audit logs."""
    limit = request.args.get('limit', 100, type=int)
    logs = get_audit_logs(limit)
    return jsonify({'success': True, 'logs': [dict(l) for l in logs]})

# ═══════════════════════════════════════════════════════════════
#  NOTIFICATIONS
# ═══════════════════════════════════════════════════════════════

@app.route('/api/notifications', methods=['GET'])
@api_required
def api_get_notifications():
    """Get user notifications."""
    user_id = request.api_user['user_id']
    unread_only = request.args.get('unread') == '1'
    notifs = get_notifications(user_id, unread_only)
    return jsonify({'success': True, 'notifications': [dict(n) for n in notifs]})

@app.route('/api/notifications/<int:notif_id>/read', methods=['POST'])
@api_required
def api_mark_notification_read(notif_id):
    """Mark notification as read."""
    mark_notification_read(notif_id)
    return jsonify({'success': True})

@app.route('/api/notifications/read-all', methods=['POST'])
@api_required
def api_mark_all_read():
    """Mark all notifications as read."""
    mark_all_notifications_read(request.api_user['user_id'])
    return jsonify({'success': True})

@app.route('/api/notifications/unread-count', methods=['GET'])
@api_required
def api_unread_count():
    """Get unread notification count."""
    from app.notifications import get_unread_count
    count = get_unread_count(request.api_user['user_id'])
    return jsonify({'success': True, 'count': count})

# ═══════════════════════════════════════════════════════════════
#  ADMIN UTILITIES
# ═══════════════════════════════════════════════════════════════

@app.route('/api/admin/clear-demo-data', methods=['POST'])
@api_required
@role_required('admin')
def api_clear_demo_data():
    """Clear all demo data."""
    try:
        counts = clear_demo_data()
        total = sum(counts.values())
        parts = [f'{v} {k}' for k, v in counts.items() if v > 0]
        log_audit(request.api_user['user_id'], 'clear_demo_data', 'system',
                  details=f'Deleted: {", ".join(parts)} ({total} total)')
        return jsonify({'success': True, 'message': f'Cleared {total} records', 'counts': counts})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/run-daily-checks', methods=['POST'])
@api_required
@role_required('admin')
def api_run_daily_checks():
    """Run daily checks (fines, reminders)."""
    run_daily_checks()
    return jsonify({'success': True, 'message': 'Daily checks completed'})

# ═══════════════════════════════════════════════════════════════
#  CLIENT PROFILE
# ═══════════════════════════════════════════════════════════════

@app.route('/api/profile', methods=['GET'])
@api_required
def api_get_profile():
    """Get client profile."""
    profile = get_client_profile(request.api_user['user_id'])
    return jsonify({'success': True, 'profile': dict(profile) if profile else None})

@app.route('/api/profile', methods=['PUT'])
@api_required
def api_update_profile():
    """Update client profile."""
    data = request.get_json() or {}
    success = update_client_profile(request.api_user['user_id'], **data)
    if success:
        return jsonify({'success': True, 'message': 'Profile updated'})
    return jsonify({'success': False, 'error': 'Failed to update profile'}), 500

# ═══════════════════════════════════════════════════════════════
#  AI ENDPOINTS
# ═══════════════════════════════════════════════════════════════

@app.route('/api/ai/credit-risk/<int:loan_id>', methods=['GET'])
@api_required
@role_required('admin', 'loan_officer')
def ai_credit_risk(loan_id):
    """Get AI credit risk assessment."""
    risk = assess_credit_risk(loan_id)
    return jsonify({'success': True, 'risk': risk})

@app.route('/api/ai/client-analysis/<int:client_id>', methods=['GET'])
@api_required
@role_required('admin', 'loan_officer')
def ai_client_analysis(client_id):
    """Get AI client analysis."""
    analysis = analyze_client(client_id)
    return jsonify({'success': True, 'analysis': analysis})

@app.route('/api/ai/faq', methods=['GET'])
@api_required
def ai_faq():
    """Get FAQ response."""
    question = request.args.get('q', '')
    if not question:
        return jsonify({'success': False, 'error': 'Question required'}), 400
    answer = get_faq_response(question)
    return jsonify({'success': True, 'question': question, 'answer': answer})

# ═══════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
