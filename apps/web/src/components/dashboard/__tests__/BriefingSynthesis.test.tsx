/**
 * BriefingSynthesis — the listen button (A2) rides the badge line.
 *
 * The control is a REAL button with a stable translated name that flips
 * between listen/stop; a failed synthesis surfaces a toast, never silence.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, render, screen, fireEvent } from '@testing-library/react';

const { useBriefingAudio } = vi.hoisted(() => ({ useBriefingAudio: vi.fn() }));
vi.mock('@/hooks/useBriefingAudio', () => ({ useBriefingAudio }));

vi.mock('@/hooks/useLiaGender', () => ({
  useLiaGender: () => ({ isMale: false }),
}));

const { toastError } = vi.hoisted(() => ({ toastError: vi.fn() }));
vi.mock('sonner', () => ({ toast: { error: toastError } }));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'fr' } }),
}));

import { BriefingSynthesis } from '../BriefingSynthesis';

function synthesis() {
  return {
    text: 'Votre journée est calme.',
    generated_at: '2026-08-20T08:00:00Z',
    usage: null,
  };
}

function audioState(over: Record<string, unknown> = {}) {
  const toggle = vi.fn();
  useBriefingAudio.mockReturnValue({
    playing: false,
    loading: false,
    error: false,
    toggle,
    ...over,
  });
  return toggle;
}

beforeEach(() => {
  useBriefingAudio.mockReset();
  toastError.mockReset();
});

describe('BriefingSynthesis listen button (A2)', () => {
  it('offers a named listen control and sends the DISPLAYED text', () => {
    const toggle = audioState();
    render(<BriefingSynthesis synthesis={synthesis()} />);

    const button = screen.getByRole('button', {
      name: 'dashboard.briefing.synthesis_listen',
    });
    fireEvent.click(button);

    expect(toggle).toHaveBeenCalledWith('Votre journée est calme.', 'female');
  });

  it('flips to a stop control while playing', () => {
    audioState({ playing: true });
    render(<BriefingSynthesis synthesis={synthesis()} />);

    const button = screen.getByRole('button', {
      name: 'dashboard.briefing.synthesis_stop',
    });
    expect(button).toHaveAttribute('aria-pressed', 'true');
  });

  it('surfaces a failed synthesis as a toast, never silence', () => {
    audioState({ error: true });
    render(<BriefingSynthesis synthesis={synthesis()} />);

    expect(toastError).toHaveBeenCalledWith('dashboard.briefing.synthesis_audio_error');
  });
});

describe('BriefingSynthesis — reading and listening remain independent', () => {
  it('starts expanded and keeps its audio control available when folded', () => {
    const toggle = audioState();
    render(<BriefingSynthesis synthesis={synthesis()} />);
    const fold = screen.getByRole('button', { name: 'dashboard.briefing.synthesis_collapse' });
    expect(fold).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText('Votre journée est calme.')).toBeVisible();
    fireEvent.click(fold);
    expect(screen.getByText('Votre journée est calme.')).not.toBeVisible();
    expect(fold).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(screen.getByRole('button', { name: 'dashboard.briefing.synthesis_listen' }));
    expect(toggle).toHaveBeenCalledWith('Votre journée est calme.', 'female');
    fireEvent.click(screen.getByRole('button', { name: 'dashboard.briefing.synthesis_expand' }));
    expect(screen.getByText('Votre journée est calme.')).toBeVisible();
  });

  it('keeps keyboard focus on the listen control while loading and ignores another press', () => {
    const toggle = audioState();
    const { rerender } = render(<BriefingSynthesis synthesis={synthesis()} />);
    const listen = screen.getByRole('button', { name: 'dashboard.briefing.synthesis_listen' });
    listen.focus();
    audioState({ loading: true, toggle });
    rerender(<BriefingSynthesis synthesis={synthesis()} />);
    expect(listen).toHaveFocus();
    expect(listen).toHaveAttribute('aria-disabled', 'true');
    expect(listen).not.toBeDisabled();
    fireEvent.click(listen);
    expect(toggle).not.toHaveBeenCalled();
  });
});

describe('BriefingSynthesis — « just updated » after a new synthesis', () => {
  it('says it for a moment when a newer synthesis replaces the one shown, never at first', () => {
    audioState();
    vi.useFakeTimers();
    try {
      const { rerender } = render(<BriefingSynthesis synthesis={synthesis()} />);
      expect(screen.queryByText('dashboard.briefing.synthesis_updated_badge')).toBeNull();

      rerender(
        <BriefingSynthesis synthesis={{ ...synthesis(), generated_at: '2026-08-20T09:00:00Z' }} />
      );

      expect(screen.getByText('dashboard.briefing.synthesis_updated_badge')).toBeInTheDocument();
      act(() => vi.advanceTimersByTime(1500));
      expect(screen.queryByText('dashboard.briefing.synthesis_updated_badge')).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });
});
