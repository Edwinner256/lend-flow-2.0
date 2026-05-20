"""
Minimal Vercel test - no Flask, no database
"""
import os
import sys

def handler(request):
    return {
        'statusCode': 200,
        'body': f'Python {sys.version} - VERCEL={os.environ.get("VERCEL", "not set")} - DB_URL={bool(os.environ.get("DATABASE_URL", ""))}'
    }
