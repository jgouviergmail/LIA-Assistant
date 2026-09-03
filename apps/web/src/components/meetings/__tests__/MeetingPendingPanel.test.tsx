/**
 * The panel of minutes that do not exist yet (ADR-259): a new row from a
 * reformat is READY with no report while the server writes; a failed write
 * leaves the row explainable, with a retry on the same template and a delete.
 */

import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import type { MeetingActions } from '@/components/meetings/useMeetingActions';
import type { MeetingDetail } from '@/types/meetings';

import { MeetingPendingPanel } from '../MeetingPendingPanel';

function actions(): MeetingActions {
  return {
    save: vi.fn(),
    resetReport: vi.fn(),
    regenerate: vi.fn(),
    reformat: vi.fn(),
    retry: vi.fn(),
    email: vi.fn(),
    deleteTranscript: vi.fn(),
    remove: vi.fn(),
  };
}

function pending(over: Partial<MeetingDetail> = {}) {
  return {
    status: 'ready',
    stage: 'synthesizing',
    report: null,
    last_error_code: null,
    template_ref: 'builtin:transcript_clean',
    template_name: 'Clean transcript',
    ...over,
  } as Pick<
    MeetingDetail,
    'status' | 'stage' | 'report' | 'last_error_code' | 'template_ref' | 'template_name'
  >;
}

describe('MeetingPendingPanel', () => {
  it('shows the write in progress with the format being applied', () => {
    renderWithProviders(<MeetingPendingPanel lng="en" meeting={pending()} actions={actions()} />);
    expect(screen.getByText('meetings.detail.pending_title')).toBeInTheDocument();
    expect(screen.getByText('meetings.detail.pending_hint')).toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('explains a failed write and retries with the same template', async () => {
    const acts = actions();
    const { user } = renderWithProviders(
      <MeetingPendingPanel
        lng="en"
        meeting={pending({ stage: null, last_error_code: 'synthesis_failed' })}
        actions={acts}
      />
    );
    expect(screen.getByText('meetings.detail.pending_failed_title')).toBeInTheDocument();
    expect(screen.getByText('meetings.errors.synthesis_failed')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'meetings.detail.try_again' }));
    expect(acts.reformat).toHaveBeenCalledWith({
      template_ref: 'builtin:transcript_clean',
      mode: 'replace',
    });
    await user.click(screen.getByRole('button', { name: 'meetings.detail.delete' }));
    expect(acts.remove).toHaveBeenCalledTimes(1);
  });

  it('offers no retry when the row carries no template to retry with', () => {
    renderWithProviders(
      <MeetingPendingPanel
        lng="en"
        meeting={pending({ stage: null, last_error_code: 'synthesis_failed', template_ref: null })}
        actions={actions()}
      />
    );
    expect(
      screen.queryByRole('button', { name: 'meetings.detail.try_again' })
    ).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'meetings.detail.delete' })).toBeInTheDocument();
  });
});
