/**
 * The radio's controls outside its page (ADR-324): the header toggle — start
 * when off, stop when on air, nothing where the radio is not offered — and the
 * bar under the header, which says where the station stands, what it costs and
 * why it ended, until dismissed.
 */

import { act, fireEvent, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen, within } from '@/__tests__/test-utils';
import type { RadioView } from '@/lib/radio/controller';
import type { RadioSegment } from '@/lib/radio/types';
import { IDLE_RADIO_VIEW, useRadioStore } from '@/stores/radioStore';

const player = vi.hoisted(() => ({
  start: vi.fn(async () => undefined),
  stop: vi.fn(async () => undefined),
  pause: vi.fn(),
  resume: vi.fn(async () => undefined),
  position: vi.fn(() => 0),
}));
vi.mock('@/lib/radio/player', () => ({ radioPlayer: () => player }));

import { RadioBannerSlot } from '../RadioBanner';
import { RadioControl, useRadioMenuAction } from '../RadioControl';

const SEGMENT: RadioSegment = {
  seq: 2,
  format: 'bulletin',
  mood: 'news',
  title: 'The nine o’clock news',
  duration_s: 180,
  transcript: [],
};

function show(changes: Partial<RadioView>): RadioView {
  const view = { ...IDLE_RADIO_VIEW, ...changes };
  act(() => useRadioStore.getState().setView(view));
  return view;
}

beforeEach(() => {
  vi.clearAllMocks();
  useRadioStore.getState().setView(IDLE_RADIO_VIEW);
});

