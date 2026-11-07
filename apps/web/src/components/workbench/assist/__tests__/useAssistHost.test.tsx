/**
 * The doors any tool can open (lot 5): a door that leads nowhere on this instance is simply absent,
 * and it answers to the operator's switch, not to the deployment's ceiling alone.
 */
import { renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { AppConfig } from '@/hooks/useAppConfig';

const { microphone } = vi.hoisted(() => ({ microphone: { reachable: true } }));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: { timezone: 'UTC' } }) }));
vi.mock('@/hooks/useVoiceInput', () => ({ canRecordVoice: () => microphone.reachable }));

import { useAssistHost } from '../useAssistHost';

const BASE: AppConfig = {
  sse: { heartbeat_interval_seconds: 30 },
  rate_limits: { enabled: false, per_minute: 60, burst: 10 },
  i18n: { supported_languages: ['en'], default_language: 'en' },
  features: {
    tool_approval_enabled: false,
    attachments_enabled: true,
    rag_spaces_enabled: false,
    rag_spaces_embedding_model: 'a-model',
    journals_enabled: false,
  },
  api_version: 'v1',
};

function configWith(enabled: readonly string[]): AppConfig {
  const capabilities = Object.fromEntries(
    ['workboard', 'rag_spaces', 'meetings', 'stt', 'tts', 'tool_assists'].map(key => [
      key,
      { enabled: enabled.includes(key), family: 'work' },
    ])
  );
  return { ...BASE, capabilities };
}

function doorsOf(config: AppConfig | null) {
  return renderHook(() => useAssistHost('en', config)).result.current.doors;
}

describe('useAssistHost', () => {
  it('offers no dictation where the page cannot reach a microphone', () => {
    microphone.reachable = false;

    expect(doorsOf(configWith(['stt'])).dictates).toBe(false);

    microphone.reachable = true;
  });

  it('always offers to be reminded, and nothing else before the configuration is read', () => {
    const doors = doorsOf(null);

    expect(doors.remind).toBeTypeOf('function');
    expect(doors.confide).toBeUndefined();
    expect(doors.keep).toBeUndefined();
    expect(doors.meetings).toBe(false);
  });

  it('hands to LIA where the board is on', () => {
    expect(doorsOf(configWith(['workboard'])).confide).toBeTypeOf('function');
    expect(doorsOf(configWith([])).confide).toBeUndefined();
  });

  it('keeps in a space only where its route exists: spaces on and the assists mounted', () => {
    expect(doorsOf(configWith(['rag_spaces', 'tool_assists'])).keep).toBeTypeOf('function');
    expect(doorsOf(configWith(['rag_spaces'])).keep).toBeUndefined();
    expect(doorsOf(configWith(['tool_assists'])).keep).toBeUndefined();
  });

  it('reads each voice’s own switch', () => {
    const doors = doorsOf(configWith(['stt']));

    expect(doors.dictates).toBe(true);
    expect(doors.reads).toBe(false);
  });

  it('follows the operator’s verdict on meetings over the deployment’s ceiling', () => {
    const base = configWith([]);
    const config = { ...base, features: { ...base.features, meetings_enabled: true } };

    expect(doorsOf(config).meetings).toBe(false);
  });
});
