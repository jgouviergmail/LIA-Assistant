import type { PsycheHistoryEntry } from '@/types/psyche';

export interface PsycheHistoryPoint {
  time: number;
  P: number;
  A: number;
  D: number;
  emotionIntensity: number | null;
  depth: number | null;
  warmth: number | null;
  trust: number | null;
  curiosity: number | null;
  engagement: number | null;
  [key: string]: number | null;
}

const percent = (value: number | undefined): number | null =>
  value === undefined || !Number.isFinite(value) ? null : Math.round(value * 100);

/** Keep exact timestamps, real gaps and every recorded series; never mutate query data. */
export function toPsycheHistoryData(entries: readonly PsycheHistoryEntry[]) {
  const points: PsycheHistoryPoint[] = [];
  const resets: { time: number; type: string }[] = [];
  const emotions = new Set<string>();
  for (const entry of entries) {
    const time = Date.parse(entry.created_at);
    if (!Number.isFinite(time)) continue;
    if (entry.snapshot_type.startsWith('reset_')) {
      resets.push({ time, type: entry.snapshot_type });
      continue;
    }
    const snapshot = entry.trait_snapshot;
    const emotionValues =
      snapshot?.active_emotions ??
      (entry.dominant_emotion && snapshot?.emotion_intensity !== undefined
        ? { [entry.dominant_emotion]: snapshot.emotion_intensity }
        : {});
    const series = Object.fromEntries(
      Object.entries(emotionValues).map(([emotion, intensity]) => {
        const key = `emo_${emotion}`;
        emotions.add(key);
        return [key, percent(intensity)];
      })
    );
    points.push({
      time,
      P: Math.round(entry.mood_pleasure * 100),
      A: Math.round(entry.mood_arousal * 100),
      D: Math.round(entry.mood_dominance * 100),
      ...series,
      emotionIntensity: percent(snapshot?.emotion_intensity),
      depth: percent(snapshot?.relationship_depth),
      warmth: percent(snapshot?.relationship_warmth),
      trust: percent(snapshot?.relationship_trust),
      curiosity: percent(snapshot?.drive_curiosity),
      engagement: percent(snapshot?.drive_engagement),
    });
  }
  return {
    points: points.sort((a, b) => a.time - b.time),
    resets: resets.sort((a, b) => a.time - b.time),
    emotions: [...emotions].sort(),
  };
}
