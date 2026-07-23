import type { NextConfig } from 'next';

import {
  APP_HEADERS_SOURCE,
  WIDGET_FRAME_PATH,
  buildAppCsp,
  buildHsts,
  buildWidgetFrameCsp,
  resolveCoepMode,
} from './src/lib/csp';

// Allow self-signed certificates for internal Docker HTTPS communication
// Required because API uses HTTPS for Google OAuth callbacks (redirect URI)
// This must be set before any HTTPS requests are made by Next.js rewrites
if (process.env.NODE_ENV === 'development') {
  process.env.NODE_TLS_REJECT_UNAUTHORIZED = '0';
}

// Allowed dev origins for cross-origin requests in development
// Must include patterns for local network access
const envOrigins = process.env.NEXT_PUBLIC_ALLOWED_DEV_ORIGINS
  ? process.env.NEXT_PUBLIC_ALLOWED_DEV_ORIGINS.split(',').map(o => o.trim())
  : [];
// Note: Wildcard patterns may not work in Next.js 16, use explicit origins
const allowedDevOrigins = [
  ...new Set([
    ...envOrigins,
    'localhost',
    '127.0.0.1',
  ]),
];

// --- Content-Security-Policy (audit wave 3, A4 + widget airlock) ---
// Both policies (strict app CSP + permissive widget-frame CSP) live in
// src/lib/csp.ts — a pure module shared with unit tests so every directive
// change is covered by non-regression tests (two CSP regressions shipped
// blind before this: voice worklets and the interactive-map embed).
const isDev = process.env.NODE_ENV === 'development';

// SEC-025: HSTS max-age (seconds), env-tunable so it can be ramped up in
// production without a rebuild. Invalid/absent → conservative default in
// buildHsts(). Only emitted in production (see headers() below) — pinning
// localhost to HTTPS-only would break local HTTP dev.
const hstsMaxAge = Number(process.env.HSTS_MAX_AGE);

