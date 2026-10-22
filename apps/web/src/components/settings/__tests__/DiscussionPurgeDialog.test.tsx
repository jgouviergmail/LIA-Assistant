import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { DiscussionPurgeDialog, type DiscussionPurgeReview } from '../DiscussionPurgeDialog';

vi.mock('@/i18n/client', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));

const review: DiscussionPurgeReview = {
  scope: ['fictional-item'],
  expected_epoch: 3,
  expected_generation: 7,
  affected_count: 2,
  pending: false,
  failed: false,
  token: 1,
};

describe('exact context purge review', () => {
  it('requires a completed preview and submits the reviewed scope and fences', async () => {
    const contextAction = vi.fn(async () => true);
    const onClose = vi.fn();
    const controls = { saving: false, error: false, contextAction };
    const { rerender } = render(
      <DiscussionPurgeDialog
        lng="fr"
        review={{ ...review, pending: true, affected_count: null }}
        controls={controls}
        onClose={onClose}
        restoreFocus={() => {}}
      />
    );
    const confirm = screen.getByRole('button', { name: 'discussions.confirm_purge' });
    expect(confirm).toBeDisabled();
    rerender(
      <DiscussionPurgeDialog
        lng="fr"
        review={review}
        controls={controls}
        onClose={onClose}
        restoreFocus={() => {}}
      />
    );
    await userEvent.click(confirm);
    await waitFor(() => expect(onClose).toHaveBeenCalledOnce());
    expect(contextAction).toHaveBeenCalledWith('purge', ['fictional-item'], {
      expected_epoch: 3,
      expected_generation: 7,
    });
  });

  it('keeps the review open after an unacknowledged mutation', async () => {
    const onClose = vi.fn();
    render(
      <DiscussionPurgeDialog
        lng="fr"
        review={review}
        controls={{ saving: false, error: true, contextAction: vi.fn(async () => false) }}
        onClose={onClose}
        restoreFocus={() => {}}
      />
    );
    await userEvent.click(screen.getByRole('button', { name: 'discussions.confirm_purge' }));
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByRole('alert')).toHaveTextContent('discussions.load_error');
  });
});
