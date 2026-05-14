"""
GoDaddy cPanel WSGI Entry Point
This file tells Apache/mod_passenger how to run the Flask app.
"""

import sys
import os

# Add the app directory to Python path
# GoDaddy sets this automatically, but we ensure it's correct
app_path = os.path.dirname(os.path.abspath(__file__))
if app_path not in sys.path:
    sys.path.insert(0, app_path)

# Set environment to production
os.environ['FLASK_ENV'] = 'production'

# Import the Flask app — GoDaddy expects a variable named "application"
from app import app as application
