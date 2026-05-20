"""
Database adapter for LendFlow — unified SQLite + PostgreSQL support.

Detects database type from DATABASE_URL env var:
  - If DATABASE_URL starts with postgres:// or postgresql:// → use psycopg2
  - Otherwise → use SQLite (default, local dev)

Wraps psycopg2 connections to present the same interface as sqlite3:
  - dict-like row access (row['column_name'] or row[0])
  - ? placeholders (auto-converted to %s)
  - .rowcount, .lastrowid compatibility
  - date('now') → CURRENT_DATE translation
  - AUTOINCREMENT → SERIAL translation
  - PRAGMA statements gracefully ignored for PostgreSQL
"""

import os
import re
import sqlite3

# ── Detect database type ────────────────────────────────────────
DATABASE_URL = os.environ.get('DATABASE_URL', '')
IS_POSTGRES = DATABASE_URL.startswith('postgres://') or DATABASE_URL.startswith('postgresql://')
DB_TYPE = 'postgres' if IS_POSTGRES else 'sqlite'

# Lazy import psycopg2 only when needed (avoids crash on Vercel if not installed)
_psycopg2 = None
_psycopg2_errors = None
_psycopg2_available = None  # None = not checked yet, True/False = result

def _ensure_psycopg2():
    """Lazy-load psycopg2. Returns (psycopg2, psycopg2.errors) or raises ImportError."""
    global _psycopg2, _psycopg2_errors, _psycopg2_available
    
    if _psycopg2_available is False:
        raise ImportError("psycopg2 is not available")
    
    if _psycopg2 is None:
        try:
            import psycopg2 as _pg
            import psycopg2.errors as _pg_err
            _psycopg2 = _pg
            _psycopg2_errors = _pg_err
            _psycopg2_available = True
            print("✅ psycopg2 loaded successfully")
        except Exception as e:
            print(f"⚠️  psycopg2 import failed: {e}")
            _psycopg2_available = False
            raise
    return _psycopg2, _psycopg2_errors

# ── Database path (SQLite only) ─────────────────────────────────
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_DB = os.path.join(_PROJECT_ROOT, 'data', 'lendflow.db')
DB_PATH = os.environ.get('DATABASE_PATH', _DEFAULT_DB)

# Regex for date('now', '±N days') translation
_DATE_MODIFIER_RE = re.compile(r"date\('now',\s*'([-+])(\d+)\s+days'\)")


# ═══════════════════════════════════════════════════════════════
#  Row wrapper — dict + index access (sqlite3.Row compatible)
# ═══════════════════════════════════════════════════════════════
class PgRow(dict):
    """A row that behaves like sqlite3.Row — accessible by both key and index."""
    def __init__(self, cursor, row_tuple):
        self._keys = [desc[0] for desc in cursor.description] if cursor.description else []
        dict.__init__(self, zip(self._keys, row_tuple))
        self._row = row_tuple

    def __getitem__(self, key):
        if isinstance(key, (int, slice)):
            return self._row[key]
        return dict.__getitem__(self, key)

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(f"'PgRow' object has no attribute '{name}'")

    def keys(self):
        return self._keys


# ═══════════════════════════════════════════════════════════════
#  Cursor wrapper — mimics sqlite3.Cursor
# ═══════════════════════════════════════════════════════════════
class PgCursor:
    """Wrapper for psycopg2 cursor that mimics sqlite3 Cursor interface."""
    def __init__(self, cursor):
        self._cursor = cursor
        self.rowcount = -1

    def execute(self, sql, params=None):
        if params is not None:
            # Convert ? placeholders → %s (psycopg2 uses %s)
            sql = sql.replace('?', '%s')
            # Ensure params is a sequence
            if not isinstance(params, (list, tuple)):
                params = (params,)
            self._cursor.execute(sql, params)
        else:
            self._cursor.execute(sql)
        self.rowcount = self._cursor.rowcount
        return self

    def executemany(self, sql, seq_of_params):
        sql = sql.replace('?', '%s')
        self._cursor.executemany(sql, seq_of_params)
        self.rowcount = self._cursor.rowcount
        return self

    def fetchone(self):
        row = self._cursor.fetchone()
        if row is None:
            return None
        return PgRow(self._cursor, row)

    def fetchall(self):
        rows = self._cursor.fetchall()
        return [PgRow(self._cursor, row) for row in rows]

    @property
    def lastrowid(self):
        """Return the last inserted row ID.
        
        psycopg2's .lastrowid returns OID (0 for modern PG without OIDs).
        Instead, we expect INSERT statements to use RETURNING id and 
        call fetchone()[0]. If no results, fall back to the cursor's value.
        """
        if self._cursor.description:
            result = self._cursor.fetchone()
            if result:
                return result[0]
        return self._cursor.lastrowid or 0

    @property
    def description(self):
        return self._cursor.description

    def close(self):
        return self._cursor.close()

    def __iter__(self):
        for row in self._cursor:
            yield PgRow(self._cursor, row)


