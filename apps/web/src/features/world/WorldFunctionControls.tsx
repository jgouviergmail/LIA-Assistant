'use client';

import { useEffect, useImperativeHandle, useRef, useState, type Ref } from 'react';
import dynamic from 'next/dynamic';
import { ArrowLeft, BookOpen, Bot, LayoutGrid, Settings2, UsersRound } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
} from '@/components/ui/dropdown-menu';
import { FeatureErrorBoundary } from '@/components/errors/FeatureErrorBoundary';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { useAppConfig } from '@/hooks/useAppConfig';
import { useApplicationAccountLifetime } from '@/hooks/useApplicationAccountLifetime';
import { MeetingNavigationProvider } from '@/components/meetings/MeetingNavigation';
import type { GeneratedAssetTab } from '@/types/generated-assets';
import { isSettingsSectionToken } from '@/lib/settings-sections';
import {
  activityEntry,
  catalogueSelection,
  activityAvailable,
  workspaceFromSelection,
  WORKSPACE_SELECTION,
  type WorldSelection,
} from './activity-entry';
import { WorldLiaMenu } from './WorldLiaMenu';
import { useAuth } from '@/hooks/useAuth';
import { useSettingsAvailability } from '@/hooks/useSettingsAvailability';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { worldCatalogue, worldActions, functionSurface } from './functions';
import { useWorldConversationDock, returnWorldFocus } from './useWorldConversationDock';
import type { SceneActivity } from './scene-activities';
import type { ZoneId } from './types';
import { WorldCatalogue } from './WorldCatalogue';
import type { MailboxScope } from './message-protocol';
import type { SettingsSearchAvailability } from '@/lib/settings-search';
import { useWorldAccountIdentity, WorldPrivateActivity } from './WorldAccountGuard';

