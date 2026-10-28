#!/usr/bin/env bash
# ===========================================================================
# Hugging Face Spaces Deployment Sync Script
# Pushes the clean, binary-free deployment branch to hf.co:spaces/Ph05/BFB
# ===========================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$ROOT_DIR"

echo "=========================================================="
echo " Syncing Sewa Setu to Hugging Face Spaces (Ph05/BFB)     "
echo "=========================================================="

CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)

# Ensure hf remote exists
if ! git remote | grep -q "^hf$"; then
    git remote add hf git@hf.co:spaces/Ph05/BFB
fi

# Switch to hf-deploy branch
git checkout hf-deploy

# Merge latest main changes
git merge main -m "sync: pull updates from main" --strategy-option theirs 2>/dev/null || true

# Ensure font binaries are never tracked on hf-deploy
git rm --cached app/fonts/*.ttf 2>/dev/null || true
git commit --amend --no-edit 2>/dev/null || true

# Push to Hugging Face Spaces main branch
echo "Pushing clean deployment tree to Hugging Face Spaces..."
GIT_SSH_COMMAND="ssh -F /dev/null -o StrictHostKeyChecking=accept-new" git push hf hf-deploy:main --force

# Switch back to original branch
git checkout "$CURRENT_BRANCH"

echo "=========================================================="
echo " Successfully deployed to Hugging Face Spaces!            "
echo " Public URL: https://ph05-bfb.hf.space                     "
echo "=========================================================="
