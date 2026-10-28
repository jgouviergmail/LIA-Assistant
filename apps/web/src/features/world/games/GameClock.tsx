'use client';
import { useEffect, useState } from 'react';
import { Clock3 } from 'lucide-react';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { WorldGameClient } from '../game-client';

export function GameClock({
  lng,
  client,
  deadline,
}: {
  lng: Language;
  client: WorldGameClient;
  deadline: number;
}) {
  const { t } = useTranslation(lng);
  const [, update] = useState(0);
  useEffect(() => {
    let timer: ReturnType<typeof setInterval> | undefined;
    const resume = () => {
      clearInterval(timer);
      if (!document.hidden)
        timer = setInterval(() => {
          client.tick();
          update(value => value + 1);
        }, 1000);
    };
    resume();
    document.addEventListener('visibilitychange', resume);
    return () => {
      clearInterval(timer);
      document.removeEventListener('visibilitychange', resume);
    };
  }, [client]);
  const now = client.serverTime();
  if (now === null) return null;
  const seconds = Math.max(0, Math.ceil(deadline - now));
  const time = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
  return (
    <span
      className="inline-flex items-center gap-1 text-xs tabular-nums text-muted-foreground"
      aria-live="off"
    >
      <Clock3 className="size-3.5" aria-hidden="true" />
      {t('world.arcade.time_left', { time })}
    </span>
  );
}
