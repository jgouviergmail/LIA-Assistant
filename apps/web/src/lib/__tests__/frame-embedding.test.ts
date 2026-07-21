/**
 * Capability probe for cross-origin iframe embedding under COEP.
 *
 * The matrix pinned here is measured, not assumed (WebKit 26.4 vs Chromium,
 * production headers replicated, real Google Maps embed): a cross-origin
 * isolated document may only embed a COEP-less cross-origin document when the
 * engine implements the Chromium-only `credentialless` iframe attribute.
 * Getting this wrong ships a permanently blank rectangle to iOS users.
 */

import { describe, it, expect, afterEach } from 'vitest';

import {
  canEmbedOpaqueCrossOriginFrame,
  engineSupportsCredentialless,
  isCrossOriginUrl,
} from '../frame-embedding';

/** The widget only applies the attribute to trusted system-skill URLs. */
const APPLIED = { credentiallessApplied: true };
const NOT_APPLIED = { credentiallessApplied: false };

/** jsdom exposes neither flag; both are installed/removed per test. */
function setEnvironment(opts: { isolated: boolean; credentialless: boolean }): void {
  Object.defineProperty(window, 'crossOriginIsolated', {
    value: opts.isolated,
    configurable: true,
    writable: true,
  });
  if (opts.credentialless) {
    Object.defineProperty(HTMLIFrameElement.prototype, 'credentialless', {
      value: false,
      configurable: true,
      writable: true,
    });
  } else {
    delete (HTMLIFrameElement.prototype as unknown as Record<string, unknown>).credentialless;
  }
}

afterEach(() => {
  delete (window as unknown as Record<string, unknown>).crossOriginIsolated;
  delete (HTMLIFrameElement.prototype as unknown as Record<string, unknown>).credentialless;
});

describe('engineSupportsCredentialless', () => {
  it('reports the Chromium-only capability', () => {
    setEnvironment({ isolated: false, credentialless: true });
    expect(engineSupportsCredentialless()).toBe(true);
    setEnvironment({ isolated: false, credentialless: false });
    expect(engineSupportsCredentialless()).toBe(false);
  });
});

describe('canEmbedOpaqueCrossOriginFrame', () => {
  it('allows the embed when the document is NOT cross-origin isolated (COEP imposes nothing)', () => {
    setEnvironment({ isolated: false, credentialless: false });
    expect(canEmbedOpaqueCrossOriginFrame(NOT_APPLIED)).toBe(true);
    expect(canEmbedOpaqueCrossOriginFrame(APPLIED)).toBe(true);
  });

  it('allows the embed when isolated, the engine supports `credentialless` AND we apply it (Chromium 110+)', () => {
    setEnvironment({ isolated: true, credentialless: true });
    expect(canEmbedOpaqueCrossOriginFrame(APPLIED)).toBe(true);
  });

  it('REFUSES the embed when isolated without `credentialless` — the WebKit/iOS case that rendered a blank frame', () => {
    setEnvironment({ isolated: true, credentialless: false });
    expect(canEmbedOpaqueCrossOriginFrame(APPLIED)).toBe(false);
  });

  it('REFUSES the embed when the attribute is NOT applied, even on a supporting engine', () => {
    // Untrusted frame, or one rehydrated from history with is_system_skill
    // cleared: Chromium refuses it too, and there the refusal is invisible —
    // `load` fires on the error document, so the watchdog never triggers.
    setEnvironment({ isolated: true, credentialless: true });
    expect(canEmbedOpaqueCrossOriginFrame(NOT_APPLIED)).toBe(false);
  });

  it('treats a missing crossOriginIsolated flag as not isolated rather than throwing', () => {
    delete (window as unknown as Record<string, unknown>).crossOriginIsolated;
    expect(canEmbedOpaqueCrossOriginFrame(NOT_APPLIED)).toBe(true);
  });
});

describe('isCrossOriginUrl', () => {
  it('reports same-origin absolute and relative URLs as same-origin', () => {
    expect(isCrossOriginUrl(window.location.origin + '/widget-frame.html')).toBe(false);
    expect(isCrossOriginUrl('/widget-frame.html')).toBe(false);
  });

  it('reports a different origin as cross-origin', () => {
    expect(isCrossOriginUrl('https://www.google.com/maps/embed?pb=x')).toBe(true);
  });

  it('treats an unparseable URL as cross-origin (conservative: we cannot prove otherwise)', () => {
    expect(isCrossOriginUrl('http://[malformed')).toBe(true);
  });
});
