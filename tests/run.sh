#!/usr/bin/env bash
# Run the Motion Studio test suite. MOTION_FAST=1 skips Chromium/render tests.
set -euo pipefail
cd "$(dirname "$0")/.."
exec python3 -m unittest discover -s tests -v "$@"