// Cross-Origin-Embedder-Policy posture (ADR-136). The VALUE is measured, not a
// default: `require-corp` blocks every external embed on WebKit (all iOS
// browsers), because the lift depends on the Chromium-only `credentialless`
// iframe attribute. See CoepMode in src/lib/csp.ts for the engine matrix.
// Env-tunable (COEP_MODE) so the posture can be reverted by restarting the
// container, without a rebuild.
const coepMode = resolveCoepMode(process.env.COEP_MODE);

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  compress: true,

  // E2E: let a production build/serve coexist with the running dev server in
  // the same bind-mounted tree. The hermetic E2E suite builds with
  // NEXT_DIST_DIR=.next-e2e and serves it on a separate port while `next dev`
  // keeps using `.next` untouched (see apps/web/e2e/README.md). Unset
  // (default) everywhere else, including the production Docker image.
  distDir: process.env.NEXT_DIST_DIR || '.next',

  // Production build configuration for Docker
  output: 'standalone',

  // Allow development access from local network (configured via NEXT_PUBLIC_ALLOWED_DEV_ORIGINS)
  ...(allowedDevOrigins && { allowedDevOrigins }),

  // Typed routes disabled due to incompatibility with i18n dynamic routes
  typedRoutes: false,

  // Turbopack configuration (default in Next.js 16)
  turbopack: {},

  experimental: {
    // Increase proxy body size limit for RAG document uploads (default: 10MB)
    // Must match RAG_SPACES_MAX_FILE_SIZE_MB (20MB) + overhead for multipart encoding
    proxyClientMaxBodySize: '25mb',
    // qemu-emulated cross-arch Docker builds (the arm64 image built on the
    // amd64 CI runner) flakily kill Next's parallel build workers with SIGILL
    // ("qemu: uncaught target signal 4"). Dockerfile.prod sets
    // NEXT_BUILD_CPUS=1 ONLY under emulation: a single build worker, plus a
    // retry margin for pages whose generation attempt was killed. Native
    // builds (env absent) keep Next's default parallelism.
    ...(process.env.NEXT_BUILD_CPUS
      ? {
          cpus: Number(process.env.NEXT_BUILD_CPUS),
          staticGenerationRetryCount: 3,
        }
      : {}),
  },

  // Environment variables.
  // `??`, NOT `||`: an EXPLICIT empty string means "same-origin relative
  // /api/v1 URLs through the BFF proxy" (hermetic E2E/CI builds set
  // NEXT_PUBLIC_API_URL=""). `||` silently rewrote it to the dev fallback and
  // every browser call went cross-origin, missing the route mocks. Only a
  // truly ABSENT variable gets the dev fallback. This block is inlined into
  // the client bundle, so it is the root of what every consumer reads.
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000',
  },

  // Enable WASM async for Sherpa-onnx KWS
  webpack: (config) => {
    config.experiments = { ...config.experiments, asyncWebAssembly: true };
    return config;
  },

  // Headers for security
  async headers() {
    return [
      {
        // Unified service worker (D5, ADR-146): must revalidate on every
        // check so a new release's SW (bumped CACHE_VERSION) deploys
        // promptly instead of being pinned by an HTTP cache.
        source: '/firebase-messaging-sw.js',
        headers: [{ key: 'Cache-Control', value: 'no-cache' }],
      },
      {
        // Every route EXCEPT the widget airlock (negative lookahead): the
        // airlock carries its own permissive CSP below, and two CSP headers
        // on one response would enforce their intersection.
        source: APP_HEADERS_SOURCE,
        headers: [
          // SEC-025: HSTS on the frontend (the public HTTPS response lacked it;
          // the API already sends it). Production only — see hstsMaxAge above.
          // Starts with a short max-age and NO includeSubDomains/preload.
          ...(isDev
            ? []
            : [{ key: 'Strict-Transport-Security', value: buildHsts(hstsMaxAge) }]),
          {
            key: 'X-DNS-Prefetch-Control',
            value: 'on'
          },
          {
            key: 'X-Frame-Options',
            value: 'SAMEORIGIN'
          },
          {
            key: 'X-Content-Type-Options',
            value: 'nosniff'
          },
          {
            key: 'Referrer-Policy',
            value: 'origin-when-cross-origin'
          },
          // COOP/COEP headers for WASM SharedArrayBuffer (Sherpa-onnx voice mode)
          // Note: OAuth uses redirect flow (not popups), so COOP won't break auth
          // require-corp enables crossOriginIsolated on ALL browsers including Safari iOS.
          // Cross-origin resources (Google Fonts, Google profile images) are handled via:
          // - Google Fonts: crossOrigin="anonymous" attribute (CORS-enabled by Google)
          // - Google profile images: proxied via /api/v1/auth/profile-image-proxy
          // - MCP App iframes: same-origin airlock shell (sends its own COEP
          //   below); its CDN subresources proved COEP-compatible pre-CSP
          {
            key: 'Cross-Origin-Embedder-Policy',
            value: coepMode
          },
          {
            key: 'Cross-Origin-Opener-Policy',
            value: 'same-origin'
          },
          // Strict CSP (audit A4) — see src/lib/csp.ts for the rationale of
          // each directive
          {
            key: 'Content-Security-Policy',
            value: buildAppCsp(isDev, process.env.NEXT_PUBLIC_API_URL)
          }
        ]
      },
      {
        // Widget airlock (see src/lib/csp.ts + ADR-098): third-party MCP App
        // widgets are bootstrapped into this same-origin shell so they get a
        // dedicated permissive CSP while the app policy above stays strict.
        // Isolation comes from the iframe sandbox (opaque origin), not CSP.
        source: WIDGET_FRAME_PATH,
        headers: [
          {
            key: 'Content-Security-Policy',
            value: buildWidgetFrameCsp()
          },
          // Parent responses carry a COEP value (see coepMode above); a nested
          // document must itself enable COEP or the browser refuses to load it
          // in the frame. `require-corp` here is compatible with BOTH parent
          // postures and was verified on Chromium and WebKit in all five
          // combinations (ADR-136) — the shell loads and receives its payload.
          {
            key: 'Cross-Origin-Embedder-Policy',
            value: 'require-corp'
          },
          {
            key: 'X-Content-Type-Options',
            value: 'nosniff'
          },
          // Legacy twin of frame-ancestors 'self' (belt and braces)
          {
            key: 'X-Frame-Options',
            value: 'SAMEORIGIN'
          },
          // The shell never needs to leak the app's URLs to widget CDNs
          {
            key: 'Referrer-Policy',
            value: 'no-referrer'
          }
        ]
      }
    ];
  },

  // API Rewrites for BFF Pattern
  // In development: Proxy /api/v1/* to backend container
  // This enables cross-port cookie sharing (SameSite=Lax) in development
  // In production: Use reverse proxy (nginx/Traefik) instead
  async rewrites() {
    // Use HTTP for rewrites to avoid self-signed cert issues
    // Next.js rewrites don't honor NODE_TLS_REJECT_UNAUTHORIZED
    // API_URL_SERVER_HTTP is HTTP variant, API_URL_SERVER may be HTTPS
    const apiUrl = process.env.API_URL_SERVER_HTTP || process.env.API_URL_SERVER || 'http://api:8000';

    return [
      {
        source: '/api/v1/:path*',
        destination: `${apiUrl}/api/v1/:path*`,
      },
    ];
  },
};

export default nextConfig;
