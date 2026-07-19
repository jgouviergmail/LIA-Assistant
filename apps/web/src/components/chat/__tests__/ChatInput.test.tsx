/**
 * ChatInput — the composer. Beyond the state-driven placeholder and the
 * Enter/Shift+Enter contract, this pins the three subsystems grafted onto it:
 *
 * - **attachments**: picking or dropping files, the per-code rejection wording,
 *   the ids + metadata forwarded on send, and the reset that lets the user pick
 *   the *same* file twice;
 * - **voice**: push-to-talk arming (which must stay inert as soon as there is
 *   text, or when hands-free voice mode owns the microphone), the transcription
 *   appended to the draft, and the STT cost metadata carried to the next send;
 * - **generation**: the stop button that replaces send while a response streams.
 *
 * The hooks are mocked at their public signatures (`UseVoiceInputReturn`,
 * `useFileUpload`'s return, `VoiceModeStore`) — no partial shapes, no casts.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor, fireEvent, act } from '@/__tests__/test-utils';
import type {
  UseVoiceInputOptions,
  UseVoiceInputReturn,
  VoiceInputState,
} from '@/hooks/useVoiceInput';
import type { PendingAttachment, useFileUpload as useFileUploadFn } from '@/hooks/useFileUpload';
import type { VoiceModeStore } from '@/stores/voiceModeStore';

type UploadHook = ReturnType<typeof useFileUploadFn>;
type UploadResult = Awaited<ReturnType<UploadHook['uploadFile']>>;

const voice = vi.hoisted(() => ({
  startRecording: vi.fn(async () => {}),
  stopRecording: vi.fn(),
  /** Captures the options ChatInput passes, so tests can fire its callbacks. */
  options: null as UseVoiceInputOptions | null,
  isSupported: false,
  isRecording: false,
  isProcessing: false,
  state: 'idle' as VoiceInputState,
}));

vi.mock('@/hooks/useVoiceInput', () => ({
  useVoiceInput: (options: UseVoiceInputOptions): UseVoiceInputReturn => {
    voice.options = options;
    return {
      state: voice.state,
      isRecording: voice.isRecording,
      isConnected: false,
      isProcessing: voice.isProcessing,
      error: null,
      transcription: null,
      durationSeconds: null,
      startRecording: voice.startRecording,
      stopRecording: voice.stopRecording,
      isSupported: voice.isSupported,
    };
  },
}));

const voiceMode = vi.hoisted(() => ({ isEnabled: false }));

