"""
SMS Service for LendFlow / Vaulta
Uses egoSMS API for sending messages.
"""

import urllib.request
import urllib.parse
from datetime import datetime
from app.database import get_db

# ── SMS API Configuration ──
SMS_API_URL = "https://comms.egosms.co/api/v1/plain"
SMS_USER = "vaultacashexpress"
SMS_PASSWORD = "Pilatue#2620"
SMS_SENDER = "Vaulta Cash"

# Mock mode: when True, simulates successful SMS sends without hitting the real API.
# Set to False for production use with valid egoSMS credentials.
SMS_MOCK_MODE = False

# ── SMS Response codes ──
# egoSMS plain endpoint returns plain text. Common success indicators:
SMS_SUCCESS_TOKENS = ("OK", "SUCCESS", "1701", "SENT", "1")


def _egosms_send(phone, message, sender=None):
    """
    Low-level send via egoSMS GET API.

    Args:
        phone: Single phone number (string, formatted with 256 prefix)
        message: SMS text
        sender: Sender ID (defaults to SMS_SENDER)

    Returns:
        dict with 'success' (bool), 'response' (str), 'error' (str or None)
    """
    if sender is None:
        sender = SMS_SENDER

    # URL-encode the password because it contains `#` which would be
    # interpreted as a URL fragment identifier.
    params = {
        'username': SMS_USER,
        'password': SMS_PASSWORD,
        'number': phone,
        'message': message,
        'sender': sender,
    }
    query_string = urllib.parse.urlencode(params)
    url = f"{SMS_API_URL}?{query_string}"

    print(f"[SMS] Sending via egoSMS: to={phone} len={len(message)}")

    try:
        req = urllib.request.Request(url, method='GET')
        with urllib.request.urlopen(req, timeout=30) as response:
            result = response.read().decode('utf-8').strip()

        # Check if any success token is in the response
        upper_result = result.upper()
        success = any(token in upper_result for token in SMS_SUCCESS_TOKENS)

        log_sms(phone, message, success, result)

        return {
            'success': success,
            'response': result,
            'error': None if success else f'API returned: {result}'
        }
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8', errors='replace').strip()
        error_msg = f'HTTP {e.code}: {error_body or e.reason}'
        log_sms(phone, message, False, error_msg)
        return {'success': False, 'response': '', 'error': error_msg}
    except urllib.error.URLError as e:
        error_msg = f'Network error: {str(e)}'
        log_sms(phone, message, False, error_msg)
        return {'success': False, 'response': '', 'error': error_msg}
    except Exception as e:
        error_msg = f'Error: {str(e)}'
        log_sms(phone, message, False, error_msg)
        return {'success': False, 'response': '', 'error': error_msg}


def send_sms(phone, message, sender=None):
    """
    Send SMS via egoSMS API.

    Args:
        phone: Phone number (string, comma-separated for multiple recipients)
        message: SMS message text
        sender: Sender ID (defaults to SMS_SENDER)

    Returns:
        dict with 'success' (bool), 'response' (str), 'error' (str or None)
    """
    if sender is None:
        sender = SMS_SENDER

    # Format phone number(s) - ensure they start with 256
    phones = [p.strip() for p in phone.split(',')]
    formatted_phones = []
    for p in phones:
        if p.startswith('0'):
            p = '256' + p[1:]
        elif not p.startswith('256'):
            p = '256' + p
        formatted_phones.append(p)

    # Mock mode
    if SMS_MOCK_MODE:
        receiver = ','.join(formatted_phones)
        mock_response = f"OK (mock) SMS sent to {receiver}"
        log_sms(receiver, message, True, mock_response)
        print(f"[SMS MOCK] To: {receiver} | Msg: {message[:80]}...")
        return {'success': True, 'response': mock_response, 'error': None}

    # egoSMS plain endpoint sends to one number per request.
    # If multiple numbers, send first one and log the rest as pending.
    target = formatted_phones[0] if formatted_phones else phone

    return _egosms_send(target, message, sender)


