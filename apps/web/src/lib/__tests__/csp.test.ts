/**
 * CSP policy builders — non-regression tests (ADR-098).
 *
 * Two CSP regressions shipped blind before these tests existed (wave-3
 * audit): voice AudioWorklets (blob: missing from script-src) and the
 * interactive-map Google Maps embed (no frame-src). Every directive that a
 * runtime feature depends on is pinned here so a future hardening pass
 * cannot silently re-break it.
 */

import { describe, it, expect } from 'vitest';

import {
  APP_HEADERS_SOURCE,
  DEFAULT_COEP_MODE,
  DEFAULT_HSTS_MAX_AGE,
  WIDGET_FRAME_PATH,
  buildAppCsp,
  buildConnectSrc,
  buildHsts,
  buildWidgetFrameCsp,
  resolveCoepMode,
} from '../csp';

/** Parse a policy string into a directive → sources map. */
function parsePolicy(policy: string): Map<string, string[]> {
  const map = new Map<string, string[]>();
  for (const raw of policy.split(';')) {
    const parts = raw.trim().split(/\s+/);
    const [directive, ...sources] = parts;
    if (directive) map.set(directive, sources);
  }
  return map;
}

describe('buildAppCsp (strict app policy)', () => {
  const prod = parsePolicy(buildAppCsp(false, 'https://api.example.com'));
  const dev = parsePolicy(buildAppCsp(true, undefined));

  it('keeps blob: in script-src — voice AudioWorklets and the Sherpa glue loader load code from blob: URLs (worklet destination is governed by script-src, not worker-src)', () => {
    expect(prod.get('script-src')).toContain('blob:');
    expect(dev.get('script-src')).toContain('blob:');
  });

  it('keeps wasm-unsafe-eval in script-src (Sherpa-onnx voice mode)', () => {
    expect(prod.get('script-src')).toContain("'wasm-unsafe-eval'");
  });

  it('allows eval only in dev (turbopack HMR)', () => {
    expect(dev.get('script-src')).toContain("'unsafe-eval'");
    expect(prod.get('script-src')).not.toContain("'unsafe-eval'");
  });

  it('declares frame-src with self + www.google.com (interactive-map embed; fallback to default-src would block it)', () => {
    expect(prod.get('frame-src')).toEqual(["'self'", 'https://www.google.com']);
  });

  it('keeps blob: workers (Sherpa WASM) and self service worker', () => {
    expect(prod.get('worker-src')).toEqual(["'self'", 'blob:']);
  });

  it('allows exactly one external script host — the Cloudflare Insights beacon injected at the edge', () => {
    const scriptSrc = prod.get('script-src') ?? [];
    expect(scriptSrc.filter(s => s.startsWith('https://'))).toEqual([
      'https://static.cloudflareinsights.com',
    ]);
  });

  it('covers Google Fonts (stylesheet + font files)', () => {
    expect(prod.get('style-src')).toContain('https://fonts.googleapis.com');
    expect(prod.get('font-src')).toContain('https://fonts.gstatic.com');
  });

  it('keeps blob: images (attachment previews) and https: images (chat markdown)', () => {
    expect(prod.get('img-src')).toEqual(expect.arrayContaining(['blob:', 'https:', 'data:']));
  });

  it('locks object-src, base-uri, form-action, frame-ancestors', () => {
    expect(prod.get('object-src')).toEqual(["'none'"]);
    expect(prod.get('base-uri')).toEqual(["'self'"]);
    expect(prod.get('form-action')).toEqual(["'self'"]);
    expect(prod.get('frame-ancestors')).toEqual(["'self'"]);
  });
});

describe('buildConnectSrc', () => {
  it('includes the API origin and its websocket variant in prod', () => {
    expect(buildConnectSrc(false, 'https://api.example.com')).toBe(
      "'self' https://api.example.com wss://api.example.com"
    );
  });

  it('falls back to self on malformed API URL', () => {
    expect(buildConnectSrc(false, 'not a url')).toBe("'self'");
  });

  it('adds HMR websockets and local API origins in dev', () => {
    const value = buildConnectSrc(true, undefined);
    expect(value).toContain('ws:');
    expect(value).toContain('http://localhost:8000');
  });
});

