'use client';
import type { WorldSpeech } from './speech';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useApplicationAccountLifetime } from '@/hooks/useApplicationAccountLifetime';
import type { SceneHost } from './scene-interactions';
import { WORLD } from './definition';
import { createRuntime, type WorldRuntime } from './runtime';
import type { Quality, WorldSnapshot } from './types';
import type { WorldDriver } from './shared-simulation';
import type { HomeSkin } from './home-projection';
import { NEUTRAL_ATMOSPHERE, type Atmosphere } from './atmosphere';

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
}

export function useWorldRuntime({
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
}: Options) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const runtimeRef = useRef<WorldRuntime | null>(null);
  const { isCurrent } = useApplicationAccountLifetime(ownerId);
  const [snapshot, setSnapshot] = useState(INITIAL);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    let active = true;
    try {
      const runtime = createRuntime(canvas, WORLD, {
        onInteract,
        speech,
        scene,
        driver,
        labels: { player, bip },
        reducedMotion: false,
        onSnapshot: value => {
          if (active && isCurrent()) setSnapshot(value);
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
  }, [ownerId, player, bip, isCurrent, attempt, driver, onInteract, scene, speech]);
  useEffect(() => {
    runtimeRef.current?.setPaused(paused);
  }, [paused, attempt, ownerId, player, bip, driver]);
  useEffect(() => {
    runtimeRef.current?.setReducedMotion(reducedMotion);
  }, [reducedMotion, attempt, ownerId, player, bip, driver]);
  useEffect(() => {
    runtimeRef.current?.setQuality(quality);
  }, [quality, attempt, ownerId, player, bip, driver]);
  useEffect(() => {
    runtimeRef.current?.setHome(home ?? null);
  }, [home, attempt, ownerId, player, bip, driver]);
  useEffect(() => {
    runtimeRef.current?.setAtmosphere(atmosphere ?? NEUTRAL_ATMOSPHERE);
  }, [atmosphere, attempt, ownerId, player, bip, driver]);

  const command = useCallback(
    (action: (runtime: WorldRuntime) => void) => {
      const runtime = runtimeRef.current;
      if (runtime && isCurrent()) action(runtime);
    },
    [isCurrent]
  );
  return {
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
