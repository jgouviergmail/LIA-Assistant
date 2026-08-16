#!/bin/bash
#
# Install Git hooks for LIA
#
# Usage:
#   ./scripts/install-hooks.sh
#
# Uses git core.hooksPath to point directly to .github/hooks
# No symlinks, no copies, always in sync!
#

set -e

echo "🔧 Installing Git hooks..."

# Verify hooks exist
if [ ! -f ".github/hooks/pre-commit" ]; then
    echo "❌ Pre-commit hook not found at .github/hooks/pre-commit"
    exit 1
fi

# Configure Git to use .github/hooks directly
git config core.hooksPath .github/hooks

# Ensure hooks are executable
chmod +x .github/hooks/pre-commit

echo "✅ Git hooks configured (using core.hooksPath)"
echo ""
echo "The pre-commit hook will run:"
echo "  - Secret detection"
echo "  - Backend: Ruff, Black, MyPy, Unit tests (fast)"
echo "  - Frontend: ESLint, TypeScript"
echo ""
echo "To bypass the hook (not recommended):"
echo "  git commit --no-verify"
