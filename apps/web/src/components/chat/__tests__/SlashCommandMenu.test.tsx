/**
 * ChatInput × slash-command menu (UXR Lot 8, A4) — the full keyboard
 * contract: menu opens on '/', filters, ↑↓ navigate (A7 recall suppressed),
 * Enter selects WITHOUT sending, Escape keeps the text, a space closes,
 * conversational commands prefill and local commands delegate.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, fireEvent } from '@/__tests__/test-utils';
import type { SlashCommand } from '@/lib/slash-commands';

vi.mock('@/hooks/useVoiceInput', () => ({
  useVoiceInput: () => ({
    state: 'idle',
    isRecording: false,
    isConnected: false,
    isProcessing: false,
    error: null,
    transcription: null,
    durationSeconds: null,
    startRecording: vi.fn(),
    stopRecording: vi.fn(),
    isSupported: false,
  }),
}));
vi.mock('@/stores/voiceModeStore', () => ({
  useVoiceModeStore: (selector: (s: { isEnabled: boolean }) => unknown) =>
    selector({ isEnabled: false }),
}));
vi.mock('@/hooks/useFileUpload', () => ({
  useFileUpload: () => ({
    attachments: [],
    uploadFile: vi.fn(),
    removeFile: vi.fn(),
    clearAttachments: vi.fn(),
    getReadyAttachmentIds: vi.fn(() => []),
    isUploading: false,
  }),
}));
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

import { ChatInput } from '../ChatInput';

const COMMANDS: SlashCommand[] = [
  {
    id: 'resume',
    kind: 'conversational',
    label: 'resume',
    description: 'compact',
    insertText: '/resume',
  },
  { id: 'briefing', kind: 'local', label: 'briefing', description: 'open' },
  {
    id: 'agenda',
    kind: 'conversational',
    label: 'agenda',
    description: 'ask',
    insertText: 'Mon agenda ?',
  },
];

const onSendMessage = vi.fn();
const onLocalCommand = vi.fn();

beforeEach(() => vi.clearAllMocks());

function renderInput(extra: Record<string, unknown> = {}) {
  return renderWithProviders(
    <ChatInput
      onSendMessage={onSendMessage}
      slashCommands={COMMANDS}
      onLocalCommand={onLocalCommand}
      sentHistory={['dernier message']}
      {...extra}
    />
  );
}

const box = () => screen.getByRole('textbox');
const type = (value: string) => fireEvent.change(box(), { target: { value } });

describe('ChatInput — slash menu', () => {
  it('opens on "/" and filters while typing', () => {
    renderInput();
    type('/');
    expect(screen.getByRole('listbox')).toBeInTheDocument();
    expect(screen.getAllByRole('option')).toHaveLength(3);
    type('/br');
    expect(screen.getAllByRole('option')).toHaveLength(1);
  });

  it('closes when the token ends (space) and on zero matches', () => {
    renderInput();
    type('/resume extra');
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    type('/zzz');
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });

  it('Enter selects the active option WITHOUT sending', () => {
    renderInput();
    type('/res');
    fireEvent.keyDown(box(), { key: 'Enter' });
    expect(onSendMessage).not.toHaveBeenCalled();
    expect(box()).toHaveValue('/resume'); // conversational prefill (3a)
  });

  it('navigates with arrows — the A7 recall never fires while open', () => {
    renderInput();
    type('/');
    fireEvent.keyDown(box(), { key: 'ArrowDown' });
    fireEvent.keyDown(box(), { key: 'Enter' });
    // Second option (briefing, local) → delegate + clear, never the recall.
    expect(onLocalCommand).toHaveBeenCalledWith('briefing');
    expect(box()).toHaveValue('');
    expect(box()).not.toHaveValue('dernier message');
  });

  it('re-filtering resets the highlight to the first option', () => {
    renderInput();
    type('/');
    // Highlight the LAST option (agenda), then type "r": the filtered list
    // is [resume, briefing] — the highlight must return to its FIRST entry
    // (resume), not clamp onto a leftover position (briefing).
    fireEvent.keyDown(box(), { key: 'ArrowDown' });
    fireEvent.keyDown(box(), { key: 'ArrowDown' });
    type('/r');
    fireEvent.keyDown(box(), { key: 'Enter' });
    expect(box()).toHaveValue('/resume');
    expect(onLocalCommand).not.toHaveBeenCalled();
  });

  it('Escape closes keeping the text; the menu stays closed for that value', () => {
    renderInput();
    type('/age');
    fireEvent.keyDown(box(), { key: 'Escape' });
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    expect(box()).toHaveValue('/age');
    // Typing again re-opens.
    type('/agen');
    expect(screen.getByRole('listbox')).toBeInTheDocument();
  });

  it('mouse selection lands before blur (onMouseDown)', () => {
    renderInput();
    type('/');
    fireEvent.mouseDown(screen.getAllByRole('option')[2]);
    expect(box()).toHaveValue('Mon agenda ?');
    expect(onSendMessage).not.toHaveBeenCalled();
  });

  it('exposes the popup contract on the native textbox (a11y)', () => {
    // ARIA 1.1-style wiring: the textarea KEEPS its native textbox role (a
    // permanent combobox role would misdescribe the composer to assistive
    // tech; jsx-a11y also rejects aria-expanded on textbox) — the popup is
    // announced through aria-controls + aria-activedescendant while open.
    renderInput();
    type('/');
    expect(box()).toHaveAttribute('aria-autocomplete', 'list');
    expect(box()).toHaveAttribute('aria-controls', 'slash-command-listbox');
    expect(box().getAttribute('aria-activedescendant')).toMatch(/slash-option-0/);
    type('hello');
    // Closed menu: BOTH popup references must vanish — aria-controls pointing
    // at an unmounted listbox is an axe critical (aria-valid-attr-value).
    expect(box().getAttribute('aria-activedescendant')).toBeNull();
    expect(box().getAttribute('aria-controls')).toBeNull();
  });
});
