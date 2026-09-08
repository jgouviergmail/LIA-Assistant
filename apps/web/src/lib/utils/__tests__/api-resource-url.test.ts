/**
 * An API resource URL must reach the API, not the frontend origin.
 *
 * The defect this pins was live: the dev API serves HTTPS only and the Next
 * rewrite refuses its self-signed certificate, so a relative `/api/v1/...`
 * answered 500 for every generated document, image, screenshot, place photo
 * and static map — while every other call, which uses the API origin, worked.
 */

import { afterEach, describe, expect, it, vi } from 'vitest';

import { apiResourceUrl } from '../api-resource-url';

const WIRE = '/api/v1/attachments/386e6a36-d880-4854-bfe8-c5518dd0dd51';
const ORIGIN = 'https://api.example.test:8000';

afterEach(() => {
  vi.unstubAllEnvs();
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
