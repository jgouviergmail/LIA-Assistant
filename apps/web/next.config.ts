import type { NextConfig } from 'next';

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

// --- Content-Security-Policy (audit wave 3, A4) ---
// Defense-in-depth against XSS: an injected <script src> or eval() is blocked
// even if a rendering bug ever reintroduces raw HTML. Constraints honored:
// - Next.js App Router ships inline bootstrap scripts → 'unsafe-inline' is
//   required in script-src (no per-request nonce with static headers). The
//   header still blocks every EXTERNAL script origin and eval().
// - Sherpa-onnx voice mode compiles WASM → 'wasm-unsafe-eval' + blob: workers.
// - MCP/Skill widget iframes use srcDoc (inherit this CSP) and are
//   self-contained by design — inline allowance keeps them working.
// - Google Fonts stylesheet + font files (see app/[lng]/layout.tsx).
// - In production the API is a separate origin (NEXT_PUBLIC_API_URL) reached
//   via fetch/SSE/WebSocket → connect-src includes it (+ ws(s) variant).
// - Dev: turbopack HMR needs eval() and websockets.
const isDev = process.env.NODE_ENV === 'development';

function buildConnectSrc(): string {
  const sources = ["'self'"];
  const apiUrl = process.env.NEXT_PUBLIC_API_URL;
  if (apiUrl) {
    try {
      const origin = new URL(apiUrl).origin;
      sources.push(origin, origin.replace(/^http/, 'ws'));
    } catch {
      // Malformed URL — fall back to same-origin only
    }
  }
  if (isDev) {
    sources.push('ws:', 'wss:', 'http://localhost:8000', 'http://127.0.0.1:8000');
  }
  return sources.join(' ');
}

const contentSecurityPolicy = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval'${isDev ? " 'unsafe-eval'" : ''}`,
  "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
  "font-src 'self' data: https://fonts.gstatic.com",
  // https: for user-facing remote images (chat markdown, connector data);
  // images are not a script vector and COEP already gates embedding
  "img-src 'self' data: blob: https:",
  "media-src 'self' data: blob:",
  "worker-src 'self' blob:",
  `connect-src ${buildConnectSrc()}`,
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'self'",
].join('; ');

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  compress: true,

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
  },

  // Environment variables
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000',
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
        source: '/:path*',
        headers: [
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
          // - MCP App iframes: use srcDoc (inline), no cross-origin fetch needed
          {
            key: 'Cross-Origin-Embedder-Policy',
            value: 'require-corp'
          },
          {
            key: 'Cross-Origin-Opener-Policy',
            value: 'same-origin'
          },
          // Strict CSP (audit A4) — see contentSecurityPolicy above for the
          // rationale of each directive
          {
            key: 'Content-Security-Policy',
            value: contentSecurityPolicy
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
