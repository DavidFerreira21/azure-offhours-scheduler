#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="$ROOT_DIR/cmd/function_app"

echo "Preparing Function App publish bundle in $APP_DIR"

# Clean generated artifacts from previous publish runs.
rm -rf "$APP_DIR/.python_packages" "$APP_DIR/.pytest_cache"

# Sync runtime modules from repository root into function app folder.
for module_dir in config discovery handlers persistence scheduler; do
  rm -rf "$APP_DIR/$module_dir"
  cp -R "$ROOT_DIR/$module_dir" "$APP_DIR/$module_dir"
  find "$APP_DIR/$module_dir" -type d -name "__pycache__" -prune -exec rm -rf {} +
done

# Sync schedules used in Azure runtime.
rm -rf "$APP_DIR/schedules"
mkdir -p "$APP_DIR/schedules"
cp "$ROOT_DIR/schedules/schedules.yaml" "$APP_DIR/schedules/schedules.yaml"

echo "Function App publish bundle ready."
