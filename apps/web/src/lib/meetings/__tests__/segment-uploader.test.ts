/**
 * The segment queue: strict order, retries that never drop a segment, offline
 * as a wait rather than a failure, fatal refusals surfaced once.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '@/lib/api-client';
import type { MeetingSegmentAck } from '@/types/meetings';

import { meetingErrorCode } from '@/lib/meetings/api';

import { SegmentUploader, type SegmentTransport } from '../segment-uploader';

function ack(sequence: number): MeetingSegmentAck {
  return { sequence, segment_count: sequence + 1, audio_bytes: 0, status: 'recording' };
}

function blob(size = 4): Blob {
  return new Blob([new Uint8Array(size)]);
}

async function flushMicrotasks(): Promise<void> {
  for (let i = 0; i < 10; i++) await Promise.resolve();
}

describe('SegmentUploader', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('uploads in sequence order, one at a time, and resolves flush when empty', async () => {
    const calls: number[] = [];
    let inFlight = 0;
    let maxInFlight = 0;
    const transport: SegmentTransport = {
      async put(_id, sequence) {
        inFlight += 1;
        maxInFlight = Math.max(maxInFlight, inFlight);
        await Promise.resolve();
        calls.push(sequence);
        inFlight -= 1;
        return ack(sequence);
      },
    };
    const progress: Array<[number, number]> = [];
    const uploader = new SegmentUploader({
      meetingId: 'm1',
      transport,
      onProgress: p => progress.push([p.uploaded, p.pending]),
    });
    uploader.enqueue(blob());
    uploader.enqueue(blob());
    uploader.enqueue(blob());
    await uploader.flush();
    expect(calls).toEqual([0, 1, 2]);
    expect(maxInFlight).toBe(1);
    expect(uploader.sequenceCount).toBe(3);
    expect(uploader.uploadedCount).toBe(3);
    expect(progress.at(-1)).toEqual([3, 0]);
  });

  it('retries a failed upload with backoff and never skips the sequence', async () => {
    let failures = 2;
    const calls: number[] = [];
    const transport: SegmentTransport = {
      async put(_id, sequence) {
        calls.push(sequence);
        if (failures > 0) {
          failures -= 1;
          throw new TypeError('network down');
        }
        return ack(sequence);
      },
    };
    const uploader = new SegmentUploader({
      meetingId: 'm1',
      transport,
      retryDelaysMs: [100, 200],
    });
    uploader.enqueue(blob());
    uploader.enqueue(blob());
    await flushMicrotasks();
    expect(calls).toEqual([0]);
    await vi.advanceTimersByTimeAsync(100);
    expect(calls).toEqual([0, 0]);
    await vi.advanceTimersByTimeAsync(200);
    await flushMicrotasks();
    expect(calls).toEqual([0, 0, 0, 1]);
    expect(uploader.pendingCount).toBe(0);
  });

  it('waits while offline instead of retrying, then resumes on the online event', async () => {
    let online = false;
    const calls: number[] = [];
    const transport: SegmentTransport = {
      async put(_id, sequence) {
        calls.push(sequence);
        return ack(sequence);
      },
    };
    const uploader = new SegmentUploader({
      meetingId: 'm1',
      transport,
      isOnline: () => online,
      retryDelaysMs: [50],
    });
    uploader.enqueue(blob());
    await vi.advanceTimersByTimeAsync(500);
    expect(calls).toEqual([]);
    online = true;
    window.dispatchEvent(new Event('online'));
    await flushMicrotasks();
    expect(calls).toEqual([0]);
  });

  it('stops for good on a fatal refusal and reports the server code once', async () => {
    const onFatal = vi.fn();
    const transport: SegmentTransport = {
      async put() {
        throw new ApiError('conflict', 409, { detail: { code: 'meeting_not_recording' } });
      },
    };
    const uploader = new SegmentUploader({ meetingId: 'm1', transport, onFatal });
    uploader.enqueue(blob());
    uploader.enqueue(blob());
    await uploader.flush();
    expect(onFatal).toHaveBeenCalledTimes(1);
    expect(onFatal).toHaveBeenCalledWith('meeting_not_recording');
    expect(uploader.enqueue(blob())).toBe(-1);
  });

  it('dispose drops the queue and settles a pending flush', async () => {
    const transport: SegmentTransport = {
      put: () => new Promise(() => undefined),
    };
    const uploader = new SegmentUploader({ meetingId: 'm1', transport });
    uploader.enqueue(blob());
    const flushed = uploader.flush();
    uploader.dispose();
    await expect(flushed).resolves.toBeUndefined();
    expect(uploader.pendingCount).toBe(0);
  });

  it('starts numbering from the resumed sequence', () => {
    const transport: SegmentTransport = { put: async (_id, s) => ack(s) };
    const uploader = new SegmentUploader({ meetingId: 'm1', transport, startSequence: 7 });
    expect(uploader.enqueue(blob())).toBe(7);
    expect(uploader.sequenceCount).toBe(8);
  });
});

describe('SegmentUploader after a fatal refusal', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('settles the count at the refused sequence and flush resolves at once', async () => {
    const transport: SegmentTransport = {
      async put(_id, sequence) {
        if (sequence === 1) {
          throw new ApiError('cap', 413, { detail: { code: 'duration_cap_reached' } });
        }
        return ack(sequence);
      },
    };
    const fatal: string[] = [];
    const uploader = new SegmentUploader({
      meetingId: 'm1',
      transport,
      retryDelaysMs: [1],
      onFatal: code => fatal.push(code),
    });
    uploader.enqueue(blob());
    uploader.enqueue(blob());
    uploader.enqueue(blob());
    await uploader.flush();
    expect(fatal).toEqual(['duration_cap_reached']);
    expect(uploader.fatalCode).toBe('duration_cap_reached');
    expect(uploader.uploadedCount).toBe(1);
    expect(uploader.sequenceCount).toBe(3);
    expect(uploader.settledSequenceCount).toBe(1);
    expect(uploader.pendingCount).toBe(2);
    // Nothing more can ever leave: a later flush must not hang the stop.
    await expect(uploader.flush()).resolves.toBeUndefined();
    expect(uploader.enqueue(blob())).toBe(-1);
  });

  it('a healthy queue settles at the assigned count', async () => {
    const transport: SegmentTransport = {
      async put(_id, sequence) {
        return ack(sequence);
      },
    };
    const uploader = new SegmentUploader({ meetingId: 'm1', transport });
    uploader.enqueue(blob());
    uploader.enqueue(blob());
    await uploader.flush();
    expect(uploader.fatalCode).toBeNull();
    expect(uploader.settledSequenceCount).toBe(2);
  });
});

describe('meetingErrorCode', () => {
  it('reads the stable code and ignores anything else', () => {
    expect(
      meetingErrorCode(new ApiError('x', 413, { detail: { code: 'segment_too_large' } }))
    ).toBe('segment_too_large');
    expect(meetingErrorCode(new ApiError('x', 500, { detail: 'boom' }))).toBeNull();
    expect(meetingErrorCode(new Error('x'))).toBeNull();
  });
});
