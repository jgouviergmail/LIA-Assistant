/**
 * sse-handlers — voice TTS events, browser screenshot side-channel and the
 * stream error handler (including the usage-limit toast).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { toast } from 'sonner';

import {
  handleVoiceCommentStart,
  handleVoiceAudioChunk,
  handleVoiceComplete,
  handleVoiceError,
  handleBrowserScreenshot,
  handleError,
} from '@/lib/sse-handlers/handlers';
import { logger } from '@/lib/logger';
import type { ChatStreamChunk, VoiceAudioChunk } from '@/types/chat';
import { buildHandlerContext, dispatchedOfType } from './context-fixture';

vi.mock('sonner', () => ({
  toast: Object.assign(vi.fn(), {
    error: vi.fn(),
    success: vi.fn(),
    warning: vi.fn(),
    loading: vi.fn(),
    info: vi.fn(),
  }),
}));

vi.mock('@/lib/logger', () => ({
  logger: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));

beforeEach(() => {
  vi.clearAllMocks();
});

describe('voice TTS handlers', () => {
  it('voice_comment_start / voice_complete / voice_error are log-only (no dispatch)', () => {
    const { context, dispatch } = buildHandlerContext();

    handleVoiceCommentStart(
      { type: 'voice_comment_start', content: '', metadata: { run_id: 'r-1' } } as ChatStreamChunk,
      context
    );
    handleVoiceComplete(
      { type: 'voice_complete', content: '', metadata: { chunk_count: 4 } } as ChatStreamChunk,
      context
    );
    handleVoiceError(
      {
        type: 'voice_error',
        content: 'tts failed',
        metadata: { error_type: 'TimeoutError' },
      } as ChatStreamChunk,
      context
    );

    expect(dispatch).not.toHaveBeenCalled();
    expect(logger.debug).toHaveBeenCalledWith('chat_voice_comment_start', expect.any(Object));
    expect(logger.info).toHaveBeenCalledWith('chat_voice_complete', expect.any(Object));
    expect(logger.warn).toHaveBeenCalledWith('chat_voice_error', expect.any(Object));
  });

  it('voice_audio_chunk forwards the audio payload to the playback queue', () => {
    const { context, handleVoiceChunk } = buildHandlerContext();
    const audio: VoiceAudioChunk = {
      audio_base64: 'bXAzZGF0YQ==',
      phrase_index: 0,
      is_last: false,
      mime_type: 'audio/mpeg',
    };

    handleVoiceAudioChunk(
      { type: 'voice_audio_chunk', content: audio as unknown as string } as ChatStreamChunk,
      context
    );

    expect(handleVoiceChunk).toHaveBeenCalledTimes(1);
    expect(handleVoiceChunk).toHaveBeenCalledWith(audio);
  });

  it('voice_audio_chunk ignores payloads without audio data', () => {
    const { context, handleVoiceChunk } = buildHandlerContext();

    handleVoiceAudioChunk(
      { type: 'voice_audio_chunk', content: {} as unknown as string } as ChatStreamChunk,
      context
    );

    expect(handleVoiceChunk).not.toHaveBeenCalled();
  });
});

describe('handleBrowserScreenshot', () => {
  it('dispatches the progressive screenshot overlay', () => {
    const { context, dispatch } = buildHandlerContext();
    const screenshot = { image_base64: 'anBlZw==', url: 'https://example.com', title: 'Example' };

    handleBrowserScreenshot(
      { type: 'browser_screenshot', content: screenshot as unknown as string } as ChatStreamChunk,
      context
    );

    expect(dispatchedOfType(dispatch, 'BROWSER_SCREENSHOT')).toEqual([screenshot]);
  });

  it('ignores payloads without an image', () => {
    const { context, dispatch } = buildHandlerContext();

    handleBrowserScreenshot(
      {
        type: 'browser_screenshot',
        content: { url: 'https://example.com' } as unknown as string,
      } as ChatStreamChunk,
      context
    );

    expect(dispatch).not.toHaveBeenCalled();
  });
});

describe('handleError', () => {
  it('dispatches STREAM_ERROR with the backend-localized message', () => {
    const { context, dispatch } = buildHandlerContext();

    handleError(
      {
        type: 'error',
        content: 'Le service est temporairement indisponible.',
        metadata: null,
      } as unknown as ChatStreamChunk,
      context
    );

    expect(dispatchedOfType(dispatch, 'STREAM_ERROR')).toEqual([
      { error: 'Le service est temporairement indisponible.' },
    ]);
    expect(logger.error).toHaveBeenCalledWith(
      'chat_stream_error',
      expect.any(Error),
      expect.objectContaining({ error_code: undefined })
    );
    expect(toast.error).not.toHaveBeenCalled();
  });

  it('shows a toast on usage_limit_exceeded (layer 1/2 enforcement)', () => {
    const { context, dispatch } = buildHandlerContext();

    handleError(
      {
        type: 'error',
        content: 'Daily limit reached',
        metadata: { error_code: 'usage_limit_exceeded' },
      } as ChatStreamChunk,
      context
    );

    expect(toast.error).toHaveBeenCalledWith('Daily limit reached');
    expect(dispatchedOfType(dispatch, 'STREAM_ERROR')).toEqual([{ error: 'Daily limit reached' }]);
  });

  it('falls back to a default toast label when the error content is empty', () => {
    const { context } = buildHandlerContext();

    handleError(
      {
        type: 'error',
        content: '',
        metadata: { error_code: 'usage_limit_exceeded' },
      } as ChatStreamChunk,
      context
    );

    expect(toast.error).toHaveBeenCalledWith('Usage limit exceeded');
  });
});
