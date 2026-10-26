import { act, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useEyesChatStore, RESTING_CHAT } from '@/stores/eyesChatStore';
import { useEyesChatState } from '../useEyesChatState';
import type { EyesWidgetProps } from '../EyesWidget';

const route = vi.hoisted(() => ({ pathname: '/fr/dashboard/chat' }));
vi.mock('next/navigation', () => ({ usePathname: () => route.pathname }));
vi.mock('next/dynamic', () => ({
  default: () => (props: EyesWidgetProps) => (
    <div
      data-testid="application-avatar"
      data-status={props.chatStatus}
      data-phase={props.streamPhase}
      data-hitl={String(props.hitlAwaiting)}
      data-dock={String(props.dockToChat)}
    />
  ),
}));
vi.mock('@/components/companion/CompanionPresence', () => ({
  isChatRoute: (pathname: string | null) => !!pathname?.includes('/dashboard/chat'),
  CompanionPresence: ({
    renderAvatar,
    attentionOnly,
    onWorkingChange,
  }: {
    renderAvatar: boolean;
    attentionOnly: boolean;
    onWorkingChange: (working: boolean) => void;
  }) => (
    <button
      type="button"
      data-testid="notification-shortcut"
      data-avatar={String(renderAvatar)}
      data-attention-only={String(attentionOnly)}
      onClick={() => onWorkingChange(true)}
    >
      Start background work
    </button>
  ),
}));

import { ApplicationEyes } from '../ApplicationEyes';

function ChatPublisher(props: EyesWidgetProps) {
  useEyesChatState(props);
  return null;
}

beforeEach(() => {
  route.pathname = '/fr/dashboard/chat';
  useEyesChatStore.getState().reset();
});

describe('the application avatar', () => {
  it('suspends duplicate graphics while preserving the notification owner', () => {
    const { rerender } = render(<ApplicationEyes hidePresentation />);
    expect(screen.queryByTestId('application-avatar')).not.toBeInTheDocument();
    expect(screen.getByTestId('notification-shortcut')).toBeInTheDocument();
    expect(screen.getByTestId('notification-shortcut')).toHaveAttribute(
      'data-attention-only',
      'true'
    );
    rerender(<ApplicationEyes />);
    expect(screen.getAllByTestId('application-avatar')).toHaveLength(1);
    expect(screen.getByTestId('notification-shortcut')).toHaveAttribute(
      'data-attention-only',
      'false'
    );
  });
  it('shows background work through the same face with a compact notification shortcut', () => {
    route.pathname = '/fr/dashboard/settings';
    render(<ApplicationEyes />);
    const face = screen.getByTestId('application-avatar');
    const shortcut = screen.getByTestId('notification-shortcut');
    expect(shortcut).toHaveAttribute('data-avatar', 'false');
    act(() => shortcut.click());
    expect(screen.getByTestId('application-avatar')).toBe(face);
    expect(face).toHaveAttribute('data-status', 'streaming');
    expect(face).toHaveAttribute('data-phase', 'progress');
  });
  it('follows real chat phases and HITL without remounting its face', () => {
    const { rerender } = render(
      <>
        <ApplicationEyes />
        <ChatPublisher chatStatus="sending" streamPhase="progress" hitlAwaiting={false} />
      </>
    );
    const face = screen.getByTestId('application-avatar');
    expect(face).toHaveAttribute('data-status', 'sending');
    rerender(
      <>
        <ApplicationEyes />
        <ChatPublisher chatStatus="streaming" streamPhase="answer" hitlAwaiting />
      </>
    );
    expect(screen.getByTestId('application-avatar')).toBe(face);
    expect(face).toHaveAttribute('data-status', 'streaming');
    expect(face).toHaveAttribute('data-phase', 'answer');
    expect(face).toHaveAttribute('data-hitl', 'true');
  });

  it('keeps one instance on every dashboard route and ignores stale chat phases off chat', () => {
    useEyesChatStore.getState().publish({
      chatStatus: 'streaming',
      streamPhase: 'progress',
      hitlAwaiting: true,
    });
    const { rerender } = render(<ApplicationEyes />);
    const face = screen.getByTestId('application-avatar');
    for (const segment of ['settings', '', 'faq', 'relations', 'meetings', 'notifications']) {
      route.pathname = `/fr/dashboard/${segment}`;
      rerender(<ApplicationEyes />);
      expect(screen.getAllByTestId('application-avatar')).toHaveLength(1);
      expect(screen.getByTestId('application-avatar')).toBe(face);
      expect(face).toHaveAttribute('data-dock', 'false');
      expect(face).toHaveAttribute('data-status', 'idle');
      expect(face).toHaveAttribute('data-hitl', 'false');
    }
    route.pathname = '/fr/dashboard/chat';
    rerender(<ApplicationEyes />);
    expect(face).toHaveAttribute('data-dock', 'true');
    expect(face).toHaveAttribute('data-status', 'streaming');
  });

  it('cleans up the page-owned phase subscription when leaving chat', () => {
    const { rerender } = render(
      <>
        <ApplicationEyes />
        <ChatPublisher chatStatus="streaming" streamPhase="progress" hitlAwaiting />
      </>
    );
    route.pathname = '/fr/dashboard/settings';
    rerender(<ApplicationEyes />);
    expect(useEyesChatStore.getState().state).toEqual(RESTING_CHAT);
    act(() => useEyesChatStore.getState().publish({ ...RESTING_CHAT, chatStatus: 'error' }));
    expect(screen.getByTestId('application-avatar')).toHaveAttribute('data-status', 'idle');
  });
});
