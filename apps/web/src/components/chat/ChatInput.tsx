import {
  useState,
  useRef,
  useCallback,
  useEffect,
  ClipboardEvent,
  KeyboardEvent,
  FormEvent,
  DragEvent,
} from 'react';
import { Button } from '@/components/ui/button';
import { Tooltip, TooltipTrigger, TooltipContent } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import { haptic } from '@/lib/haptics';
import { Send, Mic, Plus, Square, ImageUp } from 'lucide-react';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { useVoiceInput } from '@/hooks/useVoiceInput';
import { useVoiceModeStore } from '@/stores/voiceModeStore';
import { useFileUpload } from '@/hooks/useFileUpload';
import {
  CHAT_INPUT_MAX_HEIGHT_PX,
  CHAT_INPUT_MAX_LENGTH,
  SEND_TAKEOFF_RELEASE_MS,
  VOICE_PTT_TOUCH_PADDING_PX,
} from '@/lib/constants';
import { prefersReducedMotion } from '@/lib/utils/motion';
import AttachmentPreview from '@/components/chat/AttachmentPreview';
import { SlashCommandMenu, useSlashMenu } from '@/components/chat/SlashCommandMenu';
import type { SlashCommand } from '@/lib/slash-commands';
import { MessageAttachmentMeta } from '@/types/chat';
import { useMeetingRecorderContext } from '@/components/meetings/MeetingRecorderProvider';

/** Attachment metadata passed alongside IDs for immediate local display. */
export type SendAttachmentMeta = MessageAttachmentMeta;

/**
 * Per-message remote-STT cost metadata. Optionally captured from the voice
 * WebSocket and forwarded to ``onSendMessage`` so the persistence layer can
 * attach the precise cost to the user bubble.
 */
export interface SendSttMeta {
  stt_provider?: string | null;
  stt_audio_duration_seconds?: number | null;
  stt_cost_usd?: number | null;
  stt_cost_eur?: number | null;
}

export interface ChatInputProps {
  onSendMessage: (
    content: string,
    attachmentIds?: string[],
    attachmentsMeta?: SendAttachmentMeta[],
    sttMeta?: SendSttMeta
  ) => void;
  disabled?: boolean;
  isConnected?: boolean;
  apiAvailable?: boolean;
  className?: string;
  /** Called when message text changes (for geolocation prompt detection) */
  onMessageChange?: (message: string) => void;
  /** Whether attachments feature is enabled */
  attachmentsEnabled?: boolean;
  /**
   * ADR-258: the instance offers meeting recording. The composer only needs
   * it to keep hold-to-talk off the table while a meeting is being captured;
   * the recording controls live in the header and the logo menu (ADR-259).
   */
  meetingsEnabled?: boolean;
  /**
   * ADR-117 Lot 3: true while a response is streaming — with
   * onStopGeneration provided, the send button morphs into a stop button.
   * Distinct from `disabled` (usage-block must NOT offer a stop).
   */
  isGenerating?: boolean;
  /** ADR-117 Lot 3: stop-button handler (cancels the in-flight run). */
  onStopGeneration?: () => void;
  /**
   * Prefill the input on mount (onboarding volet B: `?draft=` deep link,
   * UXR Lot 2: persisted draft). Initializer only — later changes to this
   * prop are intentionally ignored (the user owns the text once the input is
   * mounted). Never auto-sent.
   */
  initialMessage?: string;
  /**
   * Past sent messages, NEWEST FIRST (UXR Lot 2 A7, extended per QA feedback
   * 2026-07-23): ArrowUp in an EMPTY input starts walking the history;
   * further ArrowUp goes older, ArrowDown comes back and lands on an empty
   * input past the newest entry. Editing the recalled text ends the walk
   * (arrows go back to caret movement). Never fires mid-edit from scratch
   * nor during IME composition. The page caps this at CHAT_SENT_HISTORY_MAX.
   */
  sentHistory?: readonly string[];
  /**
   * UXR Lot 4 (A2): controlled prefill — the documented EXCEPTION to the
   * initializer-only `initialMessage` contract. When `nonce` CHANGES, the
   * text REPLACES the input content (an explicit user action — a follow-up
   * chip click), the textarea is focused with the caret at the end, and
   * `onMessageChange` fires (draft persistence rides along). Never auto-sent.
   */
  prefill?: { text: string; nonce: number };
  /**
   * UXR Lot 8 (A4): slash-command registry (localized by the page). `/` at
   * the start of an empty input opens the filtering menu; conversational
   * commands PREFILL, local commands fire `onLocalCommand` — nothing is
   * ever auto-sent.
   */
  slashCommands?: readonly SlashCommand[];
  /** UXR Lot 8 (A4): local command handler (navigation, open search…). */
  onLocalCommand?: (commandId: string) => void;
  /**
   * N-13: the `?voice=1` PWA shortcut landed here — draw the eye (and the
   * focus) to the push-to-talk button once, WITHOUT recording: PTT is a HOLD
   * gesture and the mic permission must follow a real user press. No-op when
   * PTT is not offered (text present, voice unsupported/disabled, blocked).
   */
  spotlightVoice?: boolean;
}

