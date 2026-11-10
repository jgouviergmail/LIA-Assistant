'use client';

/**
 * LightsTool — the « Tools » lights screen (ADR-369, mock-ups « Lumières »).
 *
 * The bridge is read once: its rooms, then its zones, each with a switch and a slider
 * for all its lamps; the open room (`?room=`, the first from `lg`) beside them with
 * its scenes and each lamp's own controls; lamps no room owns under « Other
 * lights ». Rooms and lamps come in alphabetical order. Below `lg` the rooms are the screen and a room replaces them, with
 * the way back, which takes the focus — and the room's card gets it back when
 * the list returns; opening pushes, closing replaces (the workboard's rule). A
 * refused change is said in the refusal's own words; « Refresh » re-reads the
 * bridge in place. « All off » switches off what is lit, room by room, and says
 * what stayed on; once nothing is lit it says « All on », and lights what has lamps. The open
 * room's title ends on the question to LIA, as every detail's bar does.
 */
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { ArrowLeft, Lightbulb, Power, PowerOff } from '@/lib/icons';
import { type RefObject, useCallback, useMemo, useRef, useState } from 'react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { EmptyState } from '@/components/ui/empty-state';
import { Skeleton } from '@/components/ui/skeleton';
import { useDrillDownFocus } from '@/hooks/useDrillDownFocus';
import { useMediaQuery } from '@/hooks/useMediaQuery';
import {
  useWorkbenchLights,
  type LightChangeBody,
  type RoomChangeBody,
} from '@/hooks/useWorkbenchLights';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { cn } from '@/lib/utils';
import { workbenchRefusal } from '@/lib/workbench/errors';
import {
  inNameOrder,
  lampsByAnswer,
  openSelection,
  OTHER_LIGHTS,
  scenesOutsideRooms,
  type LightsSelection,
} from '@/lib/workbench/lights';
import { WORKBENCH_DESKTOP, toolPath } from '@/lib/workbench/tools';
import type {
  RereadOptions,
  WorkbenchLight,
  WorkbenchLights,
  WorkbenchRoom,
  WorkbenchScene,
} from '@/lib/workbench/types';
import { buildLocalizedPath } from '@/utils/i18n-path-utils';

import { useWorkbench } from '../WorkbenchShell';
import { WorkbenchToolHeader } from '../WorkbenchToolHeader';
import { WorkbenchUnavailable, unavailableKind } from '../WorkbenchUnavailable';
import { readyLine } from '../assist/lines';
import { askAct, BarAct } from '../DetailBar';
import { useToolBridges } from '../useToolBridges';
import { LightControls } from './LightControls';
import { RoomCard } from './RoomCard';
import { ScenePicker, type SceneRecallAct } from './ScenePicker';

export function LightsTool({ lng }: { lng: Language }) {
  const { availability } = useWorkbench();
  const tool = availability.tools.find(item => item.tool === 'lights');
  if (tool?.state !== 'ready') {
    return (
      <>
        <WorkbenchToolHeader lng={lng} tool="lights" />
        <WorkbenchUnavailable lng={lng} kind={unavailableKind(tool)} tool="lights" />
      </>
    );
  }
  return <ReadyLights lng={lng} />;
}

