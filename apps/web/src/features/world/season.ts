import type { ExperiencePreferences } from './experience-protocol';
export const SEASONS = ['spring', 'summer', 'autumn', 'winter'] as const;
export type Season = (typeof SEASONS)[number] | 'neutral';
/** Manual/off modes need no clock; calendar mode uses only the fresh native anchor. */
export function seasonAt(
  serverInstant: number | null,
  timezone: string | null,
  mode: ExperiencePreferences['season_mode'],
  hemisphere: ExperiencePreferences['hemisphere']
): Season {
  if (mode === 'off') return 'neutral';
  if (mode !== 'calendar') return mode;
  if (serverInstant === null || !Number.isFinite(serverInstant) || !timezone) return 'neutral';
  try {
    const month = Number(
      new Intl.DateTimeFormat('en-US', { timeZone: timezone, month: 'numeric' }).format(
        serverInstant
      )
    );
    const index = (month - 1 + (hemisphere === 'south' ? 6 : 0)) % 12;
    if (index < 2 || index === 11) return 'winter';
    if (index < 5) return 'spring';
    return index < 8 ? 'summer' : 'autumn';
  } catch {
    return 'neutral';
  }
}
