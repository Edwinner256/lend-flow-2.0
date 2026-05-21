<?php
$page_title = 'Clients - ' . APP_NAME;
require_once 'config.php';
require_role('admin', 'loan_officer');

// Handle create user
if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['create_client'])) {
    $response = api_post('/api/users', [
        'full_name' => $_POST['full_name'],
        'phone' => $_POST['phone'] ?? '',
        'email' => $_POST['email'] ?? '',
        'address' => $_POST['address'] ?? '',
        'id_number' => $_POST['id_number'] ?? '',
        'role' => 'client'
    ]);
    
    if ($response['success']) {
        $msg = 'Client created successfully!';
        if (!empty($response['generated_credentials'])) {
            $creds = $response['generated_credentials'];
            $msg .= "<br><strong>Username:</strong> {$creds['username']} <strong>Password:</strong> {$creds['password']}";
        }
        flash($msg, 'success');
    } else {
        flash($response['error'] ?? 'Failed to create client', 'danger');
    }
    header('Location: clients.php');
    exit;
}

// Handle delete user
if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['delete_user'])) {
    $user_id = intval($_POST['user_id']);
    $response = api_delete("/api/users/{$user_id}");
    
    if ($response['success']) {
        flash('Client deactivated successfully!', 'success');
    } else {
        flash($response['error'] ?? 'Failed to deactivate client', 'danger');
    }
    header('Location: clients.php');
    exit;
}

require_once 'includes/header.php';

// Fetch users
$users_response = api_get('/api/users');
$users = $users_response['success'] ? array_filter($users_response['users'], function($u) {
    return $u['role'] === 'client';
}) : [];
?>

<div class="d-flex justify-content-between align-items-center mb-4">
    <div>
        <h4 class="mb-1">Clients</h4>
        <p class="text-muted mb-0"><?php echo count($users); ?> client(s) registered</p>
    </div>
    <button class="btn btn-accent" data-bs-toggle="modal" data-bs-target="#addClientModal">
        <i class="bi bi-person-plus me-1"></i>Add Client
    </button>
</div>

<!-- Clients Table -->
<div class="table-card">
    <div class="table-responsive">
        <table class="table">
            <thead>
                <tr>
                    <th>ID</th>
                    <th>Name</th>
                    <th>Username</th>
                    <th>Phone</th>
                    <th>Email</th>
                    <th>ID Number</th>
                    <th>Status</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody>
                <?php if (empty($users)): ?>
                <tr><td colspan="8" class="text-center text-muted py-4">No clients found</td></tr>
                <?php else: ?>
                    <?php foreach ($users as $u): ?>
                    <tr>
                        <td><?php echo $u['id']; ?></td>
                        <td><strong><?php echo htmlspecialchars($u['full_name']); ?></strong></td>
                        <td><code><?php echo htmlspecialchars($u['username']); ?></code></td>
                        <td><?php echo htmlspecialchars($u['phone'] ?? '-'); ?></td>
                        <td><?php echo htmlspecialchars($u['email'] ?? '-'); ?></td>
                        <td><?php echo htmlspecialchars($u['id_number'] ?? '-'); ?></td>
                        <td>
                            <span class="badge <?php echo $u['is_active'] ? 'badge-active' : 'badge-rejected'; ?>">
                                <?php echo $u['is_active'] ? 'Active' : 'Inactive'; ?>
                            </span>
                        </td>
                        <td>
                            <div class="btn-group btn-group-sm">
                                <a href="client-detail.php?id=<?php echo $u['id']; ?>" class="btn btn-outline-secondary" title="View">
                                    <i class="bi bi-eye"></i>
                                </a>
                                <?php if ($u['is_active']): ?>
                                <button class="btn btn-outline-danger" onclick="deleteClient(<?php echo $u['id']; ?>, '<?php echo htmlspecialchars($u['full_name']); ?>')" title="Deactivate">
                                    <i class="bi bi-person-x"></i>
                                </button>
                                <?php endif; ?>
                            </div>
                        </td>
                    </tr>
                    <?php endforeach; ?>
                <?php endif; ?>
            </tbody>
        </table>
    </div>
</div>

<!-- Add Client Modal -->
<div class="modal fade" id="addClientModal" tabindex="-1">
    <div class="modal-dialog">
        <div class="modal-content" style="background: var(--bg-card); border: 1px solid var(--border);">
            <div class="modal-header border-secondary">
                <h5 class="modal-title">Add New Client</h5>
                <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
            </div>
            <form method="POST">
                <div class="modal-body">
                    <div class="mb-3">
                        <label class="form-label">Full Name *</label>
                        <input type="text" name="full_name" class="form-control" required>
                        <small class="text-muted">Username, email & password will be auto-generated</small>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">Phone</label>
                        <input type="text" name="phone" class="form-control" placeholder="+256 7XX XXX XXX">
                    </div>
                    <div class="mb-3">
                        <label class="form-label">Email</label>
                        <input type="email" name="email" class="form-control" placeholder="Auto-generated if empty">
                    </div>
                    <div class="mb-3">
                        <label class="form-label">ID Number</label>
                        <input type="text" name="id_number" class="form-control">
                    </div>
                    <div class="mb-3">
                        <label class="form-label">Address</label>
                        <input type="text" name="address" class="form-control">
                    </div>
                </div>
                <div class="modal-footer border-secondary">
                    <button type="button" class="btn btn-outline-secondary" data-bs-dismiss="modal">Cancel</button>
                    <button type="submit" name="create_client" class="btn btn-accent">Create Client</button>
                </div>
            </form>
        </div>
    </div>
</div>

<!-- Delete Form -->
<form id="deleteClientForm" method="POST" style="display:none">
    <input type="hidden" name="user_id" id="deleteUserId">
    <input type="hidden" name="delete_user" value="1">
</form>

<script>
function deleteClient(id, name) {
    if (confirm('Deactivate client "' + name + '"?')) {
        document.getElementById('deleteUserId').value = id;
        document.getElementById('deleteClientForm').submit();
    }
}
</script>

<?php require_once 'includes/footer.php'; ?>
