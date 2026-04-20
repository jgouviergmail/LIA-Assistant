import { useState, useRef, useCallback, KeyboardEvent, FormEvent, DragEvent } from 'react';
import { Button } from '@/components/ui/button';
import { Tooltip, TooltipTrigger, TooltipContent } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import { Send, Mic, Paperclip } from 'lucide-react';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { useVoiceInput } from '@/hooks/useVoiceInput';
import { useVoiceModeStore } from '@/stores/voiceModeStore';
import { useFileUpload } from '@/hooks/useFileUpload';
import { VOICE_PTT_TOUCH_PADDING_PX } from '@/lib/constants';
import AttachmentPreview from '@/components/chat/AttachmentPreview';
import { MessageAttachmentMeta } from '@/types/chat';

/** Attachment metadata passed alongside IDs for immediate local display. */
export type SendAttachmentMeta = MessageAttachmentMeta;

export interface ChatInputProps {
  onSendMessage: (
    content: string,
    attachmentIds?: string[],
    attachmentsMeta?: SendAttachmentMeta[]
  ) => void;
  disabled?: boolean;
  isConnected?: boolean;
  apiAvailable?: boolean;
  className?: string;
  /** Called when message text changes (for geolocation prompt detection) */
  onMessageChange?: (message: string) => void;
  /** Whether attachments feature is enabled */
  attachmentsEnabled?: boolean;
}

export const ChatInput: React.FC<ChatInputProps> = ({
  onSendMessage,
  disabled = false,
  isConnected: _isConnected = true,
  apiAvailable = true,
  className,
  onMessageChange,
  attachmentsEnabled = false,
}) => {
  const { t } = useTranslation();
  const [message, setMessage] = useState('');
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

  // Auto-resize the textarea
  const handleInput = useCallback(() => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = 'auto';
      textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`;
    }
  }, []);

  /**
   * Handle voice transcription result.
   * Puts transcribed text into the message input.
   */
  const handleVoiceTranscription = useCallback(
    (text: string) => {
      if (!text.trim()) return;

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
      onSendMessage(trimmedMessage, readyIds.length > 0 ? readyIds : undefined, readyMeta);
      setMessage('');
      onMessageChange?.('');
      clearAttachments();
      // Reset textarea height and remove focus (reset iOS zoom)
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto';
        textareaRef.current.blur();
      }
    }
  };

  // Shared upload handler with error toasts
  const processFiles = useCallback(
    async (files: File[]) => {
      for (const file of files) {
        const result = await uploadFile(file);
        if (result && 'error' in result) {
          switch (result.error) {
            case 'file_too_large':
              toast.error(t('chat.attachments.file_too_large', { max: 10 }));
              break;
            case 'type_not_allowed':
              toast.error(t('chat.attachments.type_not_allowed'));
              break;
            case 'max_attachments':
              toast.error(t('chat.attachments.max_attachments', { max: 5 }));
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

      const files = Array.from(e.dataTransfer.files).filter(
        f => f.type.startsWith('image/') || f.type === 'application/pdf'
      );
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
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
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
      if (!message.trim() && voiceSupported && !disabled && apiAvailable && !voiceModeEnabled) {
        // Prevent default ONLY for push-to-talk (blocks text selection, context menu).
        // MUST NOT be called when there's text, or it suppresses synthetic click → breaks form submit on mobile.
        if ('touches' in e) {
          e.preventDefault();
        }
        await startRecording();
      }
    },
    [message, voiceSupported, disabled, apiAvailable, voiceModeEnabled, startRecording]
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

  // Determine button state and appearance
  const hasMessage = message.trim().length > 0;
  const isButtonDisabled = disabled || !apiAvailable || isProcessing;
  // Show send mode (not push-to-talk) when: has message, processing, or voice mode active
  const showSendMode = hasMessage || isProcessing || voiceModeEnabled;

  return (
    <div
      className={cn(
        'border-t bg-card px-4 py-4 sm:px-6 relative',
        isDragOver && 'ring-2 ring-primary ring-inset bg-primary/5',
        className
      )}
      onDragEnter={handleDragEnter}
      onDragLeave={handleDragLeave}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
    >
      <div className="max-w-4xl mx-auto">
        {/* Attachment preview strip */}
        {attachmentsEnabled && (
          <AttachmentPreview attachments={attachments} onRemove={removeFile} />
        )}
        <form onSubmit={handleSubmit} className="flex gap-3">
          {/* Hidden file input */}
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*,application/pdf"
            multiple
            className="hidden"
            onChange={handleFileSelect}
          />
          {/* Paperclip button */}
          {attachmentsEnabled && (
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  type="button"
                  variant="ghost"
                  size="lg"
                  className="h-12 self-end px-3"
                  disabled={disabled || !apiAvailable || isUploading}
                  onClick={() => fileInputRef.current?.click()}
                  aria-label={t('chat.attachments.add')}
                >
                  <Paperclip className="h-4 w-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>{t('chat.attachments.add')}</TooltipContent>
            </Tooltip>
          )}
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
            placeholder={getPlaceholder()}
            className="flex-1 resize-none rounded-lg border border-input bg-background px-4 py-3 text-base mobile:text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 placeholder:text-transparent mobile:placeholder:text-muted-foreground"
            rows={1}
            disabled={disabled || !apiAvailable}
            style={{ minHeight: '48px', maxHeight: '200px' }}
            autoCapitalize="sentences"
            autoCorrect="on"
            spellCheck
            enterKeyHint="send"
          />
          {/* Send / Push-to-talk button */}
          <Button
            type={showSendMode ? 'submit' : 'button'}
            size="lg"
            disabled={isButtonDisabled || (showSendMode && !hasMessage)}
            className={cn(
              'gap-2 h-12 self-end transition-all duration-200',
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
            aria-label={
              isRecording
                ? t('chat.voice.recording')
                : isProcessing
                  ? t('chat.voice.processing')
                  : showSendMode
                    ? t('chat.input.send')
                    : t('chat.voice.hold_to_speak')
            }
          >
            <span className="relative inline-flex items-center justify-center">
              {isRecording ? (
                <Mic className="h-4 w-4" />
              ) : (
                <Send
                  className={cn(
                    'h-4 w-4 transition-opacity',
                    (disabled || isProcessing) && 'opacity-30'
                  )}
                />
              )}
              {(disabled || isProcessing) && !isRecording && (
                <LoadingSpinner className="absolute inset-0 m-auto text-primary-foreground" />
              )}
            </span>
            <span className="hidden sm:inline">
              {isRecording
                ? t('chat.voice.recording')
                : isProcessing
                  ? t('chat.voice.processing')
                  : t('chat.input.send')}
            </span>
          </Button>
        </form>
      </div>
    </div>
  );
};
