/**
 * ResponseFeedbackButtons (QW-5, ADR-138) — verdict submission, hydration,
 * verdict change, and the 👎 optional-correction flow. Never regenerates.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

import { ResponseFeedbackButtons } from '../ResponseFeedbackButtons';

const mutate = vi.fn().mockResolvedValue({ message: 'ok' });

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

  it('closes the correction input on Escape without sending', () => {
    render(<ResponseFeedbackButtons messageDbId="msg-1" />);
    fireEvent.click(screen.getByRole('button', { name: 'chat.feedback.down' }));

    const input = screen.getByRole('textbox', { name: 'chat.feedback.comment_placeholder' });
    fireEvent.keyDown(input, { key: 'Escape' });

    expect(screen.queryByRole('textbox')).toBeNull();
    expect(mutate).toHaveBeenCalledTimes(1); // only the verdict, no comment
  });
});
