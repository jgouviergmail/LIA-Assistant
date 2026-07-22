/**
 * PortraitShortcut (QW-10) — shown only with a compiled portrait
 * (arbitration #6: no teaser), opens the Journals section on click.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import { PortraitShortcut } from '../PortraitShortcut';
import type { JournalPortrait } from '@/hooks/useJournals';

let portraitValue: JournalPortrait | null = null;

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('@/hooks/useJournalPortrait', () => ({
  useJournalPortrait: () => ({
    portrait: portraitValue,
    hasPortrait: Boolean(portraitValue?.full || portraitValue?.brief),
    loading: false,
  }),
}));

describe('PortraitShortcut', () => {
  beforeEach(() => {
    portraitValue = { full: 'texte du portrait', brief: null, compiled_at: '2026-07-20T00:00:00Z' };
  });

  it('opens the journals section on click', () => {
    const onOpen = vi.fn();
    render(<PortraitShortcut onOpen={onOpen} />);

    fireEvent.click(screen.getByRole('button', { name: /settings\.portrait_shortcut\.title/ }));

    expect(onOpen).toHaveBeenCalled();
  });

  it('renders nothing without a compiled portrait (no teaser)', () => {
    portraitValue = { full: null, brief: null, compiled_at: null };
    const { container } = render(<PortraitShortcut onOpen={vi.fn()} />);
    expect(container.firstChild).toBeNull();
  });
});
