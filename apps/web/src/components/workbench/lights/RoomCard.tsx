'use client';

/**
 * RoomCard — one room of the bridge, at a glance and at a touch (ADR-369).
 *
 * Its name opens the room (its scenes and lamps); its switch turns every lamp
 * of the room on or off; its slider sets them all, sent on release. The line
 * under the name is exact — the bridge is read whole: how many lamps, and how
 * bright the ones that are on (or « off »).
 */
import Link from 'next/link';
import { House } from 'lucide-react';
import { useState } from 'react';

import { Switch } from '@/components/ui/switch';
import type { RoomChangeBody } from '@/hooks/useWorkbenchLights';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { cn } from '@/lib/utils';
import { roomBrightness } from '@/lib/workbench/lights';
import type { WorkbenchLight, WorkbenchRoom } from '@/lib/workbench/types';

import { CommitSlider } from './CommitSlider';

export interface RoomCardProps {
  lng: Language;
  room: WorkbenchRoom;
  lights: readonly WorkbenchLight[];
  /** The room open beside the list. */
  open: boolean;
  href: string;
  /** Send a change; resolves once sent and re-read, rejects (already said) when refused. */
  onChange: (change: RoomChangeBody) => Promise<void>;
  /** Hands the room's link to the screen, which gives it the focus back. */
  linkRef: (roomId: string, link: HTMLAnchorElement | null) => void;
}

export function RoomCard({ lng, room, lights, open, href, onChange, linkRef }: RoomCardProps) {
  const { t } = useTranslation(lng);
  const [onDraft, setOnDraft] = useState<boolean | null>(null);
  const on = onDraft ?? room.on;
  const brightness = roomBrightness(room.light_ids, lights);
  const count = room.light_ids.length;
  const dimmable = lights.some(
    light => room.light_ids.includes(light.id) && light.brightness !== null
  );

  return (
    <div
      className={cn('space-y-3 rounded-lg border bg-card p-4', open && 'border-primary')}
      aria-current={open ? 'true' : undefined}
    >
      <div className="flex items-center gap-3">
        <House
          className={cn('h-5 w-5 shrink-0', on ? 'text-primary' : 'text-muted-foreground')}
          aria-hidden="true"
        />
        <Link
          ref={link => linkRef(room.id, link)}
          href={href}
          scroll={false}
          className="min-w-0 flex-1 rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <span className="block truncate text-sm font-semibold text-foreground">{room.name}</span>
          <span className="block text-xs text-muted-foreground">
            {brightness === null
              ? t('workbench.lights.room_dark', { count })
              : t('workbench.lights.room_lit', { count, brightness })}
          </span>
        </Link>
        <Switch
          checked={on}
          aria-label={t('workbench.lights.room_switch', { room: room.name })}
          onCheckedChange={next => {
            setOnDraft(next);
            void onChange({ on: next })
              .catch(() => undefined)
              .finally(() => setOnDraft(null));
          }}
        />
      </div>
      {dimmable && (
        <CommitSlider
          label={t('workbench.lights.room_brightness', { room: room.name })}
          value={brightness ?? 0}
          min={0}
          max={100}
          format={value => `${Math.round(value)} %`}
          onCommit={value => onChange({ brightness: value })}
        />
      )}
    </div>
  );
}
