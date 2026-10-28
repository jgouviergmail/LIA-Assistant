import { fireEvent, render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import {
  DashboardLink,
  DashboardNavigationProvider,
  dashboardDestination,
  useDashboardChat,
} from '../DashboardNavigation';
import { CardItemActions } from '../cards/CardItemActions';
import { NotebookPen } from 'lucide-react';
const { nativeChat } = vi.hoisted(() => ({ nativeChat: vi.fn() }));
vi.mock('@/lib/chat-deep-link', () => ({ openChatDeepLink: nativeChat }));
const id = '10000000-0000-4000-8000-000000000001';

it('preserves typed workboard filters/tickets, settings, drafts, messages and meetings', () => {
  expect(
    dashboardDestination(
      '/fr/dashboard/workboard?assignee=lia&overdue=1&status=open&status=invalid&q=hello'
    )
  ).toEqual({
    kind: 'workboard',
    filters: { assignee: 'lia', sort: 'position', overdue: true, q: 'hello' },
  });
  expect(dashboardDestination('/en/dashboard/workboard/' + id)).toMatchObject({
    kind: 'workboard',
    ticketId: id,
  });
  expect(dashboardDestination('/de/dashboard/settings?section=memories')).toEqual({
    kind: 'settings',
    token: 'memories',
  });
  expect(dashboardDestination('/dashboard/settings?section=sms&message=' + id)).toEqual({
    kind: 'sms',
    messageId: id,
  });
  expect(dashboardDestination('/it/dashboard/chat?draft=Hello%20Alice')).toEqual({
    kind: 'draft',
    draft: 'Hello Alice',
  });
  expect(dashboardDestination('/es/dashboard/meetings/' + id)).toEqual({ kind: 'meeting', id });
  expect(dashboardDestination('/zh/dashboard/actions')).toEqual({ kind: 'registers' });
});
it.each([
  '//foreign.test/en/dashboard/chat?draft=x',
  '/\\foreign.test/en/dashboard/chat',
  'javascript:alert(1)',
  'https://foreign.test/en/dashboard/settings?section=memories',
  '/en/dashboard/chat?intent=EXECUTE',
  '/en/dashboard/chat?voice=1',
  '/en/dashboard/settings?section=unknown',
  '/en/dashboard/faq',
  '/en/dashboard/capabilities',
  '/en/dashboard/workboard/%ZZ',
  '/en/dashboard/workboard/%2foutside',
])('keeps unsupported or executable native navigation outside the embedded adapter: %s', href => {
  expect(dashboardDestination(href)).toBeNull();
});
it('keeps a real link and dispatches a supported destination only after the click', () => {
  const navigate = vi.fn(() => true);
  render(
    <DashboardNavigationProvider onNavigate={navigate}>
      <DashboardLink href="/fr/dashboard/settings?section=memories">Memories</DashboardLink>
      <DashboardLink href="/fr/dashboard/faq">Help</DashboardLink>
    </DashboardNavigationProvider>
  );
  const link = screen.getByRole('link', { name: 'Memories' });
  expect(link).toHaveAttribute('href', '/fr/dashboard/settings?section=memories');
  expect(navigate).not.toHaveBeenCalled();
  fireEvent.click(link);
  expect(navigate).toHaveBeenCalledExactlyOnceWith({ kind: 'settings', token: 'memories' });
  expect(screen.getByText('world.dashboard.leaves_world')).toBeInTheDocument();
});
it('retains exact executable native links and opens ordinary drafts locally', () => {
  function Actions() {
    const open = useDashboardChat();
    return (
      <>
        <button onClick={() => open('/fr/dashboard/chat?draft=Alice')}>Draft</button>
        <button onClick={() => open('/fr/dashboard/chat?intent=Bob%20%26%20Alice')}>Execute</button>
      </>
    );
  }
  const navigate = vi.fn(() => true);
  render(
    <DashboardNavigationProvider onNavigate={navigate}>
      <Actions />
    </DashboardNavigationProvider>
  );
  fireEvent.click(screen.getByRole('button', { name: 'Draft' }));
  expect(navigate).toHaveBeenCalledWith({ kind: 'draft', draft: 'Alice' });
  expect(nativeChat).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Execute' }));
  expect(nativeChat).toHaveBeenCalledExactlyOnceWith('/fr/dashboard/chat?intent=Bob%20%26%20Alice');
});
it('visibly labels an executable native departure in an embedded card menu', async () => {
  const execute = vi.fn();
  render(
    <DashboardNavigationProvider onNavigate={() => true}>
      <CardItemActions
        actions={[
          { icon: NotebookPen, label: 'Prepare meeting', opensChat: true, onSelect: execute },
        ]}
      />
    </DashboardNavigationProvider>
  );
  fireEvent.pointerDown(screen.getByRole('button', { name: 'dashboard.briefing.actions.more' }), {
    button: 0,
    ctrlKey: false,
  });
  const action = await screen.findByRole('menuitem', {
    name: 'world.dashboard.open_chat · Prepare meeting',
  });
  fireEvent.click(action);
  expect(execute).toHaveBeenCalledOnce();
});
