import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import userEvent from '@testing-library/user-event';
import { ICON_STYLES } from '@/lib/icon-style';
import { IconStyleContext } from '@/lib/icon-style-context';
const mutate = vi.hoisted(() => vi.fn());
vi.mock('@/hooks/useApiMutation', () => ({ useApiMutation: () => ({ mutate }) }));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: { id: 'owner' } }) }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
import { TooltipProvider } from '@/components/ui/tooltip';
import { DiscussionActions } from '../DiscussionActions';
const id = '10000000-0000-4000-8000-000000000001';
const metadata = { type: 'proactive_discussion', discussion_id: id };
// The pause the opening promised when it was archived.
const promised = { ...metadata, discussion_pause_hours: 24 };
beforeEach(() => vi.clearAllMocks());
describe('personal discussion feedback', () => {
  it('does not alter an existing proactive notification', () => {
    const { container } = render(<DiscussionActions metadata={{ type: 'proactive_heartbeat' }} />);
    expect(container).toBeEmptyDOMElement();
  });
  it('records the exact opening and waits for an acknowledged receipt', async () => {
    mutate.mockResolvedValueOnce({
      id,
      message_id: id,
      created_at: '2026-10-20T12:00:00Z',
      content: 'Fiction',
      state: 'dismissed',
      feedback: 'not_now',
    });
    render(<DiscussionActions metadata={promised} />, { wrapper: TooltipProvider });
    const button = screen.getByRole('button', { name: 'discussions.feedback.not_now' });
    fireEvent.click(button);
    await waitFor(() => expect(button).toHaveAttribute('aria-pressed', 'true'));
    expect(mutate).toHaveBeenCalledWith(`/proactive-discussions/openings/${id}/feedback`, {
      feedback: 'not_now',
      expected_feedback: null,
    });
  });
  it('promises no duration on an opening archived before it carried one', () => {
    render(<DiscussionActions metadata={metadata} />, { wrapper: TooltipProvider });
    expect(
      screen.getByRole('button', { name: 'discussions.feedback.not_now_plain' })
    ).toBeVisible();
    expect(
      screen.queryByRole('button', { name: 'discussions.feedback.not_now' })
    ).not.toBeInTheDocument();
  });
  it('never claims success after a failed write', async () => {
    mutate.mockRejectedValueOnce(new Error('offline'));
    render(<DiscussionActions metadata={metadata} />, { wrapper: TooltipProvider });
    const button = screen.getByRole('button', { name: 'discussions.feedback.avoid_topic' });
    fireEvent.click(button);
    await screen.findByRole('alert');
    expect(button).toHaveAttribute('aria-pressed', 'false');
    expect(button).not.toHaveClass('border-primary', 'bg-primary/10');
  });
});

it('sits at the right end of the bubble actions, wrapping as one block', () => {
  // Owner decision 2026-10-24 (replacing 2026-10-21): in the bubble's flex-wrap
  // action row the answers are pushed to the RIGHT end — on the actions' line
  // when there is room, on the next one, still right-aligned, when there is not.
  render(<DiscussionActions metadata={metadata} />, { wrapper: TooltipProvider });
  const group = screen.getByRole('button', { name: 'discussions.feedback.useful' }).parentElement;
  expect(group).toHaveClass('ml-auto', 'justify-end', 'flex-wrap');
  expect(group).not.toHaveClass('basis-full');
  expect(group).not.toHaveClass('w-full');
});

it('reply only prefills an explicit quote and never sends or writes feedback', () => {
  const prefill = vi.fn();
  render(
    <DiscussionActions
      metadata={metadata}
      content="A fictional personal opening"
      onPrefillComposer={prefill}
    />,
    { wrapper: TooltipProvider }
  );
  fireEvent.click(screen.getByRole('button', { name: 'discussions.reply' }));
  expect(prefill).toHaveBeenCalledOnce();
  expect(mutate).not.toHaveBeenCalled();
});

it.each(ICON_STYLES)(
  'shows a recorded answer and keeps keyboard focus with %s icons',
  async style => {
    const keyboard = userEvent.setup();
    mutate.mockResolvedValueOnce({
      id,
      message_id: id,
      created_at: '2026-10-20T12:00:00Z',
      content: 'Fiction',
      state: 'engaged',
      feedback: 'useful',
    });
    render(
      <IconStyleContext.Provider value={style}>
        <DiscussionActions metadata={promised} />
      </IconStyleContext.Provider>,
      { wrapper: TooltipProvider }
    );
    const useful = screen.getByRole('button', { name: 'discussions.feedback.useful' });
    // The same box as Copy or Keep, told apart by its ground alone.
    expect(useful.className).toContain('rounded-md');
    expect(useful.className).toContain('border-border/30');
    expect(useful.className).toContain('color-mix');
    expect(useful).not.toHaveClass('border-primary', 'bg-primary/10');
    expect(useful.querySelector('svg')).toHaveAttribute('data-icon-name', 'ThumbsUp');
    expect(useful.querySelector('svg')).toHaveAttribute('data-icon-style', style);
    await keyboard.tab();
    expect(useful).toHaveFocus();
    expect(useful).toHaveClass('focus-visible:ring-2', 'focus-visible:ring-ring');
    await keyboard.keyboard('{Enter}');
    await waitFor(() => expect(useful).toHaveAttribute('aria-pressed', 'true'));
    expect(useful).toHaveClass('border-primary', 'bg-primary/10', 'dark:bg-primary/15');
    // Answered: announced as unavailable, never disabled under the focus it holds.
    expect(useful).toHaveFocus();
    expect(useful).not.toBeDisabled();
    expect(useful).toHaveAttribute('aria-disabled', 'true');
    const incorrect = screen.getByRole('button', { name: 'discussions.feedback.incorrect' });
    expect(incorrect).not.toHaveClass('border-primary', 'bg-primary/10');
    fireEvent.click(incorrect);
    expect(mutate).toHaveBeenCalledOnce();
  }
);
