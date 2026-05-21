<?php
$page_title = 'Repayments - ' . APP_NAME;
require_once 'config.php';
require_login();
$user = current_user();
$flash = get_flash();

// Handle record payment (admin/officer)
if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['record_payment'])) {
    $loan_id = intval($_POST['loan_id']);
    $response = api_post('/api/loans/' . $loan_id . '/repayments', array(
        'amount' => floatval($_POST['amount']),
        'payment_method' => $_POST['payment_method'] ?? 'cash',
        'notes' => $_POST['notes'] ?? '',
        'payment_type' => $_POST['payment_type'] ?? 'principal'
    ));
    
    if ($response['success']) {
        flash('Payment recorded! Ref: ' . $response['reference'], 'success');
    } else {
        flash($response['error'] ?? 'Failed to record payment', 'danger');
    }
    header('Location: repayments.php');
    exit;
}

// Handle delete repayment (admin only)
if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['delete_repayment'])) {
    $repayment_id = intval($_POST['repayment_id']);
    $response = api_delete('/api/repayments/' . $repayment_id);
    
    if ($response['success']) {
        flash('Repayment deleted and loan balance recalculated.', 'success');
    } else {
        flash($response['error'] ?? 'Failed to delete repayment', 'danger');
    }
    header('Location: repayments.php');
    exit;
}

require_once 'includes/header.php';

// Fetch repayments
$repayments_response = api_get('/api/repayments');
$repayments = $repayments_response['success'] ? $repayments_response['repayments'] : array();

// Fetch loans for payment form
$loans_response = api_get('/api/loans');
$loans = $loans_response['success'] ? $loans_response['loans'] : array();
?>

<div class="d-flex justify-content-between align-items-center mb-4">
    <div>
        <h4 class="mb-1">Repayments</h4>
        <p class="text-muted mb-0"><?php echo count($repayments); ?> payment(s) recorded</p>
    </div>
    <?php if (in_array($user['role'], array('admin', 'loan_officer'))): ?>
    <button class="btn btn-accent" data-bs-toggle="modal" data-bs-target="#recordPaymentModal">
        <i class="bi bi-plus-lg me-1"></i>Record Payment
    </button>
    <?php endif; ?>
</div>

<!-- Repayments Table -->
<div class="table-card">
    <div class="table-responsive">
        <table class="table">
            <thead>
                <tr>
                    <th>Date</th>
                    <th>Loan #</th>
                    <th>Client</th>
                    <th>Amount</th>
                    <th>Type</th>
                    <th>Method</th>
                    <th>Reference</th>
                    <th>Notes</th>
                    <?php if ($user['role'] === 'admin'): ?><th>Actions</th><?php endif; ?>
                </tr>
            </thead>
            <tbody>
                <?php if (empty($repayments)): ?>
                <tr><td colspan="<?php echo $user['role'] === 'admin' ? 9 : 8; ?>" class="text-center text-muted py-4">No repayments found</td></tr>
                <?php else: ?>
                    <?php foreach ($repayments as $r): ?>
                    <tr>
                        <td><?php echo format_date($r['created_at']); ?></td>
                        <td><strong><?php echo h($r['loan_number']); ?></strong></td>
                        <td><?php echo h($r['client_name']); ?></td>
                        <td><strong><?php echo format_money($r['amount']); ?></strong></td>
                        <td><?php echo ucfirst($r['payment_type'] ?? 'principal'); ?></td>
                        <td><?php echo ucfirst($r['payment_method']); ?></td>
                        <td><code><?php echo h($r['reference'] ?? '-'); ?></code></td>
                        <td><?php echo h($r['notes'] ?? '-'); ?></td>
                        <?php if ($user['role'] === 'admin'): ?>
                        <td>
                            <button class="btn btn-sm btn-outline-danger" onclick="deleteRepayment(<?php echo $r['id']; ?>)" title="Delete">
                                <i class="bi bi-trash"></i>
                            </button>
                        </td>
                        <?php endif; ?>
                    </tr>
                    <?php endforeach; ?>
                <?php endif; ?>
            </tbody>
        </table>
    </div>
</div>

<!-- Record Payment Modal -->
<?php if (in_array($user['role'], array('admin', 'loan_officer'))): ?>
<div class="modal fade" id="recordPaymentModal" tabindex="-1">
    <div class="modal-dialog">
        <div class="modal-content" style="background: var(--bg-card); border: 1px solid var(--border);">
            <div class="modal-header border-secondary">
                <h5 class="modal-title">Record Payment</h5>
                <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
            </div>
            <form method="POST">
                <div class="modal-body">
                    <div class="mb-3">
                        <label class="form-label">Select Loan *</label>
                        <select name="loan_id" class="form-control" required>
                            <option value="">-- Choose Loan --</option>
                            <?php foreach ($loans as $loan): ?>
                            <option value="<?php echo $loan['id']; ?>">
                                <?php echo h($loan['loan_number']); ?> - <?php echo h($loan['client_name'] ?? ''); ?> (Balance: <?php echo format_money($loan['balance']); ?>)
                            </option>
                            <?php endforeach; ?>
                        </select>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">Amount (UGX) *</label>
                        <input type="number" name="amount" class="form-control" required min="1">
                    </div>
                    <div class="row">
                        <div class="col-6 mb-3">
                            <label class="form-label">Payment Type</label>
                            <select name="payment_type" class="form-control">
                                <option value="principal">Principal</option>
                                <option value="fine">Fine</option>
                            </select>
                        </div>
                        <div class="col-6 mb-3">
                            <label class="form-label">Method</label>
                            <select name="payment_method" class="form-control">
                                <option value="cash">Cash</option>
                                <option value="mtn">MTN MoMo</option>
                                <option value="airtel">Airtel Money</option>
                                <option value="bank">Bank Transfer</option>
                                <option value="cheque">Cheque</option>
                            </select>
                        </div>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">Notes</label>
                        <textarea name="notes" class="form-control" rows="2" placeholder="Optional notes..."></textarea>
                    </div>
                    <small class="text-muted">Reference ID will be auto-generated</small>
                </div>
                <div class="modal-footer border-secondary">
                    <button type="button" class="btn btn-outline-secondary" data-bs-dismiss="modal">Cancel</button>
                    <button type="submit" name="record_payment" class="btn btn-accent">Record Payment</button>
                </div>
            </form>
        </div>
    </div>
</div>
<?php endif; ?>

<!-- Delete Form -->
<form id="deleteRepaymentForm" method="POST" style="display:none">
    <input type="hidden" name="repayment_id" id="deleteRepaymentId">
    <input type="hidden" name="delete_repayment" value="1">
</form>

<script>
function deleteRepayment(id) {
    if (confirm('Delete this repayment? Loan balance will be recalculated.')) {
        document.getElementById('deleteRepaymentId').value = id;
        document.getElementById('deleteRepaymentForm').submit();
    }
}
</script>

<?php require_once 'includes/footer.php'; ?>
