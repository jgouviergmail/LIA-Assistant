/**
 * PortraitShortcut (QW-10) — shown only with a compiled portrait
 * (arbitration #6: no teaser), opens the Journals section on click.
 *
 * It asks for the portrait only where the journals are offered, and it is
 * TOLD so by the page, which holds the verdict that lists the section: under
 * the operator's switch the route refuses, and the section this opens is
 * absent. It reads no configuration of its own.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import { PortraitShortcut } from '../PortraitShortcut';
import type { JournalPortrait } from '@/hooks/useJournals';

let portraitValue: JournalPortrait | null = null;

const h = vi.hoisted(() => ({ asked: [] as boolean[] }));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

// Like the real hook: a disabled query asks nothing and holds nothing.
vi.mock('@/hooks/useJournalPortrait', () => ({
  useJournalPortrait: (enabled = true) => {
    h.asked.push(enabled);
    const portrait = enabled ? portraitValue : null;
    return {
      portrait,
      hasPortrait: Boolean(portrait?.full || portrait?.brief),
      loading: false,
    };
  },
}));

describe('PortraitShortcut', () => {
  beforeEach(() => {
    h.asked = [];
    portraitValue = {
      full: 'texte du portrait',
      brief: null,
      compiled_at: '2026-07-20T00:00:00Z',
      sources: null,
    };
  });

  it('opens the journals section on click', () => {
    const onOpen = vi.fn();
    render(<PortraitShortcut journalsOffered onOpen={onOpen} />);

    fireEvent.click(screen.getByRole('button', { name: /settings\.portrait_shortcut\.title/ }));

    expect(onOpen).toHaveBeenCalled();
    expect(h.asked).toEqual([true]);
  });

  it('renders nothing without a compiled portrait (no teaser)', () => {
    portraitValue = { full: null, brief: null, compiled_at: null, sources: null };
    const { container } = render(<PortraitShortcut journalsOffered onOpen={vi.fn()} />);
    expect(container.firstChild).toBeNull();
  });

  it('asks for no portrait where the journals are not offered', () => {
    const { container } = render(<PortraitShortcut journalsOffered={false} onOpen={vi.fn()} />);

    expect(h.asked).toEqual([false]);
    expect(container.firstChild).toBeNull();
  });
});
