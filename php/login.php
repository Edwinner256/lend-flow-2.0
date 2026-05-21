<?php
require_once 'config.php';

// Redirect if already logged in
if (is_logged_in()) {
    header('Location: dashboard.php');
    exit;
}

$error = '';

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $identifier = $_POST['username'] ?? '';
    $password = $_POST['password'] ?? '';
    
    if ($identifier && $password) {
        $response = api_post('/api/auth/login', [
            'username' => $identifier,
            'password' => $password
        ], false);
        
        if ($response['success']) {
            // Store session
            $_SESSION['api_token'] = $response['token'];
            $_SESSION['user_id'] = $response['user']['id'];
            $_SESSION['username'] = $response['user']['username'];
            $_SESSION['full_name'] = $response['user']['full_name'];
            $_SESSION['email'] = $response['user']['email'];
            $_SESSION['user_role'] = $response['user']['role'];
            $_SESSION['phone'] = $response['user']['phone'] ?? '';
            $_SESSION['profile_picture'] = $response['user']['profile_picture'] ?? '';
            
            header('Location: dashboard.php');
            exit;
        } else {
            $error = $response['error'] ?? 'Invalid credentials';
        }
    } else {
        $error = 'Please enter username and password';
    }
}
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login - <?php echo APP_NAME; ?></title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.1/font/bootstrap-icons.css" rel="stylesheet">
    <style>
        :root {
            --primary: #1a3c2a;
            --primary-light: #2d5a3f;
            --accent: #8b6914;
            --accent-light: #a67c1a;
        }
        body {
            background: linear-gradient(135deg, var(--primary) 0%, #0d1f15 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .login-card {
            background: rgba(255,255,255,0.05);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 16px;
            padding: 2.5rem;
            width: 100%;
            max-width: 420px;
        }
        .login-card h2 {
            color: #fff;
            font-weight: 700;
        }
        .login-card .text-muted {
            color: rgba(255,255,255,0.6) !important;
        }
        .form-control {
            background: rgba(255,255,255,0.08);
            border: 1px solid rgba(255,255,255,0.15);
            color: #fff;
            border-radius: 10px;
            padding: 0.75rem 1rem;
        }
        .form-control:focus {
            background: rgba(255,255,255,0.12);
            border-color: var(--accent);
            box-shadow: 0 0 0 3px rgba(139,105,20,0.25);
            color: #fff;
        }
        .form-control::placeholder {
            color: rgba(255,255,255,0.4);
        }
        .form-label {
            color: rgba(255,255,255,0.8);
            font-weight: 500;
        }
        .btn-primary {
            background: var(--accent);
            border: none;
            border-radius: 10px;
            padding: 0.75rem;
            font-weight: 600;
        }
        .btn-primary:hover {
            background: var(--accent-light);
        }
        .logo-icon {
            width: 60px;
            height: 60px;
            background: var(--accent);
            border-radius: 14px;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0 auto 1.5rem;
        }
        .logo-icon i {
            font-size: 1.8rem;
            color: #fff;
        }
    </style>
</head>
<body>
    <div class="login-card">
        <div class="logo-icon">
            <i class="bi bi-bank"></i>
        </div>
        <h2 class="text-center mb-1"><?php echo APP_NAME; ?></h2>
        <p class="text-muted text-center mb-4">Money Lending Management System</p>
        
        <?php if ($error): ?>
        <div class="alert alert-danger" role="alert">
            <i class="bi bi-exclamation-circle me-2"></i><?php echo htmlspecialchars($error); ?>
        </div>
        <?php endif; ?>
        
        <form method="POST" action="">
            <div class="mb-3">
                <label class="form-label">Username or Loan Number</label>
                <div class="input-group">
                    <span class="input-group-text bg-transparent border-0 text-white-50">
                        <i class="bi bi-person"></i>
                    </span>
                    <input type="text" name="username" class="form-control" placeholder="Enter username" required autofocus>
                </div>
            </div>
            
            <div class="mb-4">
                <label class="form-label">Password</label>
                <div class="input-group">
                    <span class="input-group-text bg-transparent border-0 text-white-50">
                        <i class="bi bi-lock"></i>
                    </span>
                    <input type="password" name="password" class="form-control" placeholder="Enter password" required>
                </div>
            </div>
            
            <button type="submit" class="btn btn-primary w-100">
                <i class="bi bi-box-arrow-in-right me-2"></i>Sign In
            </button>
        </form>
        
        <p class="text-muted text-center mt-4 mb-0" style="font-size: 0.85rem;">
            &copy; <?php echo date('Y'); ?> <?php echo APP_NAME; ?> v<?php echo APP_VERSION; ?>
        </p>
    </div>
</body>
</html>
