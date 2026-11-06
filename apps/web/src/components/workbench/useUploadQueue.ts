'use client';

/**
 * Files sent to the API one at a time, a queue the screen shows (ADR-369, lots 6 and 7).
 *
 * One file at a time: the server holds one transfer per account. Each file keeps what it
 * was given for, whatever the screen opens meanwhile; a failure leaves the others going.
 * Stopping aborts what is on its way and drops what waits; a screen that goes away stops
 * too. What became of the queue is told once, at its end.
 */
import { useCallback, useEffect, useRef, useState } from 'react';

import { workbenchRefusal, type WorkbenchRefusal } from '@/lib/workbench/errors';
import { FileSendStopped, sendFile } from '@/lib/workbench/upload';

/** What is on its way. */
export interface UploadNow {
  name: string;
  /** Its place in the queue, from one. */
  position: number;
  total: number;
  percent: number;
}

/** What became of a queue, for its closing sentence. */
export interface UploadTally {
  sent: number;
  failed: number;
  /** The last refusal the API named. */
  refusal: WorkbenchRefusal | null;
  stopped: boolean;
}

/** A file, and what it was given for. */
export interface Upload<TPlace> {
  file: File;
  place: TPlace;
}

const EMPTY_TALLY: UploadTally = { sent: 0, failed: 0, refusal: null, stopped: false };

export function useUploadQueue<TPlace, TAnswer>({
  path,
  formOf,
  onAnswer,
  onClosed,
}: {
  path: string;
  /** The form of one file. */
  formOf: (upload: Upload<TPlace>) => FormData;
  /** One file arrived. */
  onAnswer?: (answer: TAnswer) => void;
  /** The queue ended. */
  onClosed: (tally: UploadTally) => void;
}) {
  const [now, setNow] = useState<UploadNow | null>(null);
  const queue = useRef<Upload<TPlace>[]>([]);
  const running = useRef(false);
  const stopper = useRef<AbortController | null>(null);

  useEffect(() => () => stopper.current?.abort(), []);

  const drain = useCallback(async () => {
    running.current = true;
    const stop = new AbortController();
    stopper.current = stop;
    const tally = { ...EMPTY_TALLY };
    let position = 0;
    for (let next = queue.current.shift(); next; next = queue.current.shift()) {
      position += 1;
      const name = next.file.name;
      const place = { name, position, total: position + queue.current.length };
      setNow({ ...place, percent: 0 });
      try {
        const answer = await sendFile<TAnswer>(
          path,
          formOf(next),
          percent => setNow({ ...place, total: position + queue.current.length, percent }),
          stop.signal
        );
        tally.sent += 1;
        onAnswer?.(answer);
      } catch (error: unknown) {
        if (error instanceof FileSendStopped) {
          tally.stopped = true;
          queue.current = [];
          break;
        }
        tally.failed += 1;
        tally.refusal = workbenchRefusal(error);
      }
    }
    running.current = false;
    stopper.current = null;
    setNow(null);
    onClosed(tally);
  }, [formOf, onAnswer, onClosed, path]);

  const enqueue = useCallback(
    (uploads: readonly Upload<TPlace>[]) => {
      queue.current.push(...uploads);
      if (uploads.length > 0 && !running.current) void drain();
    },
    [drain]
  );

  const stop = useCallback(() => stopper.current?.abort(), []);

  return { now, enqueue, stop };
}
