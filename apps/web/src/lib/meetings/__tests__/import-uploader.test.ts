/**
 * Uploading an imported file (owner request 2026-10-24): cut into the chunks the
 * server publishes, sent in order through the recorder's own retrying queue,
 * completed only once every chunk landed — and a refusal or an abort never
 * completes.
 */
import { describe, expect, it, vi } from 'vitest';

import { ApiError } from '@/lib/api-client';
import { chunkCountOf, uploadImportFile } from '../import-uploader';
import type { SegmentTransport } from '../segment-uploader';
import type { MeetingSegmentAck } from '@/types/meetings';

function recordingTransport() {
  const sent: Array<{ sequence: number; text: string }> = [];
  const transport: SegmentTransport = {
    put: async (_id, sequence, blob) => {
      sent.push({ sequence, text: await blob.text() });
      const ack: MeetingSegmentAck = {
        sequence,
        segment_count: sequence + 1,
        audio_bytes: 0,
        status: 'uploading',
      };
      return ack;
    },
  };
  return { sent, transport };
}

describe('chunkCountOf', () => {
  it('cuts a file into chunks of the published size, the last one shorter', () => {
    expect(chunkCountOf(10, 4)).toBe(3);
    expect(chunkCountOf(8, 4)).toBe(2);
    expect(chunkCountOf(1, 4)).toBe(1);
  });
});

describe('uploadImportFile', () => {
  it('sends every chunk in order, then completes with their count', async () => {
    const { sent, transport } = recordingTransport();
    const complete = vi.fn().mockResolvedValue(undefined);
    const progress: Array<[number, number]> = [];

    const result = await uploadImportFile({
      meetingId: 'm1',
      file: new Blob(['abcdefghij']),
      chunkBytes: 4,
      transport,
      complete,
      onProgress: (done, total) => progress.push([done, total]),
    });

    expect(result).toEqual({ kind: 'complete' });
    expect(sent).toEqual([
      { sequence: 0, text: 'abcd' },
      { sequence: 1, text: 'efgh' },
      { sequence: 2, text: 'ij' },
    ]);
    expect(complete).toHaveBeenCalledWith('m1', 3);
    expect(progress.at(-1)).toEqual([3, 3]);
  });

  it('stops at a refusal and never completes', async () => {
    const transport: SegmentTransport = {
      put: async () => {
        throw new ApiError('refused', 415, { detail: { code: 'import_format_mismatch' } });
      },
    };
    const complete = vi.fn();

    const result = await uploadImportFile({
      meetingId: 'm1',
      file: new Blob(['abcdefgh']),
      chunkBytes: 4,
      transport,
      complete,
    });

    expect(result).toEqual({ kind: 'refused', code: 'import_format_mismatch' });
    expect(complete).not.toHaveBeenCalled();
  });

  it('says what the completion refused', async () => {
    const { transport } = recordingTransport();
    const complete = vi
      .fn()
      .mockRejectedValue(new ApiError('gap', 409, { detail: { code: 'segments_missing' } }));

    const result = await uploadImportFile({
      meetingId: 'm1',
      file: new Blob(['abcd']),
      chunkBytes: 4,
      transport,
      complete,
    });

    expect(result).toEqual({ kind: 'refused', code: 'segments_missing' });
  });

  it('an abort sends nothing more and never completes', async () => {
    const controller = new AbortController();
    let calls = 0;
    const transport: SegmentTransport = {
      put: async (_id, sequence) => {
        calls += 1;
        controller.abort();
        return { sequence, segment_count: 1, audio_bytes: 0, status: 'uploading' };
      },
    };
    const complete = vi.fn();

    const result = await uploadImportFile({
      meetingId: 'm1',
      file: new Blob(['abcdefghijkl']),
      chunkBytes: 4,
      transport,
      complete,
      signal: controller.signal,
    });

    expect(result).toEqual({ kind: 'aborted' });
    expect(calls).toBe(1);
    expect(complete).not.toHaveBeenCalled();
  });
});
