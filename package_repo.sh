#!/usr/bin/env bash
# ===========================================================================
# Sewa Setu Submission Packaging Script
# Build for Bharat Fellowship 2027 (AI Track)
# Creates a clean, standalone zip archive of the repository including full
# atomic git history, while excluding large data files and seed databases.
# ===========================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

OUTPUT_NAME="sewasetu_agent_ready_submission.zip"
OUTPUT_PATH="${SCRIPT_DIR}/${OUTPUT_NAME}"

echo "=========================================================="
echo " Packaging Sewa Setu Agent-Ready Repository Submission    "
echo "=========================================================="

# 1. Run local test suite to ensure green baseline before packaging
if [ -d ".venv" ]; then
    echo "[1/4] Validating test suite status..."
    PYTHONPATH=. .venv/bin/pytest tests/ -q || {
        echo "ERROR: Test suite failed! Please resolve tests before packaging."
        exit 1
    }
    echo "  -> All test suites passed successfully."
else
    echo "[1/4] Skipping test suite validation (no .venv found)."
fi

# 2. Remove any previous submission archive
rm -f "$OUTPUT_PATH"

# 3. Create zip archive
echo "[2/4] Packaging repository files (including .git history)..."

zip -r "$OUTPUT_PATH" . \
    -x "seed/seed.sql" \
    -x "seed/*.sql" \
    -x "*.tar.gz" \
    -x "*.zip" \
    -x ".venv/*" \
    -x "*/__pycache__/*" \
    -x "__pycache__/*" \
    -x ".pytest_cache/*" \
    -x "*/.pytest_cache/*" \
    -x "logs/*.log" \
    -x "logs/*.tar.gz" \
    -x "app/uploads/*" \
    -x "uploads/*" \
    -x "dc-briefing.mp3" \
    -x ".DS_Store" \
    -q

# 4. Verification and Checksums
echo "[3/4] Verifying generated archive integrity..."
if [ ! -f "$OUTPUT_PATH" ]; then
    echo "ERROR: Archive packaging failed!"
    exit 1
fi

FILESIZE=$(ls -lh "$OUTPUT_PATH" | awk '{print $5}')
echo "  -> Package File: ${OUTPUT_NAME}"
echo "  -> Package Size: ${FILESIZE}"

echo "[4/4] Computing SHA-256 and MD5 checksums..."
if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$OUTPUT_PATH"
elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$OUTPUT_PATH"
fi

if command -v md5sum >/dev/null 2>&1; then
    md5sum "$OUTPUT_PATH"
fi

echo "=========================================================="
echo " Packaging completed successfully! Ready for submission.  "
echo "=========================================================="