function ReadyLights({ lng }: { lng: Language }) {
  const { t } = useTranslation(lng);
  const params = useSearchParams();
  const requestedLight = params.get('light');
  const requestedRoom = params.get('room');
  const desktop = useMediaQuery(WORKBENCH_DESKTOP);
  const {
    bridge: read,
    loading,
    error,
    refresh,
    setLight,
    setRoom,
    recallScene,
    switchAll,
  } = useWorkbenchLights(true);
  // Rooms and lamps in alphabetical order, in the reader's language (owner request
  // 2026-10-31) — sorted once here, so the list, the room opened by default and the
  // lamps all follow it.
  const bridge = useMemo(() => (read ? inNameOrder(read, lng) : null), [read, lng]);
  const target = lightTarget(bridge, requestedLight, requestedRoom, desktop);
  const asked = target.roomId;
  const back = useRef<HTMLAnchorElement>(null);
  // Below lg the room replaces the list: its way back takes the focus, and the
  // room's card gets it back when the list returns (whichever way it closed).
  const linkRef = useDrillDownFocus(asked, { enabled: target.followFocus, opened: back });

  const href = useCallback(
    (room: string | null) =>
      `${buildLocalizedPath(toolPath('lights'), lng)}${room ? `?room=${encodeURIComponent(room)}` : ''}`,
    [lng]
  );
  const act = useCallback(
    async (run: () => Promise<void>) => {
      try {
        await run();
      } catch (refused: unknown) {
        const refusal = workbenchRefusal(refused);
        toast.error(refusal ? t(refusal.key, refusal.values) : t('workbench.lights.failed'));
        throw refused;
      }
    },
    [t]
  );
  // What is on screen stays on a failed re-read: the person who asked is told.
  const reread = ({ unasked = false }: RereadOptions = {}) =>
    refresh().catch(() => {
      if (!unasked) toast.error(t('workbench.lights.failed'));
    });

  if (!bridge) {
    return (
      <PendingLights
        lng={lng}
        failed={!loading && Boolean(error)}
        onRetry={() => void refresh().catch(() => undefined)}
      />
    );
  }
  const selection = openSelection(bridge, asked, target.defaultOpen);
  const empty = bridge.rooms.length === 0 && selection.orphans.length === 0;

  return (
    <>
      <WorkbenchToolHeader lng={lng} tool="lights" onRefresh={reread}>
        {!empty && <AllSwitchButton lng={lng} bridge={bridge} onSwitch={switchAll} />}
      </WorkbenchToolHeader>
      {target.missing && (
        <p role="alert" className="rounded-lg border p-3 text-sm">
          {t('workbench.states.light_target_missing')}
        </p>
      )}
      {empty ? (
        <EmptyState
          icon={Lightbulb}
          title={t('workbench.lights.no_lights_title')}
          action={{ label: t('workbench.states.refresh'), onClick: () => void reread() }}
        />
      ) : (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,20rem)_minmax(0,1fr)]">
          <RoomList
            lng={lng}
            rooms={bridge.rooms}
            lights={bridge.lights}
            cardScenes={desktop ? [] : bridge.scenes}
            otherScenes={scenesOutsideRooms(bridge)}
            selection={selection}
            replaced={selection.detailOpen && asked !== null}
            href={href}
            linkRef={linkRef}
            onRoomChange={(roomId, change) => act(() => setRoom(roomId, change))}
            onRecall={(scene, play) => act(() => recallScene(scene.id, play))}
          />
          {selection.detailOpen && (
            <RoomDetail
              lng={lng}
              selection={selection}
              scenes={bridge.scenes}
              shownBelowLg={asked !== null}
              back={back}
              backHref={href(null)}
              targetedLight={target.lightId}
              onLightChange={(lightId, change) => act(() => setLight(lightId, change))}
              onRecall={(scene, play) => act(() => recallScene(scene.id, play))}
            />
          )}
        </div>
      )}
    </>
  );
}

/** Resolve a card's lamp against the received bridge; never substitute a default room. */
function lightTarget(
  bridge: WorkbenchLights | null,
  lightId: string | null,
  roomId: string | null,
  desktop: boolean
) {
  if (!lightId) {
    return {
      roomId,
      lightId: undefined,
      missing: false,
      followFocus: !desktop,
      defaultOpen: desktop,
    };
  }
  const light = bridge?.lights.find(item => item.id === lightId);
  if (!light) {
    return {
      roomId: null,
      lightId: undefined,
      missing: bridge !== null,
      followFocus: false,
      defaultOpen: false,
    };
  }
  const room = bridge?.rooms.find(item => item.kind !== 'zone' && item.light_ids.includes(lightId));
  const resolvedRoom = room?.id ?? (light.room_id === null ? OTHER_LIGHTS : null);
  return {
    roomId: resolvedRoom,
    lightId: light.id,
    missing: bridge !== null && resolvedRoom === null,
    followFocus: false,
    defaultOpen: false,
  };
}

/**
 * Switches off what is lit, and lights everything once nothing is; says what did not follow. What
 * it offers is read from the bridge, so it follows a lamp switched by hand as it follows its own
 * click, on the same button, under the same focus.
 */
