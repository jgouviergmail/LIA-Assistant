/**
 * Small display helpers shared by the banner, the list and the detail page.
 */

import type { MeetingRecorderPhase } from '@/stores/meetingRecorderStore';
import type { MeetingStatus } from '@/types/meetings';

/** `H:MM:SS` above an hour, `M:SS` below — readable in every locale. */
export function formatElapsed(totalSeconds: number): string {
  const seconds = Math.max(0, Math.floor(totalSeconds));
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  const mm = h > 0 ? String(m).padStart(2, '0') : String(m);
  return h > 0 ? `${h}:${mm}:${String(s).padStart(2, '0')}` : `${mm}:${String(s).padStart(2, '0')}`;
}

/** Badge tone of a meeting status (ADR-205/206: tones come from one table). */
export function meetingStatusTone(
  status: MeetingStatus
): 'default' | 'success' | 'destructive' | 'warning' | 'info' | 'secondary' {
  switch (status) {
    case 'ready':
      return 'success';
    case 'failed':
      return 'destructive';
    case 'interrupted':
      return 'warning';
    case 'recording':
    case 'processing':
    case 'stopped':
      return 'info';
  }
}

/** Whether the banner should render for this phase at all. */
export function isBannerPhase(phase: MeetingRecorderPhase): boolean {
  return phase !== 'idle';
}
