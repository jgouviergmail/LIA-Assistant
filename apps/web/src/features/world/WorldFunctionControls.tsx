'use client';

import { useEffect, useImperativeHandle, useRef, type Ref } from 'react';
import dynamic from 'next/dynamic';
import { BookOpen, Bot, LayoutGrid, Settings2, UsersRound } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
} from '@/components/ui/dropdown-menu';
import { FeatureErrorBoundary } from '@/components/errors/FeatureErrorBoundary';
import { Skeleton } from '@/components/ui/skeleton';
import { useAppConfig } from '@/hooks/useAppConfig';
import { useApplicationAccountLifetime } from '@/hooks/useApplicationAccountLifetime';
import { MeetingNavigationProvider } from '@/components/meetings/MeetingNavigation';
import type { DashboardDestination } from '@/components/dashboard/DashboardNavigation';
import type { BoardFilters } from '@/types/workboard';
import type { GeneratedAssetTab } from '@/types/generated-assets';
import { isSettingsSectionToken } from '@/lib/settings-sections';
import {
  activityEntry,
  activityPresentation,
  catalogueSelection,
  activityAvailable,
  workspaceFromSelection,
  WORKSPACE_SELECTION,
  dashboardEntry,
  workspaceAvailable,
  type WorldSelection,
} from './activity-entry';
import { WorldLiaMenu } from './WorldLiaMenu';
import { useAuth } from '@/hooks/useAuth';
import { useSettingsAvailability } from '@/hooks/useSettingsAvailability';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { worldCatalogue, worldActions, functionSurface } from './functions';
import { useWorldConversationDock } from './useWorldConversationDock';
import type { SceneActivity } from './scene-activities';
import type { WorldActingState, ZoneId } from './types';
import { WorldCatalogue } from './WorldCatalogue';
import type { MailboxScope } from './message-protocol';
import type { SettingsSearchAvailability } from '@/lib/settings-search';
import { useWorldAccountIdentity } from './WorldAccountGuard';
import { useWorldActivityState } from './useWorldActivityState';
import { WorldActivityPanel } from './WorldActivityPanel';
import type { WorldGameClient } from './game-client';
import type { CabinetId } from './game-catalogue';
import { useWorldArcadeActivity } from './useWorldArcadeActivity';

const ArcadePanel = dynamic(
  () => import('./WorldArcadePanel').then(module => module.WorldArcadePanel),
  { ssr: false }
);

