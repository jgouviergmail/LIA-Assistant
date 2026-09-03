/**
 * Ordered, retrying upload of the recording's segments (ADR-258).
 *
 * The server keys a segment on `(meeting, sequence)` and treats a re-upload as
 * a harmless overwrite, so this queue can retry freely: what it must never do
 * is skip a sequence or reorder two. One upload at a time, in sequence order,
 * with exponential backoff that never gives up while the recording lasts — a
 * flaky connection drops nothing, it only delays (the server's stale window is
 * minutes, and an `interrupted` recording resumes on the next segment).
 *
 * Offline is a first-class state, not an error: while `navigator.onLine` is
 * false the queue waits for the `online` event instead of burning retries.
 *
 * The transport is injected so the queue is unit-tested without a network;
 * {@link apiSegmentTransport} is the production one.
 */

import { ApiError, apiEndpointUrl } from '@/lib/api-client';
import { meetingErrorCode } from '@/lib/meetings/api';
import { MEETING_SEGMENT_RETRY_DELAYS_MS, NATIVE_CLIENT_HEADER } from '@/lib/constants';
import { isNativeShell } from '@/lib/native/shell';
import type { MeetingSegmentAck } from '@/types/meetings';

export interface SegmentTransport {
  put(meetingId: string, sequence: number, blob: Blob): Promise<MeetingSegmentAck>;
}

export interface UploaderProgress {
  uploaded: number;
  pending: number;
  /** The server refused a segment for good (recording ended, body too large). */
  fatalCode: string | null;
}

export interface SegmentUploaderOptions {
  meetingId: string;
  transport: SegmentTransport;
  /** First sequence to assign (0 for a fresh recording, higher after a resume). */
  startSequence?: number;
  retryDelaysMs?: readonly number[];
  isOnline?: () => boolean;
  onProgress?: (progress: UploaderProgress) => void;
  /** Called once when the server refuses a segment for good. */
  onFatal?: (code: string) => void;
}

/** HTTP statuses after which retrying cannot help. */
const FATAL_STATUSES = new Set([401, 403, 404, 409, 413]);

interface QueuedSegment {
  sequence: number;
  blob: Blob;
}

function sleep(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise(resolve => {
    if (signal.aborted) return resolve();
    const timer = setTimeout(done, ms);
    function done() {
      signal.removeEventListener('abort', done);
      clearTimeout(timer);
      resolve();
    }
    signal.addEventListener('abort', done, { once: true });
  });
}

export class SegmentUploader {
  private readonly queue: QueuedSegment[] = [];
  private readonly abort = new AbortController();
  private readonly retryDelays: readonly number[];
  private readonly isOnline: () => boolean;
  private nextSequence: number;
  private uploaded = 0;
  private draining = false;
  private fatal: string | null = null;
  private idleResolvers: Array<() => void> = [];

  constructor(private readonly options: SegmentUploaderOptions) {
    this.nextSequence = options.startSequence ?? 0;
    this.retryDelays = options.retryDelaysMs ?? MEETING_SEGMENT_RETRY_DELAYS_MS;
    this.isOnline =
      options.isOnline ?? (() => (typeof navigator === 'undefined' ? true : navigator.onLine));
  }

  /** Sequence the next `enqueue` receives — the `segment_count` a stop must declare. */
  get sequenceCount(): number {
    return this.nextSequence;
  }

  get uploadedCount(): number {
    return this.uploaded;
  }

  get pendingCount(): number {
    return this.queue.length;
  }

  /** The server's final refusal, or null while the queue can still drain. */
  get fatalCode(): string | null {
    return this.fatal;
  }

  /**
   * Sequences the server holds or will hold — the count a stop declares.
   *
   * Every assigned sequence, minus the ones a fatal refusal froze in the queue:
   * after `duration_cap_reached` the refused segment and its followers never
   * existed for the server, and declaring them would report a gap that is not one.
   */
  get settledSequenceCount(): number {
    if (this.fatal === null) return this.nextSequence;
    return this.queue[0]?.sequence ?? this.nextSequence;
  }

