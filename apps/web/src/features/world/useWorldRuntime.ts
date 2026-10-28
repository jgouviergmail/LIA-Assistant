'use client';
import type { WorldSpeech } from './speech';

import { useCallback, useEffect, useEffectEvent, useMemo, useRef, useState } from 'react';
import { useApplicationAccountLifetime } from '@/hooks/useApplicationAccountLifetime';
import type { SceneHost } from './scene-interactions';
import { WORLD } from './definition';
import { createRuntime, type WorldRuntime } from './runtime';
import type { Quality, WorldActingState, WorldSnapshot } from './types';
import type { WorldDriver } from './shared-simulation';
import type { HomeSkin } from './home-projection';
import { NEUTRAL_ATMOSPHERE, type Atmosphere } from './atmosphere';
import type { PrivateSignalPresentation } from './private-signal-projection';
import type { WorldActingSource } from './useWorldActingSource';
import type { Season } from './season';
import type { CosmeticActionId } from './cosmetic-interactions';

const INITIAL: WorldSnapshot = {
  player: WORLD.spawn,
  bip: WORLD.bipSpawn,
  zone: 'arrival',
  zoom: 0.95,
  following: true,
  bipFollowing: false,
  metrics: { fps: 0, frameP95: 0, renderP95: 0, sprites: 0, textureBytes: 0 },
};
interface Options {
  onCosmeticCue?(action: CosmeticActionId, current: () => boolean, targetId: string): void;
  season?: Season;
  onActingState?(state: WorldActingState): void;
  conversationOpen?: boolean;
  acting?: WorldActingSource;
  privateSignals?: readonly PrivateSignalPresentation[];
  speech?: WorldSpeech;
  onInteract?: () => void;
  scene?: SceneHost;
  home?: HomeSkin | null;
  atmosphere?: Atmosphere;
  driver?: WorldDriver;
  ownerId: string;
  player: string;
  bip: string;
  reducedMotion: boolean;
  paused: boolean;
  quality: Quality;
  showRoute?: boolean;
}

export function useWorldRuntime({
  onCosmeticCue,
  season = 'neutral',
  onActingState,
  conversationOpen = false,
  acting,
  privateSignals,
  ownerId,
  player,
  bip,
  reducedMotion,
  paused,
  quality,
  driver,
  home,
  atmosphere,
  onInteract,
  speech,
  scene,
  showRoute = true,
}: Options) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const cosmeticCue = useEffectEvent(
    (action: CosmeticActionId, current: () => boolean, targetId: string) =>
      onCosmeticCue?.(action, current, targetId)
  );
  const runtimeRef = useRef<WorldRuntime | null>(null);
  const { isCurrent } = useApplicationAccountLifetime(ownerId);
  const [snapshot, setSnapshot] = useState(INITIAL);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const publishActing = useEffectEvent((state: WorldActingState) => onActingState?.(state));
  // Every visual setter must reach a replacement runtime, including a new scene port.
  const binding = useMemo(
    () => ({ ownerId, player, bip, driver, onInteract, scene, speech, attempt, isCurrent }),
    [ownerId, player, bip, driver, onInteract, scene, speech, attempt, isCurrent]
  );

  useEffect(() => {
    const { player, bip, driver, onInteract, scene, speech, isCurrent } = binding;
    const canvas = canvasRef.current;
    if (!canvas) return;
    let active = true;
    try {
      const runtime = createRuntime(canvas, WORLD, {
        onInteract,
        speech,
        scene,
        onCosmeticCue: cosmeticCue,
        driver,
        labels: { player, bip },
        reducedMotion: false,
        onSnapshot: value => {
          if (active && isCurrent()) {
            setSnapshot(value);
            publishActing(value.acting ?? 'idle');
          }
        },
        onFailure: () => {
          if (active && isCurrent()) setFailed(true);
        },
      });
      runtimeRef.current = runtime;
      return () => {
        active = false;
        runtimeRef.current = null;
        runtime.destroy();
      };
    } catch {
      queueMicrotask(() => {
        if (active && isCurrent()) setFailed(true);
      });
      return () => {
        active = false;
      };
    }
  }, [binding]);
  useEffect(() => {
    runtimeRef.current?.setPaused(paused);
  }, [paused, binding]);
  useEffect(() => {
    runtimeRef.current?.setReducedMotion(reducedMotion);
  }, [reducedMotion, binding]);
  useEffect(() => {
    runtimeRef.current?.setQuality(quality);
  }, [quality, binding]);
  useEffect(() => {
    runtimeRef.current?.setHome(home ?? null);
  }, [home, binding]);
  useEffect(() => {
    runtimeRef.current?.setAtmosphere(atmosphere ?? NEUTRAL_ATMOSPHERE);
  }, [atmosphere, binding]);
  useEffect(() => {
    runtimeRef.current?.setRouteVisible(showRoute);
  }, [showRoute, binding]);
  useEffect(() => {
    runtimeRef.current?.setPrivateSignals(privateSignals ?? []);
  }, [privateSignals, binding]);
  useEffect(() => {
    runtimeRef.current?.setActingSource(acting);
  }, [acting, binding]);
  useEffect(() => {
    runtimeRef.current?.setConversationOpen(conversationOpen);
  }, [conversationOpen, binding]);
  useEffect(() => {
    runtimeRef.current?.setSeason(season);
  }, [season, binding]);

  const command = useCallback(
    (action: (runtime: WorldRuntime) => void) => {
      const runtime = runtimeRef.current;
      if (runtime && isCurrent()) action(runtime);
    },
    [isCurrent]
  );
  const focusScene = useCallback(() => {
    if (isCurrent()) canvasRef.current?.focus();
  }, [isCurrent]);
  return {
    focusScene,
    canvasRef,
    snapshot,
    failed,
    retry: () => {
      setFailed(false);
      setAttempt(value => value + 1);
    },
    command,
  };
}
