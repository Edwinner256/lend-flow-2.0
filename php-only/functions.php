<?php
/**
 * LendFlow - Pure PHP + MySQL
 * Core Database Functions
 */

require_once __DIR__ . '/config.php';

// ═══════════════════════════════════════════════════════════════
//  AUTH FUNCTIONS
// ═══════════════════════════════════════════════════════════════

function authenticateUser($identifier, $password) {
    $db = getDB();
    
    // Find user by username or email
    $stmt = $db->prepare("SELECT * FROM users WHERE (username = ? OR email = ?) AND is_active = 1");
    $stmt->execute(array($identifier, $identifier));
    $user = $stmt->fetch();
    
    if (!$user) return false;
    
    if (!password_verify($password, $user['password_hash'])) return false;
    
    // Check account lockout
    if (isAccountLocked($identifier)) return false;
    
    // Record successful login
    recordLoginAttempt($identifier, true);
    
    return $user;
}

function isAccountLocked($identifier) {
    $db = getDB();
    $cutoff = date('Y-m-d H:i:s', strtotime('-' . LOCKOUT_DURATION . ' minutes'));
    
    $stmt = $db->prepare("SELECT COUNT(*) FROM login_attempts WHERE identifier = ? AND success = 0 AND created_at > ?");
    $stmt->execute(array($identifier, $cutoff));
    $failed = $stmt->fetchColumn();
    
    return $failed >= MAX_LOGIN_ATTEMPTS;
}

function getFailedAttempts($identifier) {
    $db = getDB();
    $cutoff = date('Y-m-d H:i:s', strtotime('-' . LOCKOUT_DURATION . ' minutes'));
    
    $stmt = $db->prepare("SELECT COUNT(*) FROM login_attempts WHERE identifier = ? AND success = 0 AND created_at > ?");
    $stmt->execute(array($identifier, $cutoff));
    return $stmt->fetchColumn();
}

function recordLoginAttempt($identifier, $success) {
    $db = getDB();
    $stmt = $db->prepare("INSERT INTO login_attempts (identifier, success, ip_address) VALUES (?, ?, ?)");
    $stmt->execute(array($identifier, $success ? 1 : 0, $_SERVER['REMOTE_ADDR'] ?? 'unknown'));
}

function changePassword($userId, $currentPassword, $newPassword) {
    $db = getDB();
    $stmt = $db->prepare("SELECT password_hash FROM users WHERE id = ?");
    $stmt->execute(array($userId));
    $user = $stmt->fetch();
    
    if (!$user || !password_verify($currentPassword, $user['password_hash'])) {
        return array(false, 'Current password is incorrect');
    }
    
    if (strlen($newPassword) < 8) {
        return array(false, 'Password must be at least 8 characters');
    }
    
    $hash = password_hash($newPassword, PASSWORD_DEFAULT);
    $stmt = $db->prepare("UPDATE users SET password_hash = ? WHERE id = ?");
    $stmt->execute(array($hash, $userId));
    
    return array(true, 'Password changed successfully');
}

// ═══════════════════════════════════════════════════════════════
//  USER FUNCTIONS
// ═══════════════════════════════════════════════════════════════

function getUserById($id) {
    $db = getDB();
    $stmt = $db->prepare("SELECT * FROM users WHERE id = ?");
    $stmt->execute(array($id));
    return $stmt->fetch();
}

function getAllUsers() {
    $db = getDB();
    $stmt = $db->query("SELECT * FROM users ORDER BY created_at DESC");
    return $stmt->fetchAll();
}

function getClients() {
    $db = getDB();
    $stmt = $db->query("SELECT * FROM users WHERE role = 'client' ORDER BY created_at DESC");
    return $stmt->fetchAll();
}