  /** Assign the next sequence to `blob` and start draining. */
  enqueue(blob: Blob): number {
    if (this.fatal !== null || this.abort.signal.aborted) return -1;
    const sequence = this.nextSequence++;
    this.queue.push({ sequence, blob });
    this.report();
    void this.drain();
    return sequence;
  }

  /** Resolve once every queued segment is uploaded (or the uploader stopped). */
  flush(): Promise<void> {
    // A fatal or aborted queue never drains further: nothing to wait for.
    if (this.settled && !this.draining) return Promise.resolve();
    return new Promise(resolve => {
      this.idleResolvers.push(resolve);
    });
  }

  /** Stop retrying; queued segments are dropped (the caller discards the recording). */
  dispose(): void {
    this.abort.abort();
    this.queue.length = 0;
    this.settleIdle();
  }

  private get settled(): boolean {
    return this.queue.length === 0 || this.fatal !== null || this.abort.signal.aborted;
  }

  private report(): void {
    this.options.onProgress?.({
      uploaded: this.uploaded,
      pending: this.queue.length,
      fatalCode: this.fatal,
    });
  }

  private settleIdle(): void {
    const resolvers = this.idleResolvers;
    this.idleResolvers = [];
    resolvers.forEach(resolve => resolve());
  }

  private async waitOnline(): Promise<void> {
    while (!this.isOnline() && !this.abort.signal.aborted) {
      await new Promise<void>(resolve => {
        const done = () => {
          window.removeEventListener('online', done);
          this.abort.signal.removeEventListener('abort', done);
          resolve();
        };
        window.addEventListener('online', done, { once: true });
        this.abort.signal.addEventListener('abort', done, { once: true });
        // A missed `online` event must not strand the queue: re-check periodically.
        setTimeout(done, this.retryDelays[this.retryDelays.length - 1]);
      });
    }
  }

  private async drain(): Promise<void> {
    if (this.draining) return;
    this.draining = true;
    try {
      while (!this.settled) {
        const head = this.queue[0];
        const sent = await this.uploadWithRetry(head);
        if (!sent) break;
        this.queue.shift();
        this.uploaded += 1;
        this.report();
      }
    } finally {
      this.draining = false;
      if (this.settled) this.settleIdle();
    }
  }

  /** True when uploaded; false when the uploader was aborted or hit a fatal refusal. */
  private async uploadWithRetry(segment: QueuedSegment): Promise<boolean> {
    let attempt = 0;
    while (!this.abort.signal.aborted) {
      await this.waitOnline();
      if (this.abort.signal.aborted) return false;
      try {
        await this.options.transport.put(this.options.meetingId, segment.sequence, segment.blob);
        return true;
      } catch (error) {
        if (error instanceof ApiError && FATAL_STATUSES.has(error.status)) {
          this.fatal = meetingErrorCode(error) ?? `http_${error.status}`;
          this.report();
          this.options.onFatal?.(this.fatal);
          return false;
        }
        const delay = this.retryDelays[Math.min(attempt, this.retryDelays.length - 1)];
        attempt += 1;
        await sleep(delay, this.abort.signal);
      }
    }
    return false;
  }
}

/**
 * Production transport: a raw-body PUT on the segments endpoint.
 *
 * Not `apiClient.put` — that path JSON-encodes its body and stamps
 * `application/json`; a segment is bytes. The two invariants the client
 * enforces are kept by hand: the session cookie (`credentials: 'include'`) and
 * the native-shell marker (ADR-246).
 */
export const apiSegmentTransport: SegmentTransport = {
  async put(meetingId, sequence, blob) {
    const headers: Record<string, string> = { 'Content-Type': 'application/octet-stream' };
    if (isNativeShell()) headers[NATIVE_CLIENT_HEADER] = '1';
    const response = await fetch(apiEndpointUrl(`/meetings/${meetingId}/segments/${sequence}`), {
      method: 'PUT',
      credentials: 'include',
      headers,
      body: blob,
    });
    if (!response.ok) {
      let data: unknown = undefined;
      try {
        data = await response.json();
      } catch {
        data = undefined;
      }
      throw new ApiError(`Segment upload failed (${response.status})`, response.status, data);
    }
    return (await response.json()) as MeetingSegmentAck;
  },
};
