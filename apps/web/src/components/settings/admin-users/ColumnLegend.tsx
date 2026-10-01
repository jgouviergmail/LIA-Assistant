'use client';

/**
 * What each icon column of the administrators' user table means.
 *
 * Thirty headers are a glyph alone. A pointer reads their tooltip, a screen
 * reader their `sr-only` name — a finger on a phone reads neither, so the
 * table carries its legend, folded until asked for. It reads the very
 * declarations the headers render, so the two cannot disagree.
 */

import { Info, ShieldOff, type LucideIcon } from 'lucide-react';

import { Disclosure } from '@/components/ui/disclosure';

import {
  ADMIN_USER_COUNT_COLUMNS,
  ADMIN_USER_SWITCHES,
  ADMIN_USER_SWITCH_ICONS,
  switchLabelKey,
  tableLabelKey,
} from './columns';

interface LegendEntry {
  id: string;
  icon: LucideIcon;
  labelKey: string;
}

const LEGEND: readonly LegendEntry[] = [
  { id: 'is_usage_blocked', icon: ShieldOff, labelKey: tableLabelKey('blocked') },
  ...ADMIN_USER_COUNT_COLUMNS.map(column => ({
    id: column.key,
    icon: column.icon,
    labelKey: tableLabelKey(column.labelKey),
  })),
  ...ADMIN_USER_SWITCHES.map(key => ({
    id: key,
    icon: ADMIN_USER_SWITCH_ICONS[key],
    labelKey: switchLabelKey(key),
  })),
];

export function ColumnLegend({ t }: { t: (key: string) => string }) {
  return (
    <Disclosure icon={Info} title={t('settings.admin.users.legend_title')} className="mb-4">
      <ul className="grid gap-x-4 gap-y-2 text-sm sm:grid-cols-2 lg:grid-cols-3">
        {LEGEND.map(({ id, icon: Icon, labelKey }) => (
          <li key={id} className="flex min-w-0 items-center gap-2">
            <Icon className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
            <span className="min-w-0 break-words">{t(labelKey)}</span>
          </li>
        ))}
      </ul>
    </Disclosure>
  );
}