const AvatarPanel = dynamic(
  () => import('./WorldAvatarPanel').then(module => module.WorldAvatarPanel),
  {
    ssr: false,
    loading: () => <Skeleton className="h-80 w-full" />,
  }
);
const DashboardPanel = dynamic(
  () => import('./WorldDashboardPanel').then(module => module.WorldDashboardPanel),
  { ssr: false }
);
const RadioPanel = dynamic(
  () => import('@/components/radio/RadioPage').then(module => module.RadioPage),
  { ssr: false }
);
const WorkspacePanel = dynamic(
  () => import('./WorldWorkspacePanel').then(module => module.WorldWorkspacePanel),
  { ssr: false, loading: () => <Skeleton className="h-40 w-full" /> }
);
const NativePanel = dynamic(
  () => import('./WorldNativePanel').then(module => module.WorldNativePanel),
  {
    ssr: false,
    loading: () => <Skeleton className="h-40 w-full" />,
  }
);
const PeersPanel = dynamic(() => import('./WorldPeerPanel').then(module => module.WorldPeerPanel), {
  ssr: false,
  loading: () => <Skeleton className="h-40 w-full" />,
});
type Selection = WorldSelection;
export interface WorldFunctionHandle {
  openDestination(destination: DashboardDestination): boolean;
  canOpen(activity: SceneActivity | 'lia'): boolean;
  openPlace(): boolean;
  openScene(activity: SceneActivity | 'lia'): boolean;
}
interface Props {
  arcade?: WorldGameClient;
  actingState?: WorldActingState;
  functionRef?: Ref<WorldFunctionHandle>;
  lng: Language;
  ownerId: string;
  enabled: boolean;
  suspended?: boolean;
  zone: ZoneId;
  onOpen(open: boolean, conversation: boolean): void;
  getScope?: () => MailboxScope | null;
  presenceKey?: string;
  dashboardSeatKey?: string | null;
}
export function WorldFunctionControls(props: Props) {
  // Keyed by owner only: Discuter or home editing toggles `enabled`, and a remount
  // there would drop the retained seated dashboard and buy a second paid synthesis.
  return <OwnedWorldFunctionControls key={props.ownerId} {...props} />;
}
function OwnedWorldFunctionControls({
  arcade,
  actingState,
  lng,
  ownerId,
  enabled,
  suspended = false,
  zone,
  onOpen,
  getScope,
  presenceKey,
  functionRef,
  dashboardSeatKey = null,
}: Props) {
  const { t } = useTranslation(lng);
  const { user } = useAuth();
  const { isCurrent } = useApplicationAccountLifetime(user?.id);
  const { verified } = useWorldAccountIdentity();
  const availability = useSettingsAvailability();
  const { config } = useAppConfig();
  const catalogue = worldCatalogue(availability);
  const { authorized, presentable, available } = activityAuthorization(
    enabled,
    user,
    ownerId,
    verified,
    suspended
  );
  // A launch payload belongs to its activity, including when going back. A loss of
  // authority closes the activity explicitly; the retained seated dashboard survives.
  const {
    entry,
    history,
    dashboardStarted,
    activate: activateEntry,
    navigate,
    back,
    close,
    complete,
  } = useWorldActivityState(dashboardSeatKey, authorized);
  const selection = entry.selection;
  const arcadeActivity = useWorldArcadeActivity(arcade, entry, t);
  const opener = useRef<HTMLElement | null>(null);
  const { open, conversation, dashboardOpen, nativeOpen, dockActive } = activityPresentation(
    selection,
    authorized
  );
  const dock = useWorldConversationDock(dockActive);
  useEffect(() => {
    onOpen(open, conversation);
    return () => onOpen(false, false);
  }, [open, conversation, onOpen]);
  function activate(value: Selection, button: Element | null) {
    opener.current =
      document.activeElement instanceof HTMLCanvasElement
        ? document.activeElement
        : button instanceof HTMLElement
          ? button
          : null;
    activateEntry({ selection: value });
  }
  function openMeeting(id: string) {
    if (!isCurrent() || !available) return;
    navigate(WORKSPACE_SELECTION.meetings, { meetingId: id });
  }
  function openDashboardDestination(destination: DashboardDestination): boolean {
    if (!isCurrent() || !available) return false;
    const { selection: next, ...context } = dashboardEntry(destination);
    const workspace = workspaceFromSelection(next);
    if (workspace && !workspaceAvailable(workspace, config)) return false;
    if (isSettingsSectionToken(next) && !catalogue.some(item => item.token === next)) return false;
    if (!open && document.activeElement instanceof HTMLElement)
      opener.current = document.activeElement;
    navigate(next, context);
    return true;
  }
  function canOpen(activity: SceneActivity | 'lia'): boolean {
    if (activity !== 'lia' && activity.kind === 'arcade' && !arcade?.canOpen(activity.id))
      return false;
    if (
      activity !== 'lia' &&
      activity.kind === 'workspace' &&
      activity.id === 'dashboard' &&
      !dashboardSeatKey
    )
      return false;
    return (
      available &&
      activityAvailable(activity, {
        native: new Set(
          catalogue
            .filter(item => functionSurface(item.token) === 'activity')
            .map(item => item.token)
        ),
        commands: new Set(
          worldActions(t)
            .filter(item => item.insertText)
            .map(item => item.id)
        ),
        radio: availability.radioEnabled === true,
        config,
      })
    );
  }
  function openSelection(value: Selection): boolean {
    if (!available) return false;
    if (!open && document.activeElement instanceof HTMLElement)
      opener.current = document.activeElement;
    activateEntry({ selection: value });
    return true;
  }
  useImperativeHandle(functionRef, () => ({
    openDestination: openDashboardDestination,
    canOpen,
    openPlace: () => openSelection('place'),
    openScene(activity) {
      if (!canOpen(activity)) return false;
      if (!open && document.activeElement instanceof HTMLElement)
        opener.current = document.activeElement;
      const target = activityEntry(activity, t);
      activateEntry(target);
      return true;
    },
  }));
  const title = arcadeActivity.title ?? selectionTitle(selection, catalogue, t);
  const onBack = history.length > 0 ? back : undefined;
  return (
    <>
      <FunctionTriggers
        lng={lng}
        zone={zone}
        available={available}
        peersEnabled={availability.peersEnabled}
        getScope={getScope}
        activate={activate}
      />
      {dashboardStarted && (
        <DashboardPanel
          lng={lng}
          ownerId={ownerId}
          active={presentable && dashboardOpen}
          suspended={suspended}
          opener={opener}
          onClose={close}
          onBack={onBack}
          onNavigate={openDashboardDestination}
        />
      )}
      <WorldActivityPanel
        lng={lng}
        ownerId={ownerId}
        open={nativeOpen}
        suspended={suspended}
        conversation={conversation}
        actingState={actingState}
        title={title}
        description={arcadeActivity.description}
        compact={arcadeActivity.cabinet !== undefined}
        icon={arcadeActivity.icon}
        opener={opener}
        fallbackToScene
        dock={dock}
        onClose={close}
        onBack={onBack}
      >
        {nativeOpen && selection && (
          <FeatureErrorBoundary key={selection} feature="world-private-activity">
            <MeetingNavigationProvider onOpen={openMeeting}>
              <FunctionContent
                arcade={arcade}
                cabinet={arcadeActivity.cabinet}
                onClose={close}
                lng={lng}
                ownerId={ownerId}
                selection={selection}
                zone={zone}
                availability={availability}
                openingDraft={entry.draft}
                galleryTab={entry.tab}
                initialMeetingId={entry.meetingId}
                initialFilters={entry.workboardFilters}
                initialTicketId={entry.ticketId}
                initialMessageId={entry.smsMessageId}
                getScope={getScope}
                presenceKey={presenceKey}
                onSelect={navigate}
                onBack={back}
                onDone={() => complete('world-avatar')}
                onCompose={draft => navigate('lia', { draft })}
              />
            </MeetingNavigationProvider>
          </FeatureErrorBoundary>
        )}
      </WorldActivityPanel>
    </>
  );
}

