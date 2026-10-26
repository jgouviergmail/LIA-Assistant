'use client';
import { useSyncExternalStore } from 'react';
import type { WorldSpeech } from './speech';
export function WorldSpeechAnnouncements({ speech }: { speech: WorldSpeech }) {
  const lines = useSyncExternalStore(
    speech.subscribe,
    speech.getSnapshot,
    speech.getServerSnapshot
  );
  return (
    <div className="sr-only" role="status" aria-live="polite" aria-atomic="false">
      {lines.map(line => (
        <p key={line.id} data-world-speech={line.kind} data-world-speaker={line.speaker}>
          {line.label}: {line.text}
        </p>
      ))}
    </div>
  );
}
