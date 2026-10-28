import { cosmeticPropTarget } from '../cosmetic-interactions';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import type { ComponentProps, ReactNode } from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import type { Notification } from '@/hooks/useNotifications';
import { WorldShared } from '../WorldShared';
import { WORLD } from '../definition';
import { stepSimulation, type Simulation } from '../simulation';
import type { WorldSpeech } from '../speech';
import type { Camera } from '../types';
import type { WorldRenderer } from '../renderer';
import type { WorldExperienceControl } from '../useWorldExperiencePreferences';
import type { useWorldSession } from '../useWorldSession';
import type { useWorldSound } from '../useWorldSound';
import { WorldGameClient } from '../game-client';

const state = vi.hoisted(() => ({
  verified: true,
  active: true,
  receive: new Map<string, (notice: Notification) => void>(),
  speech: new Map<string, WorldSpeech>(),
  render: vi.fn<(camera: Camera, sim: Simulation) => void>(),
}));
vi.mock('@/i18n/client', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('@/hooks/useMediaQuery', () => ({ useMediaQuery: () => false }));
vi.mock('../WorldAccountGuard', () => ({
  WorldAccountGuard: ({ children }: { children: ReactNode }) => children,
  useWorldAccountIdentity: () => ({ verified: state.verified }),
}));
vi.mock('../WorldAdmission', () => ({
  WorldAdmission: ({ onEnter }: { onEnter(alias: string): void }) => (
    <button onClick={() => onEnter('Owner')}>Enter</button>
  ),
}));
vi.mock('../useWorldSession', () => ({
  useWorldSession: () => ({ ...session, active: state.active, recovering: !state.active }),
}));
vi.mock('../useWorldEnvironment', () => ({ useWorldEnvironment: () => undefined }));
vi.mock('../useWorldPrivateSignals', () => ({
  useWorldPrivateSignals: (
    ownerId: string,
    _enabled: boolean,
    onProactive: (notice: Notification) => void
  ) => {
    state.receive.set(ownerId, onProactive);
    return { signals: [], presentation: [] };
  },
}));
vi.mock('../useWorldActingSource', () => ({ useWorldActingSource: () => undefined }));
vi.mock('../useWorldExperiencePreferences', () => ({
  useWorldExperiencePreferences: () => experience,
}));
vi.mock('../useWorldSound', () => ({ useWorldSound: () => sound }));
vi.mock('../WorldSessionDialog', () => ({ WorldSessionDialog: () => null }));
vi.mock('../WorldHelp', () => ({ WorldHelp: () => null }));
vi.mock('../WorldObjectHint', () => ({ WorldObjectHint: () => null }));
vi.mock('../WorldHud', () => ({
  WorldHud: ({ widgets }: ComponentProps<typeof import('../WorldHud').WorldHud>) => widgets,
}));
vi.mock('../WorldHomeControls', () => ({
  WorldHomeControls: ({
    onEditing,
  }: ComponentProps<typeof import('../WorldHomeControls').WorldHomeControls>) => (
    <>
      <button onClick={() => onEditing(true)}>home-open</button>
      <button onClick={() => onEditing(false)}>home-close</button>
    </>
  ),
}));
vi.mock('../WorldPhotoControls', () => ({
  WorldPhotoControls: ({
    onOpen,
  }: ComponentProps<typeof import('../WorldPhotoControls').WorldPhotoControls>) => (
    <>
      <button onClick={() => onOpen?.(true)}>photo-open</button>
      <button onClick={() => onOpen?.(false)}>photo-close</button>
    </>
  ),
}));
vi.mock('../WorldFunctionControls', () => ({
  WorldFunctionControls: ({
    onOpen,
  }: ComponentProps<typeof import('../WorldFunctionControls').WorldFunctionControls>) => (
    <>
      <button onClick={() => onOpen(true, true)}>native-open</button>
      <button onClick={() => onOpen(false, false)}>native-close</button>
    </>
  ),
}));
vi.mock('../WorldMessageControls', () => ({
  WorldMessageControls: ({
    onOpen,
  }: ComponentProps<typeof import('../WorldMessageControls').WorldMessageControls>) => (
    <>
      <button onClick={() => onOpen(true)}>social-open</button>
      <button onClick={() => onOpen(false)}>social-close</button>
    </>
  ),
}));
vi.mock('../WorldDeviceControls', () => ({
  WorldDeviceControls: ({
    ownerId,
    onOpen,
    onProactive,
    extras,
  }: ComponentProps<typeof import('../WorldDeviceControls').WorldDeviceControls>) => {
    if (onProactive) state.receive.set(ownerId, onProactive);
    return (
      <>
        {extras}
        <button onClick={() => onOpen(true)}>device-open</button>
        <button onClick={() => onOpen(false)}>device-close</button>
      </>
    );
  },
}));
vi.mock('../WorldSpeechAnnouncements', async original => {
  const actual = await original<typeof import('../WorldSpeechAnnouncements')>();
  return {
    WorldSpeechAnnouncements: ({
      speech,
    }: ComponentProps<typeof actual.WorldSpeechAnnouncements>) => {
      state.speech.set('current', speech);
      return <actual.WorldSpeechAnnouncements speech={speech} />;
    },
  };
});
vi.mock('../renderer', () => ({
  WorldRenderer: class implements Pick<WorldRenderer, keyof WorldRenderer> {
    photoScene() {
      return null;
    }
    preparePhoto() {
      return Promise.resolve();
    }
    drawCount = 0;
    textureBytes = 0;
    activeCosmeticEffects = 0;
    reducedMotion = false;
    showRoute = true;
    resize() {}
    setQuality() {}
    setHome() {}
    setAtmosphere() {}
    setSeason() {}
    cosmeticTarget(id: string) {
      const prop = WORLD.props.find(item => item.id === id);
      return prop ? cosmeticPropTarget(prop) : null;
    }
    cancelCosmetic() {}
    activateCosmetic() {
      return false;
    }
    pick() {
      return null;
    }
    setActing() {}
    setPrivateSignals() {}
    destroy() {}
    render(camera: Camera, sim: Simulation) {
      state.render(camera, sim);
    }
  },
}));

const experience: WorldExperienceControl = {
  experience: null,
  loading: false,
  failed: false,
  saving: false,
  save: async () => false,
  refresh: async () => {},
  reload: async () => true,
};
const sound: ReturnType<typeof useWorldSound> = {
  enabled: false,
  failed: false,
  volume: 0.5,
  setVolume: () => {},
  toggle: () => {},
  wake: () => {},
  receive: () => {},
  effect: () => {},
};
const session: ReturnType<typeof useWorldSession> = {
  arcade: new WorldGameClient(),
  emote: () => true,
  active: true,
  recovering: false,
  driver: {
    step(sim, dt, direction) {
      stepSimulation(sim, dt, direction);
      sim.bip.position = { x: sim.player.position.x + 1, y: sim.player.position.y };
    },
  },
  presentation: {
    connection: 'online',
    admission: 'active',
    controlling: true,
    position: null,
    offer: null,
    zone: 'arrival',
    participants: [],
    nearbyParticipants: [],
    pose: null,
    epoch: null,
  },
  mailboxScope: () => null,
  pose: { available: () => true, request: () => true },
  activity: () => {},
  control: () => {},
};
let now = 100;
const frames: FrameRequestCallback[] = [];
function advance(count = 1, start = now + 17) {
  act(() => {
    for (let index = 0; index < count; index++) {
      now = start + index * (1000 / 60);
      frames.shift()?.(now);
    }
  });
}
function enter() {
  fireEvent.click(screen.getByRole('button', { name: 'Enter' }));
}
function panel(name: string, open: boolean) {
  fireEvent.click(screen.getByRole('button', { name: `${name}-${open ? 'open' : 'close'}` }));
}
function notice(id: string): Notification {
  return {
    id,
    type: 'proactive_discussion',
    content: id,
    timestamp: new Date(),
    read: false,
    target_id: 'thread',
    metadata: { message_id: id },
  };
}
function publish(id: string, owner = 'owner') {
  act(() => state.receive.get(owner)?.(notice(id)));
}
beforeEach(() => {
  state.active = state.verified = true;
  state.receive.clear();
  state.speech.clear();
  state.render.mockClear();
  frames.length = 0;
  now = 100;
  vi.spyOn(performance, 'now').mockImplementation(() => now);
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
    frames.push(callback);
    return frames.length;
  });
  vi.stubGlobal('cancelAnimationFrame', vi.fn());
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe() {}
      disconnect() {}
    }
  );
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

