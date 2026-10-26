'use client';
import type { WorldSpeech } from './speech';

import { useEffect, useId, useRef, useState, type ReactNode, type RefObject } from 'react';
import { CircleHelp, TriangleAlert, MousePointer2 } from 'lucide-react';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { useMediaQuery } from '@/hooks/useMediaQuery';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { useWorldRuntime } from './useWorldRuntime';
import {
  useJoystickPreference,
  shouldShowJoystick,
  isJoystickPreference,
  type JoystickPreference,
} from './useJoystickPreference';
import { WorldHud } from './WorldHud';
import type { Quality } from './types';
import type { WorldDriver } from './shared-simulation';
import type { HomeSkin } from './home-projection';
import type { SceneHost, SceneTarget } from './scene-interactions';
import { WORLD } from './definition';
import './world.css';
import './mobile-hud.css';
import './avatar.css';
import { NEUTRAL_ATMOSPHERE, type Atmosphere } from './atmosphere';

function preferredQuality(): Quality {
  return typeof window !== 'undefined' &&
    window.matchMedia('(pointer: coarse), (max-width: 640px)').matches
    ? 'low'
    : 'balanced';
}

export function WorldPrototype({
  lng,
  ownerId,
  driver,
  playerAlias,
  connected = false,
  home = null,
  editingHome = false,
  interactionPaused = false,
  atmosphere = NEUTRAL_ATMOSPHERE,
  onInteract,
  scene,
  sceneLabel,
  widgets,
  speech,
}: {
  widgets?: ReactNode;
  speech?: WorldSpeech;
  lng: Language;
  ownerId: string;
  driver?: WorldDriver;
  playerAlias?: string;
  connected?: boolean;
  home?: HomeSkin | null;
  editingHome?: boolean;
  interactionPaused?: boolean;
  atmosphere?: Atmosphere;
  onInteract?: () => void;
  scene?: SceneHost;
  sceneLabel?: (target: SceneTarget) => string;
}) {
  const { t } = useTranslation(lng);
  const reducedMotion = useMediaQuery('(prefers-reduced-motion: reduce)');
  const [quality, setQuality] = useState<Quality>(preferredQuality);
  const [hudExpanded, setHudExpanded] = useState(false);
  const [joystick, setJoystick] = useJoystickPreference();
  const touch = useMediaQuery('(pointer: coarse), (max-width: 767px)');
  const [help, setHelp] = useState(false);
  const [metrics, setMetrics] = useState(false);
  const inputPaused = help || editingHome || interactionPaused;
  const descriptionId = useId();
  const { canvasRef, snapshot, failed, retry, command } = useWorldRuntime({
    ownerId,
    player: playerAlias ?? t('world.you'),
    driver,
    speech,
    bip: t('world.bip'),
    reducedMotion,
    paused: inputPaused,
    home,
    quality,
    atmosphere,
    onInteract,
    scene,
  });
  const previouslyEditing = useRef(false);
  useEffect(() => {
    if (editingHome) {
      const zone = WORLD.zones.find(item => item.id === 'home');
      if (zone)
        command(runtime =>
          runtime.explore({ x: zone.x + zone.width / 2, y: zone.y + zone.height / 2 })
        );
    } else if (previouslyEditing.current) command(runtime => runtime.recenter());
    previouslyEditing.current = editingHome;
  }, [editingHome, command]);
  return (
    <section
      className="world-prototype border border-border"
      aria-label={t('world.title')}
      data-hud-expanded={hudExpanded}
      data-world-status={worldStatus(failed, connected)}
      data-world-editing={editingHome}
      data-world-phase={atmosphere.phase}
      data-world-weather={atmosphere.weather}
    >
      {failed ? (
        <div className="world-fallback bg-background" role="alert">
          <TriangleAlert className="size-9 text-primary" aria-hidden="true" />
          <h1 className="text-xl font-semibold">{t('world.unavailable')}</h1>
          <p className="max-w-md text-center text-muted-foreground">
            {t('world.unavailable_hint')}
          </p>
          <Button onClick={retry}>{t('world.retry')}</Button>
        </div>
      ) : (
        <canvas
          ref={canvasRef}
          tabIndex={0}
          className="world-canvas"
          aria-label={t('world.canvas')}
          aria-describedby={descriptionId}
        />
      )}
      <p id={descriptionId} className="sr-only">
        {t('world.keyboard_hint')}
      </p>
      {!failed && (
        <WorldHud
          lng={lng}
          expanded={hudExpanded}
          onExpand={() => setHudExpanded(value => !value)}
          joystick={shouldShowJoystick(joystick, touch, inputPaused)}
          widgets={widgets}
          snapshot={snapshot}
          metrics={metrics}
          command={command}
          onMetrics={() => setMetrics(value => !value)}
          onHelp={() => setHelp(true)}
          atmosphere={atmosphere}
          prototype={!connected}
          nearbyLabel={snapshot.nearby ? sceneLabel?.(snapshot.nearby) : undefined}
        />
      )}
      <WorldObjectHint hover={failed ? null : snapshot.hover} label={sceneLabel} />
      <WorldHelp
        lng={lng}
        open={help}
        onOpenChange={setHelp}
        joystick={joystick}
        setJoystick={setJoystick}
        quality={quality}
        setQuality={setQuality}
        canvasRef={canvasRef}
        connected={connected}
      />
    </section>
  );
}

