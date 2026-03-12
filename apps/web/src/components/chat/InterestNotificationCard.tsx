'use client';

import { memo, useState, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { ThumbsUp, ThumbsDown, Ban, Sparkles, ExternalLink } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { MarkdownContent } from './MarkdownContent';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';
import { getIntlLocale, Language } from '@/i18n/settings';
import { useApiMutation } from '@/hooks/useApiMutation';

// ============================================================================
// Types
// ============================================================================

/**
 * Proactive interest notification metadata.
 * Matches the structure from NotificationDispatcher.
 */
export interface InterestNotificationMetadata {
  type: 'proactive_interest';
  target_id: string;
  feedback_enabled: boolean;
  source?: 'wikipedia' | 'perplexity' | 'llm_reflection';
  article_url?: string;
  citations?: string[];
  sent_at?: string;
  run_id?: string;
}

/**
 * Type guard to validate InterestNotificationMetadata at runtime.
 * Ensures all required fields are present and correctly typed.
 */
export function isInterestNotificationMetadata(
  value: unknown
): value is InterestNotificationMetadata {
  if (!value || typeof value !== 'object') return false;

  const meta = value as Record<string, unknown>;

  return (
    meta.type === 'proactive_interest' &&
    typeof meta.target_id === 'string' &&
    meta.target_id.length > 0 &&
    typeof meta.feedback_enabled === 'boolean'
  );
}

interface InterestNotificationCardProps {
  content: string;
  metadata: InterestNotificationMetadata;
  timestamp: Date;
}

type FeedbackType = 'thumbs_up' | 'thumbs_down' | 'block';

interface FeedbackPayload {
  feedback: FeedbackType;
}

// ============================================================================
// Sub-components
// ============================================================================

/**
 * Source badge component.
 * Shows the content source with appropriate styling.
 */
function SourceBadge({
  source,
  url,
}: {
  source: 'wikipedia' | 'perplexity' | 'llm_reflection' | undefined;
  url?: string;
}) {
  const { t } = useTranslation();

  const sourceConfig: Record<
    string,
    { label: string; className: string }
  > = {
    wikipedia: {
      label: 'Wikipedia',
      className: 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200',
    },
    perplexity: {
      label: 'Perplexity',
      className: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200',
    },
    llm_reflection: {
      label: t('interests.sources.reflection'),
      className:
        'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200',
    },
  };

  const config = sourceConfig[source || 'llm_reflection'];

  if (url) {
    return (
      <a
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        className={cn(
          'inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium',
          'hover:opacity-80 transition-opacity',
          config.className
        )}
      >
        {config.label}
        <ExternalLink className="h-3 w-3" />
      </a>
    );
  }

  return (
    <span
      className={cn(
        'inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium',
        config.className
      )}
    >
      {config.label}
    </span>
  );
}

/**
 * Feedback buttons component.
 * Allows users to provide feedback on proactive notifications.
 */
function FeedbackButtons({
  disabled,
  onFeedback,
  isSubmitting,
  submittedFeedback,
}: {
  disabled: boolean;
  onFeedback: (feedback: FeedbackType) => void;
  isSubmitting: boolean;
  submittedFeedback: FeedbackType | null;
}) {
  const { t } = useTranslation();

  // If feedback was submitted, show confirmation
  if (submittedFeedback) {
    return (
      <span className="text-xs text-muted-foreground">
        {submittedFeedback === 'thumbs_up' && '👍'}
        {submittedFeedback === 'thumbs_down' && '👎'}
        {submittedFeedback === 'block' && '🚫'}
        <span className="ml-1">{t('interests.feedback.thanks')}</span>
      </span>
    );
  }

  const isDisabled = disabled || isSubmitting;

  return (
    <div className="flex items-center gap-1">
      <Button
        variant="ghost"
        size="icon"
        className="h-7 w-7 hover:bg-green-100 hover:text-green-600 dark:hover:bg-green-900/30"
        onClick={() => onFeedback('thumbs_up')}
        disabled={isDisabled}
        aria-label={t('interests.feedback.like')}
      >
        <ThumbsUp className="h-4 w-4" />
      </Button>

      <Button
        variant="ghost"
        size="icon"
        className="h-7 w-7 hover:bg-orange-100 hover:text-orange-600 dark:hover:bg-orange-900/30"
        onClick={() => onFeedback('thumbs_down')}
        disabled={isDisabled}
        aria-label={t('interests.feedback.dislike')}
      >
        <ThumbsDown className="h-4 w-4" />
      </Button>

      <Button
        variant="ghost"
        size="icon"
        className="h-7 w-7 hover:bg-red-100 hover:text-red-600 dark:hover:bg-red-900/30"
        onClick={() => onFeedback('block')}
        disabled={isDisabled}
        aria-label={t('interests.feedback.block')}
      >
        <Ban className="h-4 w-4" />
      </Button>
    </div>
  );
}

// ============================================================================
// Main Component
// ============================================================================

/**
 * InterestNotificationCard - Display proactive interest notifications in chat.
 *
 * Features:
 * - Distinct visual style from regular messages (amber/orange gradient)
 * - Source badge (Wikipedia, Perplexity, LLM reflection)
 * - Feedback buttons (thumbs up, thumbs down, block)
 * - Markdown content rendering
 * - Proper error handling with toast notifications
 */
export const InterestNotificationCard = memo(function InterestNotificationCard({
  content,
  metadata,
  timestamp,
}: InterestNotificationCardProps) {
  const { t, i18n } = useTranslation();
  const locale = getIntlLocale(i18n.language as Language);
  const [submittedFeedback, setSubmittedFeedback] = useState<FeedbackType | null>(null);

  // Use the project's standard API mutation hook
  const { mutate, loading: isSubmitting } = useApiMutation<FeedbackPayload, void>({
    method: 'POST',
    componentName: 'InterestNotificationCard',
    onError: () => {
      toast.error(t('interests.feedback.error'));
    },
  });

  const formatTime = useCallback(
    (date: Date) => {
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
    },
    [locale]
  );

  const handleFeedback = useCallback(
    async (feedback: FeedbackType) => {
      if (isSubmitting || submittedFeedback) return;

      try {
        await mutate(`/interests/${metadata.target_id}/feedback`, { feedback });
        setSubmittedFeedback(feedback);

        // Show appropriate toast based on feedback type
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
        // Error already handled by onError callback
        // No need to do anything here
      }
    },
    [mutate, metadata.target_id, isSubmitting, submittedFeedback, t]
  );

  return (
    <div className="mb-4 animate-message-enter">
      <div className="flex gap-3">
        {/* Sparkles icon */}
        <div className="flex-shrink-0">
          <div
            className={cn(
              'w-9 h-9 rounded-full flex items-center justify-center shadow-sm',
              'bg-gradient-to-br from-amber-400 to-orange-500',
              'text-white ring-2 ring-amber-300/50'
            )}
          >
            <Sparkles className="h-5 w-5" />
          </div>
        </div>

        {/* Card content */}
        <div className="flex-1 max-w-2xl">
          <div
            className={cn(
              'px-4 py-3 rounded-xl shadow-md',
              'bg-gradient-to-br from-amber-50 to-orange-50',
              'dark:from-amber-950/30 dark:to-orange-950/30',
              'border border-amber-200/50 dark:border-amber-800/30',
              'hover:shadow-lg transition-shadow'
            )}
          >
            {/* Header with source badge */}
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-medium text-amber-700 dark:text-amber-300">
                {t('interests.notification.title')}
              </span>
              <SourceBadge source={metadata.source} url={metadata.article_url} />
            </div>

            {/* Content */}
            <div className="text-foreground">
              <MarkdownContent content={content} isUser={false} />
            </div>

            {/* Footer with feedback */}
            {metadata.feedback_enabled && (
              <div className="mt-3 pt-2 border-t border-amber-200/50 dark:border-amber-800/30 flex items-center justify-between">
                <span className="text-xs text-muted-foreground">
                  {t('interests.notification.helpful')}
                </span>
                <FeedbackButtons
                  disabled={!metadata.feedback_enabled}
                  onFeedback={handleFeedback}
                  isSubmitting={isSubmitting}
                  submittedFeedback={submittedFeedback}
                />
              </div>
            )}
          </div>

          {/* Timestamp */}
          <span className="text-[11px] mobile:text-xs text-muted-foreground mt-1.5 px-1 font-medium block">
            {formatTime(timestamp)}
          </span>
        </div>
      </div>
    </div>
  );
});