function AllSwitchButton({
  lng,
  bridge,
  onSwitch,
}: {
  lng: Language;
  bridge: WorkbenchLights;
  onSwitch: (
    on: boolean,
    roomIds: readonly string[],
    lightIds: readonly string[]
  ) => Promise<number>;
}) {
  const { t } = useTranslation(lng);
  const [busy, setBusy] = useState(false);
  // A zone's lamps go with their rooms: a second command would only cost the bridge's window.
  const rooms = bridge.rooms.filter(room => room.kind !== 'zone' && room.light_ids.length > 0);
  // A lamp that does not answer takes no command, and its last word says nothing of the house.
  const lamps = bridge.lights.filter(light => light.room_id === null && light.reachable !== false);
  const lit = rooms.some(room => room.on) || lamps.some(light => light.on);
  const word = lit ? 'all_off' : 'all_on';
  const switchAll = async () => {
    const roomIds = rooms.filter(room => room.on === lit).map(room => room.id);
    const lightIds = lamps.filter(light => light.on === lit).map(light => light.id);
    if (busy || roomIds.length + lightIds.length === 0) return;
    setBusy(true);
    const failed = await onSwitch(!lit, roomIds, lightIds);
    setBusy(false);
    if (failed > 0) toast.error(t(`workbench.lights.${word}_partial`, { count: failed }));
  };
  const Icon = lit ? PowerOff : Power;
  return (
    <Button
      variant="outline"
      size="sm"
      className="min-h-10 min-w-10 gap-1.5 px-0 sm:px-3"
      isLoading={busy}
      onClick={() => void switchAll()}
      aria-label={t(`workbench.lights.${word}`)}
    >
      <Icon className="h-4 w-4" aria-hidden="true" />
      <span className="hidden sm:inline">{t(`workbench.lights.${word}`)}</span>
    </Button>
  );
}

/** The bridge not read yet: its geometry, or the failure with a way to retry. */
function PendingLights({
  lng,
  failed,
  onRetry,
}: {
  lng: Language;
  failed: boolean;
  onRetry: () => void;
}) {
  return (
    <>
      <WorkbenchToolHeader lng={lng} tool="lights" />
      {failed ? (
        <WorkbenchUnavailable lng={lng} kind="error" onRetry={onRetry} />
      ) : (
        <div className="space-y-3">
          {[1, 2, 3].map(index => (
            <Skeleton key={index} className="h-24 w-full" />
          ))}
        </div>
      )}
    </>
  );
}

interface RoomListProps {
  lng: Language;
  rooms: readonly WorkbenchRoom[];
  lights: readonly WorkbenchLight[];
  /** Every room's scenes drawn on its card; none where the room sits beside the list. */
  cardScenes: readonly WorkbenchScene[];
  /** The scenes no room holds, under the rooms. */
  otherScenes: readonly WorkbenchScene[];
  selection: LightsSelection;
  /** Below lg, an open room takes the list's place. */
  replaced: boolean;
  href: (room: string | null) => string;
  linkRef: (id: string, element: HTMLElement | null) => void;
  onRoomChange: (roomId: string, change: RoomChangeBody) => Promise<void>;
  onRecall: SceneRecallAct;
}

/** The rooms, then the lamps and the scenes no room owns. */
function RoomList({
  lng,
  rooms,
  lights,
  cardScenes,
  otherScenes,
  selection,
  replaced,
  href,
  linkRef,
  onRoomChange,
  onRecall,
}: RoomListProps) {
  const { t } = useTranslation(lng);
  return (
    <div className={cn('space-y-3', replaced ? 'hidden lg:block' : 'block')}>
      {rooms.map(room => (
        <RoomCard
          key={room.id}
          lng={lng}
          room={room}
          lights={lights}
          open={room.id === selection.openId}
          href={href(room.id)}
          onChange={change => onRoomChange(room.id, { kind: room.kind, ...change })}
          linkRef={linkRef}
          scenes={cardScenes.filter(scene => scene.room_id === room.id)}
          onRecall={onRecall}
        />
      ))}
      {selection.orphans.length > 0 && (
        <Link
          ref={element => linkRef(OTHER_LIGHTS, element)}
          href={href(OTHER_LIGHTS)}
          scroll={false}
          aria-current={selection.openId === OTHER_LIGHTS ? 'true' : undefined}
          className="block rounded-lg border bg-card p-4 text-sm font-semibold text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          {t('workbench.lights.other_lights')}
        </Link>
      )}
      <ScenePicker
        lng={lng}
        scenes={otherScenes}
        labelKey="workbench.lights.other_scenes"
        onRecall={onRecall}
      />
    </div>
  );
}

