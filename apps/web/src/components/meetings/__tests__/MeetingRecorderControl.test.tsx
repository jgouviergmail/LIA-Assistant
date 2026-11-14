/**
 * The header's recording control (ADR-259, owner decision 1): one toggle,
 * two states — Record when idle, Stop while a meeting is live — and nothing at
 * all where the recorder is not offered. Below `lg` the same commands reach
 * the logo menu through `useMeetingRecorderMenuAction`.
 */

import { act, renderHook } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import type { MeetingRecorderContextValue } from '@/components/meetings/MeetingRecorderProvider';
import { useMeetingRecorderStore } from '@/stores/meetingRecorderStore';
import { ICON_STYLES } from '@/lib/icon-style';
import { IconStyleContext } from '@/lib/icon-style-context';

const context = vi.hoisted(() => ({ value: null as MeetingRecorderContextValue | null }));
vi.mock('@/components/meetings/MeetingRecorderProvider', () => ({
  useMeetingRecorderContext: () => context.value,
}));

import { MeetingRecorderControl, useMeetingRecorderMenuAction } from '../MeetingRecorderControl';

function recorder(over: Partial<MeetingRecorderContextValue> = {}): MeetingRecorderContextValue {
  return {
    phase: 'idle',
    recording: null,
    engine: null,
    limits: null,
    silencePrompt: false,
    errorCode: null,
    missingSegments: null,
    isSupported: true,
    isCapturing: false,
    isLive: false,
    start: vi.fn(async () => undefined),
    stop: vi.fn(async () => 'processing' as const),
    finalizeWithGaps: vi.fn(async () => 'processing' as const),
    resume: vi.fn(async () => undefined),
    discard: vi.fn(async () => undefined),
    dismiss: vi.fn(),
    continueAfterSilence: vi.fn(),
    ...over,
  };
}

beforeEach(() => {
  context.value = null;
  useMeetingRecorderStore.getState().reset();
});

describe('MeetingRecorderControl', () => {
  it('renders nothing without a recorder', () => {
    const { container } = renderWithProviders(<MeetingRecorderControl lng="en" />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing on a browser that cannot record', () => {
    context.value = recorder({ isSupported: false });
    const { container } = renderWithProviders(<MeetingRecorderControl lng="en" />);
    expect(container).toBeEmptyDOMElement();
  });

  it('offers Record when idle and starts the recorder', async () => {
    const rec = recorder();
    context.value = rec;
    const { user } = renderWithProviders(<MeetingRecorderControl lng="en" />);
    const button = screen.getByRole('button', { name: 'meetings.header.record' });
    expect(button).toHaveAttribute('aria-pressed', 'false');
    await user.click(button);
    expect(rec.start).toHaveBeenCalledTimes(1);
  });

  it.each(ICON_STYLES)('keeps the live recording signal and Stop action in %s', async style => {
    const rec = recorder({ phase: 'recording', isCapturing: true, isLive: true });
    context.value = rec;
    act(() => useMeetingRecorderStore.getState().setElapsed(125));
    const { user, rerender } = renderWithProviders(
      <IconStyleContext.Provider value={style}>
        <MeetingRecorderControl lng="en" />
      </IconStyleContext.Provider>
    );
    const button = screen.getByRole('button', { name: 'meetings.header.stop' });
    expect(button).toHaveAttribute('aria-pressed', 'true');
    const dot = screen.getByTestId('header-recording-dot');
    expect(dot).toHaveAttribute('data-icon-style', style);
    expect(dot).toHaveClass('text-destructive', 'animate-pulse');
    expect(dot).toHaveAttribute('fill', 'none');
    const ring = dot.querySelector('circle[cx="12"][cy="12"][r="10"]');
    expect(ring).not.toBeNull();
    // Lucide inherits its root stroke; colored artwork gives the same caller-
    // controlled recording signal to the outer ring, keeping its own red dot.
    expect(ring?.getAttribute('stroke') ?? dot.getAttribute('stroke')).toBe('currentColor');
    if (style !== 'lucide') {
      expect(ring).toHaveAttribute('fill', 'none');
      const centre = dot.querySelector('circle[cx="12"][cy="12"]:not([r="10"])');
      expect(centre?.getAttribute('fill')).toMatch(/^(?:#E5383B|url\(#.+\))$/);
    }
    expect(screen.getByText('2:05')).toBeInTheDocument();
    await user.click(button);
    expect(rec.stop).toHaveBeenCalledTimes(1);
    expect(rec.start).not.toHaveBeenCalled();

    context.value = { ...rec, phase: 'idle', isCapturing: false, isLive: false };
    rerender(
      <IconStyleContext.Provider value={style}>
        <MeetingRecorderControl lng="en" />
      </IconStyleContext.Provider>
    );
    const record = screen.getByRole('button', { name: 'meetings.header.record' });
    expect(record).toHaveAttribute('aria-pressed', 'false');
    expect(record.querySelector('svg')).not.toHaveClass('text-destructive', 'animate-pulse');
    expect(screen.queryByText('2:05')).toBeNull();
    await user.click(record);
    expect(rec.start).toHaveBeenCalledTimes(1);
  });

  it('ignores a click while the recorder is busy starting or finishing', async () => {
    const rec = recorder({ phase: 'stopping', isCapturing: false, isLive: true });
    context.value = rec;
    const { user } = renderWithProviders(<MeetingRecorderControl lng="en" />);
    const button = screen.getByRole('button', { name: 'meetings.header.stop' });
    expect(button).toHaveAttribute('aria-disabled', 'true');
    await user.click(button);
    expect(rec.stop).not.toHaveBeenCalled();
    expect(rec.start).not.toHaveBeenCalled();
  });
});

describe('useMeetingRecorderMenuAction', () => {
  it('is null without a recorder', () => {
    const { result } = renderHook(() => useMeetingRecorderMenuAction('en'));
    expect(result.current).toBeNull();
  });

  it('describes a Record entry when idle', () => {
    const rec = recorder();
    context.value = rec;
    const { result } = renderHook(() => useMeetingRecorderMenuAction('en'));
    expect(result.current?.action.label).toBe('meetings.header.record');
    expect(result.current?.live).toBeNull();
    result.current?.action.onSelect();
    expect(rec.start).toHaveBeenCalledTimes(1);
  });

  it('describes a destructive Stop entry and a live trigger while recording', () => {
    const rec = recorder({ phase: 'recording', isCapturing: true, isLive: true });
    context.value = rec;
    const { result } = renderHook(() => useMeetingRecorderMenuAction('en'));
    expect(result.current?.action.label).toBe('meetings.header.stop');
    expect(result.current?.action.tone).toBe('destructive');
    expect(result.current?.live?.label).toBe('meetings.header.live_label');
    result.current?.action.onSelect();
    expect(rec.stop).toHaveBeenCalledTimes(1);
  });
});
