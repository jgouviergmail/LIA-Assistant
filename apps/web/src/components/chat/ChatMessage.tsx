import { memo, useState, useCallback, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { Message, MessageAttachmentMeta } from '@/types/chat';
import { User, AlertCircle, ThumbsUp, ThumbsDown, Ban, FileText, X, Globe } from 'lucide-react';
import { formatNumber, formatEuro } from '@/lib/format';
import { proxyGoogleImageUrl } from '@/lib/utils';
import { MarkdownContent } from './MarkdownContent';
import { isInterestNotificationMetadata } from './InterestNotificationCard';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/hooks/useAuth';
import { getIntlLocale, Language } from '@/i18n/settings';
import { Button } from '@/components/ui/button';
import { useApiMutation } from '@/hooks/useApiMutation';
import { toast } from 'sonner';
import { formatFileSize } from '@/lib/utils/image-compress';
import { API_ENDPOINTS } from '@/lib/api-config';
import { ImageLightbox } from '@/components/ui/image-lightbox';

export interface ChatMessageProps {
  message: Message;
  isUser: boolean;
}

type FeedbackType = 'thumbs_up' | 'thumbs_down' | 'block';

/**
 * Feedback buttons for proactive interest notifications.
 * Only shown for messages with feedback_enabled and no prior feedback.
 */
function InterestFeedbackButtons({
  targetId,
  onFeedbackSubmitted,
}: {
  targetId: string;
  onFeedbackSubmitted: () => void;
}) {
  const { t } = useTranslation();
  const [isSubmitting, setIsSubmitting] = useState(false);

  const { mutate } = useApiMutation<{ feedback: FeedbackType }, void>({
    method: 'POST',
    componentName: 'ChatMessage',
    onError: () => {
      toast.error(t('interests.feedback.error'));
      setIsSubmitting(false);
    },
  });

  const handleFeedback = useCallback(
    async (feedback: FeedbackType) => {
      if (isSubmitting) return;
      setIsSubmitting(true);

      try {
        await mutate(`/interests/${targetId}/feedback`, { feedback });
        onFeedbackSubmitted();

        switch (feedback) {
          case 'thumbs_up':
            toast.success(t('interests.feedback.liked'));
            break;
          case 'thumbs_down':
            toast.info(t('interests.feedback.disliked'));
            break;
          case 'block':
            toast.info(t('interests.feedback.blocked'));
            break;
        }
      } catch {
        // Error handled by onError callback
      }
    },
    [mutate, targetId, isSubmitting, t, onFeedbackSubmitted]
  );

  return (
    <div className="flex items-center gap-1 mt-2">
      <span className="text-xs text-muted-foreground mr-2">
        {t('interests.notification.helpful')}
      </span>
      <Button
        variant="ghost"
        size="icon"
        className="h-7 w-7 hover:bg-green-100 hover:text-green-600 dark:hover:bg-green-900/30"
        onClick={() => handleFeedback('thumbs_up')}
        disabled={isSubmitting}
        aria-label={t('interests.feedback.like')}
      >
        <ThumbsUp className="h-4 w-4" />
      </Button>
      <Button
        variant="ghost"
        size="icon"
        className="h-7 w-7 hover:bg-orange-100 hover:text-orange-600 dark:hover:bg-orange-900/30"
        onClick={() => handleFeedback('thumbs_down')}
        disabled={isSubmitting}
        aria-label={t('interests.feedback.dislike')}
      >
        <ThumbsDown className="h-4 w-4" />
      </Button>
      <Button
        variant="ghost"
        size="icon"
        className="h-7 w-7 hover:bg-red-100 hover:text-red-600 dark:hover:bg-red-900/30"
        onClick={() => handleFeedback('block')}
        disabled={isSubmitting}
        aria-label={t('interests.feedback.block')}
      >
        <Ban className="h-4 w-4" />
      </Button>
    </div>
  );
}

/**
 * AI-generated image cards — rendered outside markdown to avoid
 * HTML nesting violations (<div> inside <p>).
 * Uses relative URLs served by the reverse proxy in production.
 * In dev with self-signed certs, images may not load through the proxy.
 */
function GeneratedImageCards({ images }: { images: { url: string; alt: string }[] }) {
  const [lightboxImage, setLightboxImage] = useState<{ url: string; alt: string } | null>(null);

  return (
    <>
      <div className="mt-3 space-y-3">
        {images.map((img, i) => {
          // Use relative URL to go through Next.js rewrite proxy
          const displayUrl = img.url;
          return (
            <div key={i} className="relative w-full max-w-[512px] mx-auto">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={displayUrl}
                alt={img.alt}
                className="w-full h-auto rounded-lg shadow-md cursor-pointer hover:shadow-lg transition-shadow"
                onClick={() => setLightboxImage({ url: displayUrl, alt: img.alt })}
              />
            </div>
          );
        })}
      </div>
      {lightboxImage &&
        typeof document !== 'undefined' &&
        createPortal(
          <ImageLightbox
            src={lightboxImage.url}
            alt={lightboxImage.alt}
            isOpen={true}
            onClose={() => setLightboxImage(null)}
            minWidth={512}
          />,
          document.body
        )}
    </>
  );
}

/**
 * Browser screenshot card — rendered after the message bubble for
 * messages that include a final browser screenshot (persisted in metadata).
 * Uses ImageLightbox for full-screen viewing.
 */
function BrowserScreenshotCard({ screenshot }: { screenshot: { url: string; alt: string } }) {
  const { t } = useTranslation();
  const [lightboxOpen, setLightboxOpen] = useState(false);
  return (
    <>
      <div className="mt-3">
        <div className="relative w-full max-w-[512px] mx-auto">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={screenshot.url}
            alt={screenshot.alt}
            className="w-full h-auto rounded-lg shadow-md cursor-pointer hover:shadow-lg transition-shadow"
            crossOrigin="use-credentials"
            onClick={() => setLightboxOpen(true)}
          />
          <div className="flex items-center gap-1.5 mt-1.5 px-1">
            <Globe className="h-3 w-3 text-muted-foreground flex-shrink-0" />
            <span className="text-[10px] text-muted-foreground truncate">
              {t('browser.screenshot.finalCard')}
            </span>
          </div>
        </div>
      </div>
      {lightboxOpen &&
        typeof document !== 'undefined' &&
        createPortal(
          <ImageLightbox
            src={screenshot.url}
            alt={screenshot.alt}
            isOpen={lightboxOpen}
            onClose={() => setLightboxOpen(false)}
          />,
          document.body
        )}
    </>
  );
}

/**
 * Inline attachment thumbnails for user messages.
 * Reconstructed from message_metadata.attachments for history display.
 */
function MessageAttachments({ attachments }: { attachments: MessageAttachmentMeta[] }) {
  const { t } = useTranslation();
  const [expandedImage, setExpandedImage] = useState<{ url: string; filename: string } | null>(
    null
  );
  const lightboxRef = useRef<HTMLDivElement>(null);

  // H3: Keyboard close (Escape) and focus trap for lightbox
  useEffect(() => {
    if (!expandedImage) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setExpandedImage(null);
      }
    };

    // Focus the lightbox overlay for keyboard accessibility
    lightboxRef.current?.focus();
    // Prevent body scroll while lightbox is open
    document.body.style.overflow = 'hidden';

    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = '';
    };
  }, [expandedImage]);

  if (!attachments || attachments.length === 0) return null;

  return (
    <>
      <div className="flex flex-wrap gap-2 mb-2">
        {attachments.map(att => {
          // Use client-side Object URL when available (immediate send), API URL for history reload
          const imgSrc =
            att.previewUrl || API_ENDPOINTS.ATTACHMENTS.BY_ID.replace(':attachmentId', att.id);
          const needsCrossOrigin = !att.previewUrl; // Only needed for cross-origin API requests
          return att.content_type === 'image' ? (
            <button
              key={att.id}
              type="button"
              className="relative h-20 max-w-40 rounded-lg overflow-hidden border border-white/20 hover:ring-2 hover:ring-white/40 transition-all"
              onClick={() => setExpandedImage({ url: imgSrc, filename: att.filename })}
              aria-label={att.filename}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={imgSrc}
                alt={att.filename}
                className="h-full w-auto object-contain"
                {...(needsCrossOrigin ? { crossOrigin: 'use-credentials' } : {})}
              />
            </button>
          ) : (
            <a
              key={att.id}
              href={API_ENDPOINTS.ATTACHMENTS.BY_ID.replace(':attachmentId', att.id)}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 px-3 py-2 rounded-lg bg-white/10 border border-white/20 hover:bg-white/20 transition-colors"
              aria-label={att.filename}
            >
              <FileText className="h-4 w-4 flex-shrink-0" />
              <div className="min-w-0">
                <p className="text-xs font-medium truncate max-w-[120px]">{att.filename}</p>
                <p className="text-[10px] opacity-70">{formatFileSize(att.size)}</p>
              </div>
            </a>
          );
        })}
      </div>

      {/* Lightbox overlay — rendered via portal to escape overflow:hidden ancestors */}
      {expandedImage &&
        createPortal(
          <div
            ref={lightboxRef}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm"
            onClick={() => setExpandedImage(null)}
            onKeyDown={e => {
              if (e.key === 'Escape') setExpandedImage(null);
            }}
            role="dialog"
            aria-modal="true"
            aria-label={expandedImage.filename}
            tabIndex={-1}
          >
            {/* Close button */}
            <button
              type="button"
              className="absolute top-4 right-4 p-2 rounded-full bg-black/50 text-white hover:bg-black/70 transition-colors z-10"
              onClick={() => setExpandedImage(null)}
              aria-label={t('common.close')}
            >
              <X className="h-5 w-5" />
            </button>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={expandedImage.url}
              alt={expandedImage.filename}
              className="max-w-[85vw] max-h-[75vh] mobile:max-w-[70vw] mobile:max-h-[70vh] object-contain rounded-lg shadow-2xl"
              {...(expandedImage.url.startsWith('blob:')
                ? {}
                : { crossOrigin: 'use-credentials' as const })}
              onClick={e => e.stopPropagation()}
            />
          </div>,
          document.body
        )}
    </>
  );
}

