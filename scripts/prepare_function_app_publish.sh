#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_DIR="$ROOT_DIR/src"
APP_DIR="$ROOT_DIR/function"
ROOT_REQUIREMENTS_FILE="$ROOT_DIR/requirements.txt"
FUNCTION_REQUIREMENTS_FILE="$APP_DIR/requirements.txt"
PYTHON_PACKAGES_DIR="$APP_DIR/.python_packages/lib/site-packages"

echo "Preparing Function App publish bundle in $APP_DIR"

# Clean generated artifacts from previous publish runs.
rm -rf "$APP_DIR/.python_packages" "$APP_DIR/.pytest_cache"
find "$APP_DIR" -type d -name "__pycache__" -prune -exec rm -rf {} +

# Copy the runtime dependency manifest used by Azure Functions publish.
cp "$ROOT_REQUIREMENTS_FILE" "$FUNCTION_REQUIREMENTS_FILE"

# Sync runtime modules from src/ into the function host folder.
for module_dir in config discovery handlers persistence reporting scheduler; do
  rm -rf "$APP_DIR/$module_dir"
  cp -R "$SRC_DIR/$module_dir" "$APP_DIR/$module_dir"
done

# Build the Azure Functions runtime dependencies into the publish bundle so
# the final zip can be deployed without a remote build step.
mkdir -p "$PYTHON_PACKAGES_DIR"
python3 -m pip install \
  --disable-pip-version-check \
  --requirement "$FUNCTION_REQUIREMENTS_FILE" \
  --target "$PYTHON_PACKAGES_DIR"

echo "Function App publish bundle ready."
