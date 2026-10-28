'use client';
import type { WorldSpeech } from './speech';
import type { PrivateSignalPresentation } from './private-signal-projection';
import type { WorldActingSource } from './useWorldActingSource';

import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type ReactNode,
  type RefObject,
} from 'react';
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
import type { Quality, WorldActingState } from './types';
import type { WorldDriver } from './shared-simulation';
import type { HomeSkin } from './home-projection';
import type { SceneHost, SceneTarget } from './scene-interactions';
import { WORLD } from './definition';
import './world.css';
import './mobile-hud.css';
import './avatar.css';
import { NEUTRAL_ATMOSPHERE, type Atmosphere } from './atmosphere';
import { WorldExplorationControls, type WorldExploration } from './WorldExplorationControls';
import { WorldSeasonControls } from './WorldSeasonControls';
import { seasonAt } from './season';
import { WorldEmoteControls } from './WorldEmoteControls';
import type { EmoteKind, EmoteOutcome } from './emote-catalogue';
import { WorldEmoteFeedback } from './WorldEmoteFeedback';
import type { EmoteFeedback } from './useWorldSession';
import { cosmeticActionForId, type CosmeticActionId } from './cosmetic-interactions';
import { WorldPhotoControls } from './WorldPhotoControls';

function preferredQuality(): Quality {
  return typeof window !== 'undefined' &&
    window.matchMedia('(pointer: coarse), (max-width: 640px)').matches
    ? 'low'
    : 'balanced';
}

function useWorldHudState(
  controlled: boolean | undefined,
  onChange: ((expanded: boolean) => void) | undefined
) {
  const [localExpanded, setLocalExpanded] = useState(false);
  const changeExpanded = useCallback(
    (value: boolean) => {
      setLocalExpanded(value);
      onChange?.(value);
    },
    [onChange]
  );
  return [controlled ?? localExpanded, changeExpanded] as const;
}