it.each(['social', 'native', 'home', 'device', 'photo'])(
  'queues proactive speech while the %s panel owns attention',
  name => {
    render(<WorldShared lng="en" ownerId="owner" />);
    enter();
    panel(name, true);
    publish('Opening');
    const canvas = document.querySelector('canvas');
    if (!canvas) throw new Error('Missing real world runtime canvas');
    canvas.focus();
    window.dispatchEvent(new KeyboardEvent('keydown', { code: 'ArrowRight' }));
    advance(8);
    window.dispatchEvent(new KeyboardEvent('keyup', { code: 'ArrowRight' }));
    const moved = state.render.mock.lastCall?.[1].player.position.x;
    advance(53);
    expect(screen.queryByText('LIA: Opening')).not.toBeInTheDocument();
    expect(state.render.mock.calls.length).toBeGreaterThanOrEqual(30);
    if (name === 'social' || name === 'native') expect(moved).toBeGreaterThan(WORLD.spawn.x + 0.05);
    panel(name, false);
    advance();
    expect(screen.getByText('LIA: Opening')).toBeInTheDocument();
    advance(1, now + 5001);
    expect(screen.queryByText('LIA: Opening')).not.toBeInTheDocument();
  }
);

it('expires queued openings while a panel remains open and does not replay them on return', () => {
  render(<WorldShared lng="en" ownerId="owner" />);
  enter();
  panel('social', true);
  publish('Expired opening');
  advance(1, now + 60001);
  panel('social', false);
  advance();
  expect(screen.queryByText('LIA: Expired opening')).not.toBeInTheDocument();
  panel('social', true);
  publish('Fresh opening');
  advance();
  expect(screen.queryByText('LIA: Fresh opening')).not.toBeInTheDocument();
  panel('social', false);
  advance();
  expect(screen.getByText('LIA: Fresh opening')).toBeInTheDocument();
});