/**
 * ChatMessage component - Memoized to prevent unnecessary re-renders during streaming.
 * Issue #64: Without memo, images would flash on every token because React recreates the DOM.
 */
export const ChatMessage: React.FC<ChatMessageProps> = memo(({ message, isUser }) => {
  const { i18n, t } = useTranslation();
  const { user } = useAuth();
  const isSystem = message.role === 'system';
  const locale = getIntlLocale(i18n.language as Language);
  const showTokens = user?.tokens_display_enabled ?? false;

  // Track if feedback has been submitted for proactive interest messages
  const [feedbackSubmitted, setFeedbackSubmitted] = useState(false);

  // Check if this is a proactive notification (interest, heartbeat, or future types)
  const isProactiveInterest = !isUser && isInterestNotificationMetadata(message.metadata);
  const isProactiveMessage =
    !isUser &&
    typeof message.metadata?.type === 'string' &&
    (message.metadata.type as string).startsWith('proactive_');
  const showFeedbackButtons =
    isProactiveInterest && Boolean(message.metadata?.feedback_enabled) && !feedbackSubmitted;

  // Token data: for ALL proactive types, read from metadata (centrally injected by runner),
  // then fall back to message-level fields (from DB JOIN via run_id)
  const tokensIn = isProactiveMessage
    ? ((message.metadata?.tokens_in as number | undefined) ?? message.tokensIn)
    : message.tokensIn;
  const tokensOut = isProactiveMessage
    ? ((message.metadata?.tokens_out as number | undefined) ?? message.tokensOut)
    : message.tokensOut;
  const tokensCache = isProactiveMessage
    ? ((message.metadata?.tokens_cache as number | undefined) ?? message.tokensCache ?? 0)
    : (message.tokensCache ?? 0);
  const costEur = isProactiveMessage
    ? ((message.metadata?.cost_eur as number | undefined) ?? message.costEur ?? 0)
    : (message.costEur ?? 0);
  const googleApiRequests = message.googleApiRequests ?? 0;

  const formatTime = (date: Date) => {
    const time = new Intl.DateTimeFormat(locale, {
      hour: '2-digit',
      minute: '2-digit',
    }).format(date);

    const dateStr = new Intl.DateTimeFormat(locale, {
      weekday: 'long',
      day: '2-digit',
      month: 'long',
      year: 'numeric',
    }).format(date);

    return `${time} | ${dateStr}`;
  };

  // System messages (generic system notifications)
  if (isSystem) {
    return (
      <div className="flex gap-3 mb-4 animate-message-enter">
        {/* System icon */}
        <div className="flex-shrink-0">
          <div className="w-9 h-9 rounded-full flex items-center justify-center shadow-sm bg-warning/10 text-warning ring-2 ring-warning/20">
            <AlertCircle className="h-5 w-5" />
          </div>
        </div>

        {/* System message content */}
        <div className="flex flex-col flex-1 max-w-2xl">
          <div className="px-4 py-3 rounded-xl shadow-md bg-card/70 backdrop-blur-md border border-warning/20">
            <p className="text-[13px] mobile:text-sm text-muted-foreground">{message.content}</p>
          </div>
          <span className="text-[11px] mobile:text-xs text-muted-foreground mt-1.5 px-1 font-medium">
            {formatTime(message.timestamp)}
          </span>
        </div>
      </div>
    );
  }

  // Regular user/assistant messages (including proactive interest notifications)
  // On mobile, assistant messages take full width (no flex container, direct block)
  if (!isUser) {
    return (
      <div className="mb-4 animate-message-enter mobile:flex mobile:flex-row-reverse mobile:gap-3">
        {/* Avatar - Hidden on mobile, visible on desktop - LIA trigram */}
        <div className="hidden mobile:block flex-shrink-0">
          <div className="w-10 h-10 rounded-full flex items-center justify-center shadow-md bg-gradient-to-br from-primary to-primary/80 text-primary-foreground ring-2 ring-primary/30 font-bold text-sm">
            LIA
          </div>
        </div>

        {/* Message bubble - Full width on mobile, flex-1 on tablet/desktop */}
        <div className="flex flex-col w-full mobile:flex-1 items-end">
          <div className="message-bubble message-bubble-assistant px-4 py-3 rounded-xl shadow-md bg-card/70 backdrop-blur-md text-foreground rounded-tr-none border border-border/20 hover:shadow-lg hover:border-primary/30 hover:bg-card/80 mobile:rounded-tr-xl transition-colors">
            {/* Skill indicator — top of bubble, always visible when a skill is active */}
            {message.skillName && (
              <div className="flex items-center gap-1.5 mb-2 pb-2 border-b border-border/30">
                <span className="text-[10px] px-1.5 py-0.5 rounded border bg-cyan-500/20 text-cyan-400 border-cyan-500/30 font-medium tracking-wide">
                  ✦ {message.skillName}
                </span>
              </div>
            )}
            {/* Browser screenshot — displayed first as visual context for the response */}
            {message.browserScreenshot && (
              <BrowserScreenshotCard screenshot={message.browserScreenshot} />
            )}
            <MarkdownContent content={message.content} isUser={false} />
            {/* Feedback buttons for proactive interest notifications */}
            {showFeedbackButtons && (
              <InterestFeedbackButtons
                targetId={String(message.metadata?.target_id ?? '')}
                onFeedbackSubmitted={() => setFeedbackSubmitted(true)}
              />
            )}
            {/* AI-generated images — inside bubble after text content */}
            {message.generatedImages && message.generatedImages.length > 0 && (
              <GeneratedImageCards images={message.generatedImages} />
            )}
          </div>
          <span className="text-[11px] mobile:text-xs text-muted-foreground mt-1.5 px-1 font-medium whitespace-nowrap w-full text-right">
            {formatTime(message.timestamp)}
            {tokensIn !== undefined && showTokens && (
              <span className="hidden mobile:inline">
                {' | '}
                <span className="text-orange-500">🟠 {formatNumber(tokensIn)} IN</span>{' '}
                <span className="text-green-600">🟢 {formatNumber(tokensOut || 0)} OUT</span>{' '}
                <span className="text-blue-500">🔵 {formatNumber(tokensCache)} CACHE</span>{' '}
                <span className="text-purple-500">🟣 {formatNumber(googleApiRequests)} GOOGLE</span>
                {' • '}
                <span className="text-foreground font-semibold">{formatEuro(costEur, 6)}</span>
              </span>
            )}
          </span>
        </div>
      </div>
    );
  }

  // User messages
  return (
    <div className="flex gap-3 mb-4 animate-message-enter flex-row">
      {/* Avatar */}
      <div className="flex-shrink-0">
        {message.avatar ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={proxyGoogleImageUrl(message.avatar) || message.avatar}
            alt={t('chat.avatar_alt.user')}
            className="w-9 h-9 rounded-full object-cover ring-2 ring-primary/20 shadow-sm"
            referrerPolicy="no-referrer"
          />
        ) : (
          <div className="w-9 h-9 rounded-full flex items-center justify-center shadow-sm bg-gradient-to-br from-primary to-primary/80 text-primary-foreground ring-2 ring-primary/20">
            <User className="h-4 w-4" />
          </div>
        )}
      </div>

      {/* Message bubble */}
      <div className="flex flex-col flex-1 items-start">
        <div className="message-bubble px-4 py-3 rounded-xl shadow-md bg-gradient-to-br from-primary/80 to-primary/70 backdrop-blur-md text-primary-foreground rounded-tl-none hover:shadow-lg hover:from-primary/90 hover:to-primary/80 transition-colors">
          <MessageAttachments
            attachments={
              (message.metadata?.attachments as MessageAttachmentMeta[] | undefined) ?? []
            }
          />
          <MarkdownContent content={message.content} isUser={true} />
        </div>
        <span className="text-[11px] mobile:text-xs text-muted-foreground mt-1.5 px-1 font-medium whitespace-nowrap w-full text-left">
          {formatTime(message.timestamp)}
          {/* Voice source indicator (only for voice messages) */}
          {message.source === 'voice' && (
            <span className="hidden mobile:inline">
              {' | '}
              <span className="text-purple-500">
                🎤 {message.audioDurationSeconds?.toFixed(1) ?? '?'}s
              </span>
            </span>
          )}
        </span>
      </div>
    </div>
  );
});
ChatMessage.displayName = 'ChatMessage';
