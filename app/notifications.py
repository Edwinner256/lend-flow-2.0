"""
Notification System for LendFlow
Handles reminders, alerts, and transactional notifications.
Now integrated with BoxUganda SMS API for real SMS sending.
"""

from datetime import datetime, timedelta
from app.database import get_db, send_notification, get_notifications
from app.sms_service import (
    send_sms, send_payment_reminder_sms, send_overdue_alert_sms,
    send_payment_confirmation_sms, send_loan_approved_sms,
    send_loan_rejected_sms, send_welcome_sms
)

def send_payment_reminder(loan_id):
    """Send payment reminder for a loan - both in-app and SMS"""
    conn = get_db()
    loan = conn.execute('''
        SELECT l.*, u.full_name, u.phone, u.email
        FROM loans l JOIN users u ON l.client_id = u.id
        WHERE l.id = ?
    ''', (loan_id,)).fetchone()

    if not loan:
        conn.close()
        return

    days_until_due = (datetime.strptime(loan['due_date'], '%Y-%m-%d') - datetime.now()).days

    if days_until_due <= 0:
        title = "Payment Overdue"
        message = f"Dear {loan['full_name']}, your loan payment of UGX {loan['balance']:,.0f} is now overdue. Please make payment immediately to avoid additional penalties."
        notif_type = "warning"
    elif days_until_due <= 3:
        title = "Payment Due Soon"
        message = f"Dear {loan['full_name']}, your payment of UGX {loan['balance']:,.0f} is due in {days_until_due} day(s). Please ensure timely payment to stay on track."
        notif_type = "alert"
    elif days_until_due <= 7:
        title = "Upcoming Payment"
        message = f"Dear {loan['full_name']}, a friendly reminder: your payment of UGX {loan['balance']:,.0f} is due on {loan['due_date']}."
        notif_type = "reminder"
    else:
        conn.close()
        return

    # In-app notification
    send_notification(loan['client_id'], notif_type, title, message, 'in_app')

    # Send real SMS via BoxUganda API
    if loan['phone']:
        send_payment_reminder_sms({
            'client_name': loan['full_name'],
            'client_phone': loan['phone'],
            'balance': loan['balance'],
            'due_date': loan['due_date']
        })

    conn.close()

def send_loan_approved_notification(loan_id, client_id):
    """Notify client that their loan has been approved - both in-app and SMS"""
    conn = get_db()
    loan = conn.execute('SELECT * FROM loans WHERE id = ?', (loan_id,)).fetchone()
    client = conn.execute('SELECT full_name, phone FROM users WHERE id = ?', (client_id,)).fetchone()
    
    if loan:
        # In-app notification
        send_notification(
            client_id, 'success', 'Loan Approved',
            f'Congratulations, {client["full_name"]}! Your loan of UGX {loan["principal"]:,.0f} has been approved. '
            f'Total repayment: UGX {loan["total_amount"]:,.0f}. Due date: {loan["due_date"]}. '
            f'Visit our office to collect your funds.',
            'in_app'
        )
        
        # Send real SMS
        if client and client['phone']:
            send_loan_approved_sms(client['full_name'], client['phone'], loan['principal'])
    
    conn.close()

def send_loan_rejected_notification(client_id, loan_id):
    """Notify client that their loan has been rejected - both in-app and SMS"""
    conn = get_db()
    client = conn.execute('SELECT full_name, phone FROM users WHERE id = ?', (client_id,)).fetchone()
    
    # In-app notification
    send_notification(
        client_id, 'warning', 'Loan Application Not Approved',
        f'Dear {client["full_name"]}, we regret to inform you that your loan application was not approved at this time. '
        f'Please contact your loan officer to discuss your options or reapply in the future.',
        'in_app'
    )
    
    # Send real SMS
    if client and client['phone']:
        send_loan_rejected_sms(client['full_name'], client['phone'])
    
    conn.close()

def send_welcome_notification(user_id, full_name):
    """Send welcome notification to new client - both in-app and SMS"""
    conn = get_db()
    client = conn.execute('SELECT phone FROM users WHERE id = ?', (user_id,)).fetchone()
    
    # In-app notification
    send_notification(
        user_id, 'info', 'Welcome to Vaulta Cash',
        f'Welcome, {full_name}! Your account has been created successfully. '
        f'You can now apply for loans, track repayments, and manage your finances all in one place.',
        'in_app'
    )
    
    # Send real SMS
    if client and client['phone']:
        send_welcome_sms(full_name, client['phone'])
    
    conn.close()

def send_payment_confirmation(client_id, amount, balance):
    """Send payment confirmation - both in-app and SMS"""
    conn = get_db()
    client = conn.execute('SELECT full_name, phone FROM users WHERE id = ?', (client_id,)).fetchone()
    
    # In-app notification
    status_msg = 'Your loan is fully paid off! Congratulations.' if balance <= 0 else f'Remaining balance: UGX {balance:,.0f}.'
    send_notification(
        client_id, 'success', 'Payment Received',
        f'Thank you, {client["full_name"]}! Your payment of UGX {amount:,.0f} has been received. {status_msg}',
        'in_app'
    )
    
    # Send real SMS
    if client and client['phone']:
        send_payment_confirmation_sms(client['full_name'], client['phone'], amount, balance)
    
    conn.close()

def run_daily_reminders():
    """Run daily reminder checks for all active loans"""
    conn = get_db()
    active_loans = conn.execute('SELECT id FROM loans WHERE status = "active"').fetchall()
    conn.close()

    for loan in active_loans:
        send_payment_reminder(loan['id'])

def get_unread_count(user_id):
    """Get unread notification count"""
    conn = get_db()
    count = conn.execute('SELECT COUNT(*) FROM notifications WHERE user_id = ? AND is_read = 0', (user_id,)).fetchone()[0]
    conn.close()
    return count