const AvatarPanel = dynamic(
  () => import('./WorldAvatarPanel').then(module => module.WorldAvatarPanel),
  {
    ssr: false,
    loading: () => <Skeleton className="h-80 w-full" />,
  }
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
interface ActivityEntry {
  selection: Selection | null;
  openingDraft?: string;
  galleryTab?: GeneratedAssetTab;
  meetingId?: string;
}
type EntryContext = Omit<ActivityEntry, 'selection'>;
export interface WorldFunctionHandle {
  canOpen(activity: SceneActivity | 'lia'): boolean;
  openPlace(): boolean;
  openScene(activity: SceneActivity | 'lia'): boolean;
}
interface Props {
  functionRef?: Ref<WorldFunctionHandle>;
  lng: Language;
  ownerId: string;
  enabled: boolean;
  suspended?: boolean;
  zone: ZoneId;
  onOpen(open: boolean, conversation: boolean): void;
  getScope?: () => MailboxScope | null;
  presenceKey?: string;
}
export function WorldFunctionControls(props: Props) {
  return <OwnedWorldFunctionControls key={props.ownerId + String(props.enabled)} {...props} />;
}
function OwnedWorldFunctionControls({
  lng,
  ownerId,
  enabled,
  suspended = false,
  zone,
  onOpen,
  getScope,
  presenceKey,
  functionRef,
}: Props) {
  const { t } = useTranslation(lng);
  const { user } = useAuth();
  const { isCurrent } = useApplicationAccountLifetime(user?.id);
  const { verified } = useWorldAccountIdentity();
  const availability = useSettingsAvailability();
  const { config } = useAppConfig();
  const catalogue = worldCatalogue(availability);
  // A launch payload belongs to its activity, including when going back.
  const [entry, setEntry] = useState<ActivityEntry>({ selection: null });
  const selection = entry.selection;
  const [history, setHistory] = useState<ActivityEntry[]>([]);
  const opener = useRef<HTMLElement | null>(null);
  const authorized = enabled && user?.id === ownerId && user.is_active;
  const available = authorized && verified && !suspended;
  const open = authorized && selection !== null;
  const conversation = selection === 'lia';
  const dock = useWorldConversationDock(open && conversation);
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
    setEntry({ selection: value });
    setHistory([]);
  }
  function navigate(next: Selection, context: EntryContext = {}) {
    if (entry.selection && next !== entry.selection)
      setHistory(previous => [...previous, entry].slice(-16));
    setEntry({ selection: next, ...context });
  }
  function back() {
    setEntry(history.at(-1) ?? { selection: 'catalogue' });
    setHistory(previous => previous.slice(0, -1));
  }
  function openMeeting(id: string) {
    if (!isCurrent() || !available) return;
    navigate(WORKSPACE_SELECTION.meetings, { meetingId: id });
  }
  function canOpen(activity: SceneActivity | 'lia'): boolean {
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
    setEntry({ selection: value });
    setHistory([]);
    return true;
  }
  useImperativeHandle(functionRef, () => ({
    canOpen,
    openPlace: () => openSelection('place'),
    openScene(activity) {
      if (!canOpen(activity)) return false;
      if (!open && document.activeElement instanceof HTMLElement)
        opener.current = document.activeElement;
      const target = activityEntry(activity, t);
      setEntry({
        selection: target.selection,
        openingDraft: target.draft,
        galleryTab: target.tab,
      });
      setHistory([]);
      return true;
    },
  }));
  const title = selectionTitle(selection, catalogue, t);
  const showBack = history.length > 0;
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
      <WorldPrivateActivity visible={!suspended}>
        <Dialog
          open={open}
          modal={!conversation}
          onOpenChange={value => {
            if (!value) setEntry({ selection: null });
          }}
        >
          <DialogContent
            ref={dock}
            data-world-native-panel
            className={
              conversation
                ? 'world-conversation flex flex-col overflow-hidden p-3 sm:p-4'
                : 'flex h-[min(52rem,calc(100dvh-1.5rem))] w-[calc(100%-1.5rem)] max-w-5xl flex-col overflow-hidden p-4 sm:p-6'
            }
            onInteractOutside={event => {
              if (conversation) event.preventDefault();
            }}
            onCloseAutoFocus={event => {
              returnWorldFocus(event, opener.current);
            }}
          >
            <DialogHeader className="shrink-0">
              <DialogTitle className="flex items-center gap-2">
                {conversation ? (
                  <Bot className="size-5 text-primary" aria-hidden="true" />
                ) : (
                  <LayoutGrid className="size-5 text-primary" aria-hidden="true" />
                )}
                {title}
              </DialogTitle>
              <DialogDescription>{t('world.functions.private')}</DialogDescription>
            </DialogHeader>
            {showBack && (
              <Button variant="ghost" className="min-h-11 w-fit shrink-0" onClick={back}>
                <ArrowLeft className="size-4" aria-hidden="true" />
                {t('common.back')}
              </Button>
            )}
            <div className="min-h-0 flex-1">
              {open && (
                <FeatureErrorBoundary key={selection} feature="world-private-activity">
                  <MeetingNavigationProvider onOpen={openMeeting}>
                    <FunctionContent
                      lng={lng}
                      ownerId={ownerId}
                      selection={selection}
                      zone={zone}
                      availability={availability}
                      openingDraft={entry.openingDraft}
                      galleryTab={entry.galleryTab}
                      initialMeetingId={entry.meetingId}
                      getScope={getScope}
                      presenceKey={presenceKey}
                      onSelect={navigate}
                      onBack={back}
                      onDone={() =>
                        setEntry(current =>
                          current.selection === 'world-avatar' ? { selection: null } : current
                        )
                      }
                      onCompose={draft => navigate('lia', { openingDraft: draft })}
                    />
                  </MeetingNavigationProvider>
                </FeatureErrorBoundary>
              )}
            </div>
          </DialogContent>
        </Dialog>
      </WorldPrivateActivity>
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
  lng,
  ownerId,
  selection,
  zone,
  availability,
  openingDraft,
  galleryTab,
  initialMeetingId,
  getScope,
  presenceKey,
  onSelect,
  onBack,
  onCompose,
  onDone,
}: {
  lng: Language;
  ownerId: string;
  selection: Selection;
  zone: ZoneId;
  availability: SettingsSearchAvailability;
  openingDraft?: string;
  galleryTab?: GeneratedAssetTab;
  initialMeetingId?: string;
  getScope?: () => MailboxScope | null;
  presenceKey?: string;
  onSelect(selection: Selection): void;
  onBack(): void;
  onDone(): void;
  onCompose(draft: string): void;
}) {
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
  if (workspace)
    return (
      <WorkspacePanel
        lng={lng}
        ownerId={ownerId}
        workspace={workspace}
        initialMeetingId={initialMeetingId}
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
  if (selection !== 'lia' && !isSettingsSectionToken(selection)) return null;
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
