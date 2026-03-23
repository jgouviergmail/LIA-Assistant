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
