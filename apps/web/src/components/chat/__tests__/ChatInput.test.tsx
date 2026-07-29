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

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { renderWithProviders, screen, waitFor, fireEvent, act } from '@/__tests__/test-utils';
import { CHAT_INPUT_MAX_HEIGHT_PX } from '@/lib/constants';
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

describe('ChatInput — sent-history walk (UXR Lot 2 A7, extended QA 2026-07-23)', () => {
  const HISTORY = ['relance le serveur', 'météo demain', 'résume mes mails'] as const;

  it('recalls the last sent message on ArrowUp in an empty input', () => {
    const onMessageChange = vi.fn();
    renderWithProviders(
      <ChatInput onSendMessage={vi.fn()} onMessageChange={onMessageChange} sentHistory={HISTORY} />
    );
    const box = screen.getByRole('textbox');
    fireEvent.keyDown(box, { key: 'ArrowUp' });
    expect(box).toHaveValue('relance le serveur');
    expect(onMessageChange).toHaveBeenCalledWith('relance le serveur');
  });

  it('walks older on repeated ArrowUp and stops at the oldest entry', () => {
    renderWithProviders(<ChatInput onSendMessage={vi.fn()} sentHistory={HISTORY} />);
    const box = screen.getByRole('textbox');
    fireEvent.keyDown(box, { key: 'ArrowUp' });
    fireEvent.keyDown(box, { key: 'ArrowUp' });
    expect(box).toHaveValue('météo demain');
    fireEvent.keyDown(box, { key: 'ArrowUp' });
    fireEvent.keyDown(box, { key: 'ArrowUp' });
    fireEvent.keyDown(box, { key: 'ArrowUp' });
    expect(box).toHaveValue('résume mes mails');
  });

  it('walks back down with ArrowDown and lands on an empty input past the newest', () => {
    const onMessageChange = vi.fn();
    renderWithProviders(
      <ChatInput onSendMessage={vi.fn()} onMessageChange={onMessageChange} sentHistory={HISTORY} />
    );
    const box = screen.getByRole('textbox');
    fireEvent.keyDown(box, { key: 'ArrowUp' });
    fireEvent.keyDown(box, { key: 'ArrowUp' });
    fireEvent.keyDown(box, { key: 'ArrowDown' });
    expect(box).toHaveValue('relance le serveur');
    fireEvent.keyDown(box, { key: 'ArrowDown' });
    expect(box).toHaveValue('');
    expect(onMessageChange).toHaveBeenLastCalledWith('');
  });

  it('editing the recalled text ends the walk (arrows return to the caret)', async () => {
    const { user } = renderWithProviders(
      <ChatInput onSendMessage={vi.fn()} sentHistory={HISTORY} />
    );
    const box = screen.getByRole('textbox');
    fireEvent.keyDown(box, { key: 'ArrowUp' });
    await user.type(box, ' !');
    fireEvent.keyDown(box, { key: 'ArrowUp' });
    expect(box).toHaveValue('relance le serveur !');
    fireEvent.keyDown(box, { key: 'ArrowDown' });
    expect(box).toHaveValue('relance le serveur !');
  });

  it('never recalls while the input holds text (multi-line editing stays intact)', async () => {
    const { user } = renderWithProviders(
      <ChatInput onSendMessage={vi.fn()} sentHistory={['ancien message']} />
    );
    const box = screen.getByRole('textbox');
    await user.type(box, 'en cours');
    fireEvent.keyDown(box, { key: 'ArrowUp' });
    expect(box).toHaveValue('en cours');
  });

  it('ignores ArrowUp during IME composition', () => {
    renderWithProviders(<ChatInput onSendMessage={vi.fn()} sentHistory={['拼音']} />);
    const box = screen.getByRole('textbox');
    fireEvent.keyDown(box, { key: 'ArrowUp', isComposing: true });
    expect(box).toHaveValue('');
  });

  it('is inert without history', () => {
    renderWithProviders(<ChatInput onSendMessage={vi.fn()} />);
    const box = screen.getByRole('textbox');
    fireEvent.keyDown(box, { key: 'ArrowUp' });
    expect(box).toHaveValue('');
  });

  it('caps the textarea at the backend message limit', () => {
    renderWithProviders(<ChatInput onSendMessage={vi.fn()} />);
    expect(screen.getByRole('textbox')).toHaveAttribute('maxlength', '10000');
  });
});

