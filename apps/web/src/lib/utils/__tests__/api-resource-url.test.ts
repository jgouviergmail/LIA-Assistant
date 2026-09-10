/**
 * An API resource URL must reach the API, not the frontend origin.
 *
 * The defect this pins was live: the dev API serves HTTPS only and the Next
 * rewrite refuses its self-signed certificate, so a relative `/api/v1/...`
 * answered 500 for every generated document, image, screenshot, place photo
 * and static map — while every other call, which uses the API origin, worked.
 */

import { afterEach, describe, expect, it, vi } from 'vitest';

import { apiImageProps, apiResourceUrl } from '../api-resource-url';

const WIRE = '/api/v1/attachments/386e6a36-d880-4854-bfe8-c5518dd0dd51';
const ORIGIN = 'https://api.example.test:8000';

afterEach(() => {
  vi.unstubAllEnvs();
});

describe('apiImageProps', () => {
  /**
   * Reported from production on 2026-09-10: generated image thumbnails were
   * broken in the chat AND in the gallery, while opening the very same URL
   * showed the image.
   *
   * The web app answers with `Cross-Origin-Embedder-Policy: credentialless`.
   * Under that policy a no-CORS cross-origin subresource — an `<img src>` with
   * no `crossorigin` attribute — is fetched WITHOUT credentials, so the session
   * cookie never reaches the API and it answers 401. A top-level navigation is
   * not a subresource, which is why clicking the image worked and made the
   * defect look like a rendering bug.
   *
   * Measured on the live API: it already answers
   * `access-control-allow-credentials: true` with the app's origin, so a
   * credentialed CORS request succeeds — the attribute is all that was missing.
   */
  it('asks for credentials when the resource is served from another origin', () => {
    vi.stubEnv('NEXT_PUBLIC_API_URL', ORIGIN);
    expect(apiImageProps(WIRE)).toEqual({
      src: `${ORIGIN}${WIRE}`,
      crossOrigin: 'use-credentials',
    });
  });

  it('asks for nothing when the reverse proxy serves the API on this origin', () => {
    // Same-origin subresources always carry cookies; the attribute would only
    // add a CORS check where none is needed.
    vi.stubEnv('NEXT_PUBLIC_API_URL', '');
    expect(apiImageProps(WIRE)).toEqual({ src: WIRE });
  });

  it('never claims credentials on a resource that is not ours', () => {
    vi.stubEnv('NEXT_PUBLIC_API_URL', ORIGIN);
    for (const foreign of [
      'https://upload.wikimedia.org/thumb.png',
      'data:image/png;base64,iVBORw0KGgo=',
      'blob:https://lia.example/9f1c',
    ]) {
      expect(apiImageProps(foreign)).toEqual({ src: foreign });
    }
  });
});

describe('apiResourceUrl', () => {
  it('resolves a wire URL against the configured API origin', () => {
    vi.stubEnv('NEXT_PUBLIC_API_URL', ORIGIN);
    expect(apiResourceUrl(WIRE)).toBe(`${ORIGIN}${WIRE}`);
  });

  it('keeps the relative path when no API origin is configured', () => {
    vi.stubEnv('NEXT_PUBLIC_API_URL', '');
    expect(apiResourceUrl(WIRE)).toBe(WIRE);
  });

  it('preserves a query string', () => {
    vi.stubEnv('NEXT_PUBLIC_API_URL', ORIGIN);
    const map = '/api/v1/connectors/google-location/static-map?lat=48.5&lng=7.7';
    expect(apiResourceUrl(map)).toBe(`${ORIGIN}${map}`);
  });

  it('leaves alone anything that is not an API resource', () => {
    vi.stubEnv('NEXT_PUBLIC_API_URL', ORIGIN);
    for (const untouched of [
      'https://lh3.googleusercontent.com/a/photo.jpg',
      'data:image/png;base64,AAAA',
      'blob:https://app.example.test/1234',
      '/images/logo.png',
      '',
    ]) {
      expect(apiResourceUrl(untouched)).toBe(untouched);
    }
  });
});