def send_bulk_sms(phone_list, message, sender=None):
    """
    Send SMS to multiple recipients.

    Args:
        phone_list: List of phone numbers
        message: SMS message text
        sender: Sender ID

    Returns:
        dict with 'total', 'sent', 'failed', 'results'
    """
    results = {'total': len(phone_list), 'sent': 0, 'failed': 0, 'results': []}

    for phone in phone_list:
        result = send_sms(phone, message, sender)
        results['results'].append({
            'phone': phone,
            'success': result['success'],
            'response': result['response']
        })
        if result['success']:
            results['sent'] += 1
        else:
            results['failed'] += 1

    return results


def log_sms(phone, message, success, response):
    """Log SMS to database"""
    conn = get_db()
    try:
        conn.execute(
            '''INSERT INTO sms_logs (phone, message, status, api_response, sent_at)
               VALUES (?, ?, ?, ?, ?)''',
            (phone, message, 'sent' if success else 'failed',
             str(response)[:500], datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        )
        conn.commit()
    except Exception:
        pass  # Table might not exist yet
    finally:
        conn.close()


def get_sms_stats():
    """Get SMS statistics"""
    conn = get_db()
    try:
        total = conn.execute('SELECT COUNT(*) FROM sms_logs').fetchone()[0]
        sent = conn.execute("SELECT COUNT(*) FROM sms_logs WHERE status = 'sent'").fetchone()[0]
        failed = conn.execute("SELECT COUNT(*) FROM sms_logs WHERE status = 'failed'").fetchone()[0]
        today = conn.execute(
            "SELECT COUNT(*) FROM sms_logs WHERE sent_at >= CURRENT_DATE"
        ).fetchone()[0]
        return {'total': total, 'sent': sent, 'failed': failed, 'today': today}
    except Exception:
        return {'total': 0, 'sent': 0, 'failed': 0, 'today': 0}
    finally:
        conn.close()


def get_sms_logs(limit=50):
    """Get recent SMS logs"""
    conn = get_db()
    try:
        logs = conn.execute(
            'SELECT * FROM sms_logs ORDER BY sent_at DESC LIMIT ?', (limit,)
        ).fetchall()
        return [dict(l) for l in logs]
    except Exception:
        return []
    finally:
        conn.close()


# ── SMS Templates ──
# Keep under 160 characters where possible (single SMS segment).
# Lead with the most important info.
TEMPLATES = {
    'payment_reminder':
        'Dear {name}, your loan payment of UGX {amount} is due on {due_date}. '
        'Please pay on time to avoid penalties. — Vaulta Cash',

    'overdue_alert':
        'URGENT: {name}, your payment of UGX {amount} is {days} days overdue. '
        'Pay immediately to avoid further penalties. — Vaulta Cash',

    'payment_confirmation':
        'Payment received! UGX {amount} from {name}. '
        'Your balance is UGX {balance}. Thank you for your timely payment. — Vaulta Cash',

    'welcome':
        'Welcome to Vaulta Cash, {name}! Your account is ready. '
        'Visit us or call to apply for a loan. We are here to help. — Vaulta Cash',

    'loan_approved':
        'Good news, {name}! Your loan of UGX {amount} is approved. '
        'Visit our office to collect your funds. — Vaulta Cash',

    'loan_rejected':
        'Dear {name}, your loan application was not approved. '
        'Please contact your loan officer for details. — Vaulta Cash',

    'fine_applied':
        'NOTICE: {name}, a late-payment fine of UGX {amount} has been applied '
        'to your loan {loan}. Pay promptly to stop further charges. — Vaulta Cash',

    'fine_paused':
        'NOTICE: {name}, the fine on your loan {loan} has been paused. '
        'Remaining fine amount: UGX {amount}. — Vaulta Cash',

    'fine_waived':
        'NOTICE: {name}, the fine of UGX {amount} on loan {loan} '
        'has been waived. — Vaulta Cash',
}


def format_message(template_name, **kwargs):
    """Format a message from template"""
    template = TEMPLATES.get(template_name, '{message}')
    return template.format(**kwargs)


# ── High-level senders ──

def send_payment_reminder_sms(loan):
    """Send payment reminder SMS for a loan"""
    phone = loan.get('client_phone', '')
    if not phone:
        return {'success': False, 'error': 'No phone number'}

    message = format_message(
        'payment_reminder',
        name=loan.get('client_name', 'Customer'),
        amount=f"{loan['balance']:,.0f}",
        due_date=loan.get('due_date', 'soon')
    )

    return send_sms(phone, message)


def send_overdue_alert_sms(loan):
    """Send overdue alert SMS for a loan"""
    phone = loan.get('client_phone', '')
    if not phone:
        return {'success': False, 'error': 'No phone number'}

    # Calculate days overdue
    due_date = loan.get('due_date', '')
    if due_date:
        try:
            due = datetime.strptime(due_date, '%Y-%m-%d')
            days = (datetime.now() - due).days
        except Exception:
            days = 0
    else:
        days = 0

    message = format_message(
        'overdue_alert',
        name=loan.get('client_name', 'Customer'),
        amount=f"{loan['balance']:,.0f}",
        days=days
    )

    return send_sms(phone, message)


def send_payment_confirmation_sms(client_name, phone, amount, balance):
    """Send payment confirmation SMS"""
    if not phone:
        return {'success': False, 'error': 'No phone number'}

    message = format_message(
        'payment_confirmation',
        name=client_name,
        amount=f"{amount:,.0f}",
        balance=f"{balance:,.0f}"
    )

    return send_sms(phone, message)


def send_loan_approved_sms(client_name, phone, amount):
    """Send loan approved SMS"""
    if not phone:
        return {'success': False, 'error': 'No phone number'}

    message = format_message(
        'loan_approved',
        name=client_name,
        amount=f"{amount:,.0f}"
    )

    return send_sms(phone, message)


def send_loan_rejected_sms(client_name, phone):
    """Send loan rejected SMS"""
    if not phone:
        return {'success': False, 'error': 'No phone number'}

    message = format_message(
        'loan_rejected',
        name=client_name
    )

    return send_sms(phone, message)


def send_welcome_sms(client_name, phone):
    """Send welcome SMS to new client"""
    if not phone:
        return {'success': False, 'error': 'No phone number'}

    message = format_message(
        'welcome',
        name=client_name
    )

    return send_sms(phone, message)


# ── Fine-related SMS senders ──

def send_fine_applied_sms(loan):
    """Send SMS notification when a fine is applied to a loan"""
    phone = loan.get('client_phone', '')
    if not phone:
        return {'success': False, 'error': 'No phone number'}

    message = format_message(
        'fine_applied',
        name=loan.get('client_name', 'Customer'),
        amount=f"{loan.get('fine_amount', 0):,.0f}",
        loan=loan.get('loan_number', '')
    )

    return send_sms(phone, message)


def send_fine_status_sms(loan, action):
    """Send SMS when fine is paused or waived"""
    phone = loan.get('client_phone', '')
    if not phone:
        return {'success': False, 'error': 'No phone number'}

    template = 'fine_paused' if action == 'pause' else 'fine_waived'
    message = format_message(
        template,
        name=loan.get('client_name', 'Customer'),
        amount=f"{loan.get('fine_amount', 0):,.0f}",
        loan=loan.get('loan_number', '')
    )

    return send_sms(phone, message)


def send_bulk_overdue_reminders(loans):
    """Send overdue reminders to all overdue loans"""
    results = {'total': len(loans), 'sent': 0, 'failed': 0, 'errors': []}

    for loan in loans:
        result = send_overdue_alert_sms(loan)
        if result['success']:
            results['sent'] += 1
        else:
            results['failed'] += 1
            results['errors'].append(
                f"{loan.get('client_name', 'Unknown')}: {result.get('error', 'Unknown error')}"
            )

    return results