function selectionTitle(
  selection: Selection | null,
  catalogue: ReturnType<typeof worldCatalogue>,
  t: (key: string) => string
): string {
  const selected = catalogue.find(item => item.token === selection);
  const titleKey = selected?.titleKey;
  if (selection === 'lia-menu') return t('world.lia_menu.title');
  const workspace = selection ? workspaceFromSelection(selection) : null;
  if (workspace)
    return t(workspace === 'registers' ? 'registers.title' : 'world.activities.' + workspace);
  if (selection === 'world-radio') return t('radio.page.title');
  if (selection === 'world-avatar') return t('world.avatar.title');
  if (selection === 'configuration') return t('world.settings.application');
  if (titleKey) return t(titleKey);
  if (selection === 'world-peers') return t('settings.peers.title');
  return t(selection === 'lia' ? 'world.functions.talk' : 'world.functions.title');
}

function FunctionContent({
  arcade,
  cabinet,
  onClose,
  lng,
  ownerId,
  selection,
  zone,
  availability,
  openingDraft,
  galleryTab,
  initialMeetingId,
  initialFilters,
  initialTicketId,
  initialMessageId,
  getScope,
  presenceKey,
  onSelect,
  onBack,
  onCompose,
  onDone,
}: {
  arcade?: WorldGameClient;
  cabinet?: CabinetId;
  onClose(): void;
  lng: Language;
  ownerId: string;
  selection: Selection;
  zone: ZoneId;
  availability: SettingsSearchAvailability;
  openingDraft?: string;
  galleryTab?: GeneratedAssetTab;
  initialMeetingId?: string;
  initialFilters?: BoardFilters;
  initialTicketId?: string;
  initialMessageId?: string;
  getScope?: () => MailboxScope | null;
  presenceKey?: string;
  onSelect(selection: Selection): void;
  onBack(): void;
  onDone(): void;
  onCompose(draft: string): void;
}) {
  if (selection === 'world-arcade')
    return (
      <ArcadeContent
        lng={lng}
        ownerId={ownerId}
        arcade={arcade}
        cabinet={cabinet}
        onClose={onClose}
      />
    );
  if (selection === 'world-avatar')
    return <AvatarPanel lng={lng} ownerId={ownerId} onDone={onDone} />;
  if (selection === 'configuration')
    return (
      <div className="flex h-full min-h-0 flex-col">
        <div className="shrink-0 border-b px-4 py-3">
          <Button variant="outline" className="min-h-11" onClick={() => onSelect('world-avatar')}>
            {<AvatarSettingsLabel lng={lng} />}
          </Button>
        </div>
        <div className="min-h-0 flex-1">
          <WorldCatalogue
            lng={lng}
            availability={availability}
            surface="settings"
            place={null}
            onSelect={next => onSelect(catalogueSelection(next, true))}
            onCompose={onCompose}
          />
        </div>
      </div>
    );
  const workspace = workspaceFromSelection(selection);
  if (workspace && workspace !== 'dashboard')
    return (
      <WorkspacePanel
        lng={lng}
        ownerId={ownerId}
        workspace={workspace}
        initialMeetingId={initialMeetingId}
        initialFilters={initialFilters}
        initialTicketId={initialTicketId}
        initialMessageId={initialMessageId}
        onNavigate={next => onSelect(WORKSPACE_SELECTION[next])}
        onCompose={() => onCompose('')}
      />
    );
  if (selection === 'lia-menu') return <WorldLiaMenu lng={lng} onSelect={onSelect} />;
  if (selection === 'catalogue' || selection === 'place')
    return (
      <WorldCatalogue
        lng={lng}
        availability={availability}
        surface="activity"
        place={selection === 'place' ? zone : null}
        onSelect={next => onSelect(catalogueSelection(next, false))}
        onCompose={onCompose}
      />
    );
  if (selection === 'world-radio')
    return (
      <div className="h-full overflow-y-auto">
        <RadioPanel lng={lng} available={availability.radioEnabled} />
      </div>
    );
  if (selection === 'world-peers')
    return getScope ? (
      <PeersPanel
        lng={lng}
        ownerId={ownerId}
        getScope={getScope}
        onCompose={onCompose}
        presenceKey={presenceKey}
      />
    ) : null;
  if (!isNativeSelection(selection)) return null;
  return (
    <NativePanel
      key={ownerId + selection}
      lng={lng}
      ownerId={ownerId}
      selection={selection}
      onBack={onBack}
      openingDraft={openingDraft}
      galleryTab={galleryTab}
    />
  );
}

