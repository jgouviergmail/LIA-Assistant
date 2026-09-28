'use client';

/**
 * The articles a session cited, under the programme (ADR-324).
 *
 * Each article folds, and a folded one costs nothing: its reader mounts only
 * while it is open — and the original stays one click away beside it, so the
 * article can be read at its outlet without asking for a translation. Opened, it is read whole when the newsroom could read it —
 * else the outlet's summary, said as such — in the listener's language,
 * translated when its feed speaks another. What the page shows says what it
 * is: a cut, a translation that could not be made (the original then), one
 * the listener's radio budget no longer pays for (the original, said so), and
 * what the reading cost; a translation read back from the shared cache costs
 * nothing, and says so.
 *
 * Every text here was written by a stranger: it is rendered as children, and
 * only a web address ever becomes a link, opened without a referrer.
 */

import { ExternalLink, FileText, Newspaper, RotateCcw } from 'lucide-react';
import { useId } from 'react';

import { Button } from '@/components/ui/button';
import { Disclosure } from '@/components/ui/disclosure';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { useRadioArticle } from '@/hooks/useRadioArticle';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { languageName, paragraphs, type RadioArticleRef } from '@/lib/radio/articles';
import { radioCost, webUrl } from '@/lib/radio/format';
import type { RadioArticle } from '@/lib/radio/types';

/** What the page says about an article: translated from what, cut, summary alone, cost. */
function ArticleNotes({ lng, article }: { lng: Language; article: RadioArticle }) {
  const { t } = useTranslation(lng);
  const notes: string[] = [];
  if (article.translated) {
    notes.push(
      article.source_language === null
        ? t('radio.article.translated_unknown')
        : t('radio.article.translated', {
            language: languageName(article.source_language, lng),
          })
    );
  }
  if (article.translation_failed) notes.push(t('radio.article.translation_failed'));
  if (article.budget_reached) notes.push(t('radio.article.budget_reached'));
  if (!article.complete) notes.push(t('radio.article.summary_only'));
  if (article.cut) notes.push(t('radio.article.cut'));
  // A reading that translated nothing spent nothing: only a translation, made
  // or refused after the call, has a cost to say.
  const cost =
    article.translated || article.translation_failed ? radioCost(article.cost_eur, lng) : null;
  if (cost !== null) notes.push(t('radio.article.cost', { cost }));
  if (notes.length === 0) return null;
  return (
    <ul className="space-y-0.5 text-xs text-muted-foreground">
      {notes.map(note => (
        <li key={note}>{note}</li>
      ))}
    </ul>
  );
}

function ArticleText({ lng, article }: { lng: Language; article: RadioArticle }) {
  const { t } = useTranslation(lng);
  const titleId = useId();
  const href = webUrl(article.url);
  const body = paragraphs(article.text);
  return (
    <article className="space-y-3" aria-labelledby={titleId}>
      <h3 id={titleId} className="text-base font-semibold leading-snug">
        {article.title}
      </h3>
      <ArticleNotes lng={lng} article={article} />
      {body.length > 0 ? (
        <div className="space-y-3 text-sm leading-relaxed">
          {body.map((paragraph, index) => (
            // The paragraphs of one article never reorder: their place is their identity.
            <p key={index} className="whitespace-pre-line">
              {paragraph}
            </p>
          ))}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">{t('radio.article.empty')}</p>
      )}
      {href !== null && (
        <a
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-sm text-primary underline-offset-4 hover:underline"
        >
          {t('radio.article.read_original', { outlet: article.outlet })}
          <ExternalLink className="h-3 w-3" aria-hidden="true" />
        </a>
      )}
    </article>
  );
}

/** One opened article: read (and translated) on mount, said while it waits, retried on request. */
function ArticleReader({ lng, articleId }: { lng: Language; articleId: string }) {
  const { t } = useTranslation(lng);
  const { article, loading, failed, retry } = useRadioArticle(articleId);
  if (article !== undefined) return <ArticleText lng={lng} article={article} />;
  if (failed && !loading) {
    return (
      <div role="alert" className="flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
        <span>{t('radio.article.error')}</span>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="gap-2"
          onClick={() => void retry()}
        >
          <RotateCcw className="h-4 w-4" aria-hidden="true" />
          {t('common.retry')}
        </Button>
      </div>
    );
  }
  return (
    <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground">
      <LoadingSpinner size="sm" aria-hidden="true" />
      {t('radio.article.loading')}
    </p>
  );
}

/** The article at its outlet, beside its fold: reached without opening (translating) it. */
function OriginalLink({ lng, article }: { lng: Language; article: RadioArticleRef }) {
  const { t } = useTranslation(lng);
  const href = webUrl(article.url);
  if (href === null) return null;
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      // The name opens with the visible word (label in name) and says where it goes.
      aria-label={t('radio.article.original_label', { outlet: article.outlet })}
      // At least 24 px tall: a control of its own, not a link inside a sentence (WCAG 2.5.8).
      className="mt-2 inline-flex min-h-6 shrink-0 items-center gap-1 rounded-md px-1.5 py-1 text-xs text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      {t('radio.article.original')}
      <ExternalLink className="h-3 w-3" aria-hidden="true" />
    </a>
  );
}

function publishedOn(publishedAt: string | null, lng: Language): string | undefined {
  if (publishedAt === null) return undefined;
  const date = new Date(publishedAt);
  return Number.isNaN(date.getTime())
    ? undefined
    : new Intl.DateTimeFormat(lng, { dateStyle: 'medium', timeStyle: 'short' }).format(date);
}

export function RadioArticles({
  lng,
  articles,
}: {
  lng: Language;
  articles: readonly RadioArticleRef[];
}) {
  const { t } = useTranslation(lng);
  const headingId = useId();
  if (articles.length === 0) return null;
  return (
    <section
      className="space-y-3 rounded-xl border bg-card p-4 shadow-sm"
      aria-labelledby={headingId}
    >
      <div className="space-y-1">
        <h2 id={headingId} className="flex items-center gap-2 text-base font-semibold">
          <Newspaper className="h-4 w-4 text-primary" aria-hidden="true" />
          {t('radio.article.section_title')}
        </h2>
        <p className="text-xs text-muted-foreground">{t('radio.article.section_description')}</p>
      </div>
      <ul className="space-y-2">
        {articles.map(ref => (
          <li key={ref.id} className="flex items-start gap-2">
            <Disclosure
              icon={FileText}
              title={ref.outlet}
              description={publishedOn(ref.publishedAt, lng)}
              className="min-w-0 flex-1"
            >
              <ArticleReader lng={lng} articleId={ref.id} />
            </Disclosure>
            <OriginalLink lng={lng} article={ref} />
          </li>
        ))}
      </ul>
    </section>
  );
}
