import { act, cleanup, render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useLiveStore } from '@/stores/liveStore';
import { useEyesSignalsStore } from '@/stores/eyesSignalsStore';
import { useEyesWidgetStore } from '@/stores/eyesWidgetStore';
import { usePsycheStore } from '@/stores/psycheStore';
import { useVoiceModeStore } from '@/stores/voiceModeStore';
import { EyesWidget } from '@/components/eyes/EyesWidget';
import { EYE_STYLE_IDS } from '@/components/eyes/eye-styles';
import { MIN_EXPRESSION_HOLD_MS, MASK_APPLY_DELAY_MS } from '@/components/eyes/expression-engine';
import { activeFrameSubscribers } from '@/components/eyes/rig/scheduler';
import {
  installSpiritBrowser,
  SpiritIntersectionObserver,
} from '@/components/spirit/__tests__/browser';
import { createAvatarSession } from './session-controller.avatar-fixture';
import type { LiveTransportAudio, LiveSessionMode } from '../types';

// Borrowed output/capture has separate graph lifecycle tests; no browser I/O here.
vi.mock('@/lib/voice-output/remote-capture', () => ({
  RemotePcmCapture: class {
    async warmup() {}
    attach() {
      return () => {};
    }
    flush() {}
    dispose() {}
  },
}));
vi.mock('@/components/eyes/useCompanionEnvironment', () => ({ useCompanionEnvironment: vi.fn() }));

const sessions: ReturnType<typeof createAvatarSession>[] = [];
const MODES: readonly LiveSessionMode[] = ['delegated', 'direct'];
const OUTPUTS: readonly LiveTransportAudio['ownership'][] = ['pcm', 'native', 'managed'];

beforeEach(() => {
  vi.useFakeTimers();
  useLiveStore.getState().reset();
  useEyesSignalsStore.getState().reset();
  usePsycheStore.getState().reset();
  useVoiceModeStore.getState().reset();
  localStorage.clear();
  useEyesWidgetStore.getState().reset();
  installSpiritBrowser();
  vi.stubGlobal('MediaStream', class {});
  vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue();
  vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => {});
});
afterEach(async () => {
  cleanup();
  for (const session of sessions.splice(0)) {
    session.finishWork();
    await session.controller.end();
  }
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

async function start(mode: LiveSessionMode, ownership: LiveTransportAudio['ownership']) {
  const session = createAvatarSession(mode, ownership);
  sessions.push(session);
  await session.controller.start(mode);
  expect(useLiveStore.getState().status).toBe('live');
  return session;
}

describe.each(MODES)('the %s output owns the speaking face', mode => {
  it.each(OUTPUTS)(
    '%s speech survives a late human transcript until actual output stops',
    async ownership => {
      const session = await start(mode, ownership);
      session.startSpeech();
      expect(session.output.isSpeaking).toBe(true);
      expect(useLiveStore.getState().voiceState).toBe('speaking');
      // Gemini emits audio BEFORE inputTranscription in the same content frame.
      session.events().onTranscript?.('user', 'the end of my earlier question');
      expect(useLiveStore.getState().voiceState).toBe('speaking');
      session.events().onTurnComplete?.();
      expect(useLiveStore.getState().voiceState).toBe('speaking');
      session.stopSpeech();
      expect(useLiveStore.getState().voiceState).toBe('idle');
    }
  );
  it.each(OUTPUTS)(
    '%s speech remains audible while a lookup/delegation is pending',
    async ownership => {
      const session = await start(mode, ownership);
      session.startSpeech();
      const pending = session.events().onDelegation?.([
        {
          id: 'tool',
          request: 'agenda',
          ...(mode === 'direct'
            ? { call: { name: 'get_events_tool', args: { query: 'today' } } }
            : {}),
        },
      ]);
      expect(useLiveStore.getState().delegating).toBe(true);
      expect(useLiveStore.getState().voiceState).toBe('speaking');
      session.stopSpeech();
      expect(useLiveStore.getState().voiceState).toBe('processing');
      session.finishWork();
      await pending;
    }
  );
  it.each(OUTPUTS)(
    '%s interruption and end release speech and reject an old output callback',
    async ownership => {
      const session = await start(mode, ownership);
      session.startSpeech();
      session.events().onInterrupted?.();
      expect(session.output.isSpeaking).toBe(false);
      expect(useLiveStore.getState().voiceState).toBe('recording');
      session.startSpeech();
      expect(useLiveStore.getState().voiceState).toBe('speaking');
      await session.controller.end();
      session.lateSpeech();
      expect(useLiveStore.getState()).toMatchObject({ status: 'ended', voiceState: 'idle' });
    }
  );
});

describe('Live output reaches the actual selected facial rig', () => {
  it.each(EYE_STYLE_IDS)(
    '%s keeps a moving mouth after a late transcript and rests after output ends',
    async styleId => {
      // Alternate native and PCM, plus both Live modes, on the actual skin matrix.
      const index = EYE_STYLE_IDS.indexOf(styleId);
      const session = await start(MODES[index % MODES.length], OUTPUTS[index % OUTPUTS.length]);
      useEyesWidgetStore.getState().setStyle(styleId);
      useEyesWidgetStore.getState().setSize('sm');
      useEyesWidgetStore.getState().setPosition({ xPct: 40, yPct: 30 });
      const view = render(
        <EyesWidget chatStatus="idle" streamPhase="answer" hitlAwaiting={false} />
      );
      const face = view.container.querySelector<HTMLElement>('.lia-eyes');
      if (!face) throw new Error('The chosen skin has no facial rig');
      act(() => {
        const observer = SpiritIntersectionObserver.instances.find(instance =>
          instance.targets.has(face)
        );
        if (!observer) throw new Error('The real rig is not observed');
        observer.notify(face, true);
        session.startSpeech();
        session.events().onTranscript?.('user', 'a late transcript');
        vi.advanceTimersByTime(MIN_EXPRESSION_HOLD_MS + MASK_APPLY_DELAY_MS + 25);
      });
      expect(face.dataset.expression).toBe('speaking');
      expect(activeFrameSubscribers()).toBe(1);
      const contours = new Set<string>();
      const openings: number[] = [];
      for (let frame = 0; frame < 48; frame++) {
        act(() => vi.advanceTimersByTime(32));
        contours.add(face.querySelector('[data-rig-mouth]')?.getAttribute('d') ?? '');
        openings.push(Number(face.style.getPropertyValue('--rig-mouth-open')));
      }
      expect(Math.max(...openings) - Math.min(...openings)).toBeGreaterThan(0.15);
      expect(contours.size).toBeGreaterThan(3);
      expect(view.container.querySelector('.lia-eyes')).toBe(face);
      act(() => {
        session.stopSpeech();
        vi.advanceTimersByTime(MIN_EXPRESSION_HOLD_MS + MASK_APPLY_DELAY_MS + 25);
      });
      expect(face.dataset.expression).not.toBe('speaking');
      view.unmount();
      expect(activeFrameSubscribers()).toBe(0);
    }
  );
});