describe('buildWidgetFrameCsp (airlock policy)', () => {
  const policy = parsePolicy(buildWidgetFrameCsp());

  it('allows third-party CDN runtimes (scripts, styles, fonts) — the reason the airlock exists', () => {
    expect(policy.get('script-src')).toEqual(
      expect.arrayContaining(['https:', 'blob:', "'unsafe-inline'"])
    );
    expect(policy.get('style-src')).toEqual(expect.arrayContaining(['https:', "'unsafe-inline'"]));
    expect(policy.get('font-src')).toEqual(expect.arrayContaining(['https:', 'data:']));
  });

  it("locks frame-ancestors to 'self' — the one directive doing real security work (no external site may embed the shell unsandboxed)", () => {
    expect(policy.get('frame-ancestors')).toEqual(["'self'"]);
  });

  it('keeps object-src none and base-uri none', () => {
    expect(policy.get('object-src')).toEqual(["'none'"]);
    expect(policy.get('base-uri')).toEqual(["'none'"]);
  });
});

describe('headers routing (app policy vs airlock)', () => {
  it('excludes exactly the widget frame path from the app-policy source pattern', () => {
    // path-to-regexp semantics: '/((?!widget-frame\.html).*)'
    const re = new RegExp('^/((?!widget-frame\\.html).*)$');
    expect(re.test(WIDGET_FRAME_PATH)).toBe(false);
    expect(re.test('/')).toBe(true);
    expect(re.test('/fr')).toBe(true);
    expect(re.test('/fr/chat')).toBe(true);
    expect(re.test('/api/v1/health')).toBe(true);
    expect(re.test('/models/sherpa-wasm/kws.wasm')).toBe(true);
  });

  it('keeps the exported pattern in sync with the regex used above', () => {
    expect(APP_HEADERS_SOURCE).toBe('/((?!widget-frame\\.html).*)');
  });

  it('serves the shell from the public root', () => {
    expect(WIDGET_FRAME_PATH).toBe('/widget-frame.html');
  });
});

describe('resolveCoepMode (COEP posture)', () => {
  it('defaults to credentialless — require-corp blocks every external embed on WebKit, where the Chromium-only `credentialless` attribute that lifts it does not exist', () => {
    expect(DEFAULT_COEP_MODE).toBe('credentialless');
    expect(resolveCoepMode(undefined)).toBe('credentialless');
  });

  it('honours an explicit require-corp opt-in (reverting the posture without a rebuild)', () => {
    expect(resolveCoepMode('require-corp')).toBe('require-corp');
    expect(resolveCoepMode('  Require-Corp  ')).toBe('require-corp');
  });

  it('never emits a value the platform would ignore — unknown input falls back to the default', () => {
    // A typo must not silently drop cross-origin isolation (and with it the
    // voice-mode wake word) by emitting an unparseable header value.
    for (const raw of ['', '   ', 'unsafe-none', 'require corp', 'true', 'credential-less']) {
      expect(resolveCoepMode(raw)).toBe(DEFAULT_COEP_MODE);
    }
  });
});

describe('buildHsts (SEC-025)', () => {
  it('emits a max-age with the requested value', () => {
    expect(buildHsts(31536000)).toBe('max-age=31536000');
  });

  it('never emits includeSubDomains or preload (near-irreversible — out of scope)', () => {
    const value = buildHsts(63072000);
    expect(value).not.toContain('includeSubDomains');
    expect(value).not.toContain('preload');
  });

  it('falls back to the conservative default for invalid/absent max-age', () => {
    // Number(undefined) === NaN, Number('') === 0 — both must fall back.
    expect(buildHsts(Number(undefined))).toBe(`max-age=${DEFAULT_HSTS_MAX_AGE}`);
    expect(buildHsts(0)).toBe(`max-age=${DEFAULT_HSTS_MAX_AGE}`);
    expect(buildHsts(-1)).toBe(`max-age=${DEFAULT_HSTS_MAX_AGE}`);
    expect(buildHsts()).toBe(`max-age=${DEFAULT_HSTS_MAX_AGE}`);
  });

  it('floors fractional values to an integer max-age', () => {
    expect(buildHsts(100.9)).toBe('max-age=100');
  });

  it('keeps a conservative default (<= 1 day) so rollout starts short', () => {
    expect(DEFAULT_HSTS_MAX_AGE).toBeLessThanOrEqual(86_400);
  });
});
