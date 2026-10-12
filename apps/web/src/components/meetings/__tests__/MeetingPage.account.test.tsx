import { Suspense } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, renderWithProviders, screen } from '@/__tests__/test-utils';
import { meetingDetail } from '@/__tests__/fixtures/meeting-detail';
import type { UseMeetingReturn } from '@/hooks/useMeetings';
import type { MeetingReport } from '@/types/meetings';

const { auth, query } = vi.hoisted(() => ({ auth: { owner: 'one' }, query: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: { id: auth.owner } }) }));
vi.mock('@/hooks/useMeetings', () => ({ useMeeting: query }));
vi.mock('@/hooks/useBackOrigin', () => ({ useBackOrigin: () => null }));
vi.mock('@/hooks/useLanguageParam', () => ({ useLanguageParam: () => 'en' }));
vi.mock('@/hooks/useLocalizedRouter', () => ({ useLocalizedRouter: () => ({ push: vi.fn() }) }));
vi.mock('@/components/meetings/ReformatDialog', () => ({ ReformatDialog: () => null }));
vi.mock('@/components/meetings/MeetingDetailLinks', () => ({ MeetingLineage: () => null }));
vi.mock('@/components/meetings/MeetingDetailPanels', () => ({
  FailedPanel: () => null,
  MeetingHeader: () => null,
  ProcessingPanel: () => null,
  ReadyTail: () => null,
  MinutesPanel: ({
    report,
    draft,
    onDraftChange,
  }: {
    report: MeetingReport;
    draft: MeetingReport | null;
    onDraftChange: (value: MeetingReport) => void;
  }) => (
    <>
      <p>{draft?.title ?? report.title}</p>
      <button onClick={() => onDraftChange({ ...report, title: 'Private unsaved A' })}>
        Edit controlled minutes
      </button>
    </>
  ),
}));
import MeetingPage from '@/app/[lng]/dashboard/meetings/[id]/page';

function state(title: string): UseMeetingReturn {
  return {
    meeting: meetingDetail({ report: { title, participants: [], sections: [] } }),
    isLoading: false,
    isNotFound: false,
    isActing: false,
    error: null,
    refetch: vi.fn(),
    patch: vi.fn(),
    resetReport: vi.fn(),
    regenerate: vi.fn(),
    reformat: vi.fn(),
    retry: vi.fn(),
    email: vi.fn(),
    deleteTranscript: vi.fn(),
    remove: vi.fn(),
  };
}
beforeEach(() => {
  vi.clearAllMocks();
  auth.owner = 'one';
  query.mockReturnValue(state('Account A minutes'));
});

describe('meeting page private draft lifetime', () => {
  it('discards unsaved account A minutes when B arrives and when A returns', async () => {
    const params = Promise.resolve({ lng: 'en', id: 'm1' });
    const page = (
      <Suspense fallback={<p>Loading</p>}>
        <MeetingPage params={params} />
      </Suspense>
    );
    const rendered: { view?: ReturnType<typeof renderWithProviders> } = {};
    await act(async () => {
      rendered.view = renderWithProviders(page);
    });
    if (!rendered.view) throw new Error('Meeting page did not mount');
    const { user, rerender } = rendered.view;
    await screen.findByText('Account A minutes');
    await user.click(screen.getByRole('button', { name: 'Edit controlled minutes' }));
    expect(screen.getByText('Private unsaved A')).toBeVisible();
    auth.owner = 'two';
    query.mockReturnValue(state('Account B minutes'));
    rerender(
      <Suspense fallback={<p>Loading</p>}>
        <MeetingPage params={params} />
      </Suspense>
    );
    await screen.findByText('Account B minutes');
    expect(screen.queryByText('Private unsaved A')).toBeNull();
    auth.owner = 'one';
    query.mockReturnValue(state('Account A minutes'));
    rerender(
      <Suspense fallback={<p>Loading</p>}>
        <MeetingPage params={params} />
      </Suspense>
    );
    await screen.findByText('Account A minutes');
    expect(screen.queryByText('Private unsaved A')).toBeNull();
  });
});