/** Initial textarea value (module-level: keeps the component's CC flat). */
function initialDraft(initialMessage: string | undefined): string {
  return initialMessage ?? '';
}

/**
 * N-13 one-shot voice spotlight (module-level hook — CC discipline). Waits
 * until PTT is actually offered (voiceSupported can settle async after
 * mount), then focuses the button and pulses it via a FINITE CSS animation —
 * applied imperatively (an effect synchronizing the DOM, no state), it
 * extinguishes by itself and the class stays inert afterwards. Consumed
 * once — a later mode flip must not re-trigger it. Never records: the HOLD
 * gesture stays the user's.
 */
function useVoiceSpotlight(
  spotlightVoice: boolean | undefined,
  pttOffered: boolean,
  buttonRef: React.RefObject<HTMLButtonElement | null>
): void {
  const consumedRef = useRef(false);
  useEffect(() => {
    if (!spotlightVoice || consumedRef.current || !pttOffered) return;
    const button = buttonRef.current;
    if (!button) return;
    consumedRef.current = true;
    button.focus();
    button.classList.add('voice-ptt-spotlight');
  }, [spotlightVoice, pttOffered, buttonRef]);
}

/** Stable empty history (a per-render `?? []` would defeat memoization). */
const EMPTY_SENT_HISTORY: readonly string[] = [];

/**
 * The composer accepts what the upload pipeline accepts: images and PDFs.
 * Single filter for the two OS entry points (drop and clipboard paste).
 */
function acceptedFiles(list: ArrayLike<File>): File[] {
  return Array.from(list).filter(
    file => file.type.startsWith('image/') || file.type === 'application/pdf'
  );
}

/**
 * Pure (CC discipline): could a press START push-to-talk right now? Mirrors
 * the `handlePressStart` guard — the button must LOOK like what a press
 * would DO (UX P2), so offering and starting share one predicate shape.
 */
function isPttOffered(args: {
  hasMessage: boolean;
  isProcessing: boolean;
  voiceSupported: boolean;
  voiceModeEnabled: boolean;
  /** ADR-258: the microphone is busy recording a meeting. */
  meetingRecording: boolean;
  disabled: boolean;
  apiAvailable: boolean;
}): boolean {
  return (
    !args.hasMessage &&
    !args.isProcessing &&
    args.voiceSupported &&
    !args.voiceModeEnabled &&
    !args.meetingRecording &&
    !args.disabled &&
    args.apiAvailable
  );
}

/**
 * Pure (CC discipline): the single state-true label of the send/PTT button —
 * used for BOTH the aria-label and the visible desktop text, so the two can
 * never diverge again (the pre-P2 bug was exactly that divergence).
 */
function composerButtonLabel(
  t: (key: string) => string,
  args: { isRecording: boolean; isProcessing: boolean; showSendMode: boolean }
): string {
  if (args.isRecording) return t('chat.voice.recording');
  if (args.isProcessing) return t('chat.voice.processing');
  return t(args.showSendMode ? 'chat.input.send' : 'chat.voice.hold_to_speak');
}

/**
 * Icon truth of the send/PTT button (UX P2), extracted from the render
 * hotspot (CC discipline): mic whenever the press would talk, send whenever
 * the press would send — `animating` keeps the send icon mounted through its
 * takeoff.
 */
function ComposerButtonIcon({
  showMic,
  dimmed,
  animating,
  onTakeoffEnd,
}: {
  showMic: boolean;
  dimmed: boolean;
  animating: boolean;
  onTakeoffEnd: () => void;
}) {
  if (showMic) return <Mic className="h-4 w-4" />;
  return (
    <Send
      onAnimationEnd={onTakeoffEnd}
      className={cn(
        'h-4 w-4 transition-opacity',
        dimmed && 'opacity-30',
        animating && 'animate-send-takeoff'
      )}
    />
  );
}