# ═══════════════════════════════════════════════════════════════
#  Connection wrapper — mimics sqlite3.Connection
# ═══════════════════════════════════════════════════════════════
class PgConnection:
    """Wrapper for psycopg2 connection that mimics sqlite3.Connection."""
    def __init__(self, conn):
        self._conn = conn
        # Don't autocommit — match sqlite3 behavior
        self._conn.autocommit = False

    def execute(self, sql, params=None):
        """Execute and return a cursor (like sqlite3.Connection.execute)."""
        cursor = self._conn.cursor()
        return PgCursor(cursor).execute(sql, params)

    def executemany(self, sql, seq_of_params):
        cursor = self._conn.cursor()
        return PgCursor(cursor).executemany(sql, seq_of_params)

    def commit(self):
        return self._conn.commit()

    def rollback(self):
        return self._conn.rollback()

    def close(self):
        return self._conn.close()

    def cursor(self):
        return PgCursor(self._conn.cursor())


# ═══════════════════════════════════════════════════════════════
#  Dummy cursor for PRAGMA / no-op statements
# ═══════════════════════════════════════════════════════════════
class _DummyCursor:
    """Returned for PRAGMA statements on PostgreSQL."""
    rowcount = -1
    description = None
    lastrowid = 0

    def execute(self, sql, params=None):
        return self

    def fetchone(self):
        return None

    def fetchall(self):
        return []

    def close(self):
        pass


# ═══════════════════════════════════════════════════════════════
#  SQL translation helpers
# ═══════════════════════════════════════════════════════════════
def translate_ddl(sql):
    """Translate SQLite-specific DDL to PostgreSQL-compatible DDL."""
    if not IS_POSTGRES:
        return sql
    # AUTOINCREMENT → SERIAL
    sql = sql.replace('INTEGER PRIMARY KEY AUTOINCREMENT', 'SERIAL PRIMARY KEY')
    return sql


def translate_date(sql):
    """Translate SQLite date('now') to PostgreSQL CURRENT_DATE.
    Handles modifiers like date('now', '-30 days').
    """
    if not IS_POSTGRES:
        return sql
    # date('now', '-30 days') → CURRENT_DATE - INTERVAL '30 days'
    def _replace_date_modifier(m):
        sign = m.group(1)  # '+' or '-'
        days = m.group(2)  # number
        op = '-' if sign == '-' else '+'
        return f"CURRENT_DATE {op} INTERVAL '{days} days'"
    
    sql = _DATE_MODIFIER_RE.sub(_replace_date_modifier, sql)
    # date('now') → CURRENT_DATE (must be after modifier replacement)
    sql = sql.replace("date('now')", 'CURRENT_DATE')
    return sql


def is_pragma(sql):
    """Check if SQL is a PRAGMA statement (SQLite-only)."""
    stripped = sql.strip().upper()
    return stripped.startswith('PRAGMA ')


# ═══════════════════════════════════════════════════════════════
#  get_db() — unified connection factory
# ═══════════════════════════════════════════════════════════════
def get_db():
    """Get a database connection — SQLite (local) or PostgreSQL (production).
    
    Returns a connection that supports the standard interface:
      - conn.execute(sql, params) → cursor
      - cursor.fetchone() / fetchall()
      - cursor.rowcount / lastrowid
      - row['column'] / row[0] access
    """
    if IS_POSTGRES:
        try:
            pg, pg_err = _ensure_psycopg2()
            conn = pg.connect(DATABASE_URL)
            conn.autocommit = False
            return PgConnection(conn)
        except Exception as e:
            print(f"⚠️  PostgreSQL connection failed: {e}")
            print("🔄 Falling back to SQLite for this request")
            # Fall back to SQLite if PostgreSQL fails
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            return conn
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn


# ═══════════════════════════════════════════════════════════════
#  init_db() — same interface as database.py expected
# ═══════════════════════════════════════════════════════════════
def init_db():
    """Create data directories if needed (SQLite)."""
    if IS_POSTGRES:
        return  # PostgreSQL handles this externally
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


# ═══════════════════════════════════════════════════════════════
#  Export symbols used by database.py
# ═══════════════════════════════════════════════════════════════
IntegrityError = sqlite3.IntegrityError

def _get_integrity_error():
    """Get the appropriate IntegrityError class (lazy for psycopg2)."""
    if IS_POSTGRES and _psycopg2_available:
        try:
            _, pg_err = _ensure_psycopg2()
            return pg_err.IntegrityError
        except:
            pass
    return sqlite3.IntegrityError

Row = sqlite3.Row  # fallback — we use our own wrappers for PG
