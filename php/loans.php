<?php
$page_title = 'Loans - ' . APP_NAME;
require_once 'config.php';
require_login();

// Handle loan application (client only)
if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['apply_loan'])) {
    $response = api_post('/api/loans', [
        'principal' => floatval($_POST['principal']),
        'interest_rate' => floatval($_POST['interest_rate']),
        'interest_type' => $_POST['interest_type'] ?? 'flat',
        'payment_schedule' => $_POST['payment_schedule'] ?? 'monthly',
        'purpose' => $_POST['purpose'] ?? '',
        'duration_months' => intval($_POST['duration_months'])
    ]);
    
    if ($response['success']) {
        flash('Loan application submitted successfully!', 'success');
    } else {
        flash($response['error'] ?? 'Failed to submit loan application', 'danger');
    }
    header('Location: loans.php');
    exit;
}

// Handle loan approval/rejection (admin/officer)
if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['action'])) {
    $loan_id = intval($_POST['loan_id']);
    if ($_POST['action'] === 'approve') {
        $response = api_post("/api/loans/{$loan_id}/approve", ['notes' => $_POST['notes'] ?? '']);
    } elseif ($_POST['action'] === 'reject') {
        $response = api_post("/api/loans/{$loan_id}/reject", ['reason' => $_POST['reason'] ?? '']);
    } elseif ($_POST['action'] === 'delete' && current_user()['role'] === 'admin') {
        $response = api_delete("/api/loans/{$loan_id}");
    }
    
    if (isset($response) && $response['success']) {
        flash('Loan updated successfully!', 'success');
    } else {
        flash($response['error'] ?? 'Action failed', 'danger');
    }
    header('Location: loans.php');
    exit;
}

require_once 'includes/header.php';

// Fetch loans
$loans_response = api_get('/api/loans');
$loans = $loans_response['success'] ? $loans_response['loans'] : [];
$user = current_user();
?>

<div class="d-flex justify-content-between align-items-center mb-4">
    <div>
        <h4 class="mb-1">Loans</h4>
        <p class="text-muted mb-0">Manage loan applications and tracking</p>
    </div>
    <?php if ($user['role'] === 'client'): ?>
    <button class="btn btn-accent" data-bs-toggle="modal" data-bs-target="#applyLoanModal">
        <i class="bi bi-plus-lg me-1"></i>Apply for Loan
    </button>
    <?php endif; ?>
</div>

<!-- Loans Table -->
<div class="table-card">
    <div class="table-responsive">
        <table class="table">
            <thead>
                <tr>
                    <th>Loan #</th>
                    <?php if ($user['role'] !== 'client'): ?><th>Client</th><?php endif; ?>
                    <th>Principal</th>
                    <th>Interest</th>
                    <th>Total</th>
                    <th>Paid</th>
                    <th>Balance</th>
                    <th>Status</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody>
                <?php if (empty($loans)): ?>
                <tr><td colspan="<?php echo $user['role'] === 'client' ? 8 : 9; ?>" class="text-center text-muted py-4">No loans found</td></tr>
                <?php else: ?>
                    <?php foreach ($loans as $loan): ?>
                    <tr>
                        <td><strong><?php echo htmlspecialchars($loan['loan_number']); ?></strong></td>
                        <?php if ($user['role'] !== 'client'): ?>
                        <td><?php echo htmlspecialchars($loan['client_name'] ?? '-'); ?></td>
                        <?php endif; ?>
                        <td><?php echo format_money($loan['principal']); ?></td>
                        <td><?php echo $loan['interest_rate']; ?>% (<?php echo $loan['interest_type']; ?>)</td>
                        <td><?php echo format_money($loan['total_amount']); ?></td>
                        <td><?php echo format_money($loan['amount_paid']); ?></td>
                        <td><strong><?php echo format_money($loan['balance']); ?></strong></td>
                        <td>
                            <?php
                            $status = strtolower($loan['status'] ?? 'pending');
                            $badge_class = 'badge-pending';
                            if ($status === 'active') $badge_class = 'badge-active';
                            elseif ($status === 'approved') $badge_class = 'badge-approved';
                            elseif ($status === 'rejected') $badge_class = 'badge-rejected';
                            elseif ($status === 'paid') $badge_class = 'badge-paid';
                            elseif ($status === 'overdue') $badge_class = 'badge-overdue';
                            ?>
                            <span class="badge <?php echo $badge_class; ?>"><?php echo ucfirst($status); ?></span>
                        </td>
                        <td>
                            <div class="btn-group btn-group-sm">
                                <a href="loan-detail.php?id=<?php echo $loan['id']; ?>" class="btn btn-outline-secondary" title="View">
                                    <i class="bi bi-eye"></i>
                                </a>
                                <?php if (in_array($user['role'], ['admin', 'loan_officer']) && $status === 'pending'): ?>
                                <button class="btn btn-outline-success" onclick="approveLoan(<?php echo $loan['id']; ?>)" title="Approve">
                                    <i class="bi bi-check-lg"></i>
                                </button>
                                <button class="btn btn-outline-danger" onclick="rejectLoan(<?php echo $loan['id']; ?>)" title="Reject">
                                    <i class="bi bi-x-lg"></i>
                                </button>
                                <?php endif; ?>
                                <?php if ($user['role'] === 'admin'): ?>
                                <button class="btn btn-outline-danger" onclick="deleteLoan(<?php echo $loan['id']; ?>)" title="Delete">
                                    <i class="bi bi-trash"></i>
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

