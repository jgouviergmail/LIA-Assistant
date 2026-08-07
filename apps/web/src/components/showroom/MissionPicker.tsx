'use client';

/**
 * Mission picker: the /demo entry point of the guided showroom.
 *
 * One real <button> card per mission — icon, title, one-line tagline and the
 * differentiating mechanism as a themed chip. Selecting mounts the mission
 * (keyed remount); the honesty strip stays visible above the grid so the
 * synthetic contract is stated before anything runs.
 */

import { Bell, Brain, type LucideIcon, Newspaper, Phone, Settings2, Sunrise } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type { ShowroomMissionDefinition, ShowroomMissionId } from '@/components/showroom/types';
import { Badge } from '@/components/ui/badge';

/** Icons are code, not fixture data — one per bounded mission id. */
const MISSION_ICONS: Record<ShowroomMissionId, LucideIcon> = {
  overloaded_morning: Sunrise,
  proactive_alert: Bell,
  memory_dinner: Brain,
  phone_booking: Phone,
  daily_briefing: Newspaper,
  config_tour: Settings2,
};

export interface MissionPickerProps {
  missions: readonly ShowroomMissionDefinition[];
  onSelect: (id: ShowroomMissionId) => void;
}

export function MissionPicker({ missions, onSelect }: MissionPickerProps) {
  const { t } = useTranslation();
  return (
    <div className="space-y-3">
      {/* Centred: it leads into a centred grid, and left-aligned above it the
          sentence read as a stray paragraph rather than an introduction. */}
      <p className="text-center text-sm text-muted-foreground">{t('showroom.picker.subtitle')}</p>
      <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3" role="list">
        {missions.map(mission => {
          const Icon = MISSION_ICONS[mission.id];
          return (
            <li key={mission.id}>
              <button
                type="button"
                data-testid={`showroom-pick-${mission.id}`}
                onClick={() => onSelect(mission.id)}
                // min-h-[9.5rem]: measured 2026-08-06 — content-sized cards sat
                // at 122px; the owner asked for ~+25% air, and the fixed floor
                // is also what lets `mt-auto` actually pin the badge to the
                // bottom edge instead of hugging the tagline.
                className="group flex h-full min-h-[9.5rem] w-full flex-col items-start gap-2.5 rounded-2xl border border-border/60 bg-card/70 p-5 text-left backdrop-blur-sm transition-colors hover:border-primary/50 hover:bg-card focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <span className="flex items-center gap-2 text-sm font-semibold text-foreground">
                  <Icon className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
                  {t(mission.titleKey)}
                </span>
                <span className="text-xs text-muted-foreground">{t(mission.taglineKey)}</span>
                <Badge variant="default" className="mt-auto">
                  {t(mission.mechanismKey)}
                </Badge>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