export function WorldPrototype({
  hudExpanded: controlledHudExpanded,
  onHudExpandedChange,
  onPhotoOpen,
  onActingState,
  conversationOpen = false,
  acting,
  privateSignals,
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
  exploration,
  onEmote,
  onCosmeticCue,
}: {
  hudExpanded?: boolean;
  onHudExpandedChange?(expanded: boolean): void;
  onPhotoOpen?(open: boolean): void;
  onEmote?(kind: EmoteKind): boolean;
  onCosmeticCue?(action: CosmeticActionId, current: () => boolean, targetId: string): void;
  onActingState?(state: WorldActingState): void;
  conversationOpen?: boolean;
  acting?: WorldActingSource;
  privateSignals?: readonly PrivateSignalPresentation[];
  widgets?: ReactNode | ((controls: ReactNode) => ReactNode);
  speech?: WorldSpeech;
  exploration?: WorldExploration;
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
  const [hudExpanded, changeHudExpanded] = useWorldHudState(
    controlledHudExpanded,
    onHudExpandedChange
  );
  const [joystick, setJoystick] = useJoystickPreference();
  const touch = useMediaQuery('(pointer: coarse), (max-width: 767px)');
  const compact = useMediaQuery(
    '(max-width: 767px), (max-height: 520px) and (orientation: landscape)'
  );
  const [help, setHelp] = useState(false);
  const [photoOpen, setPhotoOpen] = useState(false);
  const photoVisibility = useCallback(
    (open: boolean) => {
      setPhotoOpen(open);
      onPhotoOpen?.(open);
    },
    [onPhotoOpen]
  );
  const [metrics, setMetrics] = useState(false);
  const inputPaused = [help, photoOpen, editingHome, interactionPaused].some(Boolean);
  const descriptionId = useId();
  const { canvasRef, snapshot, failed, retry, command, focusScene } = useWorldRuntime({
    onCosmeticCue,
    season: explorationSeason(atmosphere, exploration),
    onActingState,
    conversationOpen,
    acting,
    privateSignals,
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
    showRoute: routeVisible(exploration),
  });
  const localSerial = useRef(0);
  const [localFeedback, setLocalFeedback] = useState<EmoteFeedback | null>(null);
  /** A private gesture: refused like a shared one, and said when it is refused. */
  function localGesture(kind: EmoteKind): boolean {
    const result: { outcome: EmoteOutcome } = { outcome: 'unavailable' };
    command(runtime => {
      result.outcome = runtime.emote(kind);
    });
    setLocalFeedback(
      result.outcome === 'accepted'
        ? null
        : { result: result.outcome, serial: ++localSerial.current }
    );
    return result.outcome === 'accepted';
  }
  function gesture(kind: EmoteKind): void {
    const sent =
      snapshot.zone === 'home' || !connected ? localGesture(kind) : onEmote?.(kind) === true;
    // A refused gesture keeps the controls where they are, beside its announcement.
    if (sent && touch) changeHudExpanded(false);
  }
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
  const directGestures = compact && !hudExpanded;
  const gestures = (
    <WorldEmoteControls
      lng={lng}
      canvasRef={canvasRef}
      disabled={inputPaused}
      presentation={directGestures ? 'direct' : 'menu'}
      onReturnFocus={focusScene}
      onSelect={gesture}
    />
  );
  return (
    <section
      className="world-prototype border border-border"
      aria-label={t('world.title')}
      data-hud-expanded={hudExpanded}
      data-world-status={worldStatus(failed, connected)}
      data-world-editing={editingHome}
      data-world-phase={atmosphere.phase}
      data-world-weather={atmosphere.weather}
      data-world-cosmetic-effects={snapshot.metrics.cosmeticEffects ?? 0}
    >
      <WorldSceneSurface
        lng={lng}
        failed={failed}
        retry={retry}
        canvasRef={canvasRef}
        descriptionId={descriptionId}
      />
      {!failed && (
        <WorldHud
          conversationOpen={conversationOpen}
          lng={lng}
          expanded={hudExpanded}
          onExpand={() => changeHudExpanded(!hudExpanded)}
          joystick={shouldShowJoystick(joystick, touch, inputPaused)}
          gestures={directGestures ? gestures : undefined}
          widgets={
            <WorldInteractionWidgets
              lng={lng}
              ownerId={ownerId}
              disabled={inputPaused}
              command={command}
              onPhotoOpen={photoVisibility}
              directGestures={directGestures}
              gestures={gestures}
              exploration={exploration}
              widgets={widgets}
            />
          }
          snapshot={snapshot}
          metrics={metrics}
          command={command}
          onMetrics={() => setMetrics(value => !value)}
          onHelp={() => setHelp(true)}
          atmosphere={atmosphere}
          season={explorationSeason(atmosphere, exploration)}
          prototype={!connected}
          nearbyLabel={targetLabel(snapshot.nearby, sceneLabel)}
        />
      )}
      <WorldObjectHint hover={failed ? null : snapshot.hover} label={sceneLabel} />
      <WorldEmoteFeedback lng={lng} feedback={localFeedback} />
      <WorldHelp
        exploration={exploration}
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

function WorldSceneSurface({
  lng,
  failed,
  retry,
  canvasRef,
  descriptionId,
}: {
  lng: Language;
  failed: boolean;
  retry(): void;
  canvasRef: RefObject<HTMLCanvasElement | null>;
  descriptionId: string;
}) {
  const { t } = useTranslation(lng);
  return (
    <>
      {!failed && <h1 className="sr-only">{t('world.title')}</h1>}
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
    </>
  );
}

function WorldInteractionWidgets({
  lng,
  ownerId,
  disabled,
  command,
  onPhotoOpen,
  directGestures,
  gestures,
  exploration,
  widgets,
}: {
  lng: Language;
  ownerId: string;
  disabled: boolean;
  command: ReturnType<typeof useWorldRuntime>['command'];
  onPhotoOpen(open: boolean): void;
  directGestures: boolean;
  gestures: ReactNode;
  exploration?: WorldExploration;
  widgets?: ReactNode | ((controls: ReactNode) => ReactNode);
}) {
  const controls = (
    <>
      <div className="pointer-events-auto w-fit">
        <WorldPhotoControls
          key={ownerId}
          lng={lng}
          ownerId={ownerId}
          disabled={disabled}
          command={command}
          onOpen={onPhotoOpen}
        />
      </div>
      {!directGestures && <div className="pointer-events-auto w-fit">{gestures}</div>}
      {exploration && <WorldExplorationControls lng={lng} exploration={exploration} />}
    </>
  );
  return typeof widgets === 'function' ? (
    widgets(controls)
  ) : (
    <div className="world-device-controls">
      {widgets}
      {controls}
    </div>
  );
}

function routeVisible(exploration: WorldExploration | undefined): boolean {
  return exploration?.control.experience?.preferences.show_route ?? true;
}
function targetLabel(
  target: SceneTarget | null | undefined,
  label: ((target: SceneTarget) => string) | undefined
): string | undefined {
  if (!target || (target.kind === 'object' && cosmeticActionForId(WORLD, target.id)))
    return undefined;
  return label?.(target);
}
function explorationSeason(atmosphere: Atmosphere, exploration: WorldExploration | undefined) {
  return seasonAt(
    atmosphere.time,
    atmosphere.timezone,
    exploration?.control.experience?.preferences.season_mode ?? 'calendar',
    exploration?.control.experience?.preferences.hemisphere ?? 'north'
  );
}

function WorldHelp({
  exploration,
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
  exploration?: WorldExploration;
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
        {exploration && (
          <WorldSeasonControls
            lng={lng}
            control={exploration.control}
            enabled={exploration.enabled}
          />
        )}
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
  const text = targetLabel(hover?.target, label);
  if (!hover || !text) return null;
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
      <span>{text}</span>
    </div>
  );
}

function worldStatus(failed: boolean, connected: boolean) {
  if (failed) return 'unavailable';
  return connected ? 'shared' : 'local';
}
