"""
Vercel Serverless Entry Point for LendFlow

This file adapts the Flask app to run on Vercel's Python runtime.
It handles:
  - Importing the Flask app from the root app.py (avoiding app/ package conflicts)
  - Detecting Vercel environment and adjusting DB path
"""

import sys
import os
import importlib.util

# ── Detect Vercel environment ──
IS_VERCEL = os.environ.get('VERCEL', '') == '1'

if IS_VERCEL:
    # On Vercel, use /tmp for SQLite (writable but NOT persistent across cold starts)
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

# ── Seed database on cold start for Vercel ──
if IS_VERCEL:
    try:
        # Check if DB is empty (fresh cold start)
        from app.database import get_db
        conn = get_db()
        count = conn.execute('SELECT COUNT(*) FROM loans').fetchone()[0]
        conn.close()
        if count == 0:
            # Auto-seed demo data
            import seed
            seed.seed()
    except Exception:
        pass  # Silently skip if seeding fails