function createUser($username, $email, $password, $role, $fullName, $phone = null, $address = null, $idNumber = null, $profilePicture = null) {
    $db = getDB();
    
    // Check if username or email exists
    $stmt = $db->prepare("SELECT id FROM users WHERE username = ? OR email = ?");
    $stmt->execute(array($username, $email));
    if ($stmt->fetch()) return false;
    
    $hash = password_hash($password, PASSWORD_DEFAULT);
    $stmt = $db->prepare("INSERT INTO users (username, email, password_hash, role, full_name, phone, address, id_number, profile_picture) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)");
    $stmt->execute(array($username, $email, $hash, $role, $fullName, $phone, $address, $idNumber, $profilePicture));
    
    return $db->lastInsertId();
}

function updateUser($userId, $data) {
    $db = getDB();
    $fields = array();
    $values = array();
    
    $allowed = array('full_name', 'email', 'phone', 'address', 'id_number', 'role', 'is_active');
    
    foreach ($allowed as $field) {
        if (isset($data[$field])) {
            $fields[] = $field . ' = ?';
            $values[] = $data[$field];
        }
    }
    
    if (empty($fields)) return array(false, 'No fields to update');
    
    $fields[] = 'updated_at = CURRENT_TIMESTAMP';
    $values[] = $userId;
    
    $sql = "UPDATE users SET " . implode(', ', $fields) . " WHERE id = ?";
    $stmt = $db->prepare($sql);
    $stmt->execute($values);
    
    return array(true, 'User updated');
}

function deactivateUser($userId) {
    $db = getDB();
    
    // Check for active loans
    $stmt = $db->prepare("SELECT COUNT(*) FROM loans WHERE client_id = ? AND status IN ('active', 'pending')");
    $stmt->execute(array($userId));
    $active = $stmt->fetchColumn();
    
    if ($active > 0) {
        return array(false, "Client has {$active} active/pending loan(s). Cancel them first.");
    }
    
    $stmt = $db->prepare("UPDATE users SET is_active = 0, updated_at = CURRENT_TIMESTAMP WHERE id = ?");
    $stmt->execute(array($userId));
    
    return array(true, 'User deactivated');
}

// ═══════════════════════════════════════════════════════════════
//  LOAN FUNCTIONS
// ═══════════════════════════════════════════════════════════════

function getLoans($clientId = null) {
    $db = getDB();
    
    if ($clientId) {
        $stmt = $db->prepare("SELECT l.*, u.full_name AS client_name FROM loans l LEFT JOIN users u ON l.client_id = u.id WHERE l.client_id = ? ORDER BY l.created_at DESC");
        $stmt->execute(array($clientId));
    } else {
        $stmt = $db->query("SELECT l.*, u.full_name AS client_name FROM loans l LEFT JOIN users u ON l.client_id = u.id ORDER BY l.created_at DESC");
    }
    
    return $stmt->fetchAll();
}

function getLoan($loanId) {
    $db = getDB();
    $stmt = $db->prepare("SELECT l.*, u.full_name AS client_name FROM loans l LEFT JOIN users u ON l.client_id = u.id WHERE l.id = ?");
    $stmt->execute(array($loanId));
    return $stmt->fetch();
}

function getLoanByNumber($loanNumber) {
    $db = getDB();
    $stmt = $db->prepare("SELECT l.*, u.full_name AS client_name FROM loans l LEFT JOIN users u ON l.client_id = u.id WHERE l.loan_number = ?");
    $stmt->execute(array($loanNumber));
    return $stmt->fetch();
}

