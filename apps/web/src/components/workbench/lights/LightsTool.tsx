'use client';

/**
 * LightsTool — the « Tools » lights screen (ADR-369, mock-ups « Lumières »).
 *
 * The bridge is read once: its rooms, each with a switch and a slider for all
 * its lamps; the open room (`?room=`, the first from `lg`) beside them with
 * its scenes and each lamp's own controls; lamps no room owns under « Other
 * lights ». Rooms and lamps come in alphabetical order. Below `lg` the rooms are the screen and a room replaces them, with
 * the way back, which takes the focus — and the room's card gets it back when
 * the list returns; opening pushes, closing replaces (the workboard's rule). A
 * refused change is said in the refusal's own words; « Refresh » re-reads the
 * bridge in place.
 */
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { ArrowLeft, Lightbulb, RefreshCw } from 'lucide-react';
import { type RefObject, useCallback, useMemo, useRef } from 'react';
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
  OTHER_LIGHTS,
  inNameOrder,
  openSelection,
  type LightsSelection,
} from '@/lib/workbench/lights';
import { WORKBENCH_DESKTOP, toolPath } from '@/lib/workbench/tools';
import type { WorkbenchLight, WorkbenchRoom, WorkbenchScene } from '@/lib/workbench/types';
import { buildLocalizedPath } from '@/utils/i18n-path-utils';

import { useWorkbench } from '../WorkbenchShell';
import { WorkbenchToolHeader } from '../WorkbenchToolHeader';
import { WorkbenchUnavailable, unavailableKind } from '../WorkbenchUnavailable';
import { LightControls } from './LightControls';
import { RoomCard } from './RoomCard';
import { ScenePicker } from './ScenePicker';

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
  const asked = useSearchParams().get('room');
  const desktop = useMediaQuery(WORKBENCH_DESKTOP);
  const {
    bridge: read,
    loading,
    error,
    refresh,
    setLight,
    setRoom,
    recallScene,
  } = useWorkbenchLights(true);
  // Rooms and lamps in alphabetical order, in the reader's language (owner request
  // 2026-10-31) — sorted once here, so the list, the room opened by default and the
  // lamps all follow it.
  const bridge = useMemo(() => (read ? inNameOrder(read, lng) : null), [read, lng]);
  const back = useRef<HTMLAnchorElement>(null);
  // Below lg the room replaces the list: its way back takes the focus, and the
  // room's card gets it back when the list returns (whichever way it closed).
  const linkRef = useDrillDownFocus(asked, { enabled: !desktop, opened: back });

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
  const reread = () => void refresh().catch(() => undefined);

  if (!bridge) {
    return <PendingLights lng={lng} failed={!loading && Boolean(error)} onRetry={reread} />;
  }
  const selection = openSelection(bridge, asked, desktop);
  const empty = bridge.rooms.length === 0 && selection.orphans.length === 0;

  return (
    <>
      <WorkbenchToolHeader lng={lng} tool="lights">
        <Button variant="outline" size="sm" isLoading={loading} onClick={reread}>
          <RefreshCw className="h-4 w-4" aria-hidden="true" />
          {t('workbench.lights.refresh')}
        </Button>
      </WorkbenchToolHeader>
      {empty ? (
        <EmptyState
          icon={Lightbulb}
          title={t('workbench.lights.no_lights_title')}
          action={{ label: t('workbench.lights.refresh'), onClick: reread }}
        />
      ) : (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,20rem)_minmax(0,1fr)]">
          <RoomList
            lng={lng}
            rooms={bridge.rooms}
            lights={bridge.lights}
            selection={selection}
            replaced={selection.detailOpen && asked !== null}
            href={href}
            linkRef={linkRef}
            onRoomChange={(roomId, change) => act(() => setRoom(roomId, change))}
          />
          {selection.detailOpen && (
            <RoomDetail
              lng={lng}
              selection={selection}
              scenes={bridge.scenes}
              shownBelowLg={asked !== null}
              back={back}
              backHref={href(null)}
              onLightChange={(lightId, change) => act(() => setLight(lightId, change))}
              onRecall={scene => act(() => recallScene(scene.id))}
            />
          )}
        </div>
      )}
    </>
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
  selection: LightsSelection;
  /** Below lg, an open room takes the list's place. */
  replaced: boolean;
  href: (room: string | null) => string;
  linkRef: (id: string, element: HTMLElement | null) => void;
  onRoomChange: (roomId: string, change: RoomChangeBody) => Promise<void>;
}

/** The rooms, then the lamps no room owns. */
function RoomList({
  lng,
  rooms,
  lights,
  selection,
  replaced,
  href,
  linkRef,
  onRoomChange,
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
          onChange={change => onRoomChange(room.id, change)}
          linkRef={linkRef}
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
    </div>
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
  onRecall: (scene: WorkbenchScene) => Promise<void>;
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
}: RoomDetailProps) {
  const { t } = useTranslation(lng);
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
      <h2 className="text-base font-semibold text-foreground">{title}</h2>
      <ScenePicker
        lng={lng}
        scenes={scenes.filter(scene => scene.room_id === selection.openRoom?.id)}
        onRecall={onRecall}
      />
      {/* As many columns as hold a card (`auto-fill`, never `auto-fit`, which
          would stretch a lamp alone across the window). */}
      <div className="grid gap-3 xl:grid-cols-[repeat(auto-fill,minmax(24rem,1fr))]">
        {selection.openLights.map(light => (
          <LightControls
            key={light.id}
            lng={lng}
            light={light}
            onChange={change => onLightChange(light.id, change)}
          />
        ))}
      </div>
      <p className="text-xs text-muted-foreground">{t('workbench.lights.release_hint')}</p>
    </section>
  );
}
