/**
 * Interactive guided mission — component contract (multi-mission).
 *
 * What must hold:
 * - persistent honesty labels, fixed non-editable request, progressive
 *   sources, storyboard trace, in-order decision cards, LIA's rich reply,
 *   a truthful receipt, redesigned actions (one solid primary), restart and
 *   back-to-picker;
 * - cancel explicitly means "not applied", confirm applies only to the
 *   synthetic workspace — never sent externally;
 * - keyboard-only completion, focus moves to each phase heading, exactly one
 *   polite status region, focus returns after closing the proof drawer;
 * - reduced motion: no timed advance — explicit Continue buttons instead;
 * - fetch / EventSource / WebSocket stay untouched by every interaction;
 * - the injected onEvent callback receives the bounded per-run funnel,
 *   including the per-mission started/completed variants.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { act, fireEvent, renderWithProviders, screen, within } from '@/__tests__/test-utils';
import { ShowroomMission } from '@/components/showroom/ShowroomMission';
import { getShowroomMission } from '@/components/showroom/missions';

// Reduced motion by default: deterministic Continue-driven walkthrough.
const mediaQueryMock = vi.fn((query: string) => query.includes('prefers-reduced-motion'));
vi.mock('@/hooks/useMediaQuery', () => ({
  useMediaQuery: (q: string) => mediaQueryMock(q),
}));

// The rich reply builder is tested in response-html.test.ts; here the
// renderer (next/dynamic over the chat pipeline) is replaced by a probe so
// the storyboard walkthrough stays synchronous.
vi.mock('@/components/showroom/ShowroomRichResponse', () => ({
  ShowroomRichResponse: ({ html }: { html: string }) => (
    <div data-testid="showroom-rich-response" data-html={html} />
  ),
}));

const MORNING = getShowroomMission('overloaded_morning');
const PROACTIVE = getShowroomMission('proactive_alert');
const PHONE = getShowroomMission('phone_booking');

const fetchSpy = vi.fn();
const wsSpy = vi.fn();
const esSpy = vi.fn();
const noopChange = vi.fn();

function renderMission(def = MORNING, onEvent?: (e: string) => void, onChangeMission = noopChange) {
  return renderWithProviders(
    <ShowroomMission def={def} onEvent={onEvent} onChangeMission={onChangeMission} />
  );
}

async function completeMission(
  user: ReturnType<typeof renderWithProviders>['user'],
  {
    email = 'confirm',
    calendar = 'cancel',
  }: { email?: 'confirm' | 'edit' | 'cancel'; calendar?: 'confirm' | 'cancel' } = {}
) {
  await user.click(screen.getByRole('button', { name: 'showroom.start' }));
  // 4 source reveals + reading->planning + planning->decision[0].
  for (let i = 0; i < 6; i += 1) {
    await user.click(screen.getByRole('button', { name: 'showroom.continue' }));
  }
  const emailCard = screen.getByRole('region', {
    name: 'chat.hitl.title.draft_critique',
  });
  if (email === 'edit') {
    await user.click(within(emailCard).getByRole('button', { name: 'chat.hitl.actions.edit' }));
    await user.type(within(emailCard).getByRole('textbox'), 'Merci de proposer 10:00');
    await user.click(within(emailCard).getByRole('button', { name: 'chat.hitl.edit.submit' }));
  } else {
    await user.click(
      within(emailCard).getByRole('button', {
        name: `chat.hitl.actions.${email}`,
      })
    );
  }
  const calendarCard = screen.getByRole('region', {
    name: 'chat.hitl.title.tool_confirmation',
  });
  await user.click(
    within(calendarCard).getByRole('button', {
      name: `chat.hitl.actions.${calendar}`,
    })
  );
}

describe('ShowroomMission', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', fetchSpy);
    vi.stubGlobal('WebSocket', wsSpy);
    vi.stubGlobal('EventSource', esSpy);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    fetchSpy.mockClear();
    wsSpy.mockClear();
    esSpy.mockClear();
    mediaQueryMock.mockClear();
    noopChange.mockClear();
  });

  describe('the storyboard stays in view', () => {
    // Owner request 2026-08-07: a mission reveals sources, then planning, then
    // decision cards one after another, all appended BELOW. A visitor had to
    // chase it down the page.
    it('does not move the viewport before the mission starts', () => {
      const scrollIntoView = vi.fn();
      Object.defineProperty(Element.prototype, 'scrollIntoView', {
        configurable: true,
        writable: true,
        value: scrollIntoView,
      });

      renderMission();

      expect(scrollIntoView).not.toHaveBeenCalled();
    });

    it('follows the content once the mission is running', () => {
      const scrollIntoView = vi.fn();
      Object.defineProperty(Element.prototype, 'scrollIntoView', {
        configurable: true,
        writable: true,
        value: scrollIntoView,
      });
      renderMission();

      fireEvent.click(screen.getByTestId('showroom-start'));

      expect(scrollIntoView).toHaveBeenCalled();
    });

    it('leaves room below the latest element', () => {
      renderMission();

      const sentinel = screen.getByTestId('showroom-follow-sentinel');

      // `scroll-mb-*` is what `scrollIntoView` honours; a spacer element would
      // instead show as empty space at rest.
      expect(sentinel.className).toMatch(/scroll-mb-/);
      expect(sentinel).toHaveAttribute('aria-hidden', 'true');
    });
  });

  describe('the introduction breathes', () => {
    // Owner request 2026-08-07: the intro was "trop condensé et peu lisible" —
    // title, honesty contract and the request stacked two units apart, so the
    // three read as one grey block. jsdom computes no layout, so the spacing
    // classes are the contract; what they carry is asserted elsewhere.
    it('spaces the header blocks apart', () => {
      const { container } = renderMission();

      const header = container.querySelector('header') as HTMLElement;

      expect(header.className).toMatch(/space-y-[4-9]/);
    });

    it('gives the request room to be read', () => {
      renderMission();

      const request = screen.getByTestId('showroom-request');

      expect(request.className).toContain('leading-relaxed');
      // Token comparison, not a regex: the escaping needed for a word
      // boundary is exactly what slipped a BACKSPACE byte in here once.
      expect(request.className.split(' ')).toContain('p-4');
    });

    it('states the mission title above the phase headings, not level with them', () => {
      renderMission();

      const title = screen.getByRole('heading', { name: 'showroom.m.overloaded_morning.title' });

      expect(title.className).toContain('text-xl');
    });
  });

  it('shows honesty labels, the mission title and the fixed request', () => {
    renderMission();
    for (const key of [
      'showroom.honesty.guided',
      'showroom.honesty.synthetic',
      'showroom.honesty.no_external',
    ]) {
      expect(screen.getByText(key)).toBeInTheDocument();
    }
    expect(
      screen.getByRole('heading', { name: 'showroom.m.overloaded_morning.title' })
    ).toBeInTheDocument();
    expect(screen.getByText('showroom.request')).toBeInTheDocument();
    // The request is plain rendered text — no editable control exists for it.
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  });

  it('renders a proactive mission trigger as LIA-initiated, not a quote', () => {
    renderMission(PROACTIVE);
    expect(screen.getByText('showroom.proactive_intro')).toBeInTheDocument();
    expect(screen.getByText('showroom.m.proactive_alert.request')).toBeInTheDocument();
  });

  it('walks the full canonical path to the rich reply and truthful receipt', async () => {
    const { user } = renderMission();
    await completeMission(user, { email: 'confirm', calendar: 'cancel' });

    // LIA's reply reflects the decisions (probe carries the built HTML).
    const reply = screen.getByTestId('showroom-rich-response');
    expect(reply.getAttribute('data-html')).toContain('lia-response');
    expect(reply.getAttribute('data-html')).toContain(
      'showroom.m.overloaded_morning.response.chip_calendar_cancel'
    );

    const receipt = screen.getByRole('region', {
      name: 'showroom.receipt.title',
    });
    expect(within(receipt).getByText('showroom.receipt.email_applied')).toBeInTheDocument();
    expect(within(receipt).getByText('showroom.receipt.calendar_refused')).toBeInTheDocument();
    expect(within(receipt).getByText('showroom.receipt.no_external')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'showroom.restart' })).toBeInTheDocument();
  });

  it('groups the receipt actions in the arbitrated order, without a beta CTA', async () => {
    const { user } = renderMission();
    await completeMission(user);
    expect(screen.getByRole('heading', { name: 'showroom.actions.title' })).toBeInTheDocument();
    // Owner order (2026-08-06): install → releases → source → proofs. The
    // beta CTA is gone — the demo funnels to self-hosting, not the beta.
    const receipt = screen.getByTestId('showroom-receipt');
    expect(receipt.querySelector('a[href*="/register"]')).toBeNull();
    const install = screen.getByTestId('showroom-cta-install');
    const release = screen.getByTestId('showroom-cta-release');
    const source = screen.getByTestId('showroom-cta-source');
    expect(
      install.compareDocumentPosition(release) & Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy();
    expect(release.compareDocumentPosition(source) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    // The proof trigger sits at the same default size as its outline peers
    // (the old size="sm" trigger read as a hierarchy that did not exist).
    const height = (el: HTMLElement) => el.className.match(/\bh-\d+\b/)?.[0];
    const proof = screen.getByRole('button', { name: 'showroom.proof.open' });
    expect(height(proof)).toBeDefined();
    expect(height(proof)).toBe(height(release));
    // Back to the picker from the receipt utility row.
    await user.click(screen.getByTestId('showroom-change-mission'));
    expect(noopChange).toHaveBeenCalledTimes(1);
  });

  it("separates LIA's reply from the pedagogical demo note", async () => {
    const { user } = renderMission();
    await completeMission(user);
    // The note bubble exists, labeled, OUTSIDE the rich reply.
    const note = screen.getByTestId('showroom-demo-note');
    expect(note).toHaveTextContent('showroom.m.overloaded_morning.note');
    expect(note).toHaveTextContent('showroom.note.label');
    const reply = screen.getByTestId('showroom-rich-response');
    expect(reply.contains(note)).toBe(false);
    // And the reply never carries the pedagogical text.
    expect(reply.getAttribute('data-html')).not.toContain('showroom.m.overloaded_morning.note');
  });

  it('keeps the picker return reachable even mid-run', async () => {
    const { user } = renderMission();
    await user.click(screen.getByRole('button', { name: 'showroom.start' }));
    await user.click(screen.getByTestId('showroom-back-to-picker'));
    expect(noopChange).toHaveBeenCalledTimes(1);
  });

  it('reveals exactly four sources and renders the reasoning-free trace', async () => {
    const { user } = renderMission();
    await user.click(screen.getByRole('button', { name: 'showroom.start' }));
    for (let i = 0; i < 4; i += 1) {
      await user.click(screen.getByRole('button', { name: 'showroom.continue' }));
    }
    const sources = screen.getByRole('list', { name: 'showroom.sources.title' });
    expect(within(sources).getAllByRole('listitem')).toHaveLength(4);
    // Into planning: the storyboard trace appears, without any 💭 block.
    await user.click(screen.getByRole('button', { name: 'showroom.continue' }));
    await user.click(screen.getByRole('button', { name: 'chat.trace.aria_toggle' }));
    expect(screen.queryByText('chat.trace.reasoning_title')).not.toBeInTheDocument();
  });

  it('supports the edited-email path with a bounded marker only', async () => {
    const onEvent = vi.fn();
    const { user } = renderMission(MORNING, onEvent);
    await completeMission(user, { email: 'edit', calendar: 'confirm' });
    expect(screen.getByText('showroom.receipt.email_edited')).toBeInTheDocument();
    expect(onEvent).toHaveBeenCalledWith('demo_hitl_edit');
    // The typed instructions never reach the funnel callback.
    for (const call of onEvent.mock.calls) {
      expect(JSON.stringify(call)).not.toContain('10:00');
    }
  });

  it('emits the bounded per-run funnel exactly once each, per mission', async () => {
    const onEvent = vi.fn();
    const { user } = renderMission(MORNING, onEvent);
    const count = (name: string) => onEvent.mock.calls.filter(([e]) => e === name).length;

    await completeMission(user, { email: 'confirm', calendar: 'cancel' });
    expect(count('demo_mission_started')).toBe(1);
    expect(count('demo_mission_started_overloaded_morning')).toBe(1);
    expect(count('demo_first_hitl_decided')).toBe(1);
    expect(count('demo_hitl_confirm')).toBe(1);
    expect(count('demo_hitl_cancel')).toBe(1);
    expect(count('demo_completed')).toBe(1);
    expect(count('demo_completed_overloaded_morning')).toBe(1);
    // demo_viewed is page-level (GuidedShowroom), never the mission's.
    expect(count('demo_viewed')).toBe(0);

    // Restart then complete again: a NEW run emits a new started/completed.
    await user.click(screen.getByRole('button', { name: 'showroom.restart' }));
    await completeMission(user, { email: 'cancel', calendar: 'confirm' });
    expect(count('demo_mission_started')).toBe(2);
    expect(count('demo_mission_started_overloaded_morning')).toBe(2);
    expect(count('demo_completed')).toBe(2);
    expect(count('demo_completed_overloaded_morning')).toBe(2);
  });

  it('walks a single-decision mission and tags its own funnel events', async () => {
    const onEvent = vi.fn();
    const { user } = renderMission(PHONE, onEvent);
    await user.click(screen.getByRole('button', { name: 'showroom.start' }));
    // 3 source reveals + reading->planning + planning->decision[0].
    for (let i = 0; i < 5; i += 1) {
      await user.click(screen.getByRole('button', { name: 'showroom.continue' }));
    }
    const card = screen.getByRole('region', {
      name: 'chat.hitl.title.tool_confirmation',
    });
    await user.click(within(card).getByRole('button', { name: 'chat.hitl.actions.cancel' }));
    // Refusal reaches an honest receipt: no call, refusal respected.
    expect(
      screen.getByText('showroom.m.phone_booking.decisions.authorize_call.refused')
    ).toBeInTheDocument();
    expect(screen.getByText('showroom.receipt.refusal_respected')).toBeInTheDocument();
    const count = (name: string) => onEvent.mock.calls.filter(([e]) => e === name).length;
    expect(count('demo_mission_started_phone_booking')).toBe(1);
    expect(count('demo_completed_phone_booking')).toBe(1);
    expect(count('demo_mission_started_overloaded_morning')).toBe(0);
  });

  it('emits each destination-specific CTA at most once per completed run', async () => {
    const onEvent = vi.fn();
    const { user } = renderMission(MORNING, onEvent);
    await completeMission(user);
    const count = (name: string) => onEvent.mock.calls.filter(([e]) => e === name).length;

    // Anchor navigation is jsdom-noisy; the funnel intent fires on click.
    for (const [testid, event] of [
      ['showroom-cta-source', 'demo_source_clicked'],
      ['showroom-cta-release', 'demo_release_clicked'],
      ['showroom-cta-install', 'demo_install_guide_clicked'],
    ] as const) {
      const link = screen.getByTestId(testid);
      expect(link).toHaveAttribute('target', '_blank');
      await user.click(link);
      await user.click(link); // double activation stays a single attempt
      expect(count(event)).toBe(1);
    }
  });

  it('moves focus to each phase heading and keeps one polite region', async () => {
    const { user } = renderMission();
    expect(screen.getAllByRole('status')).toHaveLength(1);
    await user.click(screen.getByRole('button', { name: 'showroom.start' }));
    expect(screen.getByRole('heading', { name: 'showroom.phases.reading_sources' })).toHaveFocus();
  });

  it('returns focus to the proof trigger after closing the drawer', async () => {
    const { user } = renderMission();
    await completeMission(user);
    const trigger = screen.getByRole('button', { name: 'showroom.proof.open' });
    await user.click(trigger);
    expect(screen.getByRole('dialog', { name: 'showroom.proof.title' })).toBeInTheDocument();
    await user.keyboard('{Escape}');
    expect(trigger).toHaveFocus();
  });

  it('never touches fetch, WebSocket or EventSource', async () => {
    const { user } = renderMission();
    await completeMission(user, { email: 'edit', calendar: 'confirm' });
    await user.click(screen.getByRole('button', { name: 'showroom.proof.open' }));
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(wsSpy).not.toHaveBeenCalled();
    expect(esSpy).not.toHaveBeenCalled();
  });

  it('advances by timer when motion is allowed', () => {
    mediaQueryMock.mockReturnValue(false); // full motion
    vi.useFakeTimers();
    try {
      renderMission();
      fireEvent.click(screen.getByRole('button', { name: 'showroom.start' }));
      expect(screen.queryByRole('button', { name: 'showroom.continue' })).not.toBeInTheDocument();
      // Each act() flushes the effect that arms the next chained timer.
      for (let i = 0; i < 8; i += 1) {
        act(() => {
          vi.advanceTimersByTime(2_000);
        });
      }
      // The pacing walks reading + planning alone, up to the first decision.
      expect(
        screen.getByRole('region', { name: 'chat.hitl.title.draft_critique' })
      ).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });
});