function isNativeSelection(selection: Selection) {
  return selection === 'lia' || isSettingsSectionToken(selection);
}
function activityAuthorization(
  enabled: boolean,
  user: { id: string; is_active: boolean } | null,
  ownerId: string,
  verified: boolean,
  suspended: boolean
) {
  const authorized = enabled && user?.id === ownerId && user.is_active;
  // A suspended transport keeps every open panel presentable; only new actions wait.
  const presentable = authorized && verified;
  return { authorized, presentable, available: presentable && !suspended };
}
function ArcadeContent({
  lng,
  ownerId,
  arcade,
  cabinet,
  onClose,
}: {
  lng: Language;
  ownerId: string;
  arcade?: WorldGameClient;
  cabinet?: CabinetId;
  onClose(): void;
}) {
  if (!arcade || !cabinet) return null;
  return (
    <ArcadePanel
      key={ownerId + cabinet}
      lng={lng}
      ownerId={ownerId}
      cabinet={cabinet}
      client={arcade}
      onClose={onClose}
    />
  );
}

/** Accessible counterparts of the in-scene activities; settings stay separate. */
function FunctionTriggers({
  lng,
  zone,
  available,
  peersEnabled,
  getScope,
  activate,
}: {
  lng: Language;
  zone: ZoneId;
  available: boolean;
  peersEnabled: boolean;
  getScope?: Props['getScope'];
  activate(value: Selection, button: Element | null): void;
}) {
  const { t } = useTranslation(lng);
  const menuTrigger = useRef<HTMLButtonElement>(null);
  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            ref={menuTrigger}
            className="min-h-11 min-w-11"
            size="sm"
            variant="ghost"
            disabled={!available}
            aria-label={t('world.functions.title')}
          >
            <LayoutGrid className="size-4" aria-hidden="true" />
            <span className="hidden sm:inline">{t('world.functions.short')}</span>
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="center" className="world-actions-menu">
          <DropdownMenuItem onSelect={() => activate('catalogue', menuTrigger.current)}>
            <LayoutGrid aria-hidden="true" />
            {t('world.functions.title')}
          </DropdownMenuItem>
          <DropdownMenuItem onSelect={() => activate('place', menuTrigger.current)}>
            <BookOpen aria-hidden="true" />
            {t('world.functions.place', { place: t('world.zones.' + zone) })}
          </DropdownMenuItem>
          {peersEnabled && getScope && (
            <DropdownMenuItem onSelect={() => activate('world-peers', menuTrigger.current)}>
              <UsersRound aria-hidden="true" />
              {t('settings.peers.title')}
            </DropdownMenuItem>
          )}
        </DropdownMenuContent>
      </DropdownMenu>
      <Button
        className="min-h-11 min-w-11"
        size="sm"
        variant="ghost"
        disabled={!available}
        aria-label={t('world.functions.talk')}
        onClick={event => activate('lia', event.currentTarget)}
      >
        <Bot className="size-4" aria-hidden="true" />
        <span className="hidden sm:inline">LIA</span>
      </Button>
      <Button
        size="sm"
        variant="ghost"
        className="min-h-11 min-w-11"
        disabled={!available}
        data-world-system-action
        aria-label={t('world.settings.application')}
        onClick={event => activate('configuration', event.currentTarget)}
      >
        <Settings2 className="size-4" aria-hidden="true" />
        <span className="hidden lg:inline">{t('world.settings.short')}</span>
      </Button>
    </>
  );
}

function AvatarSettingsLabel({ lng }: { lng: Language }) {
  const { t } = useTranslation(lng);
  return <>{t('world.avatar.change')}</>;
}