describe('ChatInput — controlled prefill (UXR Lot 4, A2)', () => {
  it('replaces the content when the prefill nonce changes and notifies', () => {
    const onMessageChange = vi.fn();
    const { rerender } = renderWithProviders(
      <ChatInput
        onSendMessage={vi.fn()}
        onMessageChange={onMessageChange}
        prefill={{ text: '', nonce: 0 }}
      />
    );
    rerender(
      <ChatInput
        onSendMessage={vi.fn()}
        onMessageChange={onMessageChange}
        prefill={{ text: 'Montre la météo de demain', nonce: 1 }}
      />
    );
    expect(screen.getByRole('textbox')).toHaveValue('Montre la météo de demain');
    expect(onMessageChange).toHaveBeenCalledWith('Montre la météo de demain');
  });

  it('never applies the MOUNT nonce (a restored draft must survive)', () => {
    renderWithProviders(
      <ChatInput
        onSendMessage={vi.fn()}
        initialMessage="brouillon restauré"
        prefill={{ text: 'écrasement interdit', nonce: 5 }}
      />
    );
    expect(screen.getByRole('textbox')).toHaveValue('brouillon restauré');
  });

  it('does not reapply an unchanged nonce on unrelated rerenders', async () => {
    const { rerender, user } = renderWithProviders(
      <ChatInput onSendMessage={vi.fn()} prefill={{ text: 'chip', nonce: 1 }} />
    );
    const box = screen.getByRole('textbox');
    await user.clear(box);
    await user.type(box, 'édition manuelle');
    rerender(<ChatInput onSendMessage={vi.fn()} prefill={{ text: 'chip', nonce: 1 }} />);
    expect(box).toHaveValue('édition manuelle');
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
    // Voice is unsupported in this file's default mock, so the fallback is a
    // plain (empty, disabled) send button — never a push-to-talk invitation.
    expect(screen.getByRole('button', { name: 'chat.input.send' })).toBeInTheDocument();
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
      result: { error: 'file_too_large', maxMB: 10 },
      key: 'chat.attachments.file_too_large',
    },
    {
      label: 'type_not_allowed',
      result: { error: 'type_not_allowed' },
      key: 'chat.attachments.type_not_allowed',
    },
    {
      label: 'max_attachments',
      result: { error: 'max_attachments', max: 5 },
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

  it('never invites to speak when the device does not support it (UX P2)', async () => {
    voice.isSupported = false;
    renderWithProviders(<ChatInput onSendMessage={vi.fn()} />);
    // The button must read as what it is: a send button with nothing to send.
    expect(screen.queryByRole('button', { name: 'chat.voice.hold_to_speak' })).toBeNull();
    const button = screen.getByRole('button', { name: 'chat.input.send' });
    expect(button).toBeDisabled();
    fireEvent.mouseDown(button);
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

/** Mirrors the global setup mock, flipping only the reduced-motion query. */
function mockReducedMotion(matches: boolean): void {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: query === '(prefers-reduced-motion: reduce)' ? matches : false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
}

describe('ChatInput — send/push-to-talk button truth (UX P2)', () => {
  afterEach(() => mockReducedMotion(false));

  it('shows the microphone icon while the draft is empty and push-to-talk is offered', () => {
    voice.isSupported = true;
    const { container } = renderWithProviders(<ChatInput onSendMessage={vi.fn()} />);
    const button = screen.getByRole('button', { name: 'chat.voice.hold_to_speak' });
    expect(button).toBeEnabled();
    expect(container.querySelector('svg.lucide-mic')).toBeInTheDocument();
    expect(container.querySelector('svg.lucide-send')).toBeNull();
  });

  it('the visible desktop label matches the offered action', () => {
    voice.isSupported = true;
    renderWithProviders(<ChatInput onSendMessage={vi.fn()} />);
    const button = screen.getByRole('button', { name: 'chat.voice.hold_to_speak' });
    expect(button.textContent).toContain('chat.voice.hold_to_speak');
    expect(button.textContent).not.toContain('chat.input.send');
  });

  it('swaps to the send icon as soon as text is present', async () => {
    voice.isSupported = true;
    const { container, user } = renderWithProviders(<ChatInput onSendMessage={vi.fn()} />);
    await user.type(screen.getByRole('textbox'), 'hello');
    expect(container.querySelector('svg.lucide-send')).toBeInTheDocument();
    expect(container.querySelector('svg.lucide-mic')).toBeNull();
  });

  it('shows a plain disabled send button when voice input is unavailable', () => {
    voice.isSupported = false;
    const { container } = renderWithProviders(<ChatInput onSendMessage={vi.fn()} />);
    expect(screen.getByRole('button', { name: 'chat.input.send' })).toBeDisabled();
    expect(container.querySelector('svg.lucide-send')).toBeInTheDocument();
    expect(container.querySelector('svg.lucide-mic')).toBeNull();
  });

  it('shows a plain disabled send button while hands-free voice mode owns the mic', () => {
    voice.isSupported = true;
    voiceMode.isEnabled = true;
    const { container } = renderWithProviders(<ChatInput onSendMessage={vi.fn()} />);
    expect(screen.getByRole('button', { name: 'chat.input.send' })).toBeDisabled();
    expect(container.querySelector('svg.lucide-send')).toBeInTheDocument();
  });

  it('keeps the send icon through the takeoff animation, then yields to the mic', async () => {
    voice.isSupported = true;
    const { container, user } = renderWithProviders(<ChatInput onSendMessage={vi.fn()} />);
    await user.type(screen.getByRole('textbox'), 'hello{Enter}');

    // The input emptied, but the takeoff must finish on the SEND icon…
    expect(container.querySelector('svg.lucide-send')).toBeInTheDocument();
    expect(container.querySelector('svg.lucide-mic')).toBeNull();
    // …then the fallback timer releases it (jsdom never fires animationend —
    // the timer is the guaranteed path; SEND_TAKEOFF_RELEASE_MS = 700 ms).
    await waitFor(() => expect(container.querySelector('svg.lucide-mic')).toBeInTheDocument(), {
      timeout: 2000,
    });
    expect(container.querySelector('svg.lucide-send')).toBeNull();
  });

  it('skips the takeoff entirely under reduced motion', async () => {
    mockReducedMotion(true);
    voice.isSupported = true;
    const { container, user } = renderWithProviders(<ChatInput onSendMessage={vi.fn()} />);
    await user.type(screen.getByRole('textbox'), 'hello{Enter}');
    // No animation to wait for: the mic returns immediately.
    expect(container.querySelector('svg.lucide-mic')).toBeInTheDocument();
    expect(container.querySelector('svg.lucide-send')).toBeNull();
  });
});

describe('ChatInput — paste (UX P1)', () => {
  const pastedPng = () => new File(['x'], 'shot.png', { type: 'image/png' });

  /** Minimal clipboard shape the handler reads: files + text/plain. */
  function clipboard(files: File[], text = '') {
    return { clipboardData: { files, getData: vi.fn(() => text) } };
  }

  it('uploads a pasted screenshot and swallows the empty text insertion', async () => {
    renderWithProviders(<ChatInput onSendMessage={vi.fn()} attachmentsEnabled />);
    const proceeded = fireEvent.paste(screen.getByRole('textbox'), clipboard([pastedPng()]));

    await waitFor(() => expect(upload.uploadFile).toHaveBeenCalledTimes(1));
    expect(uploadedNames()).toEqual(['shot.png']);
    // preventDefault fired: nothing to insert, nothing must be inserted.
    expect(proceeded).toBe(false);
  });

  it('lets a plain text paste flow through natively', () => {
    renderWithProviders(<ChatInput onSendMessage={vi.fn()} attachmentsEnabled />);
    const proceeded = fireEvent.paste(screen.getByRole('textbox'), clipboard([], 'du texte'));
    expect(upload.uploadFile).not.toHaveBeenCalled();
    expect(proceeded).toBe(true);
  });

  it('uploads the files of a mixed paste AND lets the text land', async () => {
    renderWithProviders(<ChatInput onSendMessage={vi.fn()} attachmentsEnabled />);
    const proceeded = fireEvent.paste(
      screen.getByRole('textbox'),
      clipboard([pastedPng()], 'contexte copié avec la capture')
    );
    await waitFor(() => expect(upload.uploadFile).toHaveBeenCalledTimes(1));
    expect(proceeded).toBe(true);
  });

  it('keeps only images and PDFs from the clipboard files', async () => {
    renderWithProviders(<ChatInput onSendMessage={vi.fn()} attachmentsEnabled />);
    const pdfFile = new File(['x'], 'doc.pdf', { type: 'application/pdf' });
    const binary = new File(['x'], 'setup.exe', { type: 'application/x-msdownload' });
    fireEvent.paste(screen.getByRole('textbox'), clipboard([pdfFile, binary]));

    await waitFor(() => expect(upload.uploadFile).toHaveBeenCalledTimes(1));
    expect(uploadedNames()).toEqual(['doc.pdf']);
  });

  it('ignores pasted files while attachments are disabled', async () => {
    renderWithProviders(<ChatInput onSendMessage={vi.fn()} />);
    const proceeded = fireEvent.paste(screen.getByRole('textbox'), clipboard([pastedPng()]));
    await waitFor(() => expect(upload.uploadFile).not.toHaveBeenCalled());
    expect(proceeded).toBe(true);
  });

  it('ignores pasted files while the composer is disabled', async () => {
    renderWithProviders(<ChatInput onSendMessage={vi.fn()} attachmentsEnabled disabled />);
    fireEvent.paste(screen.getByRole('textbox'), clipboard([pastedPng()]));
    await waitFor(() => expect(upload.uploadFile).not.toHaveBeenCalled());
  });
});

describe('ChatInput — drop overlay (UX P13)', () => {
  function dropZone(container: HTMLElement): Element {
    const zone = container.querySelector('[role="presentation"]');
    if (!zone) throw new Error('drop zone not found');
    return zone;
  }

  it('surfaces the drop overlay while a drag hovers the composer, and clears it', () => {
    const { container } = renderWithProviders(
      <ChatInput onSendMessage={vi.fn()} attachmentsEnabled />
    );
    const zone = dropZone(container);
    fireEvent.dragEnter(zone);
    expect(screen.getByText('chat.attachments.drop_here')).toBeInTheDocument();
    fireEvent.dragLeave(zone);
    expect(screen.queryByText('chat.attachments.drop_here')).toBeNull();
  });

  it('clears the overlay once the files are dropped', async () => {
    const { container } = renderWithProviders(
      <ChatInput onSendMessage={vi.fn()} attachmentsEnabled />
    );
    const zone = dropZone(container);
    fireEvent.dragEnter(zone);
    fireEvent.drop(zone, {
      dataTransfer: { files: [new File(['x'], 'photo.png', { type: 'image/png' })] },
    });
    await waitFor(() => expect(upload.uploadFile).toHaveBeenCalledTimes(1));
    expect(screen.queryByText('chat.attachments.drop_here')).toBeNull();
  });

  it('never appears while attachments are disabled', () => {
    const { container } = renderWithProviders(<ChatInput onSendMessage={vi.fn()} />);
    fireEvent.dragEnter(dropZone(container));
    expect(screen.queryByText('chat.attachments.drop_here')).toBeNull();
  });
});

describe('ChatInput — auto-resize scrollbar discipline (UX P2)', () => {
  function setScrollHeight(el: Element, value: number): void {
    Object.defineProperty(el, 'scrollHeight', { value, configurable: true });
  }

  it('starts with the vertical scrollbar suppressed', () => {
    renderWithProviders(<ChatInput onSendMessage={vi.fn()} />);
    expect(screen.getByRole('textbox').className).toContain('overflow-y-hidden');
  });

  it('keeps the scrollbar hidden while growing under the height cap', async () => {
    const { user } = renderWithProviders(<ChatInput onSendMessage={vi.fn()} />);
    const box = screen.getByRole('textbox');
    setScrollHeight(box, CHAT_INPUT_MAX_HEIGHT_PX - 80);
    await user.type(box, 'hello');
    expect(box.style.height).toBe(`${CHAT_INPUT_MAX_HEIGHT_PX - 80}px`);
    expect(box.style.overflowY).toBe('hidden');
  });

  it('hands over to the scrollbar exactly at the height cap', async () => {
    const { user } = renderWithProviders(<ChatInput onSendMessage={vi.fn()} />);
    const box = screen.getByRole('textbox');
    setScrollHeight(box, CHAT_INPUT_MAX_HEIGHT_PX + 100);
    await user.type(box, 'hello');
    expect(box.style.height).toBe(`${CHAT_INPUT_MAX_HEIGHT_PX}px`);
    expect(box.style.overflowY).toBe('auto');
  });
});

describe('voice spotlight (N-13 — the ?voice=1 PWA shortcut)', () => {
  it('focuses the push-to-talk button when PTT is offered', () => {
    voice.isSupported = true;
    renderWithProviders(<ChatInput onSendMessage={vi.fn()} spotlightVoice />);

    const button = screen.getByRole('button', { name: 'chat.voice.hold_to_speak' });
    expect(button).toHaveFocus();
  });

  it('NEVER starts recording by itself — the hold gesture stays the user’s', () => {
    voice.isSupported = true;
    renderWithProviders(<ChatInput onSendMessage={vi.fn()} spotlightVoice />);
    expect(voice.startRecording).not.toHaveBeenCalled();
  });

  it('is a silent no-op when voice input is not supported', () => {
    voice.isSupported = false;
    renderWithProviders(<ChatInput onSendMessage={vi.fn()} spotlightVoice />);

    // The button stays a (disabled, unfocused) send button: no stolen focus.
    const button = screen.getByRole('button', { name: 'chat.input.send' });
    expect(button).not.toHaveFocus();
  });

  it('applies the one-shot spotlight class (a FINITE CSS animation — it dies on its own)', () => {
    voice.isSupported = true;
    renderWithProviders(<ChatInput onSendMessage={vi.fn()} spotlightVoice />);
    const button = screen.getByRole('button', { name: 'chat.voice.hold_to_speak' });
    // Applied imperatively (classList, not className), so React re-renders
    // can never re-arm the pulse; extinction is the animation's own end.
    expect(button.classList.contains('voice-ptt-spotlight')).toBe(true);
  });

  it('does not spotlight without the flag', () => {
    voice.isSupported = true;
    renderWithProviders(<ChatInput onSendMessage={vi.fn()} />);
    const button = screen.getByRole('button', { name: 'chat.voice.hold_to_speak' });
    expect(button).not.toHaveFocus();
    expect(button.classList.contains('voice-ptt-spotlight')).toBe(false);
  });
});
