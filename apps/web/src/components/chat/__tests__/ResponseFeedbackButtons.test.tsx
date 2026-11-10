/**
 * ResponseFeedbackButtons (QW-5, ADR-138) — verdict submission, hydration,
 * verdict change, and the 👎 optional-correction flow. Never regenerates.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ThumbsDown as NormalizedThumbsDown, ThumbsUp as NormalizedThumbsUp } from 'lucide-react';
import { ICON_STYLES } from '@/lib/icon-style';
import { IconStyleContext } from '@/lib/icon-style-context';

// `renderWithProviders` supplies the TooltipProvider the thumb chips need —
// the real tree always has one (the copy chip next to them is tooltipped too).
import { renderWithProviders as render } from '@/__tests__/test-utils';

import { ResponseFeedbackButtons } from '../ResponseFeedbackButtons';

const mutate = vi.fn().mockResolvedValue({ message: 'ok' });

function geometry(svg: SVGSVGElement | null): string[] {
  if (!svg) throw new Error('Expected the rendered thumb SVG');
  const coordinates = ['d', 'x', 'y', 'width', 'height', 'rx', 'ry', 'cx', 'cy', 'r', 'points'];
  return [...svg.querySelectorAll('path, rect, circle, ellipse, polygon, polyline')].map(shape =>
    JSON.stringify([
      shape.localName,
      ...coordinates.map(attribute => shape.getAttribute(attribute)),
    ])
  );
}

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), info: vi.fn(), error: vi.fn() },
}));

vi.mock('@/hooks/useApiMutation', () => ({
  useApiMutation: () => ({ mutate }),
}));

describe('ResponseFeedbackButtons', () => {
  beforeEach(() => {
    mutate.mockClear();
  });

  it('keeps recognizable up and down thumb geometry in the multicolour Fluent complements', () => {
    const { getByTestId } = render(
      <>
        <span data-testid="normalized-up">
          <NormalizedThumbsUp />
        </span>
        <span data-testid="normalized-down">
          <NormalizedThumbsDown />
        </span>
        <IconStyleContext.Provider value="fluent">
          <ResponseFeedbackButtons messageDbId="msg-1" />
        </IconStyleContext.Provider>
      </>
    );

    for (const direction of ['up', 'down'] as const) {
      const button = screen.getByRole('button', { name: `chat.feedback.${direction}` });
      const icon = button.querySelector('svg');
      const reference = getByTestId(`normalized-${direction}`).querySelector('svg');
      expect(icon).not.toBeNull();
      expect(reference).not.toBeNull();
      const standardShapes = geometry(reference);
      expect(standardShapes.length).toBeGreaterThan(0);
      expect(geometry(icon)).toEqual(expect.arrayContaining(standardShapes));
      expect(icon).toHaveAttribute('data-icon-style', 'fluent');
    }
  });

  it.each(ICON_STYLES)(
    'shows and moves the keyboard-selected verdict with %s icons',
    async style => {
      const keyboard = userEvent.setup();
      render(
        <IconStyleContext.Provider value={style}>
          <ResponseFeedbackButtons messageDbId="msg-1" />
        </IconStyleContext.Provider>
      );
      const up = screen.getByRole('button', { name: 'chat.feedback.up' });
      const down = screen.getByRole('button', { name: 'chat.feedback.down' });
      expect(up).not.toHaveClass('border-primary', 'bg-primary/10');
      expect(down).not.toHaveClass('border-primary', 'bg-primary/10');
      expect(up.querySelector('svg')).toHaveAttribute('data-icon-name', 'ThumbsUp');
      expect(down.querySelector('svg')).toHaveAttribute('data-icon-name', 'ThumbsDown');
      expect(up.querySelector('svg')).toHaveAttribute('data-icon-style', style);

      await keyboard.tab();
      expect(up).toHaveFocus();
      expect(up).toHaveClass('focus-visible:ring-2', 'focus-visible:ring-ring');
      await keyboard.keyboard('{Enter}');
      await waitFor(() => expect(up).not.toBeDisabled());
      expect(up).toHaveAttribute('aria-pressed', 'true');
      expect(up).toHaveClass('border-primary', 'bg-primary/10', 'dark:bg-primary/15');

      await keyboard.tab();
      expect(down).toHaveFocus();
      await keyboard.keyboard(' ');
      await waitFor(() => expect(down).not.toBeDisabled());
      expect(up).toHaveAttribute('aria-pressed', 'false');
      expect(up).not.toHaveClass('border-primary', 'bg-primary/10');
      expect(down).toHaveAttribute('aria-pressed', 'true');
      expect(down).toHaveClass('border-primary', 'bg-primary/10');
      expect(mutate).toHaveBeenLastCalledWith('/conversations/me/messages/msg-1/feedback', {
        verdict: 'thumbs_down',
      });
    }
  );

  it('submits a thumbs_up verdict to the message endpoint', async () => {
    render(<ResponseFeedbackButtons messageDbId="msg-1" />);

    fireEvent.click(screen.getByRole('button', { name: 'chat.feedback.up' }));

    await waitFor(() =>
      expect(mutate).toHaveBeenCalledWith('/conversations/me/messages/msg-1/feedback', {
        verdict: 'thumbs_up',
      })
    );
    expect(screen.getByRole('button', { name: 'chat.feedback.up' })).toHaveProperty(
      'ariaPressed',
      'true'
    );
  });

  it('unfolds the optional correction input on thumbs_down and sends it', async () => {
    render(<ResponseFeedbackButtons messageDbId="msg-1" />);

    fireEvent.click(screen.getByRole('button', { name: 'chat.feedback.down' }));
    await waitFor(() => expect(mutate).toHaveBeenCalledTimes(1));

    const input = screen.getByRole('textbox', { name: 'chat.feedback.comment_placeholder' });
    fireEvent.change(input, { target: { value: 'La date était fausse' } });
    fireEvent.keyDown(input, { key: 'Enter' });

    await waitFor(() =>
      expect(mutate).toHaveBeenLastCalledWith('/conversations/me/messages/msg-1/feedback', {
        verdict: 'thumbs_down',
        comment: 'La date était fausse',
      })
    );
    expect(screen.queryByRole('textbox')).toBeNull();
  });

  it('hydrates the persisted verdict and re-submits only on change', async () => {
    render(<ResponseFeedbackButtons messageDbId="msg-1" initialVerdict="thumbs_up" />);

    const up = screen.getByRole('button', { name: 'chat.feedback.up' });
    expect(up).toHaveProperty('ariaPressed', 'true');
    expect(up).toHaveClass('border-primary', 'bg-primary/10');

    // Same verdict again → no request (idempotent client-side).
    fireEvent.click(up);
    expect(mutate).not.toHaveBeenCalled();

    // Changing the verdict IS allowed (sovereignty) and hits the endpoint.
    fireEvent.click(screen.getByRole('button', { name: 'chat.feedback.down' }));
    await waitFor(() =>
      expect(mutate).toHaveBeenCalledWith('/conversations/me/messages/msg-1/feedback', {
        verdict: 'thumbs_down',
      })
    );
  });

  it('renders in-flow chips and a full-width correction row (PERSO layout)', async () => {
    const { container } = render(<ResponseFeedbackButtons messageDbId="msg-1" />);
    // No overlay wrapper — the chips sit in the bubble's action row.
    expect(container.querySelector('.absolute')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'chat.feedback.down' }));
    const input = screen.getByRole('textbox', { name: 'chat.feedback.comment_placeholder' });
    // The correction line wraps under the row (flex-wrap parent + w-full).
    expect(input.parentElement?.className).toMatch(/w-full/);
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'chat.feedback.down' })).not.toBeDisabled()
    );
  });

  it('closes the correction input on Escape without sending', async () => {
    render(<ResponseFeedbackButtons messageDbId="msg-1" />);
    fireEvent.click(screen.getByRole('button', { name: 'chat.feedback.down' }));

    const input = screen.getByRole('textbox', { name: 'chat.feedback.comment_placeholder' });
    fireEvent.keyDown(input, { key: 'Escape' });

    expect(screen.queryByRole('textbox')).toBeNull();
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'chat.feedback.down' })).not.toBeDisabled()
    );
    expect(mutate).toHaveBeenCalledTimes(1); // only the verdict, no comment
    // Cancelling the optional comment never withdraws the recorded verdict.
    expect(screen.getByRole('button', { name: 'chat.feedback.down' })).toHaveClass(
      'border-primary',
      'bg-primary/10'
    );
  });
});
