<?php
$page_title = 'Users - ' . APP_NAME;
require_once 'config.php';
require_role('admin');
$user = current_user();
$flash = get_flash();

// Handle create user
if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['create_user'])) {
    $response = api_post('/api/users', array(
        'username' => $_POST['username'],
        'email' => $_POST['email'],
        'password' => $_POST['password'],
        'role' => $_POST['role'],
        'full_name' => $_POST['full_name'],
        'phone' => $_POST['phone'] ?? '',
        'address' => $_POST['address'] ?? '',
        'id_number' => $_POST['id_number'] ?? ''
    ));
    
    if ($response['success']) {
        flash('User created successfully!', 'success');
    } else {
        flash($response['error'] ?? 'Failed to create user', 'danger');
    }
    header('Location: users.php');
    exit;
}

// Handle delete user
if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['delete_user'])) {
    $user_id = intval($_POST['user_id']);
    $response = api_delete('/api/users/' . $user_id);
    
    if ($response['success']) {
        flash('User deactivated successfully!', 'success');
    } else {
        flash($response['error'] ?? 'Failed to deactivate user', 'danger');
    }
    header('Location: users.php');
    exit;
}

require_once 'includes/header.php';

// Fetch users
$users_response = api_get('/api/users');
$users = $users_response['success'] ? $users_response['users'] : array();
?>

<div class="d-flex justify-content-between align-items-center mb-4">
    <div>
        <h4 class="mb-1">User Management</h4>
        <p class="text-muted mb-0"><?php echo count($users); ?> user(s) in system</p>
    </div>
    <button class="btn btn-accent" data-bs-toggle="modal" data-bs-target="#addUserModal">
        <i class="bi bi-person-plus me-1"></i>Add User
    </button>
</div>

<!-- Users Table -->
<div class="table-card">
    <div class="table-responsive">
        <table class="table">
            <thead>
                <tr>
                    <th>ID</th>
                    <th>Name</th>
                    <th>Username</th>
                    <th>Email</th>
                    <th>Role</th>
                    <th>Phone</th>
                    <th>Status</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody>
                <?php if (empty($users)): ?>
                <tr><td colspan="8" class="text-center text-muted py-4">No users found</td></tr>
                <?php else: ?>
                    <?php foreach ($users as $u): ?>
                    <tr>
                        <td><?php echo $u['id']; ?></td>
                        <td><strong><?php echo h($u['full_name']); ?></strong></td>
                        <td><code><?php echo h($u['username']); ?></code></td>
                        <td><?php echo h($u['email']); ?></td>
                        <td>
                            <?php
                            $role_badge = 'badge-pending';
                            if ($u['role'] === 'admin') $role_badge = 'badge-rejected';
                            elseif ($u['role'] === 'loan_officer') $role_badge = 'badge-approved';
                            ?>
                            <span class="badge <?php echo $role_badge; ?>"><?php echo ucfirst(str_replace('_', ' ', $u['role'])); ?></span>
                        </td>
                        <td><?php echo h($u['phone'] ?? '-'); ?></td>
                        <td>
                            <span class="badge <?php echo $u['is_active'] ? 'badge-active' : 'badge-rejected'; ?>">
                                <?php echo $u['is_active'] ? 'Active' : 'Inactive'; ?>
                            </span>
                        </td>
                        <td>
                            <?php if ($u['id'] != $user['id'] && $u['is_active']): ?>
                            <button class="btn btn-sm btn-outline-danger" onclick="deleteUser(<?php echo $u['id']; ?>, '<?php echo h($u['full_name']); ?>')" title="Deactivate">
                                <i class="bi bi-person-x"></i>
                            </button>
                            <?php endif; ?>
                        </td>
                    </tr>
                    <?php endforeach; ?>
                <?php endif; ?>
            </tbody>
        </table>
    </div>
</div>

<!-- Add User Modal -->
<div class="modal fade" id="addUserModal" tabindex="-1">
    <div class="modal-dialog">
        <div class="modal-content" style="background: var(--bg-card); border: 1px solid var(--border);">
            <div class="modal-header border-secondary">
                <h5 class="modal-title">Add New User</h5>
                <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
            </div>
            <form method="POST">
                <div class="modal-body">
                    <div class="mb-3">
                        <label class="form-label">Full Name *</label>
                        <input type="text" name="full_name" class="form-control" required>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">Username *</label>
                        <input type="text" name="username" class="form-control" required>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">Email *</label>
                        <input type="email" name="email" class="form-control" required>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">Password *</label>
                        <input type="password" name="password" class="form-control" required minlength="8">
                    </div>
                    <div class="mb-3">
                        <label class="form-label">Role *</label>
                        <select name="role" class="form-control" required>
                            <option value="client">Client</option>
                            <option value="loan_officer">Loan Officer</option>
                            <option value="admin">Admin</option>
                        </select>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">Phone</label>
                        <input type="text" name="phone" class="form-control">
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
                    <button type="submit" name="create_user" class="btn btn-accent">Create User</button>
                </div>
            </form>
        </div>
    </div>
</div>

<!-- Delete Form -->
<form id="deleteUserForm" method="POST" style="display:none">
    <input type="hidden" name="user_id" id="deleteUserId">
    <input type="hidden" name="delete_user" value="1">
</form>

<script>
function deleteUser(id, name) {
    if (confirm('Deactivate user "' + name + '"?')) {
        document.getElementById('deleteUserId').value = id;
        document.getElementById('deleteUserForm').submit();
    }
}
</script>

<?php require_once 'includes/footer.php'; ?>