function WorldHelp({
  lng,
  open,
  onOpenChange,
  quality,
  setQuality,
  canvasRef,
  connected,
  joystick,
  setJoystick,
}: {
  joystick: JoystickPreference;
  setJoystick(value: JoystickPreference): void;
  lng: Language;
  open: boolean;
  onOpenChange(open: boolean): void;
  quality: Quality;
  setQuality(quality: Quality): void;
  canvasRef: RefObject<HTMLCanvasElement | null>;
  connected: boolean;
}) {
  const { t } = useTranslation(lng);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="max-h-[85dvh] overflow-y-auto"
        onCloseAutoFocus={event => {
          event.preventDefault();
          canvasRef.current?.focus();
        }}
      >
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <CircleHelp className="size-5 text-primary" aria-hidden="true" />
            {t('world.help')}
          </DialogTitle>
          <DialogDescription>
            {t(connected ? 'world.session.intro' : 'world.disclaimer')}
          </DialogDescription>
        </DialogHeader>
        <ul className="space-y-3 text-sm">
          <li>{t('world.keyboard_hint')}</li>
          <li>{t('world.pointer_hint')}</li>
          <li>{t('world.camera_hint')}</li>
          <li>{t('world.bip_hint')}</li>
        </ul>
        <label className="flex flex-wrap items-center justify-between gap-3 text-sm">
          {t('world.quality')}
          <select
            className="world-quality border border-border bg-background text-sm"
            value={quality}
            onChange={event => {
              const value = event.target.value;
              if (value === 'low' || value === 'balanced' || value === 'high') setQuality(value);
            }}
          >
            <option value="low">{t('world.quality_low')}</option>
            <option value="balanced">{t('world.quality_balanced')}</option>
            <option value="high">{t('world.quality_high')}</option>
          </select>
        </label>
        <label className="flex flex-wrap items-center justify-between gap-3 text-sm">
          {t('world.joystick.label')}
          <select
            className="world-quality border border-border bg-background text-sm"
            aria-label={t('world.joystick.label')}
            value={joystick}
            onChange={event => {
              if (isJoystickPreference(event.target.value)) setJoystick(event.target.value);
            }}
          >
            {(['auto', 'show', 'hide'] as const).map(value => (
              <option key={value} value={value}>
                {t('world.joystick.' + value)}
              </option>
            ))}
          </select>
        </label>
        <p className="text-xs text-muted-foreground">
          {t(connected ? 'world.session.private' : 'world.local')}
        </p>
        <Button onClick={() => onOpenChange(false)}>{t('world.play')}</Button>
      </DialogContent>
    </Dialog>
  );
}

function WorldObjectHint({
  hover,
  label,
}: {
  hover: import('./types').WorldSnapshot['hover'];
  label?: (target: SceneTarget) => string;
}) {
  if (!hover || !label) return null;
  return (
    <div
      className="world-object-hint"
      role="tooltip"
      style={{
        left: `clamp(140px, ${hover.point.x}px, calc(100% - 140px))`,
        top: Math.max(84, hover.point.y - 28),
      }}
    >
      <MousePointer2 size={16} aria-hidden="true" />
      <span>{label(hover.target)}</span>
    </div>
  );
}

function worldStatus(failed: boolean, connected: boolean) {
  if (failed) return 'unavailable';
  return connected ? 'shared' : 'local';
}