it('keeps presentation suspended across same-owner verification and recovery', () => {
  const view = render(<WorldShared lng="en" ownerId="owner" />);
  enter();
  panel('social', true);
  state.active = state.verified = false;
  view.rerender(<WorldShared lng="en" ownerId="owner" />);
  state.active = state.verified = true;
  view.rerender(<WorldShared lng="en" ownerId="owner" />);
  publish('After verification');
  advance(5);
  expect(screen.queryByText('LIA: After verification')).not.toBeInTheDocument();
  panel('social', false);
  advance();
  expect(screen.getByText('LIA: After verification')).toBeInTheDocument();
});

it('rejects an old owner callback and clears its queue before the next owner enters', () => {
  const view = render(<WorldShared lng="en" ownerId="owner" />);
  enter();
  panel('social', true);
  publish('Old queued opening');
  const oldSpeech = state.speech.get('current');
  const oldReceive = state.receive.get('owner');
  view.rerender(<WorldShared lng="en" ownerId="next-owner" />);
  enter();
  act(() => oldReceive?.(notice('Late old opening')));
  publish('Current opening', 'next-owner');
  advance(3);
  expect(oldSpeech?.getSnapshot()).toEqual([]);
  expect(screen.queryByText('LIA: Old queued opening')).not.toBeInTheDocument();
  expect(screen.queryByText('LIA: Late old opening')).not.toBeInTheDocument();
  expect(screen.getByText('LIA: Current opening')).toBeInTheDocument();
});
