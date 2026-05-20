"""
Vercel Serverless Entry Point for LendFlow

This file adapts the Flask app to run on Vercel's Python runtime.
It handles:
  - Importing the Flask app from the root app.py (avoiding app/ package conflicts)
  - Detecting Vercel environment and adjusting DB path
  - PostgreSQL persistence via DATABASE_URL (Neon DB)
  - WARNING: Without DATABASE_URL, SQLite data is LOST on every cold start
"""

import sys
import os
import importlib.util
import traceback

# ── Detect Vercel environment ──
IS_VERCEL = os.environ.get('VERCEL', '') == '1'
HAS_DATABASE_URL = os.environ.get('DATABASE_URL', '').startswith('postgres')

print(f"🔍 Vercel env: VERCEL={os.environ.get('VERCEL', 'not set')}")
print(f"🔍 DATABASE_URL present: {bool(HAS_DATABASE_URL)}")
if HAS_DATABASE_URL:
    print(f"🔍 DATABASE_URL starts with: {os.environ.get('DATABASE_URL', '')[:30]}...")

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

try:
    spec = importlib.util.spec_from_file_location(
        "lendflow_app",
        os.path.join(project_root, "app.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    print("✅ app.py loaded successfully")
except Exception as e:
    print(f"❌ Failed to load app.py: {e}")
    traceback.print_exc()
    raise

# Expose the Flask app for Vercel
app = mod.app

# ── Ensure Admin User Exists ──
# Creates or verifies the superuser admin account on every startup
try:
    from app.database import ensure_admin_exists
    ensure_admin_exists(username='admin', password='admin123?Vaulta')
    print("✅ Admin setup complete")
except Exception as e:
    print(f"⚠️  Admin setup failed: {e}")
    traceback.print_exc()
