/**
 * The composer's « + » is the file picker, and only that (ADR-259, owner
 * decision 1): recording moved to the header, the logo menu and the Meetings
 * page. What the composer keeps from ADR-258 is the microphone arbitration —
 * hold-to-talk is not offered while a meeting is being captured.
 */

import { describe, expect, it, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import type { MeetingRecorderContextValue } from '@/components/meetings/MeetingRecorderProvider';
import type { UseVoiceInputReturn } from '@/hooks/useVoiceInput';
import type { PendingAttachment, useFileUpload as useFileUploadFn } from '@/hooks/useFileUpload';
import type { VoiceModeStore } from '@/stores/voiceModeStore';

type UploadHook = ReturnType<typeof useFileUploadFn>;

const voice = vi.hoisted(() => ({ startRecording: vi.fn(async () => undefined) }));
vi.mock('@/hooks/useVoiceInput', () => ({
  useVoiceInput: (): UseVoiceInputReturn => ({
    state: 'idle',
    isRecording: false,
    isConnected: false,
    isProcessing: false,
    error: null,
    transcription: null,
    durationSeconds: null,
    startRecording: voice.startRecording,
    stopRecording: vi.fn(),
    isSupported: true,
  }),
}));

vi.mock('@/stores/voiceModeStore', () => ({
  useVoiceModeStore: (selector: (state: VoiceModeStore) => unknown) =>
    selector({
      isEnabled: false,
      state: 'idle',
      isKwsReady: false,
      isKwsLoading: false,
      isKwsListening: false,
      error: null,
      lastWakeWordTime: null,
      enable: vi.fn(),
      disable: vi.fn(),
      toggle: vi.fn(),
      setState: vi.fn(),
      setKwsReady: vi.fn(),
      setKwsLoading: vi.fn(),
      setKwsListening: vi.fn(),
      setError: vi.fn(),
      recordWakeWord: vi.fn(),
      reset: vi.fn(),
    }),
}));

vi.mock('@/hooks/useFileUpload', () => ({
  useFileUpload: (): UploadHook => ({
    attachments: [] as PendingAttachment[],
    uploadFile: vi.fn(),
    removeFile: vi.fn(),
    clearAttachments: vi.fn(),
    getReadyAttachmentIds: vi.fn(() => []),
    isUploading: false,
  }),
}));

const recorderContext = vi.hoisted(() => ({ value: null as MeetingRecorderContextValue | null }));
vi.mock('@/components/meetings/MeetingRecorderProvider', () => ({
  useMeetingRecorderContext: () => recorderContext.value,
}));

import { ChatInput } from '../ChatInput';

function recorder(over: Partial<MeetingRecorderContextValue> = {}): MeetingRecorderContextValue {
  return {
    phase: 'idle',
    recording: null,
    engine: null,
    limits: null,
    silencePrompt: false,
    errorCode: null,
    missingSegments: null,
    isSupported: true,
    isCapturing: false,
    isLive: false,
    start: vi.fn(async () => undefined),
    stop: vi.fn(async () => 'processing' as const),
    finalizeWithGaps: vi.fn(async () => 'processing' as const),
    resume: vi.fn(async () => undefined),
    discard: vi.fn(async () => undefined),
    dismiss: vi.fn(),
    continueAfterSilence: vi.fn(),
    ...over,
  };
}

beforeEach(() => {
  recorderContext.value = null;
  voice.startRecording.mockClear();
});

describe('ChatInput — the « + » is the file picker (ADR-259)', () => {
  it('shows the plain file button whether or not the instance records meetings', () => {
    recorderContext.value = recorder();
    renderWithProviders(<ChatInput onSendMessage={vi.fn()} attachmentsEnabled meetingsEnabled />);
    expect(screen.getByRole('button', { name: 'chat.attachments.add' })).toBeInTheDocument();
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
    expect(screen.queryByText(/meetings\.composer/)).not.toBeInTheDocument();
  });

  it('shows no « + » at all when attachments are disabled', () => {
    recorderContext.value = recorder();
    renderWithProviders(
      <ChatInput onSendMessage={vi.fn()} attachmentsEnabled={false} meetingsEnabled />
    );
    expect(screen.queryByRole('button', { name: 'chat.attachments.add' })).not.toBeInTheDocument();
  });

  it('keeps hold-to-talk off the table while a meeting is being captured', async () => {
    recorderContext.value = recorder({ phase: 'recording', isCapturing: true, isLive: true });
    const { user } = renderWithProviders(
      <ChatInput onSendMessage={vi.fn()} attachmentsEnabled meetingsEnabled />
    );
    const composerButton = screen.getByRole('button', { name: 'chat.input.send' });
    await user.pointer({ keys: '[MouseLeft>]', target: composerButton });
    expect(voice.startRecording).not.toHaveBeenCalled();
  });
});
