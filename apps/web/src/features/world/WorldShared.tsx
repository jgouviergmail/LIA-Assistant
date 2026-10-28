'use client';
import { useWorldSound } from './useWorldSound';
import { WorldSpeech, privateSpeechDeliveries, publicSpeechDeliveries } from './speech';
import { WorldSpeechAnnouncements } from './WorldSpeechAnnouncements';
import type { Notification } from '@/hooks/useNotifications';
import type { WorldMailbox } from './message-protocol';
import { WorldDeviceControls, type WorldDeviceHandle } from './WorldDeviceControls';
import { useWorldPrivateSignals } from './useWorldPrivateSignals';
import { useWorldSignalHost } from './useWorldSignalHost';
import { useWorldActingSource } from './useWorldActingSource';
import { WorldAdmission } from './WorldAdmission';
import { useWorldExperiencePreferences } from './useWorldExperiencePreferences';
import type { ConfirmedSeat } from './seat-activity-intent';
import { SeatDashboardIntent, dashboardOfferOpen, type SeatScope } from './seat-dashboard-intent';
import { WorldSeatedDashboard } from './WorldSeatedDashboard';

import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react';
import { LogOut } from 'lucide-react';
import { seatContext } from './seat-context';
import { Button } from '@/components/ui/button';
import { useTranslation } from '@/i18n/client';
import { useMediaQuery } from '@/hooks/useMediaQuery';
import type { Language } from '@/i18n/settings';
import { useWorldSession } from './useWorldSession';
import { WorldSessionDialog } from './WorldSessionDialog';
import { WorldPrototype } from './WorldPrototype';
import { WorldHomeControls } from './WorldHomeControls';
import { WorldFunctionControls, type WorldFunctionHandle } from './WorldFunctionControls';
import { WorldMessageControls, type WorldConversationHandle } from './WorldMessageControls';
import { sceneActivity, seatActivity } from './scene-activities';
import { activityTitle } from './activity-entry';
import type { SceneHost, SceneTarget } from './scene-interactions';
import type { HomeSkin } from './home-projection';
import './world.css';
import { useWorldEnvironment } from './useWorldEnvironment';
import { WorldAccountGuard, useWorldAccountIdentity } from './WorldAccountGuard';
import type { WorldActingState } from './types';
import { WorldEmoteAnnouncements } from './WorldEmoteAnnouncements';
import { WorldEmoteFeedback } from './WorldEmoteFeedback';

interface Props {
  lng: Language;
  ownerId: string;
}
type NativePanel = 'closed' | 'conversation' | 'activity';
function openWorldObject(
  target: Extract<SceneTarget, { kind: 'object' | 'lia' }>,
  functions: WorldFunctionHandle | null,
  openSignal: ReturnType<typeof useWorldSignalHost>
): boolean {
  if (target.kind === 'object') {
    const signalled = openSignal(target.id);
    if (signalled !== null) return signalled;
  }
  const activity = target.kind === 'lia' ? 'lia' : sceneActivity(target.id);
  return activity ? (functions?.openScene(activity) ?? false) : false;
}
export function WorldShared({ lng, ownerId }: Props) {
  // Keep unsent appearance choices mounted while native account reads revalidate.
  return <OwnedWorldShared key={ownerId} lng={lng} ownerId={ownerId} />;
}
function OwnedWorldShared({ lng, ownerId }: Props) {
  const [alias, setAlias] = useState<string | null>(null);
  if (alias)
    return (
      <WorldAccountGuard lng={lng} ownerId={ownerId}>
        <ConnectedWorld
          key={ownerId}
          lng={lng}
          ownerId={ownerId}
          alias={alias}
          onLeave={() => setAlias(null)}
        />
      </WorldAccountGuard>
    );
  return <WorldAdmission lng={lng} ownerId={ownerId} onEnter={setAlias} />;
}

