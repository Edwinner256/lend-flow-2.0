<?php
/**
 * LendFlow - Pure PHP + MySQL
 * GoDaddy Shared Hosting Compatible
 * 
 * Database Configuration
 */

// ── Database Settings ─────────────────────────────────────────
// TODO: Update these with your GoDaddy MySQL credentials
define('DB_HOST', 'localhost');
define('DB_NAME', 'lendflow_db');
define('DB_USER', 'your_db_user');
define('DB_PASS', 'your_db_password');
define('DB_CHARSET', 'utf8mb4');

// ── App Settings ──────────────────────────────────────────────
define('APP_NAME', 'LendFlow');
define('APP_VERSION', '2.0');
define('APP_URL', 'https://yourdomain.com'); // Update with your domain

// ── Upload Settings ───────────────────────────────────────────
define('UPLOAD_DIR', __DIR__ . '/uploads/');
define('MAX_FILE_SIZE', 5 * 1024 * 1024); // 5MB
define('ALLOWED_EXTENSIONS', array('png', 'jpg', 'jpeg', 'gif'));

// ── Security Settings ─────────────────────────────────────────
define('MAX_LOGIN_ATTEMPTS', 5);
define('LOCKOUT_DURATION', 15); // minutes
define('SESSION_LIFETIME', 28800); // 8 hours

// ── Error Reporting ───────────────────────────────────────────
// Set to 0 for production, E_ALL for development
error_reporting(0);
ini_set('display_errors', 0);

// ── Session Configuration ─────────────────────────────────────
ini_set('session.cookie_httponly', 1);
ini_set('session.cookie_samesite', 'Lax');
ini_set('session.gc_maxlifetime', SESSION_LIFETIME);
ini_set('session.use_strict_mode', 1);
ini_set('session.use_only_cookies', 1);

if (!isset($_SESSION['initiated'])) {
    session_start();
    session_regenerate_id(true);
    $_SESSION['initiated'] = true;
} else {
    session_start();
}

// ── Database Connection (PDO) ─────────────────────────────────
$db = null;

function getDB() {
    global $db;
    if ($db === null) {
        try {
            $dsn = 'mysql:host=' . DB_HOST . ';dbname=' . DB_NAME . ';charset=' . DB_CHARSET;
            $db = new PDO($dsn, DB_USER, DB_PASS, array(
                PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
                PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
                PDO::ATTR_EMULATE_PREPARES => false
            ));
        } catch (PDOException $e) {
            die('Database connection failed. Please check your settings in config.php');
        }
    }
    return $db;
}