/**
 * Controlled prefill (UXR Lot 4, A2) — module-level hook so every branch
 * lives OUTSIDE the component (CC discipline). Applies the text via the
 * React-endorsed "adjust state during render" pattern (never a setState in
 * an effect — react-hooks ratchet); the notify/focus side effects run in a
 * setState-free effect. The MOUNT nonce is swallowed: a restored draft must
 * never be overwritten at mount.
 */
function useControlledPrefill(args: {
  prefill: { text: string; nonce: number } | undefined;
  setMessage: (value: string) => void;
  onMessageChange: ((value: string) => void) | undefined;
  textareaRef: React.RefObject<HTMLTextAreaElement | null>;
  handleInput: () => void;
}): void {
  const { prefill, setMessage, onMessageChange, textareaRef, handleInput } = args;
  const [appliedNonce, setAppliedNonce] = useState(prefill?.nonce);
  if (prefill && prefill.nonce !== appliedNonce) {
    // Render-phase adjustment of own state — commits before paint.
    setAppliedNonce(prefill.nonce);
    setMessage(prefill.text);
  }

  const notifiedNonceRef = useRef(prefill?.nonce);
  useEffect(() => {
    if (!prefill || prefill.nonce === notifiedNonceRef.current) return;
    notifiedNonceRef.current = prefill.nonce;
    onMessageChange?.(prefill.text);
    requestAnimationFrame(() => {
      const textarea = textareaRef.current;
      if (textarea) {
        textarea.focus();
        textarea.selectionStart = textarea.selectionEnd = textarea.value.length;
      }
      handleInput();
    });
  }, [prefill, onMessageChange, textareaRef, handleInput]);
}

/**
 * ↑/↓ walk through past sent messages (UXR A7 extended, QA 2026-07-23) —
 * module-level hook so every branch lives OUTSIDE the component (CC
 * discipline). Shell semantics with one invariant: `index` is only valid
 * while the input still shows `history[index]` verbatim. The moment the
 * user edits (or sends — the input empties), the render-phase adjustment
 * below resets the walk and the arrow keys return to native caret moves.
 * Returns a keydown handler: true = event consumed.
 */
function useSentHistoryNavigation(args: {
  history: readonly string[] | undefined;
  message: string;
  setMessage: (value: string) => void;
  onMessageChange: ((value: string) => void) | undefined;
  textareaRef: React.RefObject<HTMLTextAreaElement | null>;
  handleInput: () => void;
}): (e: KeyboardEvent<HTMLTextAreaElement>) => boolean {
  const { message, setMessage, onMessageChange, textareaRef, handleInput } = args;
  const history = args.history ?? EMPTY_SENT_HISTORY;
  const [index, setIndex] = useState(-1);
  if (index !== -1 && message !== history[index]) {
    // Render-phase adjustment of own state — the walk died (edit or send).
    setIndex(-1);
  }

  return useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>): boolean => {
      if (history.length === 0 || e.nativeEvent.isComposing) return false;
      const walking = index !== -1 && message === history[index];

      const applyEntry = (nextIndex: number): boolean => {
        e.preventDefault();
        const text = nextIndex === -1 ? '' : history[nextIndex];
        setIndex(nextIndex);
        setMessage(text);
        onMessageChange?.(text);
        requestAnimationFrame(() => {
          const textarea = textareaRef.current;
          if (textarea) {
            textarea.selectionStart = textarea.selectionEnd = textarea.value.length;
          }
          handleInput();
        });
        return true;
      };

      if (e.key === 'ArrowUp') {
        if (!walking) {
          // Entry point: only from a pristine EMPTY input (multi-line
          // editing keeps its native caret behavior).
          return message === '' ? applyEntry(0) : false;
        }
        if (index < history.length - 1) return applyEntry(index + 1);
        // At the oldest entry: swallow so the caret doesn't jump to 0.
        e.preventDefault();
        return true;
      }
      if (e.key === 'ArrowDown' && walking) {
        // index 0 → back to the empty input ("past the newest send").
        return applyEntry(index - 1);
      }
      return false;
    },
    [history, index, message, setMessage, onMessageChange, textareaRef, handleInput]
  );
}

/**
 * The composer's « + » (module-level — CC discipline): the file picker, and
 * only that (ADR-259 — recording moved to the header, the logo menu and the
 * Meetings page). Nothing when attachments are off.
 *
 * A « + » rather than a paperclip (kept from ADR-258): square and narrow —
 * 44 px wide on a phone, the comfortable touch minimum, 40 px once the row is
 * wider than `mobile` — so the typing area keeps the width (owner arbitration
 * 2026-09-03).
 */
const COMPOSER_ACTION_BUTTON = 'h-12 w-11 shrink-0 self-end p-0 mobile:w-10';

