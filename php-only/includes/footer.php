        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/flatpickr"></script>
    <script>
        // Close sidebar on mobile when clicking outside
        document.addEventListener('click', function(e) {
            var sidebar = document.getElementById('sidebar');
            if (window.innerWidth < 992 && sidebar.classList.contains('show')) {
                if (!sidebar.contains(e.target) && !e.target.closest('.btn-outline-secondary')) {
                    sidebar.classList.remove('show');
                }
            }
        });
    </script>
</body>
</html>
