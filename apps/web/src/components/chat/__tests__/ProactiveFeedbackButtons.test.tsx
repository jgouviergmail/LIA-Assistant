/**
 * Proactive feedback chips (interest + heartbeat notifications).
 *
 * The contract under test is the failure path (owner arbitration 2026-07-30):
 * the vote is optimistic and FINAL in the UI — a failed submission is logged
 * by the mutation hook but never surfaces an error toast (older notifications
 * may have no matching backend row; shouting about a preference ping is worse
 * than dropping it).
 */

import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';

const mutateMock = vi.hoisted(() => vi.fn());
vi.mock('@/hooks/useApiMutation', () => ({
  useApiMutation: () => ({ mutate: mutateMock }),
}));

const toastMock = vi.hoisted(() => ({
  success: vi.fn(),
  info: vi.fn(),
  error: vi.fn(),
}));
vi.mock('sonner', () => ({ toast: toastMock }));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

import { TooltipProvider } from '@/components/ui/tooltip';
import { ProactiveFeedbackButtons } from '../ProactiveFeedbackButtons';

function renderChips(onFeedbackSubmitted = vi.fn()) {
  render(
    <TooltipProvider>
      <ProactiveFeedbackButtons
        kind="heartbeat"
        targetId="11111111-1111-4111-8111-111111111111"
        onFeedbackSubmitted={onFeedbackSubmitted}
      />
    </TooltipProvider>
  );
  return onFeedbackSubmitted;
}

describe('ProactiveFeedbackButtons', () => {
  beforeEach(() => {
    mutateMock.mockReset();
    toastMock.success.mockClear();
    toastMock.info.mockClear();
    toastMock.error.mockClear();
  });

  it('acknowledges the vote optimistically and submits it', async () => {
    mutateMock.mockResolvedValue(undefined);
    const onSubmitted = renderChips();

    fireEvent.click(screen.getByRole('button', { name: 'heartbeat.feedback.like' }));

    expect(onSubmitted).toHaveBeenCalledWith('thumbs_up');
    expect(toastMock.success).toHaveBeenCalledWith('heartbeat.feedback.liked');
    await waitFor(() =>
      expect(mutateMock).toHaveBeenCalledWith(
        '/heartbeat/notifications/11111111-1111-4111-8111-111111111111/feedback',
        { feedback: 'thumbs_up' }
      )
    );
  });

  it('NEVER shows an error toast when the submission fails', async () => {
    mutateMock.mockRejectedValue(new Error('404 notification not found'));
    const onSubmitted = renderChips();

    fireEvent.click(screen.getByRole('button', { name: 'heartbeat.feedback.dislike' }));

    // The optimistic lock and neutral acknowledgement still happen…
    expect(onSubmitted).toHaveBeenCalledWith('thumbs_down');
    expect(toastMock.info).toHaveBeenCalledWith('heartbeat.feedback.disliked');
    await waitFor(() => expect(mutateMock).toHaveBeenCalled());
    // …but the failure stays out of the user's face.
    expect(toastMock.error).not.toHaveBeenCalled();
  });

  it('locks the chips once a verdict is recorded', () => {
    render(
      <TooltipProvider>
        <ProactiveFeedbackButtons
          kind="heartbeat"
          targetId="11111111-1111-4111-8111-111111111111"
          onFeedbackSubmitted={vi.fn()}
          submittedVerdict="thumbs_up"
        />
      </TooltipProvider>
    );
    const like = screen.getByRole('button', { name: 'heartbeat.feedback.like' });
    expect(like).toBeDisabled();
    expect(like).toHaveAttribute('aria-pressed', 'true');
  });
});
