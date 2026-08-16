#!/bin/sh
set -e

# Fix permissions on .next volume (created by Docker as root)
if [ -d "/monorepo/apps/web/.next" ]; then
  echo "Fixing permissions on /monorepo/apps/web/.next volume..."
  chown -R node:node /monorepo/apps/web/.next
fi

# Fix permissions on node_modules volume (created by Docker as root)
if [ -d "/monorepo/apps/web/node_modules" ]; then
  echo "Fixing permissions on /monorepo/apps/web/node_modules volume..."
  chown -R node:node /monorepo/apps/web/node_modules
fi

# Install/update dependencies if node_modules volume is empty or outdated
# This ensures dependencies are always available even when using Docker volumes
if [ ! -f "/monorepo/apps/web/node_modules/.pnpm-workspace-state-v1.json" ]; then
  echo "Installing dependencies in volume (first run or volume was cleared)..."
  # CI=true prevents TTY prompts, --no-frozen-lockfile allows lockfile updates
  CI=true su-exec node pnpm install --filter @lia-assistant/web... --no-frozen-lockfile
fi

# Switch to node user and execute command
exec su-exec node "$@"
