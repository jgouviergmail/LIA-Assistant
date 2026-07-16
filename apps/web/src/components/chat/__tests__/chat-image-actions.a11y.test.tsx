/**
 * F013 — image-open actions and the voice overlay are native, keyboard-first.
 *
 * The chat images (markdown place/profile photos, galleries) used to carry
 * onClick on the <img> itself (mouse-only), and the voice overlay was a
 * role="button" container that CONTAINED the close button (invalid nesting).
 * These tests drive the fixed components with real userEvent keyboard
 * interaction: named buttons, Tab reachability, Enter/Space activation,
 * single activation, and sibling controls staying independent.
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { MarkdownContent } from '../MarkdownContent';
import { VoiceOverlay, type VoiceOverlayProps } from '../../voice/VoiceOverlay';

function voiceProps(over: Partial<VoiceOverlayProps> = {}): VoiceOverlayProps {
  return {
    isEnabled: true,
    state: 'listening',
    onTap: vi.fn(),
    onStop: vi.fn(),
    onDisable: vi.fn(),
    ...over,
  };
}

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

describe('voice overlay (F013)', () => {
  it('listening: the tap action is a named button, Enter activates it once', async () => {
    const user = userEvent.setup();
    const onTap = vi.fn();
    render(<VoiceOverlay {...voiceProps({ onTap })} />);

    const action = screen.getByRole('button', {
      name: 'chat.voice_mode.instruction_listening',
    });
    action.focus();
    await user.keyboard('{Enter}');
    expect(onTap).toHaveBeenCalledTimes(1);
  });

  it('recording: Space stops exactly once', async () => {
    const user = userEvent.setup();
    const onStop = vi.fn();
    render(<VoiceOverlay {...voiceProps({ state: 'recording', onStop })} />);

    screen.getByRole('button', { name: 'chat.voice_mode.instruction_recording' }).focus();
    await user.keyboard(' ');
    expect(onStop).toHaveBeenCalledTimes(1);
  });

  it('processing: no action button is rendered (nothing to activate)', () => {
    render(<VoiceOverlay {...voiceProps({ state: 'processing' })} />);
    expect(
      screen.queryByRole('button', { name: 'chat.voice_mode.instruction_processing' })
    ).toBeNull();
    // The close button remains available in every state.
    expect(screen.getByRole('button', { name: 'chat.voice_mode.disable' })).toBeTruthy();
  });

  it('close stays independent: it never triggers the tap action (no nesting)', async () => {
    const user = userEvent.setup();
    const onTap = vi.fn();
    const onDisable = vi.fn();
    render(<VoiceOverlay {...voiceProps({ onTap, onDisable })} />);

    await user.click(screen.getByRole('button', { name: 'chat.voice_mode.disable' }));
    expect(onDisable).toHaveBeenCalledTimes(1);
    expect(onTap).not.toHaveBeenCalled();
  });

  it('focus order: the action button precedes the close button', async () => {
    const user = userEvent.setup();
    render(<VoiceOverlay {...voiceProps()} />);

    await user.tab();
    expect(document.activeElement).toBe(
      screen.getByRole('button', { name: 'chat.voice_mode.instruction_listening' })
    );
    await user.tab();
    expect(document.activeElement).toBe(
      screen.getByRole('button', { name: 'chat.voice_mode.disable' })
    );
  });
});
