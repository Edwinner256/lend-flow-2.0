#!/bin/bash
# LendFlow — Quick Deploy Zip Script
# Creates a clean zip ready for GoDaddy upload

set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_NAME="LendFlow"
OUTPUT_DIR="$HOME/Desktop"
ZIP_FILE="$OUTPUT_DIR/${PROJECT_NAME}-deploy.zip"

echo ""
echo "=========================================="
echo "  LendFlow — Building Deployment Package"
echo "=========================================="
echo ""

# Run production prep first
echo "→ Running production prep..."
cd "$PROJECT_DIR"
python3 production_config.py

echo ""
echo "→ Creating clean zip (excluding dev files)..."

cd "$HOME/Downloads"

zip -r "$ZIP_FILE" "$PROJECT_NAME/" \
  -x "*.pyc" \
  -x "*__pycache__/*" \
  -x "*.pyo" \
  -x ".git/*" \
  -x ".DS_Store" \
  -x "*/.DS_Store" \
  -x "*.db" \
  -x "*.sqlite" \
  -x "static/uploads/*" \
  -x "!.gitkeep"

echo ""
echo "=========================================="
echo "  ✓ Deployment package ready!"
echo "=========================================="
echo ""
echo "  File: $ZIP_FILE"
echo "  Size: $(du -h "$ZIP_FILE" | cut -f1)"
echo ""
echo "  Next: Upload to GoDaddy cPanel File Manager"
echo "        and follow DEPLOYMENT.md"
echo ""
