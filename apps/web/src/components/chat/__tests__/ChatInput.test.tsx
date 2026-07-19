/**
 * ChatInput — the state-driven placeholder, Enter-to-send vs Shift+Enter
 * newline, the empty/disabled/unavailable guards.
 *
 * The voice, file-upload and voice-mode hooks are mocked to inert defaults so
 * the test drives the text-send path deterministically.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';

const { startRecording, stopRecording } = vi.hoisted(() => ({
  startRecording: vi.fn(),
  stopRecording: vi.fn(),
}));
vi.mock('@/hooks/useVoiceInput', () => ({
  useVoiceInput: () => ({
    state: 'idle',
    isRecording: false,
    isProcessing: false,
    startRecording,
    stopRecording,
    isSupported: false,
  }),
}));
vi.mock('@/stores/voiceModeStore', () => ({
  useVoiceModeStore: (sel: (s: { isEnabled: boolean }) => unknown) => sel({ isEnabled: false }),
}));
vi.mock('@/hooks/useFileUpload', () => ({
  useFileUpload: () => ({
    attachments: [],
    uploadFile: vi.fn(),
    removeFile: vi.fn(),
    clearAttachments: vi.fn(),
    getReadyAttachmentIds: () => [],
    isUploading: false,
  }),
}));
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

import { ChatInput } from '../ChatInput';

beforeEach(() => vi.clearAllMocks());

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