function createLoan($clientId, $principal, $interestRate, $interestType = 'flat', $paymentSchedule = 'monthly', $purpose = '', $durationMonths = 1) {
    $db = getDB();
    
    $loanNumber = generateLoanNumber();
    
    // Calculate total amount
    if ($interestType === 'flat') {
        $totalInterest = $principal * ($interestRate / 100) * $durationMonths;
    } else {
        // Reducing balance approximation
        $totalInterest = $principal * ($interestRate / 100) * ($durationMonths + 1) / 2;
    }
    $totalAmount = $principal + $totalInterest;
    $balance = $totalAmount;
    
    // Calculate due date
    $dueDate = date('Y-m-d', strtotime("+{$durationMonths} months"));
    
    $stmt = $db->prepare("INSERT INTO loans (loan_number, client_id, principal, interest_rate, interest_type, payment_schedule, total_amount, balance, purpose, duration_months, due_date) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)");
    $stmt->execute(array($loanNumber, $clientId, $principal, $interestRate, $interestType, $paymentSchedule, $totalAmount, $balance, $purpose, $durationMonths, $dueDate));
    
    return $db->lastInsertId();
}

function approveLoan($loanId, $approvedBy, $notes = '') {
    $db = getDB();
    $stmt = $db->prepare("UPDATE loans SET status = 'active', approved_by = ?, approved_at = CURRENT_TIMESTAMP WHERE id = ?");
    $stmt->execute(array($approvedBy, $loanId));
    
    // Notify client
    $loan = getLoan($loanId);
    if ($loan) {
        sendNotification($loan['client_id'], 'Loan Approved', "Your loan {$loan['loan_number']} has been approved. Total amount: " . formatMoney($loan['total_amount']));
    }
    
    return true;
}

function rejectLoan($loanId, $rejectedBy, $reason = '') {
    $db = getDB();
    $stmt = $db->prepare("UPDATE loans SET status = 'rejected', rejected_by = ?, rejection_reason = ? WHERE id = ?");
    $stmt->execute(array($rejectedBy, $reason, $loanId));
    
    $loan = getLoan($loanId);
    if ($loan) {
        sendNotification($loan['client_id'], 'Loan Rejected', "Your loan application {$loan['loan_number']} has been rejected. Reason: {$reason}");
    }
    
    return true;
}

function deleteLoan($loanId) {
    $db = getDB();
    
    // Check for repayments
    $stmt = $db->prepare("SELECT COUNT(*) FROM repayments WHERE loan_id = ?");
    $stmt->execute(array($loanId));
    if ($stmt->fetchColumn() > 0) {
        return array(false, 'Cannot delete loan with existing repayments');
    }
    
    $stmt = $db->prepare("DELETE FROM loans WHERE id = ?");
    $stmt->execute(array($loanId));
    
    return array(true, 'Loan deleted');
}

// ═══════════════════════════════════════════════════════════════
//  REPAYMENT FUNCTIONS
// ═══════════════════════════════════════════════════════════════

function getRepayments($loanId = null, $limit = 100) {
    $db = getDB();
    
    if ($loanId) {
        $stmt = $db->prepare("SELECT r.*, u.full_name AS received_by_name FROM repayments r LEFT JOIN users u ON r.received_by = u.id WHERE r.loan_id = ? ORDER BY r.created_at DESC LIMIT ?");
        $stmt->execute(array($loanId, $limit));
    } else {
        $stmt = $db->prepare("SELECT r.*, l.loan_number, u.full_name AS client_name, rb.full_name AS received_by_name FROM repayments r JOIN loans l ON r.loan_id = l.id JOIN users u ON l.client_id = u.id LEFT JOIN users rb ON r.received_by = rb.id ORDER BY r.created_at DESC LIMIT ?");
        $stmt->execute(array($limit));
    }
    
    return $stmt->fetchAll();
}

