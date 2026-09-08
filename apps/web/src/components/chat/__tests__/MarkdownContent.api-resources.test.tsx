/**
 * MarkdownContent — an API resource in markdown reaches the API.
 *
 * The assistant's answer carries relative wire URLs the backend built:
 * `/api/v1/connectors/google-places/photo/{name}` for a place photo,
 * `/api/v1/connectors/google-location/static-map?…` for a map,
 * `/api/v1/connectors/google-drive/thumbnail/{id}` for a Drive thumbnail.
 * Left relative they resolve against the FRONTEND origin, which only reaches
 * the API where a reverse proxy re-routes `/api/v1/*` — measured 2026-09-09 in
 * the developer environment, where it does not, and every one of them 500'd.
 *
 * Third-party and non-API sources must stay exactly as written.
 */

import { describe, it, expect, vi, afterEach } from 'vitest';
import { render } from '@testing-library/react';

import { MarkdownContent } from '../MarkdownContent';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const ORIGIN = 'https://api.example.test:8000';

/** The `src` of the single image the given markdown renders. */
function sourceOf(markdown: string): string {
  const { container } = render(<MarkdownContent content={markdown} />);
  const image = container.querySelector('img');
  expect(image).not.toBeNull();
  return image?.getAttribute('src') ?? '';
}

afterEach(() => {
  vi.unstubAllEnvs();
});

describe('MarkdownContent — API resources', () => {
  it('a place photo is loaded from the API origin', () => {
    vi.stubEnv('NEXT_PUBLIC_API_URL', ORIGIN);
    const path = '/api/v1/connectors/google-places/photo/abc';
    expect(sourceOf(`![lieu](${path})`)).toBe(`${ORIGIN}${path}`);
  });

  it('a static map keeps its query string', () => {
    vi.stubEnv('NEXT_PUBLIC_API_URL', ORIGIN);
    const path = '/api/v1/connectors/google-location/static-map?lat=48.58&lng=7.75';
    expect(sourceOf(`![carte](${path})`)).toBe(`${ORIGIN}${path}`);
  });

  it('a third-party image is untouched', () => {
    vi.stubEnv('NEXT_PUBLIC_API_URL', ORIGIN);
    const external = 'https://example.test/photo.jpg';
    expect(sourceOf(`![photo](${external})`)).toBe(external);
  });

  it('keeps the relative path when no API origin is configured', () => {
    vi.stubEnv('NEXT_PUBLIC_API_URL', '');
    const path = '/api/v1/connectors/google-places/photo/abc';
    expect(sourceOf(`![lieu](${path})`)).toBe(path);
  });
});