function ConnectedWorld({
  lng,
  ownerId,
  alias,
  onLeave,
}: Props & { alias: string; onLeave(): void }) {
  const { verified } = useWorldAccountIdentity();
  const compact = useMediaQuery(
    '(max-width: 767px), (max-height: 520px) and (orientation: landscape)'
  );
  const functions = useRef<WorldFunctionHandle>(null);
  const dashboardIntent = useMemo(() => new SeatDashboardIntent(), []);
  const dashboardOffer = useSyncExternalStore(
    dashboardIntent.subscribe,
    dashboardIntent.getSnapshot,
    dashboardIntent.getSnapshot
  );
  const openSeatActivity = useCallback(
    (receipt: ConfirmedSeat, scope: SeatScope) => {
      const selected = seatActivity(receipt.slot);
      if (selected) functions.current?.openScene(selected);
      else dashboardIntent.confirm(receipt, scope);
    },
    [dashboardIntent]
  );
  const {
    driver,
    presentation,
    active,
    recovering,
    control,
    activity,
    mailboxScope,
    pose,
    emote,
    arcade,
  } = useWorldSession(ownerId, alias, openSeatActivity);
  const { t } = useTranslation(lng);
  const retained = active || recovering;
  const authorized = active && verified;
  const retainedAuthorized = retained && verified;
  const dashboardSeatKey = dashboardSeatLifetime(presentation.pose, presentation.epoch);
  // The input pause and the consent dialog read one predicate: a stale offer pauses nothing.
  const offerOpen = dashboardOfferOpen(
    dashboardOffer,
    presentation.pose,
    dashboardSeatKey,
    authorized
  );
  useEffect(() => {
    if (!active || !dashboardSeatKey) dashboardIntent.cancel();
  }, [active, dashboardSeatKey, dashboardIntent]);
  const experience = useWorldExperiencePreferences(ownerId, retainedAuthorized);
  const atmosphere = useWorldEnvironment(ownerId, active);
  const sound = useWorldSound(ownerId, authorized, presentation.zone, atmosphere);
  const receiveSound = sound.receive;
  const speech = useMemo(() => new WorldSpeech(), []);
  useEffect(() => {
    speech.setActive(authorized);
    return () => speech.setActive(false);
  }, [speech, authorized]);
  const receiveSpeech = useCallback(
    (mailbox: WorldMailbox) => {
      receiveSound(mailbox);
      const now = performance.now();
      speech.receive(privateSpeechDeliveries(mailbox), mailbox.server_time, 'private', now);
      if (mailbox.public_available === true)
        speech.receive(publicSpeechDeliveries(mailbox), mailbox.server_time, 'public', now);
    },
    [speech, receiveSound]
  );
  const receiveProactive = useCallback(
    (notice: Notification) => speech.proactive(notice),
    [speech]
  );
  const privateSignals = useWorldPrivateSignals(ownerId, retainedAuthorized, receiveProactive);
  const devices = useRef<WorldDeviceHandle>(null);
  const openSignal = useWorldSignalHost(privateSignals, functions, devices);
  const acting = useWorldActingSource(ownerId, authorized);
  const [actingState, setActingState] = useState<WorldActingState>('idle');
  const [home, setHome] = useState<HomeSkin | null>(null);
  const [editingHome, setEditingHome] = useState(false);
  const [nativePanel, setNativePanel] = useState<NativePanel>('closed');
  const [photoOpen, setPhotoOpen] = useState(false);
  const nativeOpen = nativePanel !== 'closed' || photoOpen;
  const onNativeOpen = useCallback((open: boolean, conversation: boolean) => {
    setNativePanel(open ? (conversation ? 'conversation' : 'activity') : 'closed');
  }, []);
  const [socialOpen, setSocialOpen] = useState(false);
  const [hudExpanded, setHudExpanded] = useState(false);
  const [compactChatHost, setCompactChatHost] = useState<HTMLDivElement | null>(null);
  const [deviceOpen, setDeviceOpen] = useState(false);
  useEffect(() => {
    // Private panels own attention even when desktop movement and painting continue.
    speech.setProactivePaused([editingHome, nativeOpen, socialOpen, deviceOpen].some(Boolean));
  }, [speech, editingHome, nativeOpen, socialOpen, deviceOpen]);
  const interact = useCallback(() => functions.current?.openPlace(), []);
  const conversations = useRef<WorldConversationHandle>(null);
  const scene = useMemo<SceneHost>(
    () => ({
      // A snapshot gap freezes a pending approach; a reconnection pauses the
      // scene, which withdraws it.
      ready: () => pose.available(),
      canOpen(target) {
        if (target.kind === 'pose' || target.kind === 'stand') return pose.available();
        if (target.kind === 'peer') return conversations.current?.canOpen(target.id) ?? false;
        const activity = target.kind === 'lia' ? 'lia' : sceneActivity(target.id);
        return activity ? (functions.current?.canOpen(activity) ?? false) : false;
      },
      open(target) {
        if (target.kind === 'pose' || target.kind === 'stand')
          return pose.request(target.kind === 'stand' ? null : target.id);
        if (target.kind === 'peer') return conversations.current?.openFor(target.id) ?? false;
        return openWorldObject(target, functions.current, openSignal);
      },
    }),
    [pose, openSignal]
  );
  function sceneLabel(target: SceneTarget): string {
    if (target.kind === 'stand') return t('world.poses.stand');
    if (target.kind === 'pose') {
      const activity = seatActivity(target.id);
      const label = t('world.poses.' + target.action);
      return activity && functions.current?.canOpen(activity)
        ? label + ' · ' + activityTitle(activity, t)
        : label;
    }
    if (target.kind === 'lia') return t('world.lia_menu.title');
    if (target.kind === 'peer')
      return (
        presentation.participants.find(person => person.id === target.id)?.alias ??
        t('world.messages.short')
      );
    const activity = sceneActivity(target.id);
    return activity ? activityTitle(activity, t) : '';
  }
  return (
    <div
      className="relative min-h-0 flex-1"
      onPointerDownCapture={() => {
        activity();
        sound.wake();
      }}
      onKeyDownCapture={() => {
        activity();
        sound.wake();
      }}
    >
      <WorldSpeechAnnouncements speech={speech} />
      <WorldEmoteAnnouncements lng={lng} gestures={presentation.gestures} />
      <PoseFeedback lng={lng} result={presentation.poseResult} />
      <WorldEmoteFeedback lng={lng} feedback={presentation.emoteFeedback} />
      <WorldPrototype
        hudExpanded={hudExpanded}
        onHudExpandedChange={setHudExpanded}
        onPhotoOpen={setPhotoOpen}
        onEmote={emote}
        onActingState={setActingState}
        conversationOpen={nativePanel === 'conversation'}
        acting={acting}
        privateSignals={authorized ? privateSignals.presentation : undefined}
        lng={lng}
        ownerId={ownerId}
        driver={driver}
        speech={speech}
        playerAlias={alias}
        connected
        home={home}
        editingHome={editingHome}
        atmosphere={atmosphere}
        onInteract={interact}
        scene={scene}
        onCosmeticCue={sound.effect}
        sceneLabel={sceneLabel}
        exploration={{
          control: experience,
          enabled: explorationAvailable(
            active,
            verified,
            nativeOpen,
            editingHome,
            socialOpen,
            deviceOpen,
            offerOpen
          ),
        }}
        widgets={extras => (
          <WorldDeviceControls
            extras={extras}
            signals={privateSignals}
            deviceRef={devices}
            onSignal={id => openSignal(id) === true}
            lng={lng}
            ownerId={ownerId}
            sound={sound}
            enabled={retainedAuthorized}
            interactive={deviceInteractionAllowed(active, editingHome, nativeOpen, socialOpen)}
            onOpen={setDeviceOpen}
            onProactive={receiveProactive}
            onActivity={selected => functions.current?.openScene(selected)}
          />
        )}
        interactionPaused={[
          !verified,
          !active,
          nativeInteractionPaused(nativePanel, compact),
          socialOpen && compact,
          deviceOpen,
          offerOpen,
        ].some(Boolean)}
      />
      <div ref={setCompactChatHost} data-world-compact-chat-host />
      <div className="world-session-strip border border-border bg-background/95 shadow-lg">
        <span className="world-link-status text-xs" role="status">
          <span className={active ? 'bg-emerald-600' : 'bg-amber-600'} aria-hidden="true" />
          <span className="sr-only lg:not-sr-only">
            {t('world.session.' + (active ? 'shared' : presentation.connection))}
          </span>
        </span>
        <WorldHomeControls
          lng={lng}
          ownerId={ownerId}
          enabled={withoutOpenPanels(retained, nativeOpen, socialOpen)}
          onSkin={setHome}
          onEditing={setEditingHome}
        />
        <WorldFunctionControls
          arcade={arcade}
          actingState={actingState}
          functionRef={functions}
          lng={lng}
          ownerId={ownerId}
          enabled={withoutOpenPanels(retained, editingHome, socialOpen)}
          suspended={recovering}
          zone={presentation.zone}
          onOpen={onNativeOpen}
          getScope={mailboxScope}
          presenceKey={presentation.participants.map(person => person.id).join(',')}
          dashboardSeatKey={dashboardSeatKey}
        />
        <WorldSeatedDashboard
          lng={lng}
          active={authorized}
          seatKey={dashboardSeatKey}
          pose={presentation.pose}
          offer={dashboardOffer}
          intent={dashboardIntent}
          onAccept={() => {
            functions.current?.openScene({ kind: 'workspace', id: 'dashboard' });
          }}
        />
        <WorldMessageControls
          onCompactOpen={() => setHudExpanded(false)}
          compactOnDemand={compact}
          compactHost={compactChatHost}
          compactEnabled={compactConversationAvailable(deviceOpen, offerOpen, compact, hudExpanded)}
          nearbyParticipants={presentation.nearbyParticipants}
          conversationRef={conversations}
          lng={lng}
          ownerId={ownerId}
          enabled={retained}
          canOpen={active && !editingHome && !nativeOpen}
          canSend={active && presentation.zone !== 'home'}
          participants={presentation.participants}
          getScope={mailboxScope}
          onOpen={setSocialOpen}
          onMailbox={receiveSpeech}
        />
        <Button
          size="sm"
          variant="ghost"
          className="min-h-11 min-w-11"
          aria-label={t('world.session.leave')}
          onClick={() => {
            control('leave');
            onLeave();
          }}
        >
          <LogOut className="size-4" aria-hidden="true" />
          <span className="hidden lg:inline">{t('world.session.leave')}</span>
        </Button>
      </div>
      <WorldSessionDialog
        lng={lng}
        presentation={presentation}
        open={!active && verified}
        onLeave={onLeave}
        onAccept={() => control('accept')}
        onTakeover={() => control('takeover')}
      />
    </div>
  );
}