<!-- Apply Loan Modal (Client) -->
<?php if ($user['role'] === 'client'): ?>
<div class="modal fade" id="applyLoanModal" tabindex="-1">
    <div class="modal-dialog">
        <div class="modal-content" style="background: var(--bg-card); border: 1px solid var(--border);">
            <div class="modal-header border-secondary">
                <h5 class="modal-title">Apply for Loan</h5>
                <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
            </div>
            <form method="POST">
                <div class="modal-body">
                    <div class="mb-3">
                        <label class="form-label">Principal Amount (UGX)</label>
                        <input type="number" name="principal" class="form-control" required min="1000">
                    </div>
                    <div class="row">
                        <div class="col-6 mb-3">
                            <label class="form-label">Interest Rate (%)</label>
                            <input type="number" name="interest_rate" class="form-control" value="10" step="0.1" required>
                        </div>
                        <div class="col-6 mb-3">
                            <label class="form-label">Duration (Months)</label>
                            <input type="number" name="duration_months" class="form-control" value="1" min="1" max="60" required>
                        </div>
                    </div>
                    <div class="row">
                        <div class="col-6 mb-3">
                            <label class="form-label">Interest Type</label>
                            <select name="interest_type" class="form-control">
                                <option value="flat">Flat</option>
                                <option value="reducing">Reducing</option>
                            </select>
                        </div>
                        <div class="col-6 mb-3">
                            <label class="form-label">Payment Schedule</label>
                            <select name="payment_schedule" class="form-control">
                                <option value="monthly">Monthly</option>
                                <option value="weekly">Weekly</option>
                                <option value="daily">Daily</option>
                            </select>
                        </div>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">Purpose</label>
                        <textarea name="purpose" class="form-control" rows="2" placeholder="What is the loan for?"></textarea>
                    </div>
                </div>
                <div class="modal-footer border-secondary">
                    <button type="button" class="btn btn-outline-secondary" data-bs-dismiss="modal">Cancel</button>
                    <button type="submit" name="apply_loan" class="btn btn-accent">Submit Application</button>
                </div>
            </form>
        </div>
    </div>
</div>
<?php endif; ?>

<!-- Hidden forms for actions -->
<form id="approveForm" method="POST" style="display:none">
    <input type="hidden" name="loan_id" id="approveLoanId">
    <input type="hidden" name="action" value="approve">
    <input type="hidden" name="notes" value="">
</form>
<form id="rejectForm" method="POST" style="display:none">
    <input type="hidden" name="loan_id" id="rejectLoanId">
    <input type="hidden" name="action" value="reject">
    <input type="hidden" name="reason" value="">
</form>
<form id="deleteForm" method="POST" style="display:none">
    <input type="hidden" name="loan_id" id="deleteLoanId">
    <input type="hidden" name="action" value="delete">
</form>

<script>
function approveLoan(id) {
    if (confirm('Approve this loan?')) {
        document.getElementById('approveLoanId').value = id;
        document.getElementById('approveForm').submit();
    }
}
function rejectLoan(id) {
    const reason = prompt('Reason for rejection:');
    if (reason) {
        document.getElementById('rejectLoanId').value = id;
        document.querySelector('#rejectForm input[name="reason"]').value = reason;
        document.getElementById('rejectForm').submit();
    }
}
function deleteLoan(id) {
    if (confirm('Delete this loan? This cannot be undone.')) {
        document.getElementById('deleteLoanId').value = id;
        document.getElementById('deleteForm').submit();
    }
}
</script>

<?php require_once 'includes/footer.php'; ?>
