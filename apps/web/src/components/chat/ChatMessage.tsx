import { memo, useState, useCallback, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import {
  Message,
  MessageAttachmentMeta,
  type GeneratedDocument,
  type GeneratedImage,
} from '@/types/chat';
import {
  AlertCircle,
  Check,
  Copy,
  Download,
  FileText,
  Globe,
  RotateCcw,
  User,
  X,
} from 'lucide-react';
import { formatNumber, formatEuro } from '@/lib/format';
import { cn, proxyGoogleImageUrl } from '@/lib/utils';
import { classifyImageExpiry } from '@/lib/image-expiry';
import { copyMessageToClipboard } from '@/lib/message-clipboard';
import { MarkdownContent } from './MarkdownContent';
import { documentTypeIcon } from './document-card-icon';
import { PeerMessageActions } from '@/components/chat/PeerMessageActions';
import { isInterestNotificationMetadata } from './InterestNotificationCard';
import { CallDebrief } from '@/components/telephony/CallDebrief';
import { isPhoneCallDebrief } from '@/types/telephony';
import {
  ProactiveFeedbackButtons,
  type ProactiveFeedbackKind,
  type ProactiveFeedbackVerdict,
} from './ProactiveFeedbackButtons';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/hooks/useAuth';
import { getIntlLocale, Language } from '@/i18n/settings';
import { Tooltip, TooltipTrigger, TooltipContent } from '@/components/ui/tooltip';
import {
  ResponseFeedbackButtons,
  type ResponseFeedbackButtonsProps,
} from './ResponseFeedbackButtons';
import { ShareResponseMenu } from './ShareResponseMenu';
import { toast } from 'sonner';
import { formatFileSize } from '@/lib/utils/image-compress';
import { API_ENDPOINTS } from '@/lib/api-config';
import { ImageLightbox } from '@/components/ui/image-lightbox';
import { downloadImage } from '@/lib/utils/download-image';
import { AssistantAvatar, type AvatarTooltipLine } from '@/components/psyche/AssistantAvatar';
import { ExecutionTraceDisclosure } from '@/components/chat/ExecutionTraceDisclosure';
import { usePsycheStore } from '@/stores/psycheStore';
import type { ExecutionTrace } from '@/types/execution-trace';
import type { PsycheStateSummary } from '@/types/psyche';
import type { StreamPhase } from '@/types/chat-state';

export interface ChatMessageProps {
  message: Message;
  isUser: boolean;
  /** True only for the last assistant message — gates the animated psyche emoji (spec D-5). */
  isLatestAssistant?: boolean;
  /** True while this message is the active stream target (steps/caret styling). */
  isActiveStream?: boolean;
  /** 'progress' (execution steps) vs 'answer' (real tokens) — picks the styling. */
  streamPhase?: StreamPhase;
  /** History-search term highlighted in the rendered content (QW-2). */
  searchHighlight?: string;
  /**
   * Replay the prompt pinned on an error bubble (W3).
   *
   * Only wired for the LATEST error: replaying an old failure would send it
   * into a conversation that has moved on. Absent → no retry is offered.
   */
  onRetry?: (prompt: string) => void;
  /** Peers Lot 7: composer prefill for the peer Reply quick-action. */
  onPrefillComposer?: (text: string) => void;
}

/** Window (ms) within which a proactive notification counts as "just arrived". */
const PROACTIVE_FRESH_WINDOW_MS = 10_000;

/**
 * A proactive notification "just arrived" when its timestamp is within a few
 * seconds of now (either direction, to tolerate small clock skew). This tells a
 * live push apart from a history-loaded row so the avatar only rings on real
 * arrival, not on every page load (F4 — mirrors the milestone hydration guard).
 */
export function isFreshProactive(
  timestampMs: number,
  nowMs: number,
  windowMs: number = PROACTIVE_FRESH_WINDOW_MS
): boolean {
  return Math.abs(nowMs - timestampMs) < windowMs;
}

/**
 * The shape both feedback routes accept in their path.
 *
 * `POST /interests/{interest_id}/feedback` and
 * `PATCH /heartbeat/notifications/{notification_id}/feedback` each declare a
 * `UUID` path parameter, so anything else is rejected before a handler runs —
 * and the buttons swallow that failure by design (a preference ping must not
 * shout at the user). A control that cannot succeed is therefore not offered
 * at all.
 *
 * Deliberately the generic 8-4-4-4-12 form rather than a version-4 pattern:
 * Python's `UUID()` accepts any variant, and being stricter here would hide
 * buttons the server would have honoured.
 */
const FEEDBACK_TARGET_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** A verdict the backend already recorded for this notification, if any. */
function recordedVerdict(
  metadata: Record<string, unknown> | undefined
): ProactiveFeedbackVerdict | undefined {
  const value = metadata?.feedback_value;
  return value === 'thumbs_up' || value === 'thumbs_down' || value === 'block' ? value : undefined;
}

/**
 * Which proactive feedback row a bubble deserves, or null.
 *
 * Pure — extracted from the render hotspot so the routing between the two
 * backend contracts (interest vs heartbeat) is unit-testable. Heartbeat
 * notifications used to fall through here with no buttons at all despite
 * carrying `feedback_enabled: true`.
 *
 * A verdict already given does NOT remove the row any more: it comes back as
 * `submittedVerdict`, so the chosen thumb stays visible and pressed — the same
 * read as on an ordinary assistant answer. Disabled, though: unlike a response
 * verdict, a proactive one is final server-side (a "block" really blocks the
 * subject), so an enabled-looking chip would promise a reversibility the
 * product does not offer. The backend persists it as `feedback_value`, so the
 * state survives reloads and devices.
 */
export function proactiveFeedbackProps(
  metadata: Record<string, unknown> | undefined,
  /** Verdict chosen during THIS session, before the metadata catches up. */
  justSubmitted?: ProactiveFeedbackVerdict
): {
  kind: ProactiveFeedbackKind;
  targetId: string;
  runId?: string;
  submittedVerdict?: ProactiveFeedbackVerdict;
} | null {
  if (!metadata || !metadata.feedback_enabled) return null;
  const targetId = metadata.target_id;
  // Not merely non-empty: it must be an identifier the route can resolve.
  // Heartbeat notifications archived before the identity fix carry a
  // synthetic `heartbeat_<hex>` value; their vote is genuinely impossible,
  // so no control is rendered rather than one that records nothing.
  if (typeof targetId !== 'string' || !FEEDBACK_TARGET_RE.test(targetId)) return null;

  const kind: ProactiveFeedbackKind | null =
    metadata.type === 'proactive_interest'
      ? 'interest'
      : metadata.type === 'proactive_heartbeat'
        ? 'heartbeat'
        : null;
  if (kind === null) return null;

  const runId = typeof metadata.run_id === 'string' ? metadata.run_id : undefined;
  // The live choice wins over the persisted one: the metadata this render sees
  // is still the pre-vote payload right after a click.
  return { kind, targetId, runId, submittedVerdict: justSubmitted ?? recordedVerdict(metadata) };
}

/**
 * Token fields of a bubble: proactive notifications read from metadata
 * (centrally injected by the runner) with message-level fields (DB JOIN via
 * run_id) as fallback; ordinary messages read the message fields directly.
 * Pure helper extracted from the render hotspot (CC discipline).
 */
function resolveTokenFields(
  message: Message,
  isProactiveMessage: boolean
): { tokensIn?: number; tokensOut?: number; tokensCache: number; costEur: number } {
  if (!isProactiveMessage) {
    return {
      tokensIn: message.tokensIn,
      tokensOut: message.tokensOut,
      tokensCache: message.tokensCache ?? 0,
      costEur: message.costEur ?? 0,
    };
  }
  return {
    tokensIn: (message.metadata?.tokens_in as number | undefined) ?? message.tokensIn,
    tokensOut: (message.metadata?.tokens_out as number | undefined) ?? message.tokensOut,
    tokensCache: (message.metadata?.tokens_cache as number | undefined) ?? message.tokensCache ?? 0,
    costEur: (message.metadata?.cost_eur as number | undefined) ?? message.costEur ?? 0,
  };
}

/**
 * Gate + props of the response feedback chips (QW-5): ordinary, fully
 * archived assistant responses only. Pure helper (CC discipline) — returns
 * null for proactive notifications (they keep their dedicated buttons),
 * active streams, and rows without an archived DB id.
 */
function responseFeedbackProps(
  message: Message,
  isProactive: boolean,
  isActiveStream: boolean
): { messageDbId: string; initialVerdict?: 'thumbs_up' | 'thumbs_down' } | null {
  if (isProactive || isActiveStream) return null;
  const dbId = message.metadata?.message_db_id;
  if (typeof dbId !== 'string') return null;
  const verdict = (message.metadata?.response_feedback as { verdict?: string } | undefined)
    ?.verdict;
  return {
    messageDbId: dbId,
    initialVerdict: verdict === 'thumbs_up' || verdict === 'thumbs_down' ? verdict : undefined,
  };
}

/**
 * The prompt an error bubble pinned for replay (W3), or undefined.
 *
 * Lives here rather than inline in the bubble: the render function is a
 * complexity hotspot under a shrink-only ratchet, and this predicate is worth
 * testing on its own — it is what decides whether a failure has a way back.
 */
export function retryPromptOf(message: Message): string | undefined {
  if (message.metadata?.type !== 'error') return undefined;
  const prompt = message.metadata?.retryPrompt;
  return typeof prompt === 'string' && prompt.length > 0 ? prompt : undefined;
}

/**
 * T01 debrief block of a post-call proactive message — module-level so the
 * type/shape checks stay OUT of the render hotspot (CC discipline). Renders
 * nothing for any other message, malformed metadata included (a shape drift
 * from the dispatcher must degrade to the plain text, never crash the chat).
 */
function PhoneCallDebriefBlock({ metadata }: { metadata?: Record<string, unknown> }) {
  if (metadata?.type !== 'proactive_phone_call') return null;
  const debrief = metadata.debrief;
  if (!debrief || !isPhoneCallDebrief(debrief)) return null;
  return <CallDebrief debrief={debrief} />;
}

/**
 * Bubble action row (UXR Lot 1): Copy + response-feedback chips (QW-5,
 * ADR-138) in flow at the bubble's bottom — the interest-notification
 * pattern; the former top-right overlay covered the first text lines on
 * mobile. The execution-trace disclosure sits at the row's RIGHT edge (QA
 * feedback 2026-07-23), its expanded panel wrapping to a full-width line.
 * Extracted from the render hotspot (CC discipline).
 */
function AssistantActionRow({
  copied,
  onCopy,
  feedbackProps,
  proactiveFeedback,
  trace,
  message,
  onRetry,
  onPrefillComposer,
}: {
  copied: boolean;
  onCopy: () => void;
  feedbackProps: ResponseFeedbackButtonsProps | null;
  /** Proactive notification verdicts — mutually exclusive with `feedbackProps`
   *  (`responseFeedbackProps` returns null for proactive bubbles). */
  proactiveFeedback: React.ReactNode;
  trace?: ExecutionTrace;
  /** The bubble being decorated — read for its pinned retry prompt. */
  message: Message;
  /** W3: wired only on the latest error bubble (the list decides). */
  onRetry?: (prompt: string) => void;
  /** Peers Lot 7: composer prefill for the Reply quick-action (never sends). */
  onPrefillComposer?: (text: string) => void;
}) {
  const { t } = useTranslation();
  const retryPrompt = retryPromptOf(message);
  return (
    <div className="flex flex-wrap items-center gap-1 mt-2 pt-2 border-t border-border/30">
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            onClick={onCopy}
            aria-label={t('chat.message.copy')}
            className="p-1.5 rounded-md border border-border/30 bg-background/80 hover:bg-background transition-colors"
          >
            {copied ? (
              <Check className="h-3.5 w-3.5 text-green-600" />
            ) : (
              <Copy className="h-3.5 w-3.5 text-muted-foreground" />
            )}
          </button>
        </TooltipTrigger>
        <TooltipContent>{t('chat.message.copy')}</TooltipContent>
      </Tooltip>
      {/* UX P4: share/export menu — same chip family as Copy. Text-less
          bubbles (image-only answers) have nothing to share or export:
          `navigator.share({ text: '' })` rejects and the .md would be empty. */}
      {message.content.trim().length > 0 && (
        <ShareResponseMenu
          content={message.content}
          timestamp={message.timestamp}
          onPrefillComposer={onPrefillComposer}
        />
      )}
      {/* W3: a failed turn used to be a dead end — the user had to find their
          question and retype it. Labelled, not icon-only: this one re-runs a
          request that may cost tokens, so it must read as a deliberate act. */}
      {retryPrompt && onRetry && (
        <button
          type="button"
          onClick={() => onRetry(retryPrompt)}
          className="inline-flex items-center gap-1.5 rounded-md border border-border/30 bg-background/80 px-2 py-1 text-xs font-medium text-foreground/90 hover:bg-background transition-colors"
        >
          <RotateCcw className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
          {t('chat.message.retry')}
        </button>
      )}
      {feedbackProps && <ResponseFeedbackButtons {...feedbackProps} />}
      {proactiveFeedback}
      {/* Peers Lot 7: reply/block on relayed messages, accept/decline on
          incoming connection requests — self-gated on the metadata. */}
      <PeerMessageActions metadata={message.metadata} onPrefillComposer={onPrefillComposer} />
      <ExecutionTraceDisclosure trace={trace} />
    </div>
  );
}

/**
 * Assistant bubble surface classes (module-level — CC discipline).
 *
 * Peers program (Lot 7): peer notifications (`proactive_peer_*` metadata)
 * carry a subtle primary tint so relayed messages and connection events read
 * at a glance among answers. Every OTHER proactive notification (interest,
 * heartbeat, phone-call debrief…) carries a light red tint (owner request
 * 2026-08-05): LIA speaking first is a different event from LIA answering,
 * and the history must show it without reading. Ordinary answers — error
 * bubbles included, whose `metadata.type` is `error` — keep the card glass.
 */
function assistantBubbleSurface(metadata: Record<string, unknown> | undefined): string {
  const rawType = metadata?.type;
  const type = typeof rawType === 'string' ? rawType : '';
  if (type.startsWith('proactive_peer')) {
    return 'bg-primary/10 border-primary/25 hover:bg-primary/15';
  }
  if (type.startsWith('proactive_')) {
    return 'bg-destructive/10 border-destructive/25 hover:bg-destructive/15';
  }
  return 'bg-card/70 border-border/20 hover:bg-card/80';
}

/**
 * N2: say that a generated image does not last forever.
 *
 * Generated images are attachments with an `expires_at`, and a scheduler purges
 * them every 6 hours. The card offered a download button but never a reason to
 * use it — the image simply vanished from the history a day later.
 *
 * The deadline always comes from the backend: `attachments_ttl_hours` is
 * configurable, so a "24 h" written here would eventually be a lie. No
 * deadline (history predating N2) means no notice at all.
 */
function ImageExpiryNotice({
  expiresAt,
  expiredKey = 'chat.image_expiry.expired',
}: {
  expiresAt?: string | null;
  /**
   * Only the "expired" copy names the artefact ("this image/document…") —
   * document cards (ADR-226) pass their own key; the countdown copy is
   * artefact-agnostic and stays shared.
   */
  expiredKey?: string;
}) {
  const { t, i18n } = useTranslation();
  // Read once per render: the notice is informational, not a live countdown —
  // a ticking timer on every image card would re-render the whole thread.
  const expiry = classifyImageExpiry(expiresAt, new Date());
  if (expiry.kind === 'unknown') return null;

  if (expiry.kind === 'expired') {
    return <p className="mt-1 text-[11px] text-muted-foreground">{t(expiredKey)}</p>;
  }

  const at = expiry.at.toLocaleString(i18n.language, {
    dateStyle: 'short',
    timeStyle: 'short',
  });
  return (
    <p
      className={cn(
        'mt-1 text-[11px]',
        expiry.kind === 'soon' ? 'text-amber-600 dark:text-amber-500' : 'text-muted-foreground'
      )}
    >
      {expiry.kind === 'soon'
        ? t('chat.image_expiry.soon', { count: expiry.hoursLeft })
        : t('chat.image_expiry.until', { date: at })}
    </p>
  );
}

/**
 * AI-generated image cards — rendered outside markdown to avoid
 * HTML nesting violations (<div> inside <p>).
 * Uses relative URLs served by the reverse proxy in production.
 * In dev with self-signed certs, images may not load through the proxy.
 */
function GeneratedImageCards({ images }: { images: GeneratedImage[] }) {
  const { t } = useTranslation();
  const [lightboxImage, setLightboxImage] = useState<{ url: string; alt: string } | null>(null);

  return (
    <>
      <div className="mt-3 space-y-3">
        {images.map((img, i) => {
          // Use relative URL to go through Next.js rewrite proxy
          const displayUrl = img.url;
          return (
            <div key={i} className="group relative w-full max-w-[512px] mx-auto">
              {/* Opening the lightbox is a real action: a native <button>
                  wraps ONLY the image (the download button stays a sibling —
                  no nested interactive controls). Enter/Space come for free
                  (audit F013). */}
              <button
                type="button"
                onClick={() => setLightboxImage({ url: displayUrl, alt: img.alt })}
                aria-label={t('common.expand_image')}
                className="block w-full p-0 border-0 bg-transparent cursor-pointer rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={displayUrl}
                  alt={img.alt}
                  className="w-full h-auto rounded-lg shadow-md hover:shadow-lg transition-shadow [-webkit-touch-callout:default]"
                />
              </button>
              {/* Discrete download button — visible on hover (desktop) or always visible (touch) */}
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    type="button"
                    onClick={e => {
                      e.stopPropagation();
                      downloadImage(displayUrl, img.alt);
                    }}
                    className="absolute bottom-2 right-2 p-1.5 rounded-full bg-black/50 text-white opacity-0 group-hover:opacity-100 transition-opacity hover:bg-black/70 max-sm:opacity-70"
                    aria-label={t('common.download')}
                  >
                    <Download className="w-4 h-4" />
                  </button>
                </TooltipTrigger>
                <TooltipContent>{t('common.download')}</TooltipContent>
              </Tooltip>
              <ImageExpiryNotice expiresAt={img.expires_at} />
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

/** Viewer/open target for a generated document (ADR-226, amendment 2026-08-18).
 *
 * PDF opens its inline attachment URL directly (native browser viewer);
 * every other type opens the HTML document viewer page, which renders csv as
 * a table, md through the sanitized pipeline, txt as text, and offers an
 * honest download panel for office formats. The attachment id is the URL's
 * last segment by construction (`/api/v1/attachments/{id}`).
 */
function documentOpenHref(doc: GeneratedDocument, lng: string): string {
  if (doc.doc_type === 'pdf') return doc.url;
  const id = doc.url.split('/').pop() ?? '';
  const params = new URLSearchParams({ name: doc.filename, type: doc.doc_type });
  return `/${lng}/dashboard/documents/${id}?${params.toString()}`;
}

/**
 * AI-generated document cards (ADR-226) — one row per document, rendered
 * outside markdown like the image cards. The card BODY is a real `<a>` that
 * OPENS the document in a new tab; a sibling icon link downloads it directly
 * (a download is a navigation, so both controls are anchors, never buttons).
 */
function GeneratedDocumentCards({ documents }: { documents?: GeneratedDocument[] }) {
  const { t, i18n } = useTranslation();
  // The empty-case guard lives HERE, not at the call site: ChatMessage is a
  // maximum-complexity hotspot and must not gain render branches.
  if (!documents || documents.length === 0) return null;
  return (
    <div className="mt-3 space-y-2">
      {documents.map((doc, i) => {
        const Icon = documentTypeIcon(doc.doc_type);
        return (
          <div
            key={i}
            data-testid="generated-document-card"
            className="flex items-center gap-3 rounded-lg border bg-card p-3 w-full max-w-[512px] mx-auto hover:shadow-md transition-shadow"
          >
            <a
              href={documentOpenHref(doc, i18n.language)}
              target="_blank"
              rel="noopener"
              className="flex items-center gap-3 min-w-0 flex-1 rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              aria-label={t('chat.document_card.open', { name: doc.filename })}
            >
              <Icon className="w-8 h-8 shrink-0 text-primary" aria-hidden="true" />
              {/* divs, not spans: the expiry notice renders a <p>, which is
                  valid flow content inside <a>/<div> but not inside <span> */}
              <div className="min-w-0 flex-1">
                <div className="truncate font-medium text-sm">{doc.filename}</div>
                <div className="text-xs text-muted-foreground">
                  {doc.doc_type.toUpperCase()} · {formatFileSize(doc.size_bytes)}
                </div>
                <ImageExpiryNotice
                  expiresAt={doc.expires_at}
                  expiredKey="chat.document_expiry.expired"
                />
              </div>
            </a>
            <Tooltip>
              <TooltipTrigger asChild>
                <a
                  href={doc.url}
                  download={doc.filename}
                  className="p-2 shrink-0 rounded-md hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  aria-label={t('chat.document_card.download', { name: doc.filename })}
                >
                  <Download className="w-4 h-4" aria-hidden="true" />
                </a>
              </TooltipTrigger>
              <TooltipContent>{t('common.download')}</TooltipContent>
            </Tooltip>
          </div>
        );
      })}
    </div>
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
        <div className="group relative w-full max-w-[512px] mx-auto">
          {/* Real action -> native button around the image (audit F013);
              the download button below stays a sibling. */}
          <button
            type="button"
            onClick={() => setLightboxOpen(true)}
            aria-label={t('common.expand_image')}
            className="block w-full p-0 border-0 bg-transparent cursor-pointer rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={screenshot.url}
              alt={screenshot.alt}
              className="w-full h-auto rounded-lg shadow-md hover:shadow-lg transition-shadow [-webkit-touch-callout:default]"
              crossOrigin="use-credentials"
            />
          </button>
          {/* Discrete download button — visible on hover (desktop) or always visible (touch) */}
          <button
            type="button"
            onClick={e => {
              e.stopPropagation();
              downloadImage(screenshot.url, screenshot.alt);
            }}
            className="absolute bottom-8 right-2 p-1.5 rounded-full bg-black/50 text-white opacity-0 group-hover:opacity-100 transition-opacity hover:bg-black/70 max-sm:opacity-70"
            aria-label={t('common.download')}
          >
            <Download className="w-4 h-4" />
          </button>
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
            {/* role="presentation": the click handler is pure event
                plumbing (stopPropagation so clicking the image never closes
                the dialog) — not an interaction (audit F013). */}
            <div role="presentation" onClick={e => e.stopPropagation()}>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={expandedImage.url}
                alt={expandedImage.filename}
                className="max-w-[85vw] max-h-[75dvh] mobile:max-w-[70vw] mobile:max-h-[70dvh] object-contain rounded-lg shadow-2xl"
                {...(expandedImage.url.startsWith('blob:')
                  ? {}
                  : { crossOrigin: 'use-credentials' as const })}
              />
            </div>
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
export const ChatMessage: React.FC<ChatMessageProps> = memo(props => {
  const { message, isUser, isLatestAssistant = false, isActiveStream = false, onRetry } = props;
  // Streaming styling on the active bubble only: dim/pulse the execution-step
  // lines during the progress phase, blinking caret while the answer streams.
  const streamClass = isActiveStream
    ? props.streamPhase === 'progress'
      ? 'progress-steps'
      : 'stream-caret'
    : '';
  // One-shot cross-fade on the progress → answer flip: the markdown wrapper is
  // keyed 'progress' during the steps phase and 'content' from the first real
  // token onwards — exactly one remount per response, none at stream end.
  const markdownKey = isActiveStream && props.streamPhase === 'progress' ? 'progress' : 'content';
  const phaseFadeClass =
    isActiveStream && props.streamPhase === 'answer' ? 'animate-phase-fade' : undefined;
  const { i18n, t } = useTranslation();
  const { user } = useAuth();
  const isSystem = message.role === 'system';
  const locale = getIntlLocale(i18n.language as Language);
  const showTokens = user?.tokens_display_enabled ?? false;

  // Verdict chosen during this session on a proactive notification. The
  // persisted one is read from the metadata inside `proactiveFeedbackProps`;
  // this only covers the window between the click and the metadata catching
  // up, and must carry the ACTUAL verdict — a boolean would show a thumbs-up
  // to someone who pressed thumbs-down.
  const [justSubmittedVerdict, setJustSubmittedVerdict] = useState<
    ProactiveFeedbackVerdict | undefined
  >(undefined);

  // Copy-to-clipboard UI state for assistant messages. The confirmation reset
  // timer is tracked so an unmount mid-confirmation never fires a stale
  // setState (timers-cleanup rule).
  const [copied, setCopied] = useState(false);
  const copiedTimerRef = useRef<number | null>(null);

  const handleCopyMessage = useCallback(async () => {
    try {
      // ADR-177: HTML-mode messages are flattened (dual-flavor write) so the
      // paste is readable text, not raw <div class="lia-response"> markup.
      await copyMessageToClipboard(message.content);
      setCopied(true);
      toast.success(t('chat.message.copied'));
      if (copiedTimerRef.current !== null) window.clearTimeout(copiedTimerRef.current);
      copiedTimerRef.current = window.setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error(t('chat.message.error'));
    }
  }, [message.content, t]);

  useEffect(() => {
    return () => {
      if (copiedTimerRef.current !== null) window.clearTimeout(copiedTimerRef.current);
    };
  }, []);

  // Psyche store — must be called before any early return (Rules of Hooks)
  const storeState = usePsycheStore();

  // Check if this is a proactive notification (interest, heartbeat, or future types)
  const isProactiveInterest = !isUser && isInterestNotificationMetadata(message.metadata);
  const isProactiveMessage =
    !isUser &&
    typeof message.metadata?.type === 'string' &&
    (message.metadata.type as string).startsWith('proactive_');
  const feedbackRow = proactiveFeedbackProps(message.metadata, justSubmittedVerdict);
  // F4: the avatar wobbles once when a proactive notification lands live — never
  // on history rows. Captured in a mount effect (not in render) so the "now"
  // read stays pure; a history-loaded row is already stale at mount.
  const [proactiveRing, setProactiveRing] = useState(false);
  useEffect(() => {
    if (
      (isProactiveInterest || isProactiveMessage) &&
      isFreshProactive(message.timestamp.getTime(), Date.now())
    ) {
      setProactiveRing(true);
    }
    // Mount-only capture of "just arrived"; intentionally no dependencies.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Token data — proactive-vs-ordinary resolution extracted to a pure helper.
  const { tokensIn, tokensOut, tokensCache, costEur } = resolveTokenFields(
    message,
    isProactiveMessage
  );
  const googleApiRequests = message.googleApiRequests ?? 0;
  // Response feedback chips (QW-5) — null gates the render entirely.
  const feedbackProps = responseFeedbackProps(
    message,
    isProactiveInterest || isProactiveMessage,
    isActiveStream
  );

  const formatTime = (date: Date) => {
    const time = new Intl.DateTimeFormat(locale, {
      hour: '2-digit',
      minute: '2-digit',
    }).format(date);

    const now = new Date();
    const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const startOfDate = new Date(date.getFullYear(), date.getMonth(), date.getDate());
    const diffDays = Math.round((startOfToday.getTime() - startOfDate.getTime()) / 86_400_000);

    // Today: just the time (e.g. "14:30")
    if (diffDays === 0) return time;

    // Yesterday: localized label + time (e.g. "Hier 14:30")
    if (diffDays === 1) return `${t('chat.date.yesterday')} ${time}`;

    // Within the last week: weekday + time (e.g. "Lundi 14:30")
    if (diffDays >= 2 && diffDays <= 6) {
      const weekday = new Intl.DateTimeFormat(locale, {
        weekday: 'long',
      }).format(date);
      const weekdayCap = weekday.charAt(0).toLocaleUpperCase(locale) + weekday.slice(1);
      return `${weekdayCap} ${time}`;
    }

    // Older: full date | time (preserves previous behavior for historical messages)
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
  // Resolve psyche state: prefer per-message snapshot, fall back to live store.
  // storeState is read above (before early returns) to satisfy Rules of Hooks.
  const metadataPsyche = message.metadata?.psyche_state as PsycheStateSummary | undefined;
  const psycheState: PsycheStateSummary | null =
    metadataPsyche ??
    (storeState.enabled && storeState.displayAvatar
      ? {
          mood_label: storeState.moodLabel,
          mood_color: storeState.moodColor,
          mood_pleasure: storeState.moodPleasure,
          mood_arousal: storeState.moodArousal,
          mood_dominance: storeState.moodDominance,
          active_emotion: storeState.activeEmotion,
          emotion_intensity: storeState.emotionIntensity,
          relationship_stage: storeState.relationshipStage,
        }
      : null);

  // Build structured tooltip lines with PAD colors
  const tooltipLines: AvatarTooltipLine[] | undefined = psycheState
    ? [
        {
          label: t('psyche.relationshipStage', 'Relationship'),
          value: t(
            `psyche.stages.${psycheState.relationship_stage}`,
            psycheState.relationship_stage
          ),
        },
        {
          label: t('psyche.tooltip.mood', 'Mood'),
          value: t(`psyche.moods.${psycheState.mood_label}`, psycheState.mood_label),
          pad: {
            p: Math.round(psycheState.mood_pleasure * 100),
            a: Math.round(psycheState.mood_arousal * 100),
            d: Math.round(psycheState.mood_dominance * 100),
          },
        },
        ...(psycheState.active_emotion
          ? [
              {
                label: t('psyche.tooltip.emotion', 'Emotion'),
                value: `${t(`psyche.emotions.${psycheState.active_emotion}`, psycheState.active_emotion)} (${Math.round(psycheState.emotion_intensity * 100)}%)`,
              },
            ]
          : []),
      ]
    : undefined;

  if (!isUser) {
    return (
      <div className="mb-4 animate-message-enter mobile:flex mobile:flex-row-reverse mobile:gap-3">
        {/* Avatar — AssistantAvatar with psyche state (per-message or fallback) */}
        <div className="hidden mobile:block flex-shrink-0">
          <AssistantAvatar
            psycheState={psycheState}
            tooltipLines={tooltipLines}
            animate={!metadataPsyche && !!psycheState}
            animateEmoji={isLatestAssistant}
            ring={proactiveRing}
          />
        </div>

        {/* Message bubble - Full width on mobile, flex-1 on tablet/desktop */}
        <div className="group flex flex-col w-full mobile:flex-1 items-end">
          <div
            className={`relative message-bubble message-bubble-assistant px-4 py-3 rounded-xl shadow-md backdrop-blur-md text-foreground rounded-tr-none border hover:shadow-lg hover:border-primary/30 mobile:rounded-tr-xl transition-colors ${assistantBubbleSurface(message.metadata)} ${streamClass}`}
          >
            {/* Skill indicator — top of bubble, always visible when a skill is active */}
            {message.skillName && (
              <div className="flex items-center gap-1.5 mb-2 pb-2 border-b border-border/30">
                <span className="badge-glimmer text-[10px] px-1.5 py-0.5 rounded border bg-cyan-500/20 text-cyan-400 border-cyan-500/30 font-medium tracking-wide">
                  ✦ {message.skillName}
                </span>
              </div>
            )}
            {/* Browser screenshot — displayed first as visual context for the response */}
            {message.browserScreenshot && (
              <BrowserScreenshotCard screenshot={message.browserScreenshot} />
            )}
            {/* C-02: the selection-actions scope — one marker per assistant
                bubble, so a selection spanning TWO answers resolves to two
                different scopes and is refused (quoting across answers would
                stitch unrelated sentences). */}
            <div key={markdownKey} className={phaseFadeClass} data-selection-scope="assistant">
              <MarkdownContent
                content={message.content}
                isUser={false}
                searchHighlight={props.searchHighlight}
              />
            </div>
            {/* AI-generated images — inside bubble after text content */}
            {message.generatedImages && message.generatedImages.length > 0 && (
              <GeneratedImageCards images={message.generatedImages} />
            )}
            {/* AI-generated document cards (ADR-226) — same slot, below images;
                the component renders null without documents (hotspot CC rule) */}
            <GeneratedDocumentCards documents={message.generatedDocuments} />
            {/* T01: structured debrief under a post-call report (renders
                nothing for every other message — the block owns its checks). */}
            <PhoneCallDebriefBlock metadata={message.metadata} />
            {/* Bubble action row (UXR Lot 1) — hidden while streaming: an
                in-flow row at the growing edge would jitter on every token.
                Hosts the execution-trace disclosure at its right edge (the
                trace only lands with done metadata, after streaming). */}
            {!isActiveStream && (
              <AssistantActionRow
                copied={copied}
                onCopy={handleCopyMessage}
                feedbackProps={feedbackProps}
                proactiveFeedback={
                  feedbackRow ? (
                    <ProactiveFeedbackButtons
                      {...feedbackRow}
                      onFeedbackSubmitted={setJustSubmittedVerdict}
                    />
                  ) : null
                }
                trace={message.executionTrace}
                message={message}
                onRetry={onRetry}
                onPrefillComposer={props.onPrefillComposer}
              />
            )}
          </div>
          <span className="text-[11px] mobile:text-xs text-muted-foreground mt-1.5 px-1 font-medium whitespace-nowrap w-full text-right">
            {formatTime(message.timestamp)}
            {/* ADR-117 Lot 3: partial answer of a cancelled/interrupted run.
                Same metadata flag for live bubbles (synthesized done) and
                archived history rows. */}
            {Boolean(message.metadata?.interrupted) && (
              <span className="text-amber-500" title={t('chat.message.interrupted_tooltip')}>
                {' '}
                ⏸ {t('chat.message.interrupted')}
              </span>
            )}
            {tokensIn !== undefined && showTokens && (
              <span className="hidden mobile:inline">
                {' | '}
                <span className="text-orange-500">🟠 {formatNumber(tokensIn)} IN</span>{' '}
                <span className="text-green-600">🟢 {formatNumber(tokensOut || 0)} OUT</span>{' '}
                <span className="text-blue-500">🔵 {formatNumber(tokensCache)} CACHE</span>{' '}
                <span className="text-purple-500">🟣 {formatNumber(googleApiRequests)} GOOGLE</span>
                {/* Paid-TTS detail: characters synthesised. NULL/absent for
                    Edge (free) → no badge, mirror Sherpa local STT. */}
                {message.ttsCharacters != null && message.ttsCharacters > 0 && (
                  <>
                    {' '}
                    <span
                      className="text-pink-500"
                      title={
                        message.ttsProvider
                          ? t('chat.message.tts_tooltip_provider', {
                              provider: message.ttsProvider,
                              model: message.ttsModel ? ` · ${message.ttsModel}` : '',
                            })
                          : t('chat.message.tts_tooltip_fallback')
                      }
                    >
                      🔊 {formatNumber(message.ttsCharacters)} {t('chat.message.tts_unit_chars')}
                    </span>
                  </>
                )}
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
          <MarkdownContent
            content={message.content}
            isUser={true}
            searchHighlight={props.searchHighlight}
          />
        </div>
        <span className="text-[11px] mobile:text-xs text-muted-foreground mt-1.5 px-1 font-medium whitespace-nowrap w-full text-left">
          {formatTime(message.timestamp)}
          {/* Voice source indicator (only for voice messages) */}
          {message.source === 'voice' && (
            <span className="hidden mobile:inline">
              {' | '}
              <span className="text-purple-500">
                🎤{' '}
                {(message.sttAudioDurationSeconds ?? message.audioDurationSeconds)?.toFixed(1) ??
                  '?'}
                {t('chat.message.stt_unit_seconds')}
              </span>
              {/* Remote-STT per-message cost (NULL for typed text and local Sherpa) */}
              {message.sttCostEur != null && message.sttCostEur > 0 && showTokens && (
                <>
                  {' • '}
                  <span
                    className="text-foreground font-semibold"
                    title={
                      message.sttProvider
                        ? t('chat.message.stt_tooltip_provider', {
                            provider: message.sttProvider,
                          })
                        : t('chat.message.stt_tooltip_fallback')
                    }
                  >
                    {formatEuro(message.sttCostEur, 6)}
                  </span>
                </>
              )}
            </span>
          )}
        </span>
      </div>
    </div>
  );
});
ChatMessage.displayName = 'ChatMessage';