// ── Initialize Database ───────────────────────────────────────
function initDB() {
    $db = getDB();
    
    // Users table
    $db->exec("CREATE TABLE IF NOT EXISTS users (
        id INT AUTO_INCREMENT PRIMARY KEY,
        username VARCHAR(50) UNIQUE NOT NULL,
        email VARCHAR(100) UNIQUE NOT NULL,
        password_hash VARCHAR(255) NOT NULL,
        role ENUM('admin', 'loan_officer', 'client') NOT NULL DEFAULT 'client',
        full_name VARCHAR(100) NOT NULL,
        phone VARCHAR(20),
        address VARCHAR(255),
        id_number VARCHAR(50),
        profile_picture VARCHAR(255),
        is_active TINYINT(1) DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        INDEX idx_username (username),
        INDEX idx_role (role),
        INDEX idx_active (is_active)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");
    
    // Client profiles
    $db->exec("CREATE TABLE IF NOT EXISTS client_profiles (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT UNIQUE NOT NULL,
        employer VARCHAR(100),
        monthly_income DECIMAL(12,2),
        credit_score INT,
        next_of_kin VARCHAR(100),
        next_of_kin_phone VARCHAR(20),
        bank_name VARCHAR(100),
        bank_account VARCHAR(50),
        mpesa_number VARCHAR(20),
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");
    
    // Loans table - with loan_date and timestamp fields
    $db->exec("CREATE TABLE IF NOT EXISTS loans (
        id INT AUTO_INCREMENT PRIMARY KEY,
        loan_number VARCHAR(20) UNIQUE NOT NULL,
        client_id INT NOT NULL,
        loan_officer_id INT,
        principal DECIMAL(12,2) NOT NULL,
        interest_rate DECIMAL(5,2) NOT NULL,
        interest_type ENUM('flat', 'reducing') DEFAULT 'flat',
        payment_schedule ENUM('daily', 'weekly', 'monthly') DEFAULT 'monthly',
        total_amount DECIMAL(12,2) NOT NULL,
        amount_paid DECIMAL(12,2) DEFAULT 0,
        balance DECIMAL(12,2) NOT NULL,
        fine_amount DECIMAL(12,2) DEFAULT 0,
        fine_active TINYINT(1) DEFAULT 0,
        status ENUM('pending', 'approved', 'active', 'paid', 'overdue', 'rejected', 'cancelled') DEFAULT 'pending',
        purpose TEXT,
        duration_months INT DEFAULT 1,
        loan_date DATE NOT NULL,
        loan_time TIME NOT NULL,
        approved_by INT,
        approved_at TIMESTAMP NULL,
        rejected_by INT,
        rejection_reason TEXT,
        due_date DATE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        FOREIGN KEY (client_id) REFERENCES users(id),
        FOREIGN KEY (loan_officer_id) REFERENCES users(id),
        FOREIGN KEY (approved_by) REFERENCES users(id),
        FOREIGN KEY (rejected_by) REFERENCES users(id),
        INDEX idx_client (client_id),
        INDEX idx_status (status),
        INDEX idx_loan_number (loan_number),
        INDEX idx_loan_date (loan_date)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");
    
    // Repayments table
    $db->exec("CREATE TABLE IF NOT EXISTS repayments (
        id INT AUTO_INCREMENT PRIMARY KEY,
        loan_id INT NOT NULL,
        amount DECIMAL(12,2) NOT NULL,
        payment_type ENUM('principal', 'fine') DEFAULT 'principal',
        payment_method ENUM('cash', 'mtn', 'airtel', 'bank', 'cheque') DEFAULT 'cash',
        reference VARCHAR(50),
        received_by INT,
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (loan_id) REFERENCES loans(id) ON DELETE CASCADE,
        FOREIGN KEY (received_by) REFERENCES users(id),
        INDEX idx_loan (loan_id),
        INDEX idx_created (created_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");
    
    // Notifications table
    $db->exec("CREATE TABLE IF NOT EXISTS notifications (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL,
        title VARCHAR(100) NOT NULL,
        message TEXT NOT NULL,
        is_read TINYINT(1) DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        INDEX idx_user_read (user_id, is_read)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");
    
    // Audit log table
    $db->exec("CREATE TABLE IF NOT EXISTS audit_log (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL,
        action VARCHAR(50) NOT NULL,
        entity_type VARCHAR(50),
        entity_id INT,
        details TEXT,
        ip_address VARCHAR(45),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id),
        INDEX idx_user_action (user_id, action),
        INDEX idx_created (created_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");
    
    // Login attempts table
    $db->exec("CREATE TABLE IF NOT EXISTS login_attempts (
        id INT AUTO_INCREMENT PRIMARY KEY,
        identifier VARCHAR(100) NOT NULL,
        success TINYINT(1) DEFAULT 0,
        ip_address VARCHAR(45),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_identifier (identifier),
        INDEX idx_created (created_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");
    
    // SMS logs table
    $db->exec("CREATE TABLE IF NOT EXISTS sms_logs (
        id INT AUTO_INCREMENT PRIMARY KEY,
        phone VARCHAR(20) NOT NULL,
        message TEXT NOT NULL,
        status ENUM('sent', 'failed', 'pending') DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_phone (phone)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");
    
    // Ensure uploads directory exists
    if (!is_dir(UPLOAD_DIR)) {
        mkdir(UPLOAD_DIR, 0755, true);
    }
    
    // Ensure admin user exists
    ensureAdminExists();
}

// ── Ensure Admin User Exists ──────────────────────────────────
function ensureAdminExists() {
    $db = getDB();
    $stmt = $db->prepare("SELECT id FROM users WHERE username = ?");
    $stmt->execute(array('admin'));
    $admin = $stmt->fetch();
    
    if (!$admin) {
        $hash = password_hash('admin123?Vaulta', PASSWORD_DEFAULT);
        $stmt = $db->prepare("INSERT INTO users (username, email, password_hash, role, full_name, is_active) VALUES (?, ?, ?, ?, ?, 1)");
        $stmt->execute(array('admin', 'admin@vaulta.local', $hash, 'admin', 'System Admin'));
    } else {
        // Update admin password to ensure it matches
        $hash = password_hash('admin123?Vaulta', PASSWORD_DEFAULT);
        $stmt = $db->prepare("UPDATE users SET password_hash = ?, role = 'admin', is_active = 1 WHERE id = ?");
        $stmt->execute(array($hash, $admin['id']));
    }
}

// ── Helper Functions ──────────────────────────────────────────

function h($string) {
    return htmlspecialchars($string, ENT_QUOTES, 'UTF-8');
}

function formatMoney($amount) {
    return 'UGX ' . number_format(floatval($amount), 0, '.', ',');
}

function formatDate($date) {
    if (!$date) return '-';
    return date('M d, Y', strtotime($date));
}

function formatTime($time) {
    if (!$time) return '-';
    return date('h:i A', strtotime($time));
}

function generateLoanNumber() {
    $db = getDB();
    $year = date('Y');
    $stmt = $db->prepare("SELECT loan_number FROM loans WHERE loan_number LIKE ? ORDER BY id DESC LIMIT 1");
    $stmt->execute(array("VL-%-{$year}"));
    $last = $stmt->fetch();
    
    if ($last) {
        $parts = explode('-', $last['loan_number']);
        $num = intval(end($parts)) + 1;
    } else {
        $num = 1;
    }
    
    return sprintf('VL-%03d-%d', $num, $year);
}

function generateReference() {
    return 'PAY-' . date('Ymd') . strtoupper(substr(bin2hex(random_bytes(3)), 0, 6));
}

function flash($message, $type = 'info') {
    $_SESSION['flash'] = array('message' => $message, 'type' => $type);
}

function getFlash() {
    if (isset($_SESSION['flash'])) {
        $flash = $_SESSION['flash'];
        unset($_SESSION['flash']);
        return $flash;
    }
    return null;
}

function alertClass($type) {
    $classes = array(
        'success' => 'alert-success',
        'danger' => 'alert-danger',
        'warning' => 'alert-warning',
        'info' => 'alert-info'
    );
    return isset($classes[$type]) ? $classes[$type] : 'alert-info';
}

function logAudit($userId, $action, $entityType = null, $entityId = null, $details = null) {
    $db = getDB();
    $stmt = $db->prepare("INSERT INTO audit_log (user_id, action, entity_type, entity_id, details, ip_address) VALUES (?, ?, ?, ?, ?, ?)");
    $stmt->execute(array($userId, $action, $entityType, $entityId, $details, $_SERVER['REMOTE_ADDR'] ?? 'unknown'));
}

function sendNotification($userId, $title, $message) {
    $db = getDB();
    $stmt = $db->prepare("INSERT INTO notifications (user_id, title, message) VALUES (?, ?, ?)");
    $stmt->execute(array($userId, $title, $message));
}

function getUnreadCount($userId) {
    $db = getDB();
    $stmt = $db->prepare("SELECT COUNT(*) FROM notifications WHERE user_id = ? AND is_read = 0");
    $stmt->execute(array($userId));
    return $stmt->fetchColumn();
}

// ── Initialize on every request ───────────────────────────────
initDB();