function addRepayment($loanId, $amount, $paymentMethod, $reference, $receivedBy, $notes = '', $paymentType = 'principal') {
    $db = getDB();
    
    $stmt = $db->prepare("INSERT INTO repayments (loan_id, amount, payment_type, payment_method, reference, received_by, notes) VALUES (?, ?, ?, ?, ?, ?, ?)");
    $stmt->execute(array($loanId, $amount, $paymentType, $paymentMethod, $reference, $receivedBy, $notes));
    
    // Update loan balance
    $loan = getLoan($loanId);
    if ($loan) {
        if ($paymentType === 'fine') {
            $newFine = max(0, $loan['fine_amount'] - $amount);
            $stmt = $db->prepare("UPDATE loans SET fine_amount = ?, amount_paid = amount_paid + ? WHERE id = ?");
            $stmt->execute(array($newFine, $amount, $loanId));
        } else {
            $newPaid = $loan['amount_paid'] + $amount;
            $newBalance = max(0, $loan['balance'] - $amount);
            $status = $newBalance <= 0 ? 'paid' : 'active';
            $stmt = $db->prepare("UPDATE loans SET amount_paid = ?, balance = ?, status = ? WHERE id = ?");
            $stmt->execute(array($newPaid, $newBalance, $status, $loanId));
        }
    }
    
    // Notify client
    if ($loan) {
        sendNotification($loan['client_id'], 'Payment Received', "Payment of " . formatMoney($amount) . " received for loan {$loan['loan_number']}. Reference: {$reference}");
    }
    
    return true;
}

function deleteRepayment($repaymentId) {
    $db = getDB();
    
    $stmt = $db->prepare("SELECT loan_id, amount, payment_type FROM repayments WHERE id = ?");
    $stmt->execute(array($repaymentId));
    $repayment = $stmt->fetch();
    
    if (!$repayment) return false;
    
    // Delete repayment
    $stmt = $db->prepare("DELETE FROM repayments WHERE id = ?");
    $stmt->execute(array($repaymentId));
    
    // Recalculate loan balance
    $loan = getLoan($repayment['loan_id']);
    if ($loan) {
        $totalPaid = 0;
        $stmt = $db->prepare("SELECT SUM(amount) FROM repayments WHERE loan_id = ? AND payment_type = 'principal'");
        $stmt->execute(array($repayment['loan_id']));
        $totalPaid = $stmt->fetchColumn() ?: 0;
        
        $newBalance = max(0, $loan['total_amount'] - $totalPaid);
        $status = $newBalance <= 0 ? 'paid' : 'active';
        
        $stmt = $db->prepare("UPDATE loans SET amount_paid = ?, balance = ?, status = ? WHERE id = ?");
        $stmt->execute(array($totalPaid, $newBalance, $status, $repayment['loan_id']));
    }
    
    return true;
}

// ═══════════════════════════════════════════════════════════════
//  DASHBOARD FUNCTIONS
// ═══════════════════════════════════════════════════════════════

function getDashboardStats() {
    $db = getDB();
    
    $stats = array();
    
    // Total loaned
    $stmt = $db->query("SELECT COALESCE(SUM(principal), 0) FROM loans");
    $stats['total_loaned'] = $stmt->fetchColumn();
    
    // Total outstanding
    $stmt = $db->query("SELECT COALESCE(SUM(balance), 0) FROM loans WHERE status IN ('active', 'overdue')");
    $stats['total_outstanding'] = $stmt->fetchColumn();
    
    // Total collected
    $stmt = $db->query("SELECT COALESCE(SUM(amount_paid), 0) FROM loans");
    $stats['total_collected'] = $stmt->fetchColumn();
    
    // Active loans
    $stmt = $db->query("SELECT COUNT(*) FROM loans WHERE status = 'active'");
    $stats['active_loans'] = $stmt->fetchColumn();
    
    // Pending loans
    $stmt = $db->query("SELECT COUNT(*) FROM loans WHERE status = 'pending'");
    $stats['pending_loans'] = $stmt->fetchColumn();
    
    // Overdue loans
    $stmt = $db->query("SELECT COUNT(*) FROM loans WHERE status = 'overdue' OR (status = 'active' AND due_date < CURDATE())");
    $stats['overdue_count'] = $stmt->fetchColumn();
    
    // Total clients
    $stmt = $db->query("SELECT COUNT(*) FROM users WHERE role = 'client'");
    $stats['total_clients'] = $stmt->fetchColumn();
    
    return $stats;
}

