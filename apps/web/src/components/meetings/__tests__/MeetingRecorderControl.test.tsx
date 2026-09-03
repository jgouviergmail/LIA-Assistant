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

  it('offers Stop while live, pulses, shows the elapsed time and stops the recorder', async () => {
    const rec = recorder({ phase: 'recording', isCapturing: true, isLive: true });
    context.value = rec;
    act(() => useMeetingRecorderStore.getState().setElapsed(125));
    const { user } = renderWithProviders(<MeetingRecorderControl lng="en" />);
    const button = screen.getByRole('button', { name: 'meetings.header.stop' });
    expect(button).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByTestId('header-recording-dot')).toHaveClass('animate-pulse');
    expect(screen.getByText('2:05')).toBeInTheDocument();
    await user.click(button);
    expect(rec.stop).toHaveBeenCalledTimes(1);
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
