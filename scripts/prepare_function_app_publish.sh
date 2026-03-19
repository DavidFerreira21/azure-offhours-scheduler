#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_DIR="$ROOT_DIR/src"
APP_DIR="$ROOT_DIR/function"
ROOT_REQUIREMENTS_FILE="$ROOT_DIR/requirements.txt"
FUNCTION_REQUIREMENTS_FILE="$APP_DIR/requirements.txt"

echo "Preparing Function App publish bundle in $APP_DIR"

# Clean generated artifacts from previous publish runs.
rm -rf "$APP_DIR/.python_packages" "$APP_DIR/.pytest_cache"

# Copy the runtime dependency manifest used by Azure Functions publish.
cp "$ROOT_REQUIREMENTS_FILE" "$FUNCTION_REQUIREMENTS_FILE"

# Sync runtime modules from src/ into the function host folder.
for module_dir in config discovery handlers persistence reporting scheduler; do
  rm -rf "$APP_DIR/$module_dir"
  cp -R "$SRC_DIR/$module_dir" "$APP_DIR/$module_dir"
  find "$APP_DIR/$module_dir" -type d -name "__pycache__" -prune -exec rm -rf {} +
done

echo "Function App publish bundle ready."
