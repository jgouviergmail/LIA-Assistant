'use client';

import { SeatActivityIntent, type ConfirmedSeat } from './seat-activity-intent';
import type { SeatScope } from './seat-dashboard-intent';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useApiMutation } from '@/hooks/useApiMutation';
import { useApplicationAccountLifetime } from '@/hooks/useApplicationAccountLifetime';
import { apiEndpointUrl } from '@/lib/api-client';
import { WorldLink, type LinkStatus } from './shared-link';
import { WorldSynchronizer, type WorldDriver } from './shared-simulation';
import { stepSimulation, zoneAt } from './simulation';
import type { ZoneId } from './types';
import { WORLD } from './definition';
import { compilePoseSlots } from './pose-slots';
import type { EmoteKind, EmoteOutcome, EmoteRefusal } from './emote-catalogue';
import { publicGestures, type PublicGesture } from './emote-presentation';
import { EmoteReceipts } from './emote-receipts';
import { WorldGameClient } from './game-client';
import { compileNavigation } from './navigation';
import { nearbyConversations } from './nearby-conversations';

export interface WorldParticipant {
  id: string;
  alias: string;
}
/** A refused gesture to announce; each refusal has its own serial, so a repeat is heard. */
export interface EmoteFeedback {
  result: EmoteRefusal;
  serial: number;
}

export interface SessionPresentation {
  gestures?: readonly PublicGesture[];
  connection: LinkStatus;
  admission: 'active' | 'waiting' | 'absent';
  controlling: boolean;
  position: number | null;
  offer: number | null;
  zone: ZoneId;
  poseResult?: 'accepted' | 'occupied' | 'out_of_reach' | 'invalid' | null;
  emoteFeedback?: EmoteFeedback | null;
  participants: WorldParticipant[];
  nearbyParticipants: readonly WorldParticipant[];
  pose: string | null;
  epoch: string | null;
}
const NO_GESTURES: readonly PublicGesture[] = Object.freeze([]);
const NO_NEARBY: readonly WorldParticipant[] = Object.freeze([]);
const SOCIAL_NAVIGATION = compileNavigation(WORLD);
const SOCIAL_POSES = compilePoseSlots(WORLD);
const INITIAL: SessionPresentation = {
  gestures: NO_GESTURES,
  connection: 'connecting',
  admission: 'absent',
  controlling: false,
  position: null,
  offer: null,
  zone: 'arrival',
  emoteFeedback: null,
  participants: [],
  nearbyParticipants: NO_NEARBY,
  pose: null,
  epoch: null,
};
/** What a receipt announces: nothing new (undefined), a withdrawal (null) or a refusal. */
function receiptFeedback(
  outcome: EmoteOutcome | null,
  serial: () => number
): EmoteFeedback | null | undefined {
  if (outcome === null) return undefined;
  return outcome === 'accepted' ? null : { result: outcome, serial: serial() };
}

