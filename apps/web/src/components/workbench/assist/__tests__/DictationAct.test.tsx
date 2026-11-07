/**
 * Words said into a field (lot 8): the microphone opens on the press and only then, a press ends
 * it, the words join the field as it stands at the answer, and a failure gives the icon back.
 */
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { UseVoiceInputOptions } from '@/hooks/useVoiceInput';

const { voice, toast } = vi.hoisted(() => ({
  voice: {
    options: null as UseVoiceInputOptions | null,
    isRecording: false,
    startRecording: vi.fn(),
    stopRecording: vi.fn(),
  },
  toast: Object.assign(vi.fn(), { info: vi.fn(), error: vi.fn() }),
}));
vi.mock('@/hooks/useVoiceInput', () => ({
  useVoiceInput: (options: UseVoiceInputOptions) => {
    voice.options = options;
    return voice;
  },
}));
vi.mock('sonner', () => ({ toast }));
vi.mock('@/i18n/client', () => ({
  useTranslation: () => ({
    t: (key: string, values?: Record<string, string>) =>
      values ? `${key} ${JSON.stringify(values)}` : key,
  }),
}));

import { DictationAct } from '../DictationAct';

const STOP = 'workbench.assist.voice.stop_dictation';

function dictate(onWords = vi.fn()) {
  const onEnd = vi.fn();
  const view = render(<DictationAct lng="en" onWords={onWords} onEnd={onEnd} />);
  return { onWords, onEnd, ...view };
}

beforeEach(() => {
  vi.clearAllMocks();
  voice.isRecording = false;
  voice.options = null;
});

describe('DictationAct', () => {
  it('opens the microphone once it stands, and not before', async () => {
    dictate();

    await waitFor(() => expect(voice.startRecording).toHaveBeenCalledOnce());
  });

  it('ends on a press once it listens', async () => {
    voice.isRecording = true;
    dictate();
    const user = userEvent.setup();

    await user.click(screen.getByRole('button', { name: STOP }));

    expect(voice.stopRecording).toHaveBeenCalledOnce();
  });

  it('holds its press while nothing listens yet', async () => {
    dictate();
    const user = userEvent.setup();

    await user.click(screen.getByRole('button', { name: STOP }));

    expect(voice.stopRecording).not.toHaveBeenCalled();
  });

  it('hands the words over, trimmed, to the field as it stands at the answer', () => {
    const first = vi.fn();
    const last = vi.fn();
    const { rerender, onEnd } = dictate(first);
    rerender(<DictationAct lng="en" onWords={last} onEnd={onEnd} />);

    act(() => voice.options?.onTranscription?.('  Hello there '));

    expect(first).not.toHaveBeenCalled();
    expect(last).toHaveBeenCalledWith('Hello there');
    expect(onEnd).toHaveBeenCalledOnce();
  });

  it('says nothing was heard, and adds nothing', () => {
    const { onWords, onEnd } = dictate();

    act(() => voice.options?.onTranscription?.('   '));

    expect(onWords).not.toHaveBeenCalled();
    expect(toast.info).toHaveBeenCalledWith('workbench.assist.voice.nothing_heard');
    expect(onEnd).toHaveBeenCalledOnce();
  });

  it('says what a remote engine cost, and nothing of a local one', () => {
    dictate();

    act(() => voice.options?.onTranscription?.('Hello'));
    expect(toast).not.toHaveBeenCalled();

    act(() =>
      voice.options?.onTranscription?.('Hello', {
        stt_provider: 'remote',
        stt_audio_duration_seconds: 4,
        stt_cost_usd: 0.001,
        stt_cost_eur: 0.002,
      })
    );
    expect(toast).toHaveBeenCalledOnce();
  });

  it('gives the icon back on a failure, and says so', () => {
    const { onWords, onEnd } = dictate();

    act(() => voice.options?.onError?.(new Error('denied')));

    expect(toast.error).toHaveBeenCalledWith('workbench.assist.voice.dictation_failed');
    expect(onWords).not.toHaveBeenCalled();
    expect(onEnd).toHaveBeenCalledOnce();
  });
});
