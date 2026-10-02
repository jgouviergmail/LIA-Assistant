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
for hook in pre-commit pre-push; do
    if [ ! -f ".github/hooks/$hook" ]; then
        echo "❌ Hook not found at .github/hooks/$hook"
        exit 1
    fi
done

# Configure Git to use .github/hooks directly
git config core.hooksPath .github/hooks

# Ensure hooks are executable
chmod +x .github/hooks/pre-commit .github/hooks/pre-push

echo "✅ Git hooks configured (using core.hooksPath)"
echo ""
echo "The pre-commit hook will run:"
echo "  - Secret detection"
echo "  - Backend: Ruff, Black, MyPy, Unit tests (fast)"
echo "  - Frontend: ESLint, TypeScript"
echo ""
echo "The pre-push hook will run the CI's secret scan (task security:secrets, Docker)"
echo "on the commits the push sends."
echo ""
echo "To bypass the hook (not recommended):"
echo "  git commit --no-verify"
