'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Scaling } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useFloatingDrag } from '@/hooks/useFloatingDrag';
import { useAvatarRuntime } from '@/lib/avatars/runtime';
import type { AvatarEngine } from '@/lib/avatars/engine';
import type { AvatarConnectionState } from '@/lib/avatars/types';
import { cn } from '@/lib/utils';
import { AVATAR_SIZES, useAvatarWindowStore, type AvatarSize } from '@/stores/avatarWindowStore';

const NEXT_SIZE: Record<AvatarSize, AvatarSize> = { sm: 'md', md: 'lg', lg: 'sm' };
const TOOLBAR_TAP_HIDE_MS = 4000;

/** Match the animated companion: hover/focus on desktop, a brief tap reveal on touch. */
function useSizeControl(wasRecentDrag: () => boolean) {
  const [tapVisible, setTapVisible] = useState(false);
  useEffect(() => {
    if (!tapVisible) return;
    const timer = setTimeout(() => setTapVisible(false), TOOLBAR_TAP_HIDE_MS);
    return () => clearTimeout(timer);
  }, [tapVisible]);
  const onSurfaceClick = (event: React.MouseEvent<HTMLDivElement>) => {
    if ((event.target as HTMLElement).closest('button')) return;
    if (!window.matchMedia('(hover: none)').matches || wasRecentDrag()) return;
    setTapVisible(value => !value);
  };
  return { tapVisible, onSurfaceClick };
}

/** Keep stop acknowledgement independent of the chat subtree and its fallback. */
function useStopControl(engine: AvatarEngine | null) {
  const [stopping, setStopping] = useState(false);
  const [stopResult, setStopResult] = useState<boolean | null>(null);
  const stop = async () => {
    if (stopping || !engine) return;
    setStopping(true);
    try {
      setStopResult(await engine.stop());
    } finally {
      setStopping(false);
    }
  };
  return { stopping, stopResult, stop, reset: () => setStopResult(null) };
}

function AvatarConnectionFeedback({
  engine,
  state,
  onRetry,
}: {
  engine: AvatarEngine;
  state: AvatarConnectionState;
  onRetry: () => void;
}) {
  const { t } = useTranslation();
  if (state === 'ready') return null;
  return (
    <div className="space-y-2 px-2 py-2 text-xs" role="status">
      <p>
        {t(
          state === 'unavailable'
            ? engine.failure === 'avatar_start_rate_limited'
              ? 'settings.avatar.window_rate_limited'
              : engine.failure === 'avatar_start_busy'
                ? 'settings.avatar.window_busy'
                : 'settings.avatar.window_unavailable'
            : 'settings.avatar.window_connecting'
        )}
      </p>
      <Button
        variant="outline"
        size="sm"
        className="min-h-11 w-full"
        onClick={() => {
          void engine.media.unlock();
          if (state === 'unavailable') void engine.retry();
          onRetry();
        }}
      >
        {t(
          state === 'unavailable' ? 'settings.avatar.window_retry' : 'settings.avatar.window_unlock'
        )}
      </Button>
    </div>
  );
}

export function AvatarWindow() {
  const { t } = useTranslation();
  const { engine, present, state } = useAvatarRuntime();
  const { stopping, stopResult, stop, reset } = useStopControl(engine);
  const root = useRef<HTMLDivElement>(null);
  const { size, position, setSize, setPosition } = useAvatarWindowStore();
  const drag = useFloatingDrag(root, position, setPosition, present && !!engine);
  const { tapVisible, onSurfaceClick } = useSizeControl(drag.wasRecentDrag);
  const attach = useCallback(
    (video: HTMLVideoElement | null) => engine?.media.attach(video),
    [engine]
  );
  if (!present || !engine) return null;
  const pixel = drag.displayPos;
  const anchor = pixel
    ? { left: pixel.x, top: pixel.y }
    : position
      ? { left: `${position.xPct}vw`, top: `${position.yPct}vh` }
      : { right: 16, bottom: 'max(112px, env(safe-area-inset-bottom))' };
  return (
    <div
      ref={root}
      role="toolbar"
      aria-label={t('settings.avatar.window_move')}
      tabIndex={0}
      onPointerDown={drag.onPointerDown}
      onPointerMove={drag.onPointerMove}
      onPointerUp={drag.onPointerUp}
      onPointerCancel={drag.onPointerUp}
      onLostPointerCapture={drag.onPointerUp}
      onKeyDown={drag.onKeyDown}
      onClick={onSurfaceClick}
      className="group fixed z-30 cursor-grab touch-none rounded-xl border border-primary/30 bg-card shadow-lg active:cursor-grabbing focus-visible:ring-2 focus-visible:ring-primary"
      style={{
        ...anchor,
        width: `min(${AVATAR_SIZES[size]}px, calc(100vw - 32px))`,
        maxHeight: 'calc(100dvh - 32px)',
      }}
    >
      <div
        className={cn(
          'absolute -top-3 left-1/2 z-10 -translate-x-1/2 transition-opacity',
          'group-hover:pointer-events-auto group-hover:opacity-100',
          'group-focus-within:pointer-events-auto group-focus-within:opacity-100',
          tapVisible ? 'pointer-events-auto opacity-100' : 'pointer-events-none opacity-0'
        )}
      >
        <button
          type="button"
          aria-label={t('settings.avatar.window_cycle_size')}
          title={t(`settings.avatar.window_${size}`)}
          onClick={() => setSize(NEXT_SIZE[size])}
          className="flex h-6 w-6 items-center justify-center rounded-full bg-muted text-muted-foreground shadow ring-1 ring-border transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary [@media(hover:none)]:h-8 [@media(hover:none)]:w-8"
        >
          <Scaling aria-hidden className="h-3.5 w-3.5" />
        </button>
      </div>
      <video
        ref={attach}
        muted
        autoPlay
        playsInline
        aria-label={t('settings.avatar.title')}
        className="block aspect-square w-full rounded-xl object-contain bg-black"
        style={{ maxHeight: 'max(80px, calc(100dvh - 192px))' }}
      />
      <AvatarConnectionFeedback engine={engine} state={state} onRetry={reset} />
      <div className="px-2 pb-2 pt-1">
        <Button
          variant="outline"
          size="sm"
          className="min-h-11 w-full"
          aria-disabled={stopping}
          onClick={stop}
        >
          {t(stopping ? 'settings.avatar.window_stopping' : 'settings.avatar.window_stop')}
        </Button>
        {stopResult !== null && state === 'unavailable' ? (
          <p role="status" className="pt-2 text-xs">
            {t(
              stopResult
                ? 'settings.avatar.window_stopped'
                : 'settings.avatar.window_stop_unconfirmed'
            )}
          </p>
        ) : null}
      </div>
    </div>
  );
}
