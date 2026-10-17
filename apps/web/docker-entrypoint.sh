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

# The app volume survives image rebuilds, but its pnpm links target the image's
# root node_modules. A marker alone cannot prove those links are still valid.
dependencies_ready() {
  su-exec node node -e '
    const app = "/monorepo/apps/web";
    const expected = require(app + "/package.json").dependencies.next;
    const installed = require(app + "/node_modules/next/package.json").version;
    require.resolve(app + "/node_modules/next/dist/bin/next");
    if (installed !== expected) process.exit(1);
  ' >/dev/null 2>&1
}

dependency_error() {
  echo "Development dependencies do not match the app. Rebuild the web image:" >&2
  echo "docker compose -f docker-compose.dev.yml up -d --build --no-deps web" >&2
  exit 1
}

if [ ! -f "/monorepo/apps/web/node_modules/.pnpm-workspace-state-v1.json" ] || ! dependencies_ready; then
  echo "Installing development dependencies from the image lockfile..."
  # Keep installation deterministic. A host manifest newer than this image
  # requires rebuilding, rather than silently rewriting the image lockfile.
  if ! CI=true su-exec node pnpm install --filter @lia-assistant/web... --frozen-lockfile; then
    dependency_error
  fi
  if ! dependencies_ready; then
    dependency_error
  fi
fi

# Switch to node user and execute command
exec su-exec node "$@"
