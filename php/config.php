<?php
/**
 * LendFlow PHP Frontend Configuration
 * 
 * GoDaddy Shared Hosting Compatible
 * Connects PHP frontend to Flask API on Render
 * 
 * PHP Requirements: 7.4+ (GoDaddy default)
 * Required Extensions: curl, json, session
 */

// ── Error Reporting (disable in production) ───────────────────
// Set to 0 for production, 1 for debugging
error_reporting(0);
ini_set('display_errors', 0);

// ── API Configuration ─────────────────────────────────────────
// TODO: Replace with your actual Render URL after deployment
define('API_URL', 'https://your-app-name.onrender.com');
define('API_TIMEOUT', 30); // seconds

// ── App Configuration ─────────────────────────────────────────
define('APP_NAME', 'LendFlow');
define('APP_VERSION', '2.0');

// ── Session Configuration (GoDaddy compatible) ────────────────
// Use GoDaddy's default session save path
ini_set('session.cookie_httponly', 1);
ini_set('session.cookie_samesite', 'Lax');
ini_set('session.gc_maxlifetime', 28800); // 8 hours
ini_set('session.use_strict_mode', 1);
ini_set('session.use_only_cookies', 1);

// Regenerate session ID on login for security
if (!isset($_SESSION['initiated'])) {
    session_start();
    session_regenerate_id(true);
    $_SESSION['initiated'] = true;
} else {
    session_start();
}

// ── API Helper Functions ──────────────────────────────────────

/**
 * Make an API request to the Flask backend.
 * GoDaddy compatible - uses curl with proper error handling
 */
function api_request($method, $endpoint, $data = null, $requireAuth = true) {
    $url = API_URL . $endpoint;
    
    // Check if curl is available (GoDaddy requirement)
    if (!function_exists('curl_init')) {
        return array('success' => false, 'error' => 'cURL is not enabled on this server. Contact GoDaddy support.');
    }
    
    $ch = curl_init();
    curl_setopt($ch, CURLOPT_URL, $url);
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_TIMEOUT, API_TIMEOUT);
    curl_setopt($ch, CURLOPT_CONNECTTIMEOUT, 10);
    curl_setopt($ch, CURLOPT_CUSTOMREQUEST, $method);
    curl_setopt($ch, CURLOPT_FOLLOWLOCATION, true);
    
    $headers = array(
        'Content-Type: application/json',
        'Accept: application/json'
    );
    
    // Add auth token if required
    if ($requireAuth && isset($_SESSION['api_token'])) {
        $headers[] = 'Authorization: Bearer ' . $_SESSION['api_token'];
    }
    
    curl_setopt($ch, CURLOPT_HTTPHEADER, $headers);
    
    // Add request body for POST/PUT
    if ($data !== null && in_array($method, array('POST', 'PUT', 'PATCH'))) {
        curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode($data));
    }
    
    // SSL verification (required for Render HTTPS)
    curl_setopt($ch, CURLOPT_SSL_VERIFYPEER, true);
    curl_setopt($ch, CURLOPT_SSL_VERIFYHOST, 2);
    
    $response = curl_exec($ch);
    $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    $error = curl_error($ch);
    curl_close($ch);
    
    if ($error) {
        return array('success' => false, 'error' => 'Connection error: ' . $error);
    }
    
    if ($httpCode >= 500) {
        return array('success' => false, 'error' => 'API server error (HTTP ' . $httpCode . ')');
    }
    
    $result = json_decode($response, true);
    
    if ($result === null) {
        return array('success' => false, 'error' => 'Invalid API response');
    }
    
    return $result;
}

/**
 * GET request helper
 */
function api_get($endpoint, $requireAuth = true) {
    return api_request('GET', $endpoint, null, $requireAuth);
}

/**
 * POST request helper
 */
function api_post($endpoint, $data = array(), $requireAuth = true) {
    return api_request('POST', $endpoint, $data, $requireAuth);
}

/**
 * PUT request helper
 */
function api_put($endpoint, $data = array(), $requireAuth = true) {
    return api_request('PUT', $endpoint, $data, $requireAuth);
}

/**
 * DELETE request helper
 */
function api_delete($endpoint, $requireAuth = true) {
    return api_request('DELETE', $endpoint, null, $requireAuth);
}

// ── Auth Helper Functions ─────────────────────────────────────

/**
 * Check if user is logged in
 */
function is_logged_in() {
    return isset($_SESSION['user_id']) && isset($_SESSION['api_token']);
}

/**
 * Require login - redirect to login page if not authenticated
 */
function require_login() {
    if (!is_logged_in()) {
        header('Location: login.php');
        exit;
    }
}

/**
 * Require specific role - redirect to dashboard if insufficient permissions
 */
function require_role() {
    require_login();
    $roles = func_get_args();
    if (!in_array($_SESSION['user_role'], $roles)) {
        header('Location: dashboard.php?error=permission');
        exit;
    }
}

/**
 * Get current user info from session
 */
function current_user() {
    return array(
        'id' => isset($_SESSION['user_id']) ? $_SESSION['user_id'] : null,
        'username' => isset($_SESSION['username']) ? $_SESSION['username'] : null,
        'full_name' => isset($_SESSION['full_name']) ? $_SESSION['full_name'] : null,
        'email' => isset($_SESSION['email']) ? $_SESSION['email'] : null,
        'role' => isset($_SESSION['user_role']) ? $_SESSION['user_role'] : null,
        'phone' => isset($_SESSION['phone']) ? $_SESSION['phone'] : null,
        'profile_picture' => isset($_SESSION['profile_picture']) ? $_SESSION['profile_picture'] : null
    );
}

/**
 * Logout user
 */
function logout() {
    if (isset($_SESSION['api_token'])) {
        api_post('/api/auth/logout', array(), true);
    }
    session_unset();
    session_destroy();
    header('Location: login.php');
    exit;
}

// ── Utility Functions ─────────────────────────────────────────

/**
 * Format currency (UGX)
 */
function format_money($amount) {
    return 'UGX ' . number_format(floatval($amount), 0, '.', ',');
}

/**
 * Format date
 */
function format_date($date) {
    if (!$date) return '-';
    return date('M d, Y', strtotime($date));
}

/**
 * Show flash message
 */
function flash($message, $type = 'info') {
    $_SESSION['flash'] = array('message' => $message, 'type' => $type);
}

/**
 * Get and clear flash message
 */
function get_flash() {
    if (isset($_SESSION['flash'])) {
        $flash = $_SESSION['flash'];
        unset($_SESSION['flash']);
        return $flash;
    }
    return null;
}

/**
 * Get Bootstrap alert class from flash type
 */
function alert_class($type) {
    $classes = array(
        'success' => 'alert-success',
        'danger' => 'alert-danger',
        'warning' => 'alert-warning',
        'info' => 'alert-info'
    );
    return isset($classes[$type]) ? $classes[$type] : 'alert-info';
}

/**
 * Escape HTML output
 */
function h($string) {
    return htmlspecialchars($string, ENT_QUOTES, 'UTF-8');
}