describe('RadioControl', () => {
  it('renders nothing where the radio is not offered', () => {
    const { container } = renderWithProviders(<RadioControl lng="en" enabled={false} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('starts the station from the click when it is off', () => {
    renderWithProviders(<RadioControl lng="en" enabled />);
    const button = screen.getByRole('button', { name: 'radio.header.start' });
    expect(button).toHaveAttribute('aria-pressed', 'false');
    fireEvent.click(button);
    expect(player.start).toHaveBeenCalledTimes(1);
  });

  it('stops it while it is on air, and ignores a click while it signs off', () => {
    renderWithProviders(<RadioControl lng="en" enabled />);
    show({ status: 'playing', sessionId: 's1' });
    fireEvent.click(screen.getByRole('button', { name: 'radio.header.stop' }));
    expect(player.stop).toHaveBeenCalledTimes(1);

    show({ status: 'ending', sessionId: 's1' });
    const signingOff = screen.getByRole('button', { name: 'radio.header.stop' });
    expect(signingOff).toHaveAttribute('aria-disabled', 'true');
    fireEvent.click(signingOff);
    expect(player.stop).toHaveBeenCalledTimes(1);
    expect(player.start).not.toHaveBeenCalled();
  });

  it('offers the same command in the logo menu', () => {
    const { result } = renderHook(() => useRadioMenuAction('en', true));
    expect(result.current?.label).toBe('radio.header.start');
    act(() => useRadioStore.getState().setView({ ...IDLE_RADIO_VIEW, status: 'waiting' }));
    expect(result.current?.tone).toBe('destructive');
  });
});

describe('RadioBannerSlot', () => {
  it('is absent while the radio is off', () => {
    const { container } = renderWithProviders(<RadioBannerSlot lng="en" />);
    expect(container).toBeEmptyDOMElement();
  });

  it('publishes its height for the chat shell while it shows, and withdraws it', () => {
    const observers: Array<() => void> = [];
    class FakeResizeObserver {
      constructor(callback: () => void) {
        observers.push(callback);
      }
      observe() {}
      disconnect() {}
    }
    const previous = globalThis.ResizeObserver;
    globalThis.ResizeObserver = FakeResizeObserver as unknown as typeof ResizeObserver;
    try {
      renderWithProviders(<RadioBannerSlot lng="en" />);
      expect(observers).toHaveLength(0); // off: the chat shell loses nothing
      show({ status: 'waiting', sessionId: 's1' });
      expect(observers).toHaveLength(1);
      act(() => observers[0]());
      expect(document.documentElement.style.getPropertyValue('--radio-banner-h')).toBe('0px');
      show({ status: 'idle' });
      expect(document.documentElement.style.getPropertyValue('--radio-banner-h')).toBe('');
    } finally {
      globalThis.ResizeObserver = previous;
    }
  });

  it('names the station, says what airs and what it has cost, and pauses it', () => {
    renderWithProviders(<RadioBannerSlot lng="en" />);
    show({
      status: 'playing',
      sessionId: 's1',
      current: SEGMENT,
      costEur: 0.0042,
      stationName: 'Radio Alex',
    });
    const bar = screen.getByRole('region', { name: /Radio Alex/ });
    expect(bar).toHaveTextContent('The nine o’clock news');
    expect(bar).toHaveTextContent('€0.0042');
    // What is announced is where the station stands and what airs — never a
    // cost that changes every few seconds under a screen reader.
    const announced = screen.getByRole('status');
    expect(announced).toHaveTextContent('radio.banner.playing');
    expect(announced).toHaveTextContent('The nine o’clock news');
    expect(announced).not.toHaveTextContent('€0.0042');
    fireEvent.click(screen.getByRole('button', { name: /radio.banner.pause/ }));
    expect(player.pause).toHaveBeenCalledTimes(1);
  });

  it('shows the language’s name for the station before the session names it', () => {
    renderWithProviders(<RadioBannerSlot lng="en" />);
    show({ status: 'starting', sessionId: null });
    expect(screen.getByRole('region', { name: /radio.station_name/ })).toBeInTheDocument();
  });

  it('prices the listening planned beside what it has cost', () => {
    renderWithProviders(<RadioBannerSlot lng="en" />);
    show({
      status: 'playing',
      sessionId: 's1',
      current: SEGMENT,
      costEur: 0.0123,
      stopAt: new Date(Date.now() + 23 * 60_000).toISOString(),
      costEstimateEur: 0.0512,
      costEstimateS: 1800,
    });
    expect(screen.getByText('radio.banner.estimate')).toBeInTheDocument();
    // Each figure says what it is to a screen reader, by text — an aria-label
    // on a plain span is read by none.
    expect(screen.getByText('radio.banner.cost_label')).toHaveClass('sr-only');
    expect(screen.getByText('radio.banner.estimate_label')).toHaveClass('sr-only');
    expect(document.querySelector('span[aria-label]')).toBeNull();
  });

  it('keeps what airs on its line through a pause, and the line itself between two programmes', () => {
    renderWithProviders(<RadioBannerSlot lng="en" />);
    show({ status: 'paused', sessionId: 's1', current: SEGMENT });
    const announced = screen.getByRole('status');
    expect(announced).toHaveTextContent('The nine o’clock news');
    // Between two programmes nothing airs, and the line stays — empty — so the
    // bar never changes height under the listener's finger.
    show({ status: 'waiting', sessionId: 's1', current: null });
    expect(screen.getByRole('status')).not.toHaveTextContent('The nine o’clock news');
    expect(screen.getByRole('status').querySelectorAll('p')).toHaveLength(2);
  });

  it('holds the width of the longer of pause and resume, and names only the one shown', () => {
    renderWithProviders(<RadioBannerSlot lng="en" />);
    show({ status: 'playing', sessionId: 's1', current: SEGMENT });
    const pause = screen.getByRole('button', { name: 'radio.banner.pause' });
    // Both labels lay out (the button never resizes on a pause, so a second
    // click meant to resume cannot land on stop); the hidden one is unnamed.
    const resume = within(pause).getByText('radio.banner.resume');
    expect(resume).toHaveAttribute('aria-hidden', 'true');
    expect(resume).toHaveClass('invisible');
    show({ status: 'paused', sessionId: 's1', current: SEGMENT });
    const resumeButton = screen.getByRole('button', { name: 'radio.banner.resume' });
    expect(within(resumeButton).getByText('radio.banner.pause')).toHaveClass('invisible');
  });

  it('hands the focus to restart once the stop the listener pressed has ended the session', () => {
    renderWithProviders(<RadioBannerSlot lng="en" />);
    show({ status: 'playing', sessionId: 's1', current: SEGMENT });
    const stop = screen.getByRole('button', { name: /radio.banner.stop/ });
    stop.focus();
    fireEvent.click(stop);
    expect(player.stop).toHaveBeenCalledTimes(1);
    show({ status: 'ending', sessionId: 's1' });
    expect(stop).toHaveFocus(); // signing off: stop stays, inert, under the finger
    show({ status: 'ended', sessionId: 's1', endReason: 'listener' });
    expect(screen.getByRole('button', { name: /radio.banner.restart/ })).toHaveFocus();
  });

  it('leaves the focus where the listener moved it after pressing stop', () => {
    renderWithProviders(<RadioBannerSlot lng="en" />);
    show({ status: 'playing', sessionId: 's1', current: SEGMENT });
    fireEvent.click(screen.getByRole('button', { name: /radio.banner.stop/ }));
    const elsewhere = document.createElement('input');
    document.body.append(elsewhere);
    elsewhere.focus();
    show({ status: 'ended', sessionId: 's1', endReason: 'listener' });
    expect(elsewhere).toHaveFocus();
    elsewhere.remove();
  });

  it('hands the focus back once per stop, never to the next session’s own end', () => {
    renderWithProviders(<RadioBannerSlot lng="en" />);
    show({ status: 'playing', sessionId: 's1', current: SEGMENT });
    fireEvent.click(screen.getByRole('button', { name: /radio.banner.stop/ }));
    show({ status: 'ended', sessionId: 's1', endReason: 'listener' });
    expect(screen.getByRole('button', { name: /radio.banner.restart/ })).toHaveFocus();
    // Started again, the next session ends by its timer: nobody pressed stop.
    show({ status: 'playing', sessionId: 's2', current: SEGMENT });
    show({ status: 'ended', sessionId: 's2', endReason: 'timer' });
    expect(screen.getByRole('button', { name: /radio.banner.restart/ })).not.toHaveFocus();
  });

  it('takes no focus when the session ends by itself', () => {
    renderWithProviders(<RadioBannerSlot lng="en" />);
    show({ status: 'playing', sessionId: 's1', current: SEGMENT });
    show({ status: 'ended', sessionId: 's1', endReason: 'timer' });
    expect(screen.getByRole('button', { name: /radio.banner.restart/ })).not.toHaveFocus();
  });

  it('keeps pause and stop the same size, side by side, and in place while it tunes in', () => {
    renderWithProviders(<RadioBannerSlot lng="en" />);
    show({ status: 'starting', sessionId: null });
    const pause = screen.getByRole('button', { name: /radio.banner.pause/ });
    const stop = screen.getByRole('button', { name: /radio.banner.stop/ });
    expect(pause.parentElement).toBe(stop.parentElement);
    expect(pause.parentElement).toHaveClass('grid-cols-2');
    // Tuning in: nothing to pause yet, and the control stays where it will be.
    expect(pause).toHaveAttribute('aria-disabled', 'true');
    fireEvent.click(pause);
    expect(player.pause).not.toHaveBeenCalled();
  });

  it('resumes a paused station', () => {
    renderWithProviders(<RadioBannerSlot lng="en" />);
    show({ status: 'paused', sessionId: 's1', current: SEGMENT });
    fireEvent.click(screen.getByRole('button', { name: /radio.banner.resume/ }));
    expect(player.resume).toHaveBeenCalledTimes(1);
  });

  it('reduces the phone player to two lines with pause and stop still available', () => {
    renderWithProviders(<RadioBannerSlot lng="en" />);
    show({ status: 'playing', sessionId: 's1', current: SEGMENT, stationName: 'Radio Alex' });
    const collapse = screen.getByRole('button', { name: 'radio.banner.collapse' });
    collapse.focus();
    fireEvent.click(collapse);

    const expand = screen.getByRole('button', { name: 'radio.banner.expand' });
    expect(expand).toHaveFocus();
    const compact = expand.parentElement;
    expect(compact).not.toBeNull();
    expect(within(compact!).getByRole('status').querySelectorAll('p')).toHaveLength(2);
    expect(within(compact!).getByRole('status')).toHaveTextContent('The nine o’clock news');
    fireEvent.click(within(compact!).getByRole('button', { name: 'radio.banner.pause' }));
    expect(player.pause).toHaveBeenCalledTimes(1);

    show({ status: 'paused', sessionId: 's1', current: SEGMENT, stationName: 'Radio Alex' });
    fireEvent.click(within(compact!).getByRole('button', { name: 'radio.banner.resume' }));
    expect(player.resume).toHaveBeenCalledTimes(1);
    fireEvent.click(within(compact!).getByRole('button', { name: 'radio.banner.stop' }));
    expect(player.stop).toHaveBeenCalledTimes(1);
    fireEvent.click(expand);
    expect(screen.getByRole('button', { name: 'radio.banner.collapse' })).toHaveFocus();
  });

  it('says in full why a start was refused, up to when the radio may play again', () => {
    renderWithProviders(<RadioBannerSlot lng="en" />);
    show({
      status: 'ended',
      sessionId: null,
      error: 'radio_budget_reached',
      refusedBudget: { maxEur: 2, liftsAt: '2026-09-27T12:00:00Z' },
    });
    // Live, the line holds still on one line; the sentence of an end ends on its
    // instant, and a phone would cut exactly that.
    const line = screen.getByText('radio.errors.radio_budget_reached').closest('p');
    expect(line).not.toHaveClass('truncate');
  });

  it('says why it ended until dismissed — and shows again at the next start', () => {
    renderWithProviders(<RadioBannerSlot lng="en" />);
    show({ status: 'ended', sessionId: 's1', endReason: 'budget' });
    expect(screen.getByRole('status')).toHaveTextContent('radio.end_reason.budget');
    fireEvent.click(screen.getByRole('button', { name: 'radio.banner.dismiss' }));
    expect(screen.queryByRole('status')).not.toBeInTheDocument();

    show({ status: 'ended', sessionId: null, error: 'start_failed' });
    expect(screen.getByRole('status')).toHaveTextContent('radio.errors.start_failed');
    fireEvent.click(screen.getByRole('button', { name: /radio.banner.restart/ }));
    expect(player.start).toHaveBeenCalledTimes(1);
  });
});
