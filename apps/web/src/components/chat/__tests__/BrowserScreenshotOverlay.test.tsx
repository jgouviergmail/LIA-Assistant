/**
 * BrowserScreenshotOverlay — the screenshot image, title and URL truncation.
 */

import { describe, it, expect } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { BrowserScreenshotOverlay } from '../BrowserScreenshotOverlay';

describe('BrowserScreenshotOverlay', () => {
  it('renders the screenshot image and title', () => {
    renderWithProviders(
      <BrowserScreenshotOverlay
        screenshot={{ url: 'https://example.com', title: 'Example', image_base64: 'AAAA' }}
      />
    );
    const img = screen.getByRole('img', { name: 'Example' });
    expect(img).toHaveAttribute('src', 'data:image/jpeg;base64,AAAA');
    expect(screen.getByText('Example')).toBeInTheDocument();
  });

  it('truncates a long URL to 57 chars plus an ellipsis', () => {
    const url = 'https://example.com/' + 'a'.repeat(80);
    renderWithProviders(
      <BrowserScreenshotOverlay screenshot={{ url, title: 'T', image_base64: 'AAAA' }} />
    );
    expect(screen.getByText(url.slice(0, 57) + '...')).toBeInTheDocument();
  });
});
