<?php
require_once __DIR__ . '/config.php';

// ── Auth Check ────────────────────────────────────────────────
function requireLogin() {
    if (!isset($_SESSION['user_id'])) {
        header('Location: login.php');
        exit;
    }
    // Check session timeout
    if (isset($_SESSION['last_activity'])) {
        $last = strtotime($_SESSION['last_activity']);
        if (time() - $last > SESSION_LIFETIME) {
            session_destroy();
            header('Location: login.php?expired=1');
            exit;
        }
    }
    $_SESSION['last_activity'] = date('Y-m-d H:i:s');
}

function requireRole() {
    requireLogin();
    $roles = func_get_args();
    if (!in_array($_SESSION['user_role'], $roles)) {
        header('Location: dashboard.php?error=permission');
        exit;
    }
}

function currentUser() {
    return array(
        'id' => $_SESSION['user_id'] ?? null,
        'username' => $_SESSION['username'] ?? null,
        'full_name' => $_SESSION['full_name'] ?? null,
        'email' => $_SESSION['email'] ?? null,
        'role' => $_SESSION['user_role'] ?? null,
        'phone' => $_SESSION['phone'] ?? null,
        'profile_picture' => $_SESSION['profile_picture'] ?? null
    );
}

function logout() {
    session_destroy();
    header('Location: login.php');
    exit;
}
