'use client';

/**
 * BriefingGridSettings — visibility + ordering of the 9 dashboard briefing
 * cards (UXR Lot 5, B4; server-persisted, JSONB new-dict backend rule).
 *
 * Keyboard-first: the ↑/↓ buttons are the universal reorder path (named with
 * the card title, edges disabled, polite position announcement); HTML5
 * drag-and-drop is a pointer-only enhancement on the same rows. A hidden
 * card is never fetched backend-side — the switch is a real API economy.
 */

import { useRef, useState } from 'react';
import { ArrowDown, ArrowUp, GripVertical, LayoutDashboard } from 'lucide-react';
import { toast } from 'sonner';

import { BRIEFING_CARD_ICONS } from '@/components/dashboard/briefing-card-icons';
import { SettingsSection } from '@/components/settings/SettingsSection';
import { Switch } from '@/components/ui/switch';
import {
  moveSection,
  reorderTo,
  toggleHidden,
  useBriefingPreferences,
} from '@/hooks/useBriefingPreferences';
import { useTranslation } from '@/i18n/client';
import type { BriefingSection } from '@/types/briefing';
import type { BaseSettingsProps } from '@/types/settings';

export function BriefingGridSettings({ lng }: BaseSettingsProps) {
  const { t } = useTranslation(lng);
  const { preferences, save } = useBriefingPreferences();
  const [announcement, setAnnouncement] = useState('');
  const dragNameRef = useRef<BriefingSection | null>(null);

  if (!preferences) return null;

  const cardTitle = (name: BriefingSection) => t(`dashboard.briefing.cards.${name}.title`);

  const persist = async (next: typeof preferences): Promise<boolean> => {
    const ok = await save(next);
    if (!ok) toast.error(t('common.error'));
    return ok;
  };

  const handleMove = async (name: BriefingSection, direction: 'up' | 'down') => {
    const order = moveSection(preferences.order, name, direction);
    if (order === preferences.order) return;
    // Announce AFTER the persist: on a failed save the order rolls back and
    // a position announcement would state something that never happened.
    const ok = await persist({ ...preferences, order });
    if (ok) {
      setAnnouncement(
        t('settings.briefing_grid.position', {
          card: cardTitle(name),
          position: order.indexOf(name) + 1,
          total: order.length,
        })
      );
    }
  };

  const handleDrop = (target: BriefingSection) => {
    const dragged = dragNameRef.current;
    dragNameRef.current = null;
    if (!dragged || dragged === target) return;
    const order = reorderTo(preferences.order, dragged, preferences.order.indexOf(target));
    void persist({ ...preferences, order });
  };

  const content = (
    <div className="space-y-1">
      <p className="text-xs text-muted-foreground mb-3">
        {t('settings.briefing_grid.description')}
      </p>
      <ul className="space-y-1" role="list">
        {preferences.order.map((name, index) => {
          const visible = !preferences.hidden.includes(name);
          const CardIcon = BRIEFING_CARD_ICONS[name];
          return (
            <li
              key={name}
              draggable
              onDragStart={() => {
                dragNameRef.current = name;
              }}
              onDragOver={event => event.preventDefault()}
              onDrop={() => handleDrop(name)}
              className="flex items-center gap-2 rounded-lg border border-border/40 bg-card/60 px-3 py-2"
            >
              <GripVertical className="h-4 w-4 shrink-0 text-muted-foreground/60" aria-hidden />
              {/* The card's own icon, theme-coloured (owner rule 2026-08-05:
                  a title never goes without one) — the reader recognises the
                  card here by the same mark it carries on the dashboard. */}
              <CardIcon className="h-4 w-4 shrink-0 text-primary" aria-hidden />
              <span className="flex-1 truncate text-sm font-medium">{cardTitle(name)}</span>
              <button
                type="button"
                onClick={() => void handleMove(name, 'up')}
                disabled={index === 0}
                aria-label={t('settings.briefing_grid.move_up', { card: cardTitle(name) })}
                className="p-1.5 rounded-md border border-border/30 bg-background/80 hover:bg-background disabled:opacity-30 disabled:cursor-not-allowed"
              >
                <ArrowUp className="h-3.5 w-3.5" aria-hidden />
              </button>
              <button
                type="button"
                onClick={() => void handleMove(name, 'down')}
                disabled={index === preferences.order.length - 1}
                aria-label={t('settings.briefing_grid.move_down', { card: cardTitle(name) })}
                className="p-1.5 rounded-md border border-border/30 bg-background/80 hover:bg-background disabled:opacity-30 disabled:cursor-not-allowed"
              >
                <ArrowDown className="h-3.5 w-3.5" aria-hidden />
              </button>
              <Switch
                checked={visible}
                onCheckedChange={() =>
                  void persist({ ...preferences, hidden: toggleHidden(preferences.hidden, name) })
                }
                aria-label={t(
                  visible ? 'settings.briefing_grid.hide' : 'settings.briefing_grid.show',
                  { card: cardTitle(name) }
                )}
              />
            </li>
          );
        })}
      </ul>
      <div aria-live="polite" className="sr-only">
        {announcement}
      </div>
    </div>
  );

  return (
    <SettingsSection
      value="briefing-grid"
      title={t('settings.briefing_grid.title')}
      description={t('settings.briefing_grid.description')}
      icon={LayoutDashboard}
    >
      {content}
    </SettingsSection>
  );
}
