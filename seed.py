"""Seed script to create demo data for LendFlow (max 10 loans)"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app.database import (
    init_db, create_user, create_loan, approve_loan, add_repayment,
    update_client_profile, send_notification, log_audit, get_db, get_loan
)


def seed():
    print("Initializing database...")
    init_db()

    # ============================================================
    # 1. Create admin user
    # ============================================================
    admin_id = create_user(
        'admin', 'admin@lendflow.com', 'admin123', 'admin',
        'Admin User', '0700000001'
    )
    print(f"Created admin (id={admin_id})")

    # ============================================================
    # 2. Create loan officers
    # ============================================================
    officer1_id = create_user(
        'officer', 'officer@lendflow.com', 'officer123', 'loan_officer',
        'Jane Muthoni', '0700000002'
    )
    officer2_id = create_user(
        'officer2', 'officer2@lendflow.com', 'officer123', 'loan_officer',
        'John Kamau', '0700000003'
    )
    print(f"Created loan officers (id={officer1_id}, {officer2_id})")

    # ============================================================
    # 3. Create clients (6 clients for variety)
    # ============================================================
    clients = [
        ('alice',   'alice@lendflow.com',   'client123', 'client', 'Alice Wanjiku',   '0711111111', 'Nairobi'),
        ('brian',   'brian@email.com',      'brian123',  'client', 'Brian Ochieng',    '0722222222', 'Mombasa'),
        ('carol',   'carol@email.com',      'carol123',  'client', 'Carol Njeri',      '0733333333', 'Kisumu'),
        ('david',   'david@email.com',      'david123',  'client', 'David Kiprop',     '0744444444', 'Nakuru'),
        ('faith',   'faith@email.com',      'faith123',  'client', 'Faith Akinyi',     '0755555555', 'Eldoret'),
        ('grace',   'grace@email.com',      'grace123',  'client', 'Grace Atieno',     '0766666666', 'kampala'),
    ]

    client_ids = []
    for username, email, password, role, name, phone, address in clients:
        cid = create_user(username, email, password, role, name, phone, address)
        client_ids.append(cid)
        print(f"Created client: {name} (id={cid})")

    # ============================================================
    # 4. Client profiles
    # ============================================================
    update_client_profile(
        client_ids[0],
        employer='Safaricom PLC', monthly_income=85000, credit_score=720,
        mpesa_number='0711111111', bank_name='KCB', bank_account='1234567890',
        next_of_kin='Peter Wanjiku', next_of_kin_phone='0711111112'
    )
    update_client_profile(
        client_ids[1],
        employer='Equity Bank', monthly_income=65000, credit_score=680,
        mpesa_number='0722222222', bank_name='Equity', bank_account='0987654321'
    )
    update_client_profile(
        client_ids[2],
        employer='Self Employed', monthly_income=45000, credit_score=650,
        mpesa_number='0733333333'
    )
    update_client_profile(
        client_ids[3],
        employer='Kenya Airways', monthly_income=120000, credit_score=780,
        mpesa_number='0744444444', bank_name='NCBA', bank_account='5678901234'
    )
    update_client_profile(
        client_ids[4],
        employer='Teacher', monthly_income=55000, credit_score=700,
        mpesa_number='0755555555', bank_name='Co-op Bank', bank_account='3456789012'
    )
    update_client_profile(
        client_ids[5],
        employer='Uganda Breweries', monthly_income=70000, credit_score=690,
        mpesa_number='0766666666', bank_name='Stanbic', bank_account='1122334455'
    )

    # ============================================================
    # 5. Loans — exactly 10, varied statuses & schedules
    # ============================================================

    # ── Loan 1: Alice — active, partial payments ──
    loan1_id, loan1_num = create_loan(
        client_ids[0], 50000, 10, 'flat', 'monthly', 3,
        'Business expansion', officer1_id,
        'Peter Wanjiku', '0711111112', processing_fee=2000
    )
    approve_loan(loan1_id, admin_id)
    add_repayment(loan1_id, 15000, 'mtn', 'MTN-REF-001', officer1_id, 'First installment')
    add_repayment(loan1_id, 10000, 'airtel', 'AIR-REF-001', officer1_id, 'Second installment')
    print(f"Loan {loan1_num}: Alice — UGX 50,000 (active, 2/3 payments made)")

    # ── Loan 2: Brian — active, freshly approved ──
    loan2_id, loan2_num = create_loan(
        client_ids[1], 30000, 12, 'flat', 'monthly', 2,
        'School fees', officer1_id, processing_fee=1000
    )
    approve_loan(loan2_id, admin_id)
    print(f"Loan {loan2_num}: Brian — UGX 30,000 (active, no payments yet)")

    # ── Loan 3: Carol — fully paid off ──
    loan3_id, loan3_num = create_loan(
        client_ids[2], 20000, 10, 'flat', 'monthly', 6,
        'Medical bills', officer2_id, processing_fee=500
    )
    approve_loan(loan3_id, admin_id)
    # Pay entire principal + interest: 20,000 + (20,000 * 10% * 6) = 32,000
    loan3 = get_loan(loan3_id)
    add_repayment(loan3_id, loan3['total_amount'], 'cash', 'CASH-001', officer2_id, 'Full payment')
    print(f"Loan {loan3_num}: Carol — UGX 20,000 (paid off)")

    # ── Loan 4: David — active, one payment made ──
    loan4_id, loan4_num = create_loan(
        client_ids[3], 100000, 8, 'flat', 'monthly', 6,
        'Car purchase', officer2_id,
        'Mary Kiprop', '0744444445', processing_fee=3000
    )
    approve_loan(loan4_id, admin_id)
    add_repayment(loan4_id, 25000, 'bank', 'BANK-TRF-001', officer2_id, 'First monthly installment')
    print(f"Loan {loan4_num}: David — UGX 100,000 (active, 1 payment made)")

    # ── Loan 5: Faith — pending (not yet approved) ──
    loan5_id, loan5_num = create_loan(
        client_ids[4], 15000, 15, 'flat', 'monthly', 1,
        'Emergency', officer1_id, processing_fee=500
    )
    print(f"Loan {loan5_num}: Faith — UGX 15,000 (pending approval)")

    # ── Loan 6: Alice — active, weekly schedule ──
    loan6_id, loan6_num = create_loan(
        client_ids[0], 80000, 10, 'flat', 'weekly', 4,
        'Home renovation', officer2_id, processing_fee=2000
    )
    approve_loan(loan6_id, admin_id)
    print(f"Loan {loan6_num}: Alice — UGX 80,000 (active, weekly schedule)")

    # ── Loan 7: Brian — reducing balance, active ──
    loan7_id, loan7_num = create_loan(
        client_ids[1], 45000, 11, 'reducing', 'monthly', 3,
        'Stock purchase', officer1_id,
        'Grace Atieno', '0766666666', processing_fee=1500
    )
    approve_loan(loan7_id, admin_id)
    print(f"Loan {loan7_num}: Brian — UGX 45,000 (active, reducing balance)")

    # ── Loan 8: Carol — active, weekly schedule ──
    loan8_id, loan8_num = create_loan(
        client_ids[2], 25000, 10, 'flat', 'weekly', 2,
        'Shop renovation', officer2_id, processing_fee=1000
    )
    approve_loan(loan8_id, admin_id)
    add_repayment(loan8_id, 5000, 'mtn', 'MTN-CAROL-01', officer2_id, 'Week 1 payment')
    print(f"Loan {loan8_num}: Carol — UGX 25,000 (active, weekly, 1 payment made)")

    # ── Loan 9: David — large loan, pending approval ──
    loan9_id, loan9_num = create_loan(
        client_ids[3], 200000, 9, 'flat', 'monthly', 12,
        'Land purchase', officer2_id,
        'John Kamau', '0700000003', processing_fee=5000
    )
    print(f"Loan {loan9_num}: David — UGX 200,000 (pending approval — large loan)")

    # ── Loan 10: Grace — defaulted (overdue, fine applied) ──
    loan10_id, loan10_num = create_loan(
        client_ids[5], 35000, 10, 'flat', 'monthly', 2,
        'Business startup', officer1_id,
        'Faith Akinyi', '0755555555', processing_fee=1000
    )
    approve_loan(loan10_id, admin_id)
    # Mark as defaulted with an overdue date and fine
    conn = get_db()
    conn.execute(
        "UPDATE loans SET status = 'defaulted', due_date = date('now', '-30 days'), "
        "next_payment_date = date('now', '-30 days'), default_count = 3, "
        "fine_amount = fine_amount + 73, fine_active = 1, "
        "balance = balance + 73 WHERE id = ?",
        (loan10_id,)
    )
    conn.commit()
    conn.close()
    print(f"Loan {loan10_num}: Grace — UGX 35,000 (defaulted, overdue, fine applied)")

    # ============================================================
    # 6. Welcome notifications
    # ============================================================
    for cid in client_ids:
        send_notification(
            cid, 'info', 'Welcome to LendFlow!',
            'Your account has been created. You can now apply for loans.',
            'in_app'
        )

    # ============================================================
    # 7. Summary
    # ============================================================
    print("\n" + "=" * 55)
    print("  Demo data seeded successfully! (10 loans, 6 clients)")
    print("=" * 55)
    print()
    print("📋 Loan Summary:")
    print(f"  1. {loan1_num}  Alice Wanjiku   UGX  50,000  active      (2 payments)")
    print(f"  2. {loan2_num}  Brian Ochieng   UGX  30,000  active")
    print(f"  3. {loan3_num}  Carol Njeri     UGX  20,000  paid off")
    print(f"  4. {loan4_num}  David Kiprop    UGX 100,000  active      (1 payment)")
    print(f"  5. {loan5_num}  Faith Akinyi    UGX  15,000  pending")
    print(f"  6. {loan6_num}  Alice Wanjiku   UGX  80,000  active      (weekly)")
    print(f"  7. {loan7_num}  Brian Ochieng   UGX  45,000  active      (reducing)")
    print(f"  8. {loan8_num}  Carol Njeri     UGX  25,000  active      (weekly, 1 pay)")
    print(f"  9. {loan9_num}  David Kiprop    UGX 200,000  pending     (large loan)")
    print(f" 10. {loan10_num} Grace Atieno    UGX  35,000  defaulted   (overdue+fine)")
    print()
    print("🔑 Login Credentials:")
    print("  Admin:   admin    / admin123")
    print("  Officer: officer  / officer123")
    print("  Client:  alice    / client123")


if __name__ == '__main__':
    seed()
