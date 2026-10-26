'use client';

import { SeatActivityIntent } from './seat-activity-intent';

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

export interface WorldParticipant {
  id: string;
  alias: string;
}

export interface SessionPresentation {
  connection: LinkStatus;
  admission: 'active' | 'waiting' | 'absent';
  controlling: boolean;
  position: number | null;
  offer: number | null;
  zone: ZoneId;
  poseResult?: 'accepted' | 'occupied' | 'out_of_reach' | 'invalid' | null;
  participants: WorldParticipant[];
}
const INITIAL: SessionPresentation = {
  connection: 'connecting',
  admission: 'absent',
  controlling: false,
  position: null,
  offer: null,
  zone: 'arrival',
  participants: [],
};

export function useWorldSession(
  ownerId: string,
  alias: string,
  onSeatActivity?: (slot: string) => void
) {
  const seatIntent = useMemo(() => new SeatActivityIntent(), []);
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
        if (connection !== 'online') seatIntent.cancel();
        if (owned())
          setPresentation(previous =>
            connection === 'connecting'
              ? INITIAL
              : previous.connection === connection
                ? previous
                : { ...previous, connection }
          );
      },
      onView: view => {
        if (!owned()) return;
        if (document.hidden) seatIntent.cancel();
        const acceptedSeat = seatIntent.accept(view, channel.stream, performance.now());
        if (acceptedSeat) onSeatActivity?.(acceptedSeat);
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
            connection: 'online' as const,
            admission: view.status,
            controlling: view.controlling,
            position: view.position,
            offer: view.offer_until,
            zone: view.you ? zoneAt(WORLD, view.you.position) : 'arrival',
            participants,
            poseResult: view.pose_result,
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
    const cancelSeat = () => seatIntent.cancel();
    const hideSeat = () => {
      if (document.hidden) cancelSeat();
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
      seatIntent.cancel();
      window.removeEventListener('blur', cancelSeat);
      document.removeEventListener('visibilitychange', hideSeat);
      channel.control('leave');
      channel.stop();
      if (link.current === channel) {
        link.current = null;
        synchronizer.current = null;
      }
    };
  }, [ownerId, alias, isCurrent, mutate, seatIntent, onSeatActivity]);

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
  return {
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
  };
}
