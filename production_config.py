"""
Production Configuration for LendFlow
Apply these changes before deploying to GoDaddy.

USAGE:
  1. Copy this file to your server as production_config.py
  2. Run: python3 production_config.py
  3. It will patch app.py and sms_service.py for production
"""

import os
import secrets

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

def generate_secret_key():
    """Generate a cryptographically secure secret key."""
    return secrets.token_hex(32)

def patch_app_py():
    """Update app.py for production settings."""
    app_path = os.path.join(PROJECT_DIR, 'app.py')
    
    with open(app_path, 'r') as f:
        content = f.read()
    
    # Turn off debug mode
    content = content.replace(
        "app.run(debug=True, host='0.0.0.0', port=5000)",
        "app.run(debug=False, host='127.0.0.1', port=5000)"
    )
    
    with open(app_path, 'w') as f:
        f.write(content)
    
    print("✓ app.py — debug mode disabled")

def patch_sms_service():
    """Turn off SMS mock mode for production."""
    sms_path = os.path.join(PROJECT_DIR, 'app', 'sms_service.py')
    
    with open(sms_path, 'r') as f:
        content = f.read()
    
    content = content.replace(
        'SMS_MOCK_MODE = True',
        'SMS_MOCK_MODE = False'
    )
    
    with open(sms_path, 'w') as f:
        f.write(content)
    
    print("✓ sms_service.py — mock mode disabled")

def create_env_file():
    """Create a .env file with production values."""
    env_path = os.path.join(PROJECT_DIR, '.env')
    secret_key = generate_secret_key()
    
    with open(env_path, 'w') as f:
        f.write(f"""# LendFlow Production Environment Variables
# DO NOT commit this file to version control

SECRET_KEY={secret_key}
FLASK_ENV=production
SMS_MOCK_MODE=False
""")
    
    print(f"✓ .env — created with secure SECRET_KEY")
    print(f"  Your secret key: {secret_key[:16]}...")

def create_gitignore():
    """Create .gitignore to protect sensitive files."""
    gitignore_path = os.path.join(PROJECT_DIR, '.gitignore')
    
    with open(gitignore_path, 'w') as f:
        f.write("""# Database
*.db
*.sqlite

# Environment
.env
.env.local

# Python
__pycache__/
*.pyc
*.pyo
*.egg-info/
dist/
build/
venv/
.venv/

# IDE
.vscode/
.idea/
*.swp

# OS
.DS_Store
Thumbs.db

# Uploads (keep folder, ignore contents)
static/uploads/*
!static/uploads/.gitkeep

# Logs
*.log
""")
    
    print("✓ .gitignore — created")

def create_gitkeep():
    """Ensure uploads folder exists but stays empty in git."""
    uploads_dir = os.path.join(PROJECT_DIR, 'static', 'uploads')
    os.makedirs(uploads_dir, exist_ok=True)
    
    gitkeep = os.path.join(uploads_dir, '.gitkeep')
    if not os.path.exists(gitkeep):
        open(gitkeep, 'w').close()
    
    print("✓ static/uploads/.gitkeep — created")

if __name__ == '__main__':
    print("\n" + "=" * 50)
    print("  LendFlow — Production Prep")
    print("=" * 50 + "\n")
    
    patch_app_py()
    patch_sms_service()
    create_env_file()
    create_gitignore()
    create_gitkeep()
    
    print("\n" + "=" * 50)
    print("  Ready for deployment!")
    print("=" * 50)
    print("""
Next steps:
  1. Review the changes above
  2. Zip the project: zip -r lendflow.zip LendFlow/ -x '*.pyc' '__pycache__/*' '.git/*'
  3. Upload to GoDaddy cPanel File Manager
  4. Follow DEPLOYMENT.md for cPanel setup
""")