function ComposerAttachmentsControl({
  t,
  attachmentsEnabled,
  disabled,
  onPickFile,
}: {
  t: (key: string) => string;
  attachmentsEnabled: boolean;
  disabled: boolean;
  onPickFile: () => void;
}) {
  if (!attachmentsEnabled) return null;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="lg"
          className={COMPOSER_ACTION_BUTTON}
          disabled={disabled}
          onClick={onPickFile}
          aria-label={t('chat.attachments.add')}
        >
          <Plus className="h-5 w-5" aria-hidden="true" />
        </Button>
      </TooltipTrigger>
      <TooltipContent>{t('chat.attachments.add')}</TooltipContent>
    </Tooltip>
  );
}

/**
 * ADR-258 (module-level hook — CC discipline): the two microphone owners
 * (voice mode, meeting capture) folded into ONE predicate, so the hold-to-talk
 * guard keeps a single condition. `null` context (outside the dashboard
 * provider) reads as "no meeting".
 */
function useComposerRecorder(
  meetingsEnabled: boolean,
  voiceModeEnabled: boolean
): {
  meetingRecording: boolean;
  pttBlocked: boolean;
} {
  const context = useMeetingRecorderContext();
  const meetingRecording = meetingsEnabled && (context?.isCapturing ?? false);
  return { meetingRecording, pttBlocked: voiceModeEnabled || meetingRecording };
}