vi.mock('@/stores/voiceModeStore', () => ({
  useVoiceModeStore: (selector: (state: VoiceModeStore) => unknown) =>
    selector({
      isEnabled: voiceMode.isEnabled,
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

const upload = vi.hoisted(() => ({
  uploadFile: vi.fn<UploadHook['uploadFile']>(),
  removeFile: vi.fn(),
  clearAttachments: vi.fn(),
  getReadyAttachmentIds: vi.fn(),
  attachments: [] as PendingAttachment[],
  isUploading: false,
}));

vi.mock('@/hooks/useFileUpload', () => ({
  useFileUpload: (): UploadHook => ({
    attachments: upload.attachments,
    uploadFile: upload.uploadFile,
    removeFile: upload.removeFile,
    clearAttachments: upload.clearAttachments,
    getReadyAttachmentIds: upload.getReadyAttachmentIds,
    isUploading: upload.isUploading,
  }),
}));

const { toast } = vi.hoisted(() => ({ toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));

import { ChatInput } from '../ChatInput';

function attachment(over: Partial<PendingAttachment> = {}): PendingAttachment {
  return {
    tempId: 'tmp-1',
    attachmentId: 'att-1',
    filename: 'photo.png',
    mimeType: 'image/png',
    size: 1234,
    contentType: 'image',
    status: 'ready',
    progress: 100,
    ...over,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  voice.options = null;
  voice.isSupported = false;
  voice.isRecording = false;
  voice.isProcessing = false;
  voice.state = 'idle';
  voiceMode.isEnabled = false;
  upload.attachments = [];
  upload.isUploading = false;
  upload.uploadFile.mockResolvedValue({ success: true });
  upload.getReadyAttachmentIds.mockReturnValue([]);
});

/** File equality is opaque (two Files compare equal), so assert on names. */
function uploadedNames(): string[] {
  return upload.uploadFile.mock.calls.map(([file]) => file.name);
}

/** The hidden file input shares its accessible name with the paperclip button. */
function fileInput(): HTMLInputElement {
  const found = screen
    .getAllByLabelText('chat.attachments.add')
    .find((el): el is HTMLInputElement => el instanceof HTMLInputElement);
  if (!found) throw new Error('file input not found');
  return found;
}

describe('ChatInput — placeholder', () => {
  it('shows the normal placeholder when available', () => {
    renderWithProviders(<ChatInput onSendMessage={vi.fn()} />);
    expect(screen.getByPlaceholderText('chat.input.placeholder')).toBeInTheDocument();
  });

  it('shows the disabled placeholder when disabled', () => {
    renderWithProviders(<ChatInput onSendMessage={vi.fn()} disabled />);
    expect(screen.getByPlaceholderText('chat.input.placeholder_disabled')).toBeInTheDocument();
  });

  it('shows the unavailable placeholder when the API is down', () => {
    renderWithProviders(<ChatInput onSendMessage={vi.fn()} apiAvailable={false} />);
    expect(screen.getByPlaceholderText('chat.input.placeholder_unavailable')).toBeInTheDocument();
  });
});

describe('ChatInput — sending', () => {
  it('sends the trimmed message on Enter', async () => {
    const onSendMessage = vi.fn();
    const { user } = renderWithProviders(<ChatInput onSendMessage={onSendMessage} />);
    await user.type(screen.getByRole('textbox'), 'hello there{Enter}');
    expect(onSendMessage).toHaveBeenCalledWith('hello there', undefined, undefined, undefined);
  });

  it('clears the textarea after sending', async () => {
    const { user } = renderWithProviders(<ChatInput onSendMessage={vi.fn()} />);
    const box = screen.getByRole('textbox');
    await user.type(box, 'hello{Enter}');
    expect(box).toHaveValue('');
  });

  it('inserts a newline on Shift+Enter without sending', async () => {
    const onSendMessage = vi.fn();
    const { user } = renderWithProviders(<ChatInput onSendMessage={onSendMessage} />);
    const box = screen.getByRole('textbox');
    await user.type(box, 'line one{Shift>}{Enter}{/Shift}line two');
    expect(onSendMessage).not.toHaveBeenCalled();
    expect(box).toHaveValue('line one\nline two');
  });

  it('does not send an empty (whitespace-only) message', async () => {
    const onSendMessage = vi.fn();
    const { user } = renderWithProviders(<ChatInput onSendMessage={onSendMessage} />);
    await user.type(screen.getByRole('textbox'), '   {Enter}');
    expect(onSendMessage).not.toHaveBeenCalled();
  });

  it('does not send while disabled', async () => {
    const onSendMessage = vi.fn();
    const { user } = renderWithProviders(<ChatInput onSendMessage={onSendMessage} disabled />);
    await user.type(screen.getByRole('textbox'), 'hello{Enter}');
    expect(onSendMessage).not.toHaveBeenCalled();
  });

  it('does not send when the API is unavailable', async () => {
    const onSendMessage = vi.fn();
    const { user } = renderWithProviders(
      <ChatInput onSendMessage={onSendMessage} apiAvailable={false} />
    );
    await user.type(screen.getByRole('textbox'), 'hello{Enter}');
    expect(onSendMessage).not.toHaveBeenCalled();
  });

  it('sends through the send button once text is present', async () => {
    const onSendMessage = vi.fn();
    const { user } = renderWithProviders(<ChatInput onSendMessage={onSendMessage} />);
    await user.type(screen.getByRole('textbox'), 'hello');
    await user.click(screen.getByRole('button', { name: 'chat.input.send' }));
    expect(onSendMessage).toHaveBeenCalledWith('hello', undefined, undefined, undefined);
  });

  it('reports every keystroke to the parent, and the reset after sending', async () => {
    const onMessageChange = vi.fn();
    const { user } = renderWithProviders(
      <ChatInput onSendMessage={vi.fn()} onMessageChange={onMessageChange} />
    );
    await user.type(screen.getByRole('textbox'), 'hi{Enter}');
    expect(onMessageChange).toHaveBeenCalledWith('h');
    expect(onMessageChange).toHaveBeenCalledWith('hi');
    expect(onMessageChange).toHaveBeenLastCalledWith('');
  });

  it('prefills from initialMessage without sending (onboarding deep link)', () => {
    const onSendMessage = vi.fn();
    renderWithProviders(
      <ChatInput onSendMessage={onSendMessage} initialMessage="Trouve le contact Jean" />
    );

    expect(screen.getByRole('textbox')).toHaveValue('Trouve le contact Jean');
    expect(onSendMessage).not.toHaveBeenCalled();
  });

  it('prefilled text is editable and sendable like typed text', async () => {
    const onSendMessage = vi.fn();
    const { user } = renderWithProviders(
      <ChatInput onSendMessage={onSendMessage} initialMessage="Bonjour" />
    );

    await user.type(screen.getByRole('textbox'), ' LIA{Enter}');
    expect(onSendMessage).toHaveBeenCalledWith('Bonjour LIA', undefined, undefined, undefined);
  });
});

describe('ChatInput — generation in flight', () => {
  it('offers to stop the stream instead of sending', async () => {
    const onStopGeneration = vi.fn();
    const { user } = renderWithProviders(
      <ChatInput onSendMessage={vi.fn()} isGenerating onStopGeneration={onStopGeneration} />
    );
    expect(screen.queryByRole('button', { name: 'chat.input.send' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'chat.input.stop' }));
    expect(onStopGeneration).toHaveBeenCalledTimes(1);
  });

  it('keeps the send button when no stop handler is wired', () => {
    renderWithProviders(<ChatInput onSendMessage={vi.fn()} isGenerating />);
    expect(screen.queryByRole('button', { name: 'chat.input.stop' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'chat.voice.hold_to_speak' })).toBeInTheDocument();
  });
});

describe('ChatInput — attachments', () => {
  it('offers no way to attach a file until attachments are enabled', () => {
    renderWithProviders(<ChatInput onSendMessage={vi.fn()} />);
    // The file input itself is always mounted but unreachable — the paperclip
    // that opens it is what gates the feature.
    expect(screen.queryByRole('button', { name: 'chat.attachments.add' })).not.toBeInTheDocument();
  });

  it('uploads each picked file and lets the same file be picked again', async () => {
    const { user } = renderWithProviders(<ChatInput onSendMessage={vi.fn()} attachmentsEnabled />);
    const file = new File(['x'], 'photo.png', { type: 'image/png' });
    const input = fileInput();

    await user.upload(input, file);

    await waitFor(() => expect(upload.uploadFile).toHaveBeenCalledWith(file));
    // The input is reset so re-picking the same file still fires a change event.
    expect(input.value).toBe('');
  });

  it('locks the attach button while an upload is in flight', () => {
    upload.isUploading = true;
    renderWithProviders(<ChatInput onSendMessage={vi.fn()} attachmentsEnabled />);
    expect(screen.getByRole('button', { name: 'chat.attachments.add' })).toBeDisabled();
  });

  const REJECTIONS: Array<{ label: string; result: UploadResult; key: string }> = [
    {
      label: 'file_too_large',
      result: { error: 'file_too_large' },
      key: 'chat.attachments.file_too_large',
    },
    {
      label: 'type_not_allowed',
      result: { error: 'type_not_allowed' },
      key: 'chat.attachments.type_not_allowed',
    },
    {
      label: 'max_attachments',
      result: { error: 'max_attachments' },
      key: 'chat.attachments.max_attachments',
    },
    {
      label: 'upload_failed',
      result: { error: 'upload_failed' },
      key: 'chat.attachments.upload_error',
    },
  ];

  it.each(REJECTIONS)('explains a $label rejection', async ({ result, key }) => {
    upload.uploadFile.mockResolvedValue(result);
    const { user } = renderWithProviders(<ChatInput onSendMessage={vi.fn()} attachmentsEnabled />);
    await user.upload(fileInput(), new File(['x'], 'photo.png', { type: 'image/png' }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith(key));
  });

  it('forwards the ready attachment ids and their metadata, then clears them', async () => {
    upload.attachments = [attachment()];
    upload.getReadyAttachmentIds.mockReturnValue(['att-1']);
    const onSendMessage = vi.fn();
    const { user } = renderWithProviders(
      <ChatInput onSendMessage={onSendMessage} attachmentsEnabled />
    );

    await user.type(screen.getByRole('textbox'), 'look at this{Enter}');

    expect(onSendMessage).toHaveBeenCalledWith(
      'look at this',
      ['att-1'],
      [
        {
          id: 'att-1',
          filename: 'photo.png',
          mime_type: 'image/png',
          size: 1234,
          content_type: 'image',
        },
      ],
      undefined
    );
    expect(upload.clearAttachments).toHaveBeenCalledTimes(1);
  });

  it('ignores an attachment that is still uploading when building the metadata', async () => {
    upload.attachments = [attachment({ status: 'uploading', attachmentId: undefined })];
    upload.getReadyAttachmentIds.mockReturnValue(['att-1']);
    const onSendMessage = vi.fn();
    const { user } = renderWithProviders(
      <ChatInput onSendMessage={onSendMessage} attachmentsEnabled />
    );

    await user.type(screen.getByRole('textbox'), 'hello{Enter}');

    expect(onSendMessage).toHaveBeenCalledWith('hello', ['att-1'], [], undefined);
  });
});

describe('ChatInput — drag and drop', () => {
  function dropZone(container: HTMLElement): Element {
    const zone = container.querySelector('[role="presentation"]');
    if (!zone) throw new Error('drop zone not found');
    return zone;
  }

  const png = () => new File(['x'], 'photo.png', { type: 'image/png' });

  it('uploads the images and PDFs that were dropped, and only those', async () => {
    const { container } = renderWithProviders(
      <ChatInput onSendMessage={vi.fn()} attachmentsEnabled />
    );
    const image = png();
    const pdf = new File(['x'], 'doc.pdf', { type: 'application/pdf' });
    const binary = new File(['x'], 'setup.exe', { type: 'application/x-msdownload' });

    fireEvent.drop(dropZone(container), { dataTransfer: { files: [image, pdf, binary] } });

    await waitFor(() => expect(upload.uploadFile).toHaveBeenCalledTimes(2));
    expect(uploadedNames()).toEqual([image.name, pdf.name]);
    expect(uploadedNames()).not.toContain(binary.name);
  });

  it('refuses a drop when attachments are not enabled', async () => {
    const { container } = renderWithProviders(<ChatInput onSendMessage={vi.fn()} />);
    fireEvent.drop(dropZone(container), { dataTransfer: { files: [png()] } });
    await waitFor(() => expect(upload.uploadFile).not.toHaveBeenCalled());
  });

  it('refuses a drop while the composer is disabled', async () => {
    const { container } = renderWithProviders(
      <ChatInput onSendMessage={vi.fn()} attachmentsEnabled disabled />
    );
    fireEvent.drop(dropZone(container), { dataTransfer: { files: [png()] } });
    await waitFor(() => expect(upload.uploadFile).not.toHaveBeenCalled());
  });

  it('survives a drag that enters and leaves without dropping', () => {
    const { container } = renderWithProviders(
      <ChatInput onSendMessage={vi.fn()} attachmentsEnabled />
    );
    const zone = dropZone(container);
    fireEvent.dragEnter(zone);
    fireEvent.dragOver(zone);
    fireEvent.dragLeave(zone);
    expect(screen.getByRole('textbox')).toBeInTheDocument();
    expect(upload.uploadFile).not.toHaveBeenCalled();
  });
});

describe('ChatInput — push-to-talk', () => {
  beforeEach(() => {
    voice.isSupported = true;
  });

  it('offers to hold to speak while the draft is empty', () => {
    renderWithProviders(<ChatInput onSendMessage={vi.fn()} />);
    expect(screen.getByRole('button', { name: 'chat.voice.hold_to_speak' })).toBeInTheDocument();
  });

  it('records while the button is held, and stops on release', async () => {
    renderWithProviders(<ChatInput onSendMessage={vi.fn()} />);
    const button = screen.getByRole('button', { name: 'chat.voice.hold_to_speak' });

    fireEvent.mouseDown(button);
    await waitFor(() => expect(voice.startRecording).toHaveBeenCalledTimes(1));
    fireEvent.mouseUp(button);
    expect(voice.stopRecording).toHaveBeenCalledTimes(1);
  });

  it('stops arming the microphone as soon as there is text to send', async () => {
    const { user } = renderWithProviders(<ChatInput onSendMessage={vi.fn()} />);
    await user.type(screen.getByRole('textbox'), 'hello');

    const button = screen.getByRole('button', { name: 'chat.input.send' });
    fireEvent.mouseDown(button);
    await waitFor(() => expect(voice.startRecording).not.toHaveBeenCalled());
  });

  it('leaves the microphone to hands-free voice mode when it is active', async () => {
    voiceMode.isEnabled = true;
    renderWithProviders(<ChatInput onSendMessage={vi.fn()} />);
    // Voice mode owns the mic: the button is a plain (disabled, empty) send.
    const button = screen.getByRole('button', { name: 'chat.input.send' });
    fireEvent.mouseDown(button);
    await waitFor(() => expect(voice.startRecording).not.toHaveBeenCalled());
  });

  it('does not arm the microphone when the device does not support it', async () => {
    voice.isSupported = false;
    renderWithProviders(<ChatInput onSendMessage={vi.fn()} />);
    fireEvent.mouseDown(screen.getByRole('button', { name: 'chat.voice.hold_to_speak' }));
    await waitFor(() => expect(voice.startRecording).not.toHaveBeenCalled());
  });

  it('announces the recording state', () => {
    voice.isRecording = true;
    voice.state = 'recording';
    renderWithProviders(<ChatInput onSendMessage={vi.fn()} />);
    expect(screen.getByRole('button', { name: 'chat.voice.recording' })).toBeInTheDocument();
  });

  it('announces the processing state and locks the button', () => {
    voice.isProcessing = true;
    voice.state = 'processing';
    renderWithProviders(<ChatInput onSendMessage={vi.fn()} />);
    expect(screen.getByRole('button', { name: 'chat.voice.processing' })).toBeDisabled();
  });
});

describe('ChatInput — transcription', () => {
  /** Fires the transcription callback ChatInput handed to the voice hook. */
  function transcribe(text: string, meta?: { stt_provider?: string | null }) {
    act(() => {
      voice.options?.onTranscription?.(text, meta);
    });
  }

  it('fills the empty draft with the transcribed text', async () => {
    renderWithProviders(<ChatInput onSendMessage={vi.fn()} />);
    transcribe('bonjour LIA');
    await waitFor(() => expect(screen.getByRole('textbox')).toHaveValue('bonjour LIA'));
  });

  it('appends to an existing draft with a single separating space', async () => {
    const onMessageChange = vi.fn();
    const { user } = renderWithProviders(
      <ChatInput onSendMessage={vi.fn()} onMessageChange={onMessageChange} />
    );
    await user.type(screen.getByRole('textbox'), 'salut ');
    transcribe('LIA');

    await waitFor(() => expect(screen.getByRole('textbox')).toHaveValue('salut LIA'));
    await waitFor(() => expect(onMessageChange).toHaveBeenLastCalledWith('salut LIA'));
  });

  it('ignores an empty transcription', async () => {
    const { user } = renderWithProviders(<ChatInput onSendMessage={vi.fn()} />);
    await user.type(screen.getByRole('textbox'), 'salut');
    transcribe('   ');
    expect(screen.getByRole('textbox')).toHaveValue('salut');
  });

  it('carries the remote STT cost metadata to the next send, once', async () => {
    const onSendMessage = vi.fn();
    const { user } = renderWithProviders(<ChatInput onSendMessage={onSendMessage} />);
    act(() => {
      voice.options?.onTranscription?.('bonjour', {
        stt_provider: 'openai',
        stt_audio_duration_seconds: 2.5,
        stt_cost_usd: 0.001,
        stt_cost_eur: 0.0009,
      });
    });
    await waitFor(() => expect(screen.getByRole('textbox')).toHaveValue('bonjour'));

    await user.type(screen.getByRole('textbox'), '{Enter}');
    expect(onSendMessage).toHaveBeenLastCalledWith('bonjour', undefined, undefined, {
      stt_provider: 'openai',
      stt_audio_duration_seconds: 2.5,
      stt_cost_usd: 0.001,
      stt_cost_eur: 0.0009,
    });

    // The metadata belongs to that message only: a typed follow-up carries none.
    await user.type(screen.getByRole('textbox'), 'et ensuite ?{Enter}');
    expect(onSendMessage).toHaveBeenLastCalledWith('et ensuite ?', undefined, undefined, undefined);
  });

  it('leaves a local transcription without cost metadata', async () => {
    const onSendMessage = vi.fn();
    const { user } = renderWithProviders(<ChatInput onSendMessage={onSendMessage} />);
    transcribe('bonjour', { stt_provider: null });
    await waitFor(() => expect(screen.getByRole('textbox')).toHaveValue('bonjour'));

    await user.type(screen.getByRole('textbox'), '{Enter}');
    expect(onSendMessage).toHaveBeenCalledWith('bonjour', undefined, undefined, undefined);
  });
});

describe('ChatInput — voice errors', () => {
  it.each([
    ['permission denied by the user', 'chat.voice.error_permission'],
    ['Permission denied', 'chat.voice.error_permission'],
    ['recording is not supported here', 'chat.voice.error_not_supported'],
    ['ticket expired', 'chat.voice.error_connection'],
    ['socket exploded', 'chat.voice.error_generic'],
  ])('classifies "%s" into an actionable message', (message, key) => {
    renderWithProviders(<ChatInput onSendMessage={vi.fn()} />);
    act(() => {
      voice.options?.onError?.(new Error(message));
    });
    expect(toast.error).toHaveBeenCalledWith(key);
  });
});