/** A room's lamps; those that answer first, those that do not set apart under a title. */
function LampGroups({
  lng,
  lights,
  onLightChange,
  targetedLight,
}: {
  lng: Language;
  lights: readonly WorkbenchLight[];
  onLightChange: (lightId: string, change: LightChangeBody) => Promise<void>;
  targetedLight?: string;
}) {
  const { t } = useTranslation(lng);
  const { answering, silent } = lampsByAnswer(lights);
  const cards = (lamps: readonly WorkbenchLight[]) => (
    // As many columns as hold a card (`auto-fill`, never `auto-fit`, which would stretch a
    // lamp alone across the window).
    <div className="grid gap-3 xl:grid-cols-[repeat(auto-fill,minmax(24rem,1fr))]">
      {lamps.map(light => (
        <LightControls
          key={light.id}
          lng={lng}
          light={light}
          targeted={targetedLight === light.id}
          onChange={change => onLightChange(light.id, change)}
        />
      ))}
    </div>
  );
  if (silent.length === 0) return cards(answering);
  const group = (title: string, lamps: readonly WorkbenchLight[]) => (
    <section aria-label={title} className="space-y-2">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {title}
      </h3>
      {cards(lamps)}
    </section>
  );
  return (
    <>
      {answering.length > 0 &&
        group(t('workbench.lights.answering_group', { count: answering.length }), answering)}
      {group(t('workbench.lights.silent_group', { count: silent.length }), silent)}
    </>
  );
}

interface RoomDetailProps {
  lng: Language;
  selection: LightsSelection;
  scenes: readonly WorkbenchScene[];
  /** Below lg the detail shows only when the URL names it. */
  shownBelowLg: boolean;
  back: RefObject<HTMLAnchorElement | null>;
  backHref: string;
  onLightChange: (lightId: string, change: LightChangeBody) => Promise<void>;
  onRecall: SceneRecallAct;
  targetedLight?: string;
}

/** The open room: its scenes and each of its lamps. */
function RoomDetail({
  lng,
  selection,
  scenes,
  shownBelowLg,
  back,
  backHref,
  onLightChange,
  onRecall,
  targetedLight,
}: RoomDetailProps) {
  const { t } = useTranslation(lng);
  const { ask } = useToolBridges(lng);
  const title = selection.openRoom?.name ?? t('workbench.lights.other_lights');
  return (
    <section
      aria-label={title}
      className={cn('min-w-0 space-y-4', shownBelowLg ? 'block' : 'hidden lg:block')}
    >
      <Link
        ref={back}
        href={backHref}
        replace
        scroll={false}
        className="inline-flex min-h-11 items-center gap-2 rounded-md px-1 text-sm text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring lg:hidden"
      >
        <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        {t('workbench.lights.back_to_rooms')}
      </Link>
      <div className="flex items-center gap-1">
        <h2 className="min-w-0 text-base font-semibold text-foreground">{title}</h2>
        {/* Taller than the title: the margins keep the line the height the title gave it. */}
        <span className="-my-2 shrink-0">
          <BarAct
            act={askAct(
              t('workbench.ask.label'),
              () => ask(t('workbench.ask.lights', { name: title })),
              { lines: [readyLine(t, 'lights', { name: title }, ask)] }
            )}
          />
        </span>
      </div>
      <ScenePicker
        lng={lng}
        scenes={scenes.filter(scene => scene.room_id === selection.openRoom?.id)}
        onRecall={onRecall}
      />
      <LampGroups
        lng={lng}
        lights={selection.openLights}
        onLightChange={onLightChange}
        targetedLight={targetedLight}
      />
      <p className="text-xs text-muted-foreground">{t('workbench.lights.release_hint')}</p>
    </section>
  );
}