export const ChatInput: React.FC<ChatInputProps> = ({
  onSendMessage,
  disabled = false,
  isConnected: _isConnected = true,
  apiAvailable = true,
  className,
  onMessageChange,
  attachmentsEnabled = false,
  meetingsEnabled = false,
  isGenerating = false,
  onStopGeneration,
  initialMessage,
  sentHistory,
  prefill,
  slashCommands,
  onLocalCommand,
  spotlightVoice,
}) => {
  const { t } = useTranslation();
  const [message, setMessage] = useState(initialDraft(initialMessage));
  // Holds the remote-STT cost metadata of the latest transcription that fed
  // the input. Cleared once the message is actually sent, or when the user
  // wipes the input. Stays NULL for text-only typed messages and for local
  // (Sherpa) transcriptions.
  const [pendingSttMeta, setPendingSttMeta] = useState<SendSttMeta | null>(null);
  // One-shot takeoff animation on the send icon (micro-interactions batch I3).
  // While true, the send icon stays mounted even though the emptied input
  // would otherwise swap it for the mic (UX P2).
  const [justSent, setJustSent] = useState(false);

  // Fallback release of the takeoff state: `onAnimationEnd` is the nominal
  // path, but if the keyframe never runs (hidden tab, motion preference
  // flipped mid-flight) the send icon must not stay stuck in mic territory.
  useEffect(() => {
    if (!justSent) return;
    const timer = window.setTimeout(() => setJustSent(false), SEND_TAKEOFF_RELEASE_MS);
    return () => window.clearTimeout(timer);
  }, [justSent]);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const {
    attachments,
    uploadFile,
    removeFile,
    clearAttachments,
    getReadyAttachmentIds,
    isUploading,
  } = useFileUpload();
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Check if voice mode (active listening) is enabled - disable push-to-talk when active
  const voiceModeEnabled = useVoiceModeStore(s => s.isEnabled);
  // ADR-258: a meeting being captured keeps hold-to-talk off the table.
  const { meetingRecording, pttBlocked } = useComposerRecorder(meetingsEnabled, voiceModeEnabled);

  // Auto-resize the textarea. The vertical scrollbar exists only once the
  // height cap freezes growth (UX P2) — below it, the box grows and any
  // transient overflow (fractional DPI rounding, pre-resize keystroke) must
  // not flash a scrollbar.
  const handleInput = useCallback(() => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = 'auto';
      textarea.style.height = `${Math.min(textarea.scrollHeight, CHAT_INPUT_MAX_HEIGHT_PX)}px`;
      textarea.style.overflowY =
        textarea.scrollHeight > CHAT_INPUT_MAX_HEIGHT_PX ? 'auto' : 'hidden';
    }
  }, []);

  // UXR Lot 4 (A2): controlled prefill — all logic in the module-level hook.
  useControlledPrefill({ prefill, setMessage, onMessageChange, textareaRef, handleInput });

  // UXR A7 extended (QA 2026-07-23): ↑/↓ history walk over past sends.
  const handleHistoryKey = useSentHistoryNavigation({
    history: sentHistory,
    message,
    setMessage,
    onMessageChange,
    textareaRef,
    handleInput,
  });

  // UXR Lot 8 (A4): slash-command selection — conversational commands prefill
  // (caret at end, focused), local commands clear + delegate to the page.
  const applySlashSelection = useCallback(
    (command: SlashCommand) => {
      if (command.kind === 'local') {
        setMessage('');
        onMessageChange?.('');
        onLocalCommand?.(command.id);
        return;
      }
      const text = command.insertText ?? '';
      setMessage(text);
      onMessageChange?.(text);
      requestAnimationFrame(() => {
        const textarea = textareaRef.current;
        if (textarea) {
          textarea.focus();
          textarea.selectionStart = textarea.selectionEnd = textarea.value.length;
        }
        handleInput();
      });
    },
    [onMessageChange, onLocalCommand, handleInput]
  );
  const slashMenu = useSlashMenu({
    message,
    commands: slashCommands,
    onSelect: applySlashSelection,
  });

  /**
   * Handle voice transcription result.
   * Puts transcribed text into the message input.
   */
  const handleVoiceTranscription = useCallback(
    (text: string, meta?: import('@/lib/voice-input-service').VoiceTranscriptionMeta) => {
      if (!text.trim()) return;

      // Capture STT cost metadata for the next send. Only meaningful when
      // the backend used a remote provider (``stt_provider`` set). For local
      // Sherpa transcriptions the meta is None and we keep the previous
      // pending state untouched (it may carry an earlier remote chunk).
      if (meta?.stt_provider) {
        setPendingSttMeta({
          stt_provider: meta.stt_provider ?? null,
          stt_audio_duration_seconds: meta.stt_audio_duration_seconds ?? null,
          stt_cost_usd: meta.stt_cost_usd ?? null,
          stt_cost_eur: meta.stt_cost_eur ?? null,
        });
      }

      // Append to existing message with space separator
      // Note: We need to compute the new message and update both states separately
      // to avoid calling parent setState inside our own setState callback
      // (which causes "Cannot update component while rendering" error in React 19)
      setMessage(prev => {
        const newMessage = prev.trim() ? `${prev.trim()} ${text}` : text;
        // Schedule parent state update for next tick to avoid render conflict
        queueMicrotask(() => {
          onMessageChange?.(newMessage);
        });
        // Trigger resize after state update
        requestAnimationFrame(() => handleInput());
        return newMessage;
      });
    },
    [onMessageChange, handleInput]
  );

  /**
   * Get user-friendly error message.
   */
  const getErrorMessage = useCallback(
    (err: Error): string => {
      if (err.message.includes('permission denied') || err.message.includes('Permission denied')) {
        return t('chat.voice.error_permission');
      }
      if (err.message.includes('not supported')) {
        return t('chat.voice.error_not_supported');
      }
      if (err.message.includes('ticket')) {
        return t('chat.voice.error_connection');
      }
      return t('chat.voice.error_generic');
    },
    [t]
  );

  // Voice input hook for push-to-talk
  const {
    state: voiceState,
    isRecording,
    isProcessing,
    startRecording,
    stopRecording,
    isSupported: voiceSupported,
  } = useVoiceInput({
    onTranscription: handleVoiceTranscription,
    onError: err => {
      toast.error(getErrorMessage(err));
    },
  });

  const handleSend = () => {
    const trimmedMessage = message.trim();
    if (trimmedMessage && !disabled && apiAvailable) {
      const readyIds = getReadyAttachmentIds();
      // Build attachment metadata for immediate thumbnail display in user message.
      // Note: previewUrl (Object URL) is NOT passed because clearAttachments() revokes
      // them immediately after send. The API URL works fine since files are already uploaded.
      const readyMeta: SendAttachmentMeta[] | undefined =
        readyIds.length > 0
          ? attachments
              .filter(a => a.status === 'ready' && a.attachmentId)
              .map(a => ({
                id: a.attachmentId!,
                filename: a.filename,
                mime_type: a.mimeType,
                size: a.size,
                content_type: a.contentType,
              }))
          : undefined;
      onSendMessage(
        trimmedMessage,
        readyIds.length > 0 ? readyIds : undefined,
        readyMeta,
        pendingSttMeta ?? undefined
      );
      // Under reduced motion the takeoff keyframe is dead (`animation: none`),
      // so `onAnimationEnd` would never fire and the send icon would stay
      // stuck in place of the mic — never arm it there.
      if (!prefersReducedMotion()) setJustSent(true);
      setMessage('');
      setPendingSttMeta(null);
      onMessageChange?.('');
      clearAttachments();
      // Reset textarea height and remove focus (reset iOS zoom)
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto';
        textareaRef.current.style.overflowY = 'hidden';
        textareaRef.current.blur();
      }
    }
  };

  // Shared upload handler with error toasts. The size/count rejections carry
  // the limit that actually applied (image and document caps differ), so the
  // toast never claims a wrong number.
  const processFiles = useCallback(
    async (files: File[]) => {
      for (const file of files) {
        const result = await uploadFile(file);
        if (result && 'error' in result) {
          switch (result.error) {
            case 'file_too_large':
              toast.error(t('chat.attachments.file_too_large', { max: result.maxMB }));
              break;
            case 'type_not_allowed':
              toast.error(t('chat.attachments.type_not_allowed'));
              break;
            case 'max_attachments':
              toast.error(t('chat.attachments.max_attachments', { max: result.max }));
              break;
            case 'upload_failed':
              toast.error(t('chat.attachments.upload_error'));
              break;
          }
        }
      }
    },
    [uploadFile, t]
  );

  // UX P1: a screenshot (or copied file) in the clipboard goes through the
  // exact same pipeline as picking or dropping it. preventDefault ONLY when
  // the clipboard carries no text: a mixed paste keeps its native text
  // insertion while the files upload alongside.
  const handlePaste = useCallback(
    (e: ClipboardEvent<HTMLTextAreaElement>) => {
      if (!attachmentsEnabled || disabled || !apiAvailable) return;
      const files = acceptedFiles(e.clipboardData?.files ?? []);
      if (files.length === 0) return;
      if (e.clipboardData.getData('text/plain').length === 0) {
        e.preventDefault();
      }
      void processFiles(files);
    },
    [attachmentsEnabled, disabled, apiAvailable, processFiles]
  );

  // File selection handler (input[type=file])
  const handleFileSelect = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      if (e.target.files) {
        await processFiles(Array.from(e.target.files));
      }
      e.target.value = '';
    },
    [processFiles]
  );

  // Drag & drop state and handlers
  const [isDragOver, setIsDragOver] = useState(false);
  const dragCounterRef = useRef(0);

  const handleDragEnter = useCallback(
    (e: DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      if (!attachmentsEnabled || disabled || !apiAvailable) return;
      dragCounterRef.current += 1;
      if (dragCounterRef.current === 1) setIsDragOver(true);
    },
    [attachmentsEnabled, disabled, apiAvailable]
  );

  const handleDragLeave = useCallback((e: DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounterRef.current -= 1;
    if (dragCounterRef.current === 0) setIsDragOver(false);
  }, []);

  const handleDragOver = useCallback((e: DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  }, []);

  const handleDrop = useCallback(
    async (e: DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      setIsDragOver(false);
      dragCounterRef.current = 0;
      if (!attachmentsEnabled || disabled || !apiAvailable) return;

      const files = acceptedFiles(e.dataTransfer.files);
      if (files.length > 0) {
        await processFiles(files);
      }
    },
    [attachmentsEnabled, disabled, apiAvailable, processFiles]
  );

  // Determine the placeholder message based on status
  const getPlaceholder = () => {
    if (!apiAvailable) {
      return t('chat.input.placeholder_unavailable');
    }
    if (disabled) {
      return t('chat.input.placeholder_disabled');
    }
    return t('chat.input.placeholder');
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    // UXR Lot 8 (A4): the open slash menu owns ↑/↓/Enter/Escape — this also
    // suppresses the A7 recall and the send while navigating options.
    if (slashMenu.handleKeyDown(e)) return;
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
      return;
    }
    // UXR A7 extended (QA 2026-07-23): ↑/↓ walk through past sends — all
    // branches live in useSentHistoryNavigation (module level).
    handleHistoryKey(e);
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    // Don't send if any voice input phase is active (connecting, recording, processing)
    if (!isRecording && !isProcessing && voiceState !== 'connecting') {
      handleSend();
    }
  };

  // Push-to-talk handlers
  // Always attached to button (not conditional on showSendMode) to prevent race conditions
  // where handlers become undefined during a touch event if state changes mid-press.
  const handlePressStart = useCallback(
    async (e: React.MouseEvent | React.TouchEvent) => {
      // Only activate push-to-talk when all conditions are met.
      // When conditions fail (text present, voice mode active, etc.), do nothing
      // and let native events flow through (form submit on mobile).
      if (!message.trim() && voiceSupported && !disabled && apiAvailable && !pttBlocked) {
        // Prevent default ONLY for push-to-talk (blocks text selection, context menu).
        // MUST NOT be called when there's text, or it suppresses synthetic click → breaks form submit on mobile.
        if ('touches' in e) {
          e.preventDefault();
        }
        // Fired inside the gesture handler, which is the only place browsers
        // honour it — and BEFORE the await, so the confirmation is immediate
        // rather than tied to how long the microphone takes to open.
        haptic('start');
        await startRecording();
      }
    },
    [message, voiceSupported, disabled, apiAvailable, pttBlocked, startRecording]
  );

  const handlePressEnd = useCallback(
    (e?: React.MouseEvent | React.TouchEvent) => {
      // Only preventDefault on touch if we're actually stopping/cancelling voice input.
      // Otherwise, let native events flow (form submit on mobile).
      const isVoiceActive = isRecording || voiceState === 'connecting';
      if (e && 'touches' in e && isVoiceActive) {
        e.preventDefault();
      }
      // Always call stopRecording - it handles all states internally:
      // 'idle' → noop, 'connecting' → cancel via cancelledRef, 'recording' → stop+process
      stopRecording();
    },
    [isRecording, voiceState, stopRecording]
  );

  const handleTouchMove = useCallback(
    (e: React.TouchEvent) => {
      if (!isRecording) return;
      const touch = e.touches[0];
      if (!touch) return;
      const rect = e.currentTarget.getBoundingClientRect();
      if (
        touch.clientX < rect.left - VOICE_PTT_TOUCH_PADDING_PX ||
        touch.clientX > rect.right + VOICE_PTT_TOUCH_PADDING_PX ||
        touch.clientY < rect.top - VOICE_PTT_TOUCH_PADDING_PX ||
        touch.clientY > rect.bottom + VOICE_PTT_TOUCH_PADDING_PX
      ) {
        handlePressEnd();
      }
    },
    [isRecording, handlePressEnd]
  );

  // Determine button state and appearance (UX P2 — the button is visually
  // TRUE). Push-to-talk is offered only when a press could actually start it;
  // in every other situation the button is a send button — disabled while
  // there is nothing to send, never a false invitation to speak.
  const hasMessage = message.trim().length > 0;
  const isButtonDisabled = disabled || !apiAvailable || isProcessing;
  const showSendMode = !isPttOffered({
    hasMessage,
    isProcessing,
    voiceSupported,
    voiceModeEnabled,
    meetingRecording,
    disabled,
    apiAvailable,
  });
  const buttonLabel = composerButtonLabel(t, { isRecording, isProcessing, showSendMode });

  // N-13: one-shot voice spotlight — logic lives in the module-level hook.
  const composerButtonRef = useRef<HTMLButtonElement>(null);
  useVoiceSpotlight(spotlightVoice, !showSendMode, composerButtonRef);

  return (
    // role="presentation": drag-and-drop is a pointer-only convenience — the
    // universal path to attachments is the labelled attach button + file
    // input below (audit F012/F045).
    <div
      role="presentation"
      className={cn(
        // Frosted glass, same material as the chat header (owner request
        // 2026-07-30). The surface must live HERE: an opaque `bg-card` on this
        // root covered any translucency the page wrapper tried to apply, which
        // is why the effect kept not showing. Its counterpart is the composer
        // being sticky INSIDE the scroll container — blur only renders what
        // actually passes behind it.
        'border-t border-border/30 bg-card/60 backdrop-blur-xl px-4 py-4 sm:px-6 relative',
        isDragOver && 'ring-2 ring-primary ring-inset bg-primary/5',
        className
      )}
      onDragEnter={handleDragEnter}
      onDragLeave={handleDragLeave}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
    >
      {/* Drop overlay (UX P13): a visible landing zone instead of a bare
          ring. Non-interactive by construction (pointer-events-none, so it
          never steals dragleave/drop from the container) and aria-hidden —
          the labelled paperclip stays the universal path to attachments. */}
      {isDragOver && (
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center bg-primary/5"
        >
          <div className="flex items-center gap-2 rounded-lg border-2 border-dashed border-primary/60 bg-background/95 px-4 py-3 text-sm font-medium text-foreground shadow-lg">
            <ImageUp className="h-5 w-5 text-primary" aria-hidden="true" />
            {t('chat.attachments.drop_here')}
          </div>
        </div>
      )}
      <div className="max-w-4xl mx-auto">
        {/* Attachment preview strip */}
        {attachmentsEnabled && (
          <AttachmentPreview attachments={attachments} onRemove={removeFile} />
        )}
        {/* `gap-2` on a phone, `gap-3` from `mobile`: two gaps around a
            square action button, the typing area takes the difference. */}
        <form onSubmit={handleSubmit} className="flex gap-2 mobile:gap-3">
          {/* Hidden file input */}
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*,application/pdf"
            multiple
            className="hidden"
            onChange={handleFileSelect}
            aria-label={t('chat.attachments.add')}
          />
          {/* « + »: the file picker (ADR-259) — extracted (CC discipline). */}
          <ComposerAttachmentsControl
            t={t}
            attachmentsEnabled={attachmentsEnabled}
            disabled={disabled || !apiAvailable || isUploading}
            onPickFile={() => fileInputRef.current?.click()}
          />
          {/* Positional wrapper (UXR Lot 8): the slash menu floats above the
              textarea, which carries the combobox role itself (ARIA 1.2). */}
          <div className="relative flex-1">
            <SlashCommandMenu menu={slashMenu} />
            <textarea
              ref={textareaRef}
              value={message}
              onChange={e => {
                const newValue = e.target.value;
                setMessage(newValue);
                onMessageChange?.(newValue);
                handleInput();
              }}
              onKeyDown={handleKeyDown}
              onPaste={handlePaste}
              maxLength={CHAT_INPUT_MAX_LENGTH}
              placeholder={getPlaceholder()}
              aria-label={getPlaceholder()}
              aria-autocomplete="list"
              // Only references the listbox while it is MOUNTED (axe:
              // aria-valid-attr-value) — the open/closed branch lives in
              // useSlashMenu (CC discipline).
              aria-controls={slashMenu.controlsId}
              aria-activedescendant={slashMenu.activeOptionId}
              // `block`: a textarea is INLINE by default, so its baseline adds ~6 px
              // below it — the wrapper grew to 54 px while every control
              // stayed 48 px, and the field sat 6 px above the paperclip and
              // the send button (measured). Nothing else aligned them.
              className="block w-full resize-none overflow-y-hidden rounded-lg border border-input bg-background px-4 py-3 text-base mobile:text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 placeholder:text-transparent mobile:placeholder:text-muted-foreground"
              rows={1}
              disabled={disabled || !apiAvailable}
              style={{ minHeight: '48px', maxHeight: `${CHAT_INPUT_MAX_HEIGHT_PX}px` }}
              autoCapitalize="sentences"
              autoCorrect="on"
              spellCheck
              enterKeyHint="send"
            />
          </div>
          {/* Stop button (ADR-117 Lot 3): replaces send while a response is
              streaming. Cancellation is not a rollback — tools that already
              ran have acted; it stops what remains. */}
          {isGenerating && onStopGeneration ? (
            <Button
              type="button"
              size="lg"
              variant="destructive"
              className="gap-2 h-12 self-end transition-all duration-200"
              onClick={onStopGeneration}
              aria-label={t('chat.input.stop')}
            >
              <Square className="h-4 w-4" />
              <span className="hidden sm:inline">{t('chat.input.stop')}</span>
            </Button>
          ) : (
            <>
              {/* Send / Push-to-talk button */}
              <Button
                ref={composerButtonRef}
                type={showSendMode ? 'submit' : 'button'}
                size="lg"
                disabled={isButtonDisabled || (showSendMode && !hasMessage)}
                className={cn(
                  // Icon-only at every width: `px-5` on a phone keeps a 56 px
                  // hold-to-talk target and gives the field the rest.
                  'gap-2 h-12 self-end px-5 transition-all duration-200 mobile:px-8',
                  'touch-manipulation select-none [-webkit-touch-callout:none]',
                  isRecording && 'bg-destructive hover:bg-destructive/90 animate-pulse'
                )}
                // Handlers always attached to prevent race conditions when showSendMode
                // changes during a touch event. Guards inside handlers filter non-PTT calls.
                onMouseDown={handlePressStart}
                onMouseUp={handlePressEnd}
                onMouseLeave={isRecording ? handlePressEnd : undefined}
                onTouchStart={handlePressStart}
                onTouchEnd={handlePressEnd}
                onTouchCancel={handlePressEnd}
                onTouchMove={isRecording ? handleTouchMove : undefined}
                onContextMenu={e => e.preventDefault()}
                aria-label={buttonLabel}
              >
                <span className="relative inline-flex items-center justify-center">
                  <ComposerButtonIcon
                    showMic={isRecording || !(showSendMode || justSent)}
                    dimmed={disabled || isProcessing}
                    animating={justSent}
                    onTakeoffEnd={() => setJustSent(false)}
                  />
                  {(disabled || isProcessing) && !isRecording && (
                    <LoadingSpinner className="absolute inset-0 m-auto text-primary-foreground" />
                  )}
                </span>
                <span className="hidden sm:inline">{buttonLabel}</span>
              </Button>
            </>
          )}
        </form>
      </div>
    </div>
  );
};
