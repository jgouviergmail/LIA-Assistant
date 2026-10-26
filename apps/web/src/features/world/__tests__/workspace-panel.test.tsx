import { Suspense, lazy, type ComponentType } from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { WorldWorkspacePanel } from '../WorldWorkspacePanel';

const state = vi.hoisted(() => ({
  user: { id: 'owner', is_active: true },
  features: { meetings_enabled: true, workboard_enabled: true, sms_enabled: true },
}));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: state.user }) }));
vi.mock('@/hooks/useAppConfig', () => ({
  useAppConfig: () => ({ config: { features: state.features } }),
}));
vi.mock('@/i18n/client', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('next/dynamic', () => ({
  default: (load: () => Promise<ComponentType<Record<string, unknown>>>) => {
    const Loaded = lazy(async () => ({ default: await load() }));
    return function DynamicContent(props: Record<string, unknown>) {
      return (
        <Suspense fallback="Loading native">
          <Loaded {...props} />
        </Suspense>
      );
    };
  },
}));
vi.mock('@/components/meetings/MeetingsWorkspace', () => ({
  MeetingsWorkspace: ({
    active,
    onOpenMeeting,
    onEmptyAction,
  }: {
    active: boolean;
    onOpenMeeting(id: string): void;
    onEmptyAction(): void;
  }) => (
    <div>
      <span>{active ? 'List active' : 'List paused'}</span>
      <button onClick={() => onOpenMeeting('meeting-a')}>First meeting</button>
      <button onClick={onEmptyAction}>Prepare meeting</button>
    </div>
  ),
}));
vi.mock('@/components/meetings/MeetingDetailWorkspace', () => ({
  MeetingDetailWorkspace: ({
    id,
    onBack,
    onOpenMeeting,
  }: {
    id: string;
    onBack(): void;
    onOpenMeeting(id: string): void;
  }) => (
    <div>
      <h2>{id}</h2>
      <button onClick={onBack}>Back to meetings</button>
      <button onClick={() => onOpenMeeting('meeting-b')}>Related meeting</button>
    </div>
  ),
}));
vi.mock('@/components/relations/RelationsWorkspace', () => ({
  RelationsWorkspace: ({
    scrollPort,
  }: {
    scrollPort: { read(): number; write(top: number): void };
  }) => <button onClick={() => scrollPort.write(scrollPort.read() + 120)}>Move reader</button>,
}));
vi.mock('@/components/notifications/NotificationsHub', () => ({
  NotificationsHub: ({ onOpenJournal }: { onOpenJournal(): void }) => (
    <button onClick={onOpenJournal}>Open registers</button>
  ),
}));
vi.mock('@/components/workboard/WorkboardPage', () => ({
  WorkboardPage: ({ embedded }: { embedded: boolean }) => (
    <p>{embedded ? 'Embedded workboard' : 'Standalone'}</p>
  ),
}));
vi.mock('@/components/effects/RegistersPage', () => ({
  RegistersPage: () => <p>Native registers</p>,
}));
vi.mock('@/components/sms/SmsArchive', () => ({ SmsArchive: () => <p>Private SMS archive</p> }));

beforeEach(() => {
  state.user = { id: 'owner', is_active: true };
  state.features = { meetings_enabled: true, workboard_enabled: true, sms_enabled: true };
});
const props = { lng: 'en' as const, ownerId: 'owner', onNavigate: vi.fn(), onCompose: vi.fn() };

it('pauses the meeting list during detail, supports related meetings and restores focus on return', async () => {
  const view = render(<WorldWorkspacePanel {...props} workspace="meetings" />);
  const opener = await screen.findByRole('button', { name: 'First meeting' });
  opener.focus();
  fireEvent.click(opener);
  expect(await screen.findByRole('heading', { name: 'meeting-a' })).toBeVisible();
  expect(screen.getByText('List paused')).not.toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: 'Related meeting' }));
  expect(await screen.findByRole('heading', { name: 'meeting-b' })).toBeVisible();
  await act(async () => {
    fireEvent.click(screen.getByRole('button', { name: 'Back to meetings' }));
    await new Promise(resolve => requestAnimationFrame(resolve));
  });
  expect(opener).toHaveFocus();
  expect(screen.getByText('List active')).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: 'Prepare meeting' }));
  expect(props.onCompose).toHaveBeenCalledTimes(1);
  state.user = { id: 'peer', is_active: true };
  view.rerender(<WorldWorkspacePanel {...props} workspace="meetings" />);
  expect(screen.queryByText('List active')).not.toBeInTheDocument();
});

it('uses the embedded scroll port and retains private navigation inside the world', async () => {
  const view = render(<WorldWorkspacePanel {...props} workspace="relations" />);
  const move = await screen.findByRole('button', { name: 'Move reader' });
  const scroller = view.container.firstElementChild as HTMLElement;
  scroller.scrollTop = 270;
  fireEvent.click(move);
  expect(scroller.scrollTop).toBe(390);
  view.rerender(<WorldWorkspacePanel {...props} workspace="alerts" />);
  fireEvent.click(await screen.findByRole('button', { name: 'Open registers' }));
  expect(props.onNavigate).toHaveBeenCalledWith('registers');
  view.rerender(<WorldWorkspacePanel {...props} workspace="registers" />);
  expect(await screen.findByText('Native registers')).toBeVisible();
  view.rerender(<WorldWorkspacePanel {...props} workspace="workboard" />);
  expect(await screen.findByText('Embedded workboard')).toBeVisible();
});

it('does not expose SMS after the feature is withdrawn or the account is deactivated', async () => {
  const view = render(<WorldWorkspacePanel {...props} workspace="sms" />);
  expect(await screen.findByText('Private SMS archive')).toBeVisible();
  state.features.sms_enabled = false;
  view.rerender(<WorldWorkspacePanel {...props} workspace="sms" />);
  expect(screen.getByRole('status')).toHaveTextContent('world.functions.unavailable');
  expect(screen.queryByText('Private SMS archive')).not.toBeInTheDocument();
  state.user.is_active = false;
  view.rerender(<WorldWorkspacePanel {...props} workspace="sms" />);
  expect(view.container).toBeEmptyDOMElement();
});

it('opens a freshly imported meeting locally and can return to the retained list', async () => {
  render(<WorldWorkspacePanel {...props} workspace="meetings" initialMeetingId="imported-meeting" />);
  expect(await screen.findByRole('heading', { name: 'imported-meeting' })).toBeVisible();
  expect(screen.getByText('List paused')).not.toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: 'Back to meetings' }));
  expect(await screen.findByText('List active')).toBeVisible();
});
