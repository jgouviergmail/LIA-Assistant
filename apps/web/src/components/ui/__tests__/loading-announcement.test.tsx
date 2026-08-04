/**
 * LoadingAnnouncement — the one spoken "loading" of a route-level skeleton.
 *
 * Making `Skeleton` decorative removed fourteen English live regions from the
 * settings loading screen. It also removed the ONLY signal a screen-reader user
 * had that the route was loading, since React renders `loading.tsx` without
 * moving focus and without announcing anything. This component puts that signal
 * back — once, and in the reader's language.
 */

import { describe, it, expect } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { LoadingAnnouncement } from '../loading-announcement';

describe('LoadingAnnouncement', () => {
  it('announces the loading state from the active locale', () => {
    renderWithProviders(<LoadingAnnouncement />);
    expect(screen.getByRole('status')).toHaveTextContent('common.loading');
  });

  it('stays invisible — the skeleton is what the sighted reader sees', () => {
    renderWithProviders(<LoadingAnnouncement />);
    expect(screen.getByRole('status')).toHaveClass('sr-only');
  });
});
