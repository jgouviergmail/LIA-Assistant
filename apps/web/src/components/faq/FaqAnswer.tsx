'use client';

/**
 * A FAQ answer whose written examples are actionable (W1).
 *
 * The answers hold hundreds of ready-made instructions addressed to LIA,
 * authored and translated across six languages, that until now could only be
 * read and retyped. Each bulleted one becomes a button that prefills the chat
 * composer through the existing `?draft=` rail — the same rail the onboarding
 * examples, the briefing cards and the open-loop entries already use.
 *
 * Rendering contract:
 *  - the surrounding HTML keeps its existing `dangerouslySetInnerHTML` path,
 *    unchanged: it is content compiled from the repository, which the repo
 *    charter allows;
 *  - each command is a real React `<button>` whose text is passed as children,
 *    hence auto-escaped. The XSS posture is strictly unchanged, and the
 *    interactive parts are focusable and nameable like any other control.
 *
 * The prefill NEVER sends. Landing in the composer with the phrase ready is
 * the point: the user can read it, edit it, and decide.
 */

import { useTranslation } from '@/i18n/client';
import { type Language } from '@/i18n/settings';

import { splitFaqAnswer } from './faq-examples';

export interface FaqAnswerProps {
  /** Current URL locale — same instance the surrounding page translates with. */
  lng: Language;
  /** Authored HTML of the answer (already highlighted when searching). */
  html: string;
  /** Called with the phrase to prefill; the caller owns the navigation. */
  onExampleClick?: (text: string) => void;
}

export function FaqAnswer({ lng, html, onExampleClick }: FaqAnswerProps) {
  const { t } = useTranslation(lng);
  const segments = splitFaqAnswer(html);

  // Without a handler the page keeps its previous, purely readable rendering —
  // no dangling buttons that would do nothing when pressed.
  if (!onExampleClick) {
    return <div dangerouslySetInnerHTML={{ __html: html }} />;
  }

  return (
    <div>
      {segments.map((segment, index) =>
        segment.kind === 'html' ? (
          <span key={index} dangerouslySetInnerHTML={{ __html: segment.html }} />
        ) : (
          <button
            key={index}
            type="button"
            onClick={() => onExampleClick(segment.text)}
            // Named beyond its own text: "Trouve le contact de Jean" alone does
            // not say what pressing it does.
            aria-label={t('faq.try_example', { example: segment.text })}
            className="italic text-left underline decoration-dotted decoration-primary/40 underline-offset-2 hover:text-primary hover:decoration-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-sm transition-colors"
          >
            {segment.text}
          </button>
        )
      )}
    </div>
  );
}