export function useWorldSession(
  ownerId: string,
  alias: string,
  onSeatActivity?: (receipt: ConfirmedSeat, scope: SeatScope) => void
) {
  const seatIntent = useMemo(() => new SeatActivityIntent(), []);
  const emoteReceipts = useMemo(() => new EmoteReceipts(), []);
  const emoteSerial = useRef(0);
  const { client: arcade } = useMemo(() => ({ ownerId, client: new WorldGameClient() }), [ownerId]);
  const { isCurrent } = useApplicationAccountLifetime(ownerId);
  const link = useRef<WorldLink | null>(null);
  const synchronizer = useRef<WorldSynchronizer | null>(null);
  const [presentation, setPresentation] = useState(INITIAL);
  const { mutate } = useApiMutation<
    { consent: true },
    { ticket: string; version: number; account_id: string }
  >({
    method: 'POST',
    componentName: 'WorldAdmission',
    retainResponse: false,
  });
  const driver: WorldDriver = useMemo(
    () => ({
      step(sim, dt, direction) {
        if (Math.hypot(direction.x, direction.y) > 0 || sim.player.path.length) seatIntent.cancel();
        if (synchronizer.current) synchronizer.current.step(sim, dt, direction);
        else {
          sim.player.path = [];
          sim.visitors = [];
          stepSimulation(sim, dt, { x: 0, y: 0 });
        }
      },
    }),
    [seatIntent]
  );

  useEffect(() => {
    let active = true;
    const url = new URL(apiEndpointUrl('/world/ws'), window.location.href);
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
    const owned = () => active && isCurrent();
    const nextSerial = () => ++emoteSerial.current;
    const channel = new WorldLink({
      url: url.href,
      scene: `${WORLD.id}:${WORLD.version}`,
      ticket: async signal => {
        const response = await mutate('/world/ticket', { consent: true }, { signal });
        if (
          !response ||
          response.version !== 1 ||
          response.account_id !== ownerId ||
          typeof response.ticket !== 'string' ||
          response.ticket.length < 32 ||
          response.ticket.length > 128
        ) {
          throw new Error('world_ticket_unavailable');
        }
        return response.ticket;
      },
      onStatus: connection => {
        if (owned()) arcadeSession.suspend(connection);
        if (connection !== 'online') {
          seatIntent.cancel();
          emoteReceipts.cancel();
        }
        if (owned())
          setPresentation(previous =>
            connection === 'connecting'
              ? INITIAL
              : previous.connection === connection
                ? previous
                : {
                    ...previous,
                    connection,
                    gestures: NO_GESTURES,
                    nearbyParticipants: NO_NEARBY,
                    emoteFeedback: null,
                  }
          );
      },
      onView: view => {
        if (!owned()) return;
        const now = performance.now();
        arcadeSession.receive(view, channel.stream, now);
        if (document.hidden) seatIntent.cancel();
        const acceptedSeat = seatIntent.accept(view, channel.stream, now);
        // The offer is confirmed against the live link, never against the receipt itself.
        const live = link.current?.view;
        if (acceptedSeat && live && link.current)
          onSeatActivity?.(acceptedSeat, { stream: link.current.stream, epoch: live.epoch });
        const feedback = receiptFeedback(
          emoteReceipts.accept(view, channel.stream, now),
          nextSerial
        );
        setPresentation(previous => {
          const people = view.actors.map(({ id, alias }) => ({ id, alias }));
          const participants =
            previous.participants.length === people.length &&
            people.every(
              (person, index) =>
                person.id === previous.participants[index].id &&
                person.alias === previous.participants[index].alias
            )
              ? previous.participants
              : people;
          const next: SessionPresentation = {
            gestures: document.hidden
              ? NO_GESTURES
              : publicGestures(view, previous.gestures ?? NO_GESTURES),
            connection: 'online' as const,
            admission: view.status,
            controlling: view.controlling,
            position: view.position,
            offer: view.offer_until,
            zone: view.you ? zoneAt(WORLD, view.you.position) : 'arrival',
            participants,
            nearbyParticipants: document.hidden
              ? NO_NEARBY
              : nearbyConversations(
                  view,
                  previous.nearbyParticipants,
                  WORLD,
                  SOCIAL_NAVIGATION,
                  SOCIAL_POSES
                ),
            poseResult: view.pose_result,
            emoteFeedback: feedback === undefined ? (previous.emoteFeedback ?? null) : feedback,
            pose: view.you?.pose ?? null,
            epoch: view.epoch,
          };
          return Object.keys(next).every(
            key =>
              previous[key as keyof SessionPresentation] === next[key as keyof SessionPresentation]
          )
            ? previous
            : next;
        });
      },
    });
    const arcadeSession = arcade.attach({
      active: () => owned() && channel.canMove === true && !document.hidden,
      send: intent => (owned() ? channel.game(intent) : null),
    });
    const cancelSeat = () => seatIntent.cancel();
    const hideSeat = () => {
      if (document.hidden) {
        cancelSeat();
        if (owned())
          setPresentation(previous =>
            previous.nearbyParticipants.length
              ? { ...previous, nearbyParticipants: NO_NEARBY }
              : previous
          );
      }
    };
    window.addEventListener('blur', cancelSeat);
    document.addEventListener('visibilitychange', hideSeat);
    link.current = channel;
    synchronizer.current = new WorldSynchronizer(channel);
    // As with native queries, a discarded StrictMode setup must not spend a
    // server ticket. The microtask belongs to this exact account/effect lifetime.
    void Promise.resolve().then(() => {
      if (owned()) channel.start();
    });
    return () => {
      active = false;
      arcadeSession.dispose();
      seatIntent.cancel();
      emoteReceipts.cancel();
      window.removeEventListener('blur', cancelSeat);
      document.removeEventListener('visibilitychange', hideSeat);
      channel.control('leave');
      channel.stop();
      if (link.current === channel) {
        link.current = null;
        synchronizer.current = null;
      }
    };
  }, [ownerId, alias, isCurrent, mutate, seatIntent, emoteReceipts, onSeatActivity, arcade]);

  const mailboxScope = useCallback(
    () => (isCurrent() ? (link.current?.mailboxScope() ?? null) : null),
    [isCurrent]
  );
  const admitted = presentation.admission === 'active' && presentation.controlling;
  const active = presentation.connection === 'online' && admitted;
  const recovering = presentation.connection === 'reconnecting' && admitted;

  const pose = useMemo(
    () => ({
      available: () => isCurrent() && (link.current?.canMove ?? false),
      request: (id: string | null) => {
        const channel = link.current;
        if (!isCurrent() || !channel?.canMove) return false;
        if (id) {
          if (!synchronizer.current?.settled) return false;
          const slot = compilePoseSlots(WORLD).find(item => item.id === id);
          const position = channel.view?.you?.position;
          if (
            !slot ||
            !position ||
            Math.hypot(position.x - slot.approach.x, position.y - slot.approach.y) > 0.6
          )
            return false;
        }
        const seq = channel.pose(id);
        seatIntent.cancel();
        if (seq === null) return false;
        if (id && channel.view)
          seatIntent.arm({
            slot: id,
            seq,
            epoch: channel.view.epoch,
            stream: channel.stream,
            now: performance.now(),
          });
        return true;
      },
    }),
    [isCurrent, seatIntent]
  );
  const emote = useCallback(
    (kind: EmoteKind): boolean => {
      const channel = link.current;
      const sent = isCurrent() && channel ? channel.emote(kind) : 'unavailable';
      if (typeof sent === 'number' && channel?.view) {
        emoteReceipts.arm({
          seq: sent,
          epoch: channel.view.epoch,
          stream: channel.stream,
          now: performance.now(),
        });
        setPresentation(previous =>
          previous.emoteFeedback ? { ...previous, emoteFeedback: null } : previous
        );
        return true;
      }
      const result = typeof sent === 'number' ? 'unavailable' : sent;
      setPresentation(previous => ({
        ...previous,
        emoteFeedback: { result, serial: ++emoteSerial.current },
      }));
      return false;
    },
    [isCurrent, emoteReceipts]
  );
  return {
    arcade,
    pose,
    active,
    recovering,
    driver,
    presentation,
    mailboxScope,
    control: (type: 'takeover' | 'accept' | 'leave') => {
      seatIntent.cancel();
      link.current?.control(type);
    },
    activity: () => link.current?.activity(),
    emote,
  };
}
