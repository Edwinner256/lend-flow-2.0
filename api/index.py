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

# ── NO AUTO-SEEDING ──
# Demo data seeding is permanently disabled.
# The system starts with a clean database. Admin must create users manually.