function dashboardSeatLifetime(pose: string | null, epoch: string | null): string | null {
  if (!pose || !epoch) return null;
  const context = seatContext(pose);
  return context?.dashboardEligible ? epoch + ':' + pose : null;
}

function explorationAvailable(active: boolean, verified: boolean, ...panels: boolean[]): boolean {
  return withoutOpenPanels(active && verified, ...panels);
}
function withoutOpenPanels(ready: boolean, ...panels: boolean[]): boolean {
  return ready && !panels.some(Boolean);
}

function PoseFeedback({
  lng,
  result,
}: {
  lng: Language;
  result: import('./useWorldSession').SessionPresentation['poseResult'];
}) {
  const { t } = useTranslation(lng);
  if (!result || result === 'accepted') return null;
  return (
    <p className="world-pose-feedback border bg-background text-sm" role="status">
      {t('world.poses.' + result)}
    </p>
  );
}

function deviceInteractionAllowed(
  active: boolean,
  editing: boolean,
  native: boolean,
  social: boolean
): boolean {
  return active && !editing && !native && !social;
}

function nativeInteractionPaused(panel: NativePanel, compact: boolean): boolean {
  return panel === 'activity' || (panel === 'conversation' && compact);
}

function compactConversationAvailable(
  device: boolean,
  dashboard: boolean,
  compact: boolean,
  expanded: boolean
): boolean {
  return !device && !dashboard && !(compact && expanded);
}
