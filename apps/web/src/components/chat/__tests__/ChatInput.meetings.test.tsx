/**
 * The paperclip becomes a menu when meeting recording is offered (ADR-258):
 * add a file / record a meeting, and Stop while recording. Without a provider
 * or with the flag off, the historical file button stays exactly as it was.
 */

import { describe, expect, it, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import type { UseMeetingRecorderReturn } from '@/hooks/useMeetingRecorder';
import type { UseVoiceInputReturn } from '@/hooks/useVoiceInput';
import type { PendingAttachment, useFileUpload as useFileUploadFn } from '@/hooks/useFileUpload';
import type { VoiceModeStore } from '@/stores/voiceModeStore';

type UploadHook = ReturnType<typeof useFileUploadFn>;

vi.mock('@/hooks/useVoiceInput', () => ({
  useVoiceInput: (): UseVoiceInputReturn => ({
    state: 'idle',
    isRecording: false,
    isConnected: false,
    isProcessing: false,
    error: null,
    transcription: null,
    durationSeconds: null,
    startRecording: vi.fn(async () => undefined),
    stopRecording: vi.fn(),
    isSupported: false,
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

const recorderContext = vi.hoisted(() => ({ value: null as UseMeetingRecorderReturn | null }));
vi.mock('@/components/meetings/MeetingRecorderProvider', () => ({
  useMeetingRecorderContext: () => recorderContext.value,
}));

import { ChatInput } from '../ChatInput';

function recorder(over: Partial<UseMeetingRecorderReturn> = {}): UseMeetingRecorderReturn {
  return {
    phase: 'idle',
    recording: null,
    engine: null,
    limits: null,
    elapsedSeconds: 0,
    level: 0,
    uploadedSegments: 0,
    pendingSegments: 0,
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
});

describe('ChatInput — meeting recording entry', () => {
  it('keeps the plain file button when the feature is off', () => {
    recorderContext.value = recorder();
    renderWithProviders(
      <ChatInput onSendMessage={vi.fn()} attachmentsEnabled meetingsEnabled={false} />
    );
    expect(screen.getByRole('button', { name: 'chat.attachments.add' })).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'meetings.composer.menu_label' })
    ).not.toBeInTheDocument();
  });

  it('keeps the plain file button without a recorder provider', () => {
    renderWithProviders(<ChatInput onSendMessage={vi.fn()} attachmentsEnabled meetingsEnabled />);
    expect(screen.getByRole('button', { name: 'chat.attachments.add' })).toBeInTheDocument();
  });

  it('opens a menu with "Add a file" and "Record a meeting", and starts the recorder', async () => {
    const rec = recorder();
    recorderContext.value = rec;
    const { user } = renderWithProviders(
      <ChatInput onSendMessage={vi.fn()} attachmentsEnabled meetingsEnabled />
    );
    await user.click(screen.getByRole('button', { name: 'meetings.composer.menu_label' }));
    expect(
      await screen.findByRole('menuitem', { name: 'meetings.composer.add_file' })
    ).toBeInTheDocument();
    await user.click(screen.getByRole('menuitem', { name: 'meetings.composer.record' }));
    expect(rec.start).toHaveBeenCalledTimes(1);
  });

  it('offers Stop while a recording is open and marks the paperclip', async () => {
    const rec = recorder({ phase: 'recording', isCapturing: true, isLive: true });
    recorderContext.value = rec;
    const { user } = renderWithProviders(
      <ChatInput onSendMessage={vi.fn()} attachmentsEnabled meetingsEnabled />
    );
    expect(screen.getByTestId('composer-recording-dot')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'meetings.composer.menu_label' }));
    await user.click(await screen.findByRole('menuitem', { name: 'meetings.composer.stop' }));
    expect(rec.stop).toHaveBeenCalledTimes(1);
  });

  it('still offers the recording menu when attachments are disabled', async () => {
    recorderContext.value = recorder();
    const { user } = renderWithProviders(
      <ChatInput onSendMessage={vi.fn()} attachmentsEnabled={false} meetingsEnabled />
    );
    await user.click(screen.getByRole('button', { name: 'meetings.composer.menu_label' }));
    expect(
      await screen.findByRole('menuitem', { name: 'meetings.composer.record' })
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('menuitem', { name: 'meetings.composer.add_file' })
    ).not.toBeInTheDocument();
  });
});
