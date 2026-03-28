#!/bin/bash

##
# Install/update Claude CLI on the host server.
#
# This script is idempotent — safe to run multiple times.
# It installs Node.js (if needed) and Claude Code CLI.
#
# Usage:
#   ssh user@server 'bash -s' < scripts/deploy/setup-claude-cli.sh
#   # Or with custom workspace:
#   ssh user@server 'CLAUDE_WORKSPACE=/opt/claude bash -s' < scripts/deploy/setup-claude-cli.sh
#
# Prerequisites:
#   - sudo access (for Node.js installation)
#   - Internet access (for npm)
#
# After first install, authenticate manually:
#   ssh user@server
#   claude auth login
##

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[CLAUDE-CLI]${NC} $1"; }
log_success() { echo -e "${GREEN}[CLAUDE-CLI]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[CLAUDE-CLI]${NC} $1"; }
log_error() { echo -e "${RED}[CLAUDE-CLI]${NC} $1"; }

WORKSPACE_DIR="${CLAUDE_WORKSPACE:-$HOME/lia-workspace}"

# 1. Install Node.js (if not present)
if ! command -v node &>/dev/null; then
    log_info "Installing Node.js 22.x..."
    curl -fsSL https://deb.nodesource.com/setup_22.x | sudo bash -
    sudo apt-get install -y nodejs
    log_success "Node.js $(node --version) installed"
else
    log_info "Node.js $(node --version) already installed"
fi

# 2. Install/update Claude CLI
if command -v claude &>/dev/null; then
    log_info "Updating Claude CLI..."
    npm update -g @anthropic-ai/claude-code 2>/dev/null || \
        sudo npm update -g @anthropic-ai/claude-code
    log_success "Claude CLI updated"
else
    log_info "Installing Claude CLI..."
    npm install -g @anthropic-ai/claude-code 2>/dev/null || \
        sudo npm install -g @anthropic-ai/claude-code
    log_success "Claude CLI installed"
fi

# 3. Create workspace directory
mkdir -p "$WORKSPACE_DIR"
log_info "Workspace directory: $WORKSPACE_DIR"

# 4. Verify installation
CLAUDE_VERSION=$(claude --version 2>/dev/null || echo "unknown")
CLAUDE_PATH=$(which claude 2>/dev/null || echo "not found")

log_success "Claude CLI ready"
log_info "  Version: $CLAUDE_VERSION"
log_info "  Path: $CLAUDE_PATH"
log_info "  Workspace: $WORKSPACE_DIR"

# 5. Check authentication status
AUTH_STATUS=$(claude auth status 2>&1 || true)
if echo "$AUTH_STATUS" | grep -qi "logged in\|authenticated"; then
    log_success "Authentication: OK"
else
    log_warning "Authentication: NOT configured"
    log_warning "Run 'claude auth login' manually to authenticate"
fi

echo ""
log_success "Setup complete!"
