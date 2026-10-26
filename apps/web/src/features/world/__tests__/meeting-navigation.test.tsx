import { Suspense, createRef, lazy, type ComponentProps, type ComponentType } from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { it, expect, vi } from 'vitest';
import { makeUser } from '@/__tests__/factories';
import { appConfigFixture } from '@/__tests__/fixtures/app-config';
import { MeetingOpenLink } from '@/components/meetings/MeetingNavigation';
import { WorldFunctionControls, type WorldFunctionHandle } from '../WorldFunctionControls';
import type { WorldNativePanel } from '../WorldNativePanel';
import type { WorldWorkspacePanel } from '../WorldWorkspacePanel';

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: makeUser({ id: 'owner', is_active: true }) }),
}));
vi.mock('@/hooks/useAppConfig', () => ({
  useAppConfig: () => ({
    config: appConfigFixture({
      features: { meetings_enabled: true, meetings_import_enabled: true },
    }),
    loading: false,
    error: null,
  }),
}));
vi.mock('@/hooks/useSettingsAvailability', () => ({
  useSettingsAvailability: () => ({ isSuperuser: false, radioEnabled: false }),
}));
vi.mock('@/i18n/client', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('next/dynamic', () => ({
  default: (load: () => Promise<ComponentType<Record<string, unknown>>>) => {
    const Loaded = lazy(async () => ({ default: await load() }));
    return function DynamicContent(props: Record<string, unknown>) {
      return (
        <Suspense fallback="Loading activity">
          <Loaded {...props} />
        </Suspense>
      );
    };
  },
}));
vi.mock('../WorldNativePanel', () => ({
  WorldNativePanel: ({ selection }: ComponentProps<typeof WorldNativePanel>) => (
    <div>
      <p>Native activity: {selection}</p>
      <MeetingOpenLink id="imported-meeting" href="/en/dashboard/meetings/imported-meeting">
        Open imported meeting
      </MeetingOpenLink>
    </div>
  ),
}));
vi.mock('../WorldWorkspacePanel', () => ({
  WorldWorkspacePanel: ({
    workspace,
    initialMeetingId,
  }: ComponentProps<typeof WorldWorkspacePanel>) => (
    <h2>
      {workspace}: {initialMeetingId ?? 'list'}
    </h2>
  ),
}));

it('keeps imported meetings inside the world, restores its previous activity and clears a new opening', async () => {
  const handle = createRef<WorldFunctionHandle>();
  render(
    <WorldFunctionControls
      lng="en"
      ownerId="owner"
      enabled
      zone="arrival"
      onOpen={vi.fn()}
      functionRef={handle}
    />
  );
  fireEvent.click(screen.getByRole('button', { name: 'world.functions.talk' }));
  // The actual navigation boundary chooses a local action inside this host.
  fireEvent.click(await screen.findByRole('button', { name: 'Open imported meeting' }));
  expect(await screen.findByRole('heading', { name: 'meetings: imported-meeting' })).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: 'common.back' }));
  expect(await screen.findByText('Native activity: lia')).toBeVisible();
  fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape', code: 'Escape' });
  act(() => {
    expect(handle.current?.openScene({ kind: 'workspace', id: 'meetings' })).toBe(true);
  });
  expect(await screen.findByRole('heading', { name: 'meetings: list' })).toBeVisible();
  expect(screen.queryByText('meetings: imported-meeting')).not.toBeInTheDocument();
});
