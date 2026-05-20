"""
Vercel Serverless Entry Point for LendFlow

This file adapts the Flask app to run on Vercel's Python runtime.
It handles:
  - Importing the Flask app from the root app.py (avoiding app/ package conflicts)
  - Detecting Vercel environment and adjusting DB path
  - WARNING: Without DATABASE_URL, SQLite data is LOST on every cold start
"""

import sys
import os
import importlib.util

# ── Detect Vercel environment ──
IS_VERCEL = os.environ.get('VERCEL', '') == '1'
HAS_DATABASE_URL = os.environ.get('DATABASE_URL', '').startswith('postgres')

if IS_VERCEL and not HAS_DATABASE_URL:
    # CRITICAL WARNING: SQLite on Vercel is NOT persistent.
    # All data (users, loans, repayments) is wiped on every serverless cold start.
    # Set DATABASE_URL environment variable to a PostgreSQL connection string.
    import warnings
    warnings.warn(
        "CRITICAL: Running on Vercel without DATABASE_URL. "
        "SQLite is stored in /tmp and will be LOST on every cold start. "
        "Set DATABASE_URL to a PostgreSQL connection string for persistence.",
        RuntimeWarning, stacklevel=1
    )
    os.environ.setdefault('DATABASE_PATH', '/tmp/lendflow.db')

# ── Load the Flask app from root app.py ──
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

spec = importlib.util.spec_from_file_location(
    "lendflow_app",
    os.path.join(project_root, "app.py")
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

# Expose the Flask app for Vercel
app = mod.app

# ── Seed database on cold start (Vercel SQLite / fresh PostgreSQL) ──
# ONLY seed if the database is truly empty (no users AND no loans)
# This prevents re-seeding over user-created data
if IS_VERCEL or HAS_DATABASE_URL:
    try:
        from app.database import get_db
        conn = get_db()
        user_count = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        loan_count = conn.execute('SELECT COUNT(*) FROM loans').fetchone()[0]
        conn.close()
        # Only seed if BOTH users and loans are empty (fresh database)
        if user_count == 0 and loan_count == 0:
            import seed
            seed.seed()
    except Exception:
        pass  # Silently skip if seeding fails
