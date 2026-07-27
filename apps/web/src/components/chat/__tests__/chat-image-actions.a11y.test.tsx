/**
 * F013 — image-open actions are native and keyboard-first.
 *
 * The chat images (markdown place/profile photos, galleries) used to carry
 * onClick on the <img> itself, which is mouse-only. These tests drive the
 * fixed component with real userEvent keyboard interaction: named buttons,
 * Enter/Space activation, single activation per press, and no nested
 * interactive content inside the action button.
 *
 * The companion `voice overlay` block was removed with `VoiceOverlay` itself:
 * the component had no consumer left (the live surface is `VoiceModeBadge`),
 * and its F013 fixes died with it.
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { MarkdownContent } from '../MarkdownContent';

describe('markdown image-open actions (F013)', () => {
  const PLACE_MD = '![Terrasse du café](/api/v1/connectors/google-places/photo?ref=abc)';

  it('exposes the place photo as a named button and opens the lightbox on Enter', async () => {
    const user = userEvent.setup();
    render(<MarkdownContent content={PLACE_MD} />);

    const expand = screen.getByRole('button', { name: 'common.expand_image' });
    expand.focus();
    expect(document.activeElement).toBe(expand);

    await user.keyboard('{Enter}');
    // The ImageLightbox portal is open: its named close button exists.
    expect(screen.getByRole('button', { name: 'common.close' })).toBeTruthy();
  });

  it('opens exactly once per activation and closes from the keyboard', async () => {
    const user = userEvent.setup();
    render(<MarkdownContent content={PLACE_MD} />);

    screen.getByRole('button', { name: 'common.expand_image' }).focus();
    await user.keyboard('{Enter}');

    // Single activation → exactly ONE lightbox close button.
    expect(screen.getAllByRole('button', { name: 'common.close' })).toHaveLength(1);

    await user.keyboard('{Escape}');
    expect(screen.queryByRole('button', { name: 'common.close' })).toBeNull();
  });

  it('keeps the image alt on the img, the action name on the button', () => {
    render(<MarkdownContent content={PLACE_MD} />);
    const expand = screen.getByRole('button', { name: 'common.expand_image' });
    const img = expand.querySelector('img');
    expect(img?.getAttribute('alt')).toBe('Terrasse du café');
    // No nested interactive content inside the action button.
    expect(expand.querySelector('button, a, input')).toBeNull();
  });
});