// ═══════════════════════════════════════════════════════════════
//  NOTIFICATION FUNCTIONS
// ═══════════════════════════════════════════════════════════════

function getNotifications($userId, $unreadOnly = false) {
    $db = getDB();
    
    if ($unreadOnly) {
        $stmt = $db->prepare("SELECT * FROM notifications WHERE user_id = ? AND is_read = 0 ORDER BY created_at DESC LIMIT 50");
    } else {
        $stmt = $db->prepare("SELECT * FROM notifications WHERE user_id = ? ORDER BY created_at DESC LIMIT 50");
    }
    
    $stmt->execute(array($userId));
    return $stmt->fetchAll();
}

function markNotificationRead($notifId) {
    $db = getDB();
    $stmt = $db->prepare("UPDATE notifications SET is_read = 1 WHERE id = ?");
    $stmt->execute(array($notifId));
}

function markAllNotificationsRead($userId) {
    $db = getDB();
    $stmt = $db->prepare("UPDATE notifications SET is_read = 1 WHERE user_id = ?");
    $stmt->execute(array($userId));
}

// ═══════════════════════════════════════════════════════════════
//  REPORT FUNCTIONS
// ═══════════════════════════════════════════════════════════════

function getProfitLoss($year = null, $month = null) {
    $db = getDB();
    
    if (!$year) $year = date('Y');
    if (!$month) $month = date('m');
    
    $startDate = "{$year}-{$month}-01";
    $endDate = date('Y-m-t', strtotime($startDate));
    
    $report = array('year' => $year, 'month' => $month, 'transactions' => array());
    
    // Total repayments (income)
    $stmt = $db->prepare("SELECT COALESCE(SUM(amount), 0) FROM repayments WHERE created_at BETWEEN ? AND ?");
    $stmt->execute(array($startDate, $endDate . ' 23:59:59'));
    $report['total_income'] = $stmt->fetchColumn();
    
    // Get individual transactions
    $stmt = $db->prepare("SELECT r.amount, r.created_at, r.payment_type, l.loan_number, u.full_name AS client_name FROM repayments r JOIN loans l ON r.loan_id = l.id JOIN users u ON l.client_id = u.id WHERE r.created_at BETWEEN ? AND ? ORDER BY r.created_at DESC");
    $stmt->execute(array($startDate, $endDate . ' 23:59:59'));
    $report['transactions'] = $stmt->fetchAll();
    
    $report['total_expenses'] = 0; // Add expenses tracking if needed
    $report['net_profit'] = $report['total_income'] - $report['total_expenses'];
    
    return $report;
}

function getAuditLogs($limit = 100) {
    $db = getDB();
    $stmt = $db->prepare("SELECT a.*, u.username, u.full_name FROM audit_log a LEFT JOIN users u ON a.user_id = u.id ORDER BY a.created_at DESC LIMIT ?");
    $stmt->execute(array($limit));
    return $stmt->fetchAll();
}

// ═══════════════════════════════════════════════════════════════
//  DAILY CHECKS (Fines & Overdue)
// ═══════════════════════════════════════════════════════════════

function runDailyChecks() {
    $db = getDB();
    
    // Mark overdue loans
    $stmt = $db->query("UPDATE loans SET status = 'overdue' WHERE status = 'active' AND due_date < CURDATE()");
    
    // Apply fines to overdue loans
    $stmt = $db->query("SELECT id, principal FROM loans WHERE status = 'overdue' AND fine_active = 1");
    $overdue = $stmt->fetchAll();
    
    foreach ($overdue as $loan) {
        $fine = $loan['principal'] * 0.05; // 5% fine
        $stmt = $db->prepare("UPDATE loans SET fine_amount = fine_amount + ? WHERE id = ?");
        $stmt->execute(array($fine, $loan['id']));
    }
}
