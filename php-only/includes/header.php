<?php
require_once __DIR__ . '/auth.php';
requireLogin();
$user = currentUser();
$flash = getFlash();
$unread = getUnreadCount($user['id']);
$currentPage = basename($_SERVER['PHP_SELF'], '.php');
?>
<!DOCTYPE html>
<html lang="en" data-bs-theme="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title><?php echo h($pageTitle ?? APP_NAME); ?></title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.1/font/bootstrap-icons.css" rel="stylesheet">
    <link href="https://cdn.jsdelivr.net/npm/flatpickr/dist/flatpickr.min.css" rel="stylesheet">
    <link href="https://cdn.jsdelivr.net/npm/flatpickr/dist/themes/dark.css" rel="stylesheet">
    <style>
        :root {
            --sidebar-width: 260px;
            --primary: #1a3c2a;
            --primary-light: #2d5a3f;
            --accent: #8b6914;
            --accent-light: #a67c1a;
            --bg-dark: #0d1117;
            --bg-card: #161b22;
            --border: #30363d;
        }
        body { background: var(--bg-dark); color: #e6edf3; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
        .sidebar { position: fixed; top: 0; left: 0; width: var(--sidebar-width); height: 100vh; background: var(--primary); border-right: 1px solid var(--border); z-index: 1000; overflow-y: auto; transition: transform 0.3s ease; }
        .sidebar-brand { padding: 1.25rem 1.5rem; border-bottom: 1px solid rgba(255,255,255,0.1); display: flex; align-items: center; gap: 0.75rem; }
        .sidebar-brand .logo { width: 40px; height: 40px; background: var(--accent); border-radius: 10px; display: flex; align-items: center; justify-content: center; }
        .sidebar-brand .logo i { font-size: 1.3rem; color: #fff; }
        .sidebar-brand h5 { color: #fff; margin: 0; font-weight: 700; }
        .sidebar-brand small { color: rgba(255,255,255,0.5); font-size: 0.75rem; }
        .sidebar-nav { padding: 1rem 0; }
        .sidebar-nav .nav-section { padding: 0.5rem 1.5rem 0.25rem; font-size: 0.7rem; text-transform: uppercase; letter-spacing: 1px; color: rgba(255,255,255,0.35); font-weight: 600; }
        .sidebar-nav a { display: flex; align-items: center; gap: 0.75rem; padding: 0.65rem 1.5rem; color: rgba(255,255,255,0.7); text-decoration: none; font-size: 0.9rem; transition: all 0.2s; border-left: 3px solid transparent; }
        .sidebar-nav a:hover { background: rgba(255,255,255,0.05); color: #fff; }
        .sidebar-nav a.active { background: rgba(255,255,255,0.08); color: #fff; border-left-color: var(--accent); }
        .sidebar-nav a i { width: 20px; text-align: center; font-size: 1.1rem; }
        .sidebar-nav .badge { margin-left: auto; background: var(--accent); font-size: 0.7rem; }
        .main-content { margin-left: var(--sidebar-width); min-height: 100vh; }
        .top-navbar { background: var(--bg-card); border-bottom: 1px solid var(--border); padding: 0.75rem 1.5rem; display: flex; align-items: center; justify-content: space-between; position: sticky; top: 0; z-index: 999; }
        .top-navbar .user-info { display: flex; align-items: center; gap: 0.75rem; }
        .top-navbar .avatar { width: 36px; height: 36px; background: var(--accent); border-radius: 50%; display: flex; align-items: center; justify-content: center; color: #fff; font-weight: 600; font-size: 0.9rem; }
        .stat-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px; padding: 1.25rem; transition: transform 0.2s, box-shadow 0.2s; }
        .stat-card:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.3); }
        .stat-card .icon { width: 48px; height: 48px; border-radius: 12px; display: flex; align-items: center; justify-content: center; font-size: 1.4rem; }
        .stat-card .value { font-size: 1.75rem; font-weight: 700; margin: 0.5rem 0 0.25rem; }
        .stat-card .label { color: #8b949e; font-size: 0.85rem; }
        .table-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px; overflow: hidden; }
        .table-card .table { margin-bottom: 0; color: #e6edf3; }
        .table-card .table thead th { background: rgba(255,255,255,0.03); border-bottom: 1px solid var(--border); color: #8b949e; font-weight: 600; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.5px; padding: 0.85rem 1rem; }
        .table-card .table tbody td { border-bottom: 1px solid var(--border); padding: 0.75rem 1rem; vertical-align: middle; }
        .table-card .table tbody tr:last-child td { border-bottom: none; }
        .badge-active { background: #238636; color: #fff; }
        .badge-pending { background: #9e6a03; color: #fff; }
        .badge-approved { background: #1f6feb; color: #fff; }
        .badge-rejected { background: #da3633; color: #fff; }
        .badge-paid { background: #238636; color: #fff; }
        .badge-overdue { background: #da3633; color: #fff; }
        .btn-accent { background: var(--accent); border: none; color: #fff; }
        .btn-accent:hover { background: var(--accent-light); color: #fff; }
        .form-control, .form-select { background: rgba(255,255,255,0.05); border: 1px solid var(--border); color: #e6edf3; }
        .form-control:focus, .form-select:focus { background: rgba(255,255,255,0.08); border-color: var(--accent); color: #e6edf3; box-shadow: 0 0 0 3px rgba(139,105,20,0.2); }
        .form-label { color: rgba(255,255,255,0.8); font-weight: 500; }
        .modal-content { background: var(--bg-card); border: 1px solid var(--border); }
        .modal-header, .modal-footer { border-color: var(--border) !important; }
        .btn-close-white { filter: invert(1); }
        @media (max-width: 991px) { .sidebar { transform: translateX(-100%); } .sidebar.show { transform: translateX(0); } .main-content { margin-left: 0; } }
    </style>
</head>
<body>
    <nav class="sidebar" id="sidebar">
        <div class="sidebar-brand">
            <div class="logo"><i class="bi bi-bank"></i></div>
            <div><h5><?php echo APP_NAME; ?></h5><small>v<?php echo APP_VERSION; ?></small></div>
        </div>
        <div class="sidebar-nav">
            <div class="nav-section">Main</div>
            <a href="dashboard.php" class="<?php echo $currentPage === 'dashboard' ? 'active' : ''; ?>"><i class="bi bi-grid-1x2"></i> Dashboard</a>
            <a href="loans.php" class="<?php echo $currentPage === 'loans' ? 'active' : ''; ?>"><i class="bi bi-cash-stack"></i> Loans</a>
            <a href="repayments.php" class="<?php echo $currentPage === 'repayments' ? 'active' : ''; ?>"><i class="bi bi-arrow-down-circle"></i> Repayments</a>
            <?php if (in_array($user['role'], array('admin', 'loan_officer'))): ?>
            <div class="nav-section">Management</div>
            <a href="clients.php" class="<?php echo $currentPage === 'clients' ? 'active' : ''; ?>"><i class="bi bi-people"></i> Clients</a>
            <a href="users.php" class="<?php echo $currentPage === 'users' ? 'active' : ''; ?>"><i class="bi bi-person-gear"></i> Users</a>
            <?php endif; ?>
            <?php if ($user['role'] === 'admin'): ?>
            <div class="nav-section">Admin</div>
            <a href="reports.php" class="<?php echo $currentPage === 'reports' ? 'active' : ''; ?>"><i class="bi bi-bar-chart"></i> Reports</a>
            <a href="audit-log.php" class="<?php echo $currentPage === 'audit-log' ? 'active' : ''; ?>"><i class="bi bi-shield-check"></i> Audit Log</a>
            <?php endif; ?>
            <div class="nav-section">Account</div>
            <a href="notifications.php" class="<?php echo $currentPage === 'notifications' ? 'active' : ''; ?>"><i class="bi bi-bell"></i> Notifications <?php if ($unread > 0): ?><span class="badge"><?php echo $unread; ?></span><?php endif; ?></a>
            <a href="profile.php" class="<?php echo $currentPage === 'profile' ? 'active' : ''; ?>"><i class="bi bi-person-circle"></i> Profile</a>
            <a href="logout.php"><i class="bi bi-box-arrow-left"></i> Logout</a>
        </div>
    </nav>

    <div class="main-content">
        <div class="top-navbar">
            <button class="btn btn-sm btn-outline-secondary d-lg-none" onclick="document.getElementById('sidebar').classList.toggle('show')"><i class="bi bi-list"></i></button>
            <div class="user-info">
                <div class="avatar"><?php echo strtoupper(substr($user['full_name'], 0, 1)); ?></div>
                <div>
                    <div style="font-weight: 600; font-size: 0.9rem;"><?php echo h($user['full_name']); ?></div>
                    <div style="font-size: 0.75rem; color: #8b949e;"><?php echo ucfirst(str_replace('_', ' ', $user['role'])); ?></div>
                </div>
            </div>
        </div>

        <div class="p-3 p-md-4">
            <?php if ($flash): ?>
            <div class="alert <?php echo alertClass($flash['type']); ?> alert-dismissible fade show" role="alert">
                <?php echo $flash['message']; ?>
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            </div>
            <?php endif; ?>
