'use client';
import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react';
import { useApplicationAccountLifetime } from '@/hooks/useApplicationAccountLifetime';
import { useLiveHoldsMicrophone } from '@/stores/liveStore';
import { useRadioHoldsAudio } from '@/stores/radioStore';
import { useMeetingIsCapturing } from '@/stores/meetingRecorderStore';
import { useVoiceModeStore } from '@/stores/voiceModeStore';
import { useEyesSignalsStore } from '@/stores/eyesSignalsStore';
import { ambientFor } from './audio/catalogue';
import { RecipientChime } from './audio/message-chime';
import { BrowserWorldAudio } from './audio/browser-audio';
import { Soundscape } from './audio/soundscape';
import { soundPreference, volumePreference } from './audio/sound-preference';
import type { WorldMailbox } from './message-protocol';
import type { Atmosphere } from './atmosphere';
import type { CosmeticActionId } from './cosmetic-interactions';
import { cosmeticCue } from './audio/cosmetic-cues';
export interface WorldSoundControl {
  enabled: boolean;
  failed: boolean;
  volume: number;
  setVolume(value: number): void;
  toggle(): void;
}
export function useWorldSound(
  ownerId: string,
  active: boolean,
  zone: string | null,
  atmosphere: Atmosphere
) {
  const preference = useMemo(() => soundPreference(ownerId), [ownerId]);
  const loudness = useMemo(() => volumePreference(ownerId), [ownerId]);
  const volume = useSyncExternalStore(
    loudness.subscribe,
    loudness.snapshot,
    loudness.serverSnapshot
  );
  const enabled = useSyncExternalStore(
    preference.subscribe,
    preference.snapshot,
    preference.serverSnapshot
  );
  const cues = useRef<RecipientChime | null>(null);
  const player = useRef<Soundscape | null>(null);
  const { isCurrent } = useApplicationAccountLifetime(ownerId);
  const [failed, setFailed] = useState(false);
  const live = useLiveHoldsMicrophone(),
    radio = useRadioHoldsAudio(),
    meeting = useMeetingIsCapturing();
  const listening = useVoiceModeStore(state => state.isEnabled);
  const speaking = useEyesSignalsStore(state => state.audioPlaying);
  const priority = live || radio || meeting || listening || speaking;
  const scene = ambientFor(zone, atmosphere);
  useEffect(() => {
    const ownedCues = new RecipientChime();
    cues.current = ownedCues;
    const engine = new Soundscape(new BrowserWorldAudio());
    player.current = engine;
    return () => {
      ownedCues.setActive(false);
      if (cues.current === ownedCues) cues.current = null;
      engine.destroy();
      if (player.current === engine) player.current = null;
    };
  }, [ownerId]);
  useEffect(() => {
    player.current?.setVolume(volume);
  }, [volume, ownerId]);
  useEffect(() => {
    void player.current?.select(scene);
  }, [scene, ownerId]);
  useEffect(() => {
    const engine = player.current;
    const update = () => engine?.pause(!active || priority || document.hidden || !isCurrent());
    update();
    document.addEventListener('visibilitychange', update);
    return () => document.removeEventListener('visibilitychange', update);
  }, [active, priority, ownerId, isCurrent]);
  useEffect(() => {
    if (!enabled) player.current?.disable();
  }, [enabled, ownerId]);
  useEffect(() => {
    cues.current?.setActive(active);
    return () => cues.current?.setActive(false);
  }, [active, ownerId]);
  const wake = useCallback(() => {
    const engine = player.current;
    if (!engine || !active || priority || document.hidden || !isCurrent() || !preference.snapshot())
      return;
    void engine.enable().then(ok => {
      if (player.current === engine && isCurrent() && preference.snapshot()) {
        if (!ok) preference.update(false);
        setFailed(!ok);
      }
    });
  }, [active, priority, isCurrent, preference]);
  const toggle = useCallback(() => {
    const next = !preference.snapshot();
    preference.update(next);
    if (next) wake();
    else player.current?.disable();
  }, [preference, wake]);
  const receive = useCallback(
    (mailbox: WorldMailbox) => {
      if (!active || !isCurrent()) return;
      cues.current?.setActive(true);
      if (cues.current?.receive(mailbox)) void player.current?.notify();
    },
    [active, isCurrent]
  );
  const setVolume = useCallback(
    (value: number) => {
      if (isCurrent()) loudness.update(value);
    },
    [isCurrent, loudness]
  );
  const effect = useCallback(
    (action: CosmeticActionId, current: () => boolean, targetId: string) => {
      const cue = cosmeticCue(action, targetId);
      if (!cue || !active || priority || document.hidden || !isCurrent()) return;
      void player.current?.effect(cue, () => isCurrent() && current());
    },
    [active, priority, isCurrent]
  );
  return { enabled, volume, setVolume, failed, toggle, wake, receive, effect };
}
