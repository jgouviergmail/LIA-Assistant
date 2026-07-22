'use client';

import { useMemo, useState } from 'react';
import { ChevronDown, Search, X } from 'lucide-react';
import { useTranslation } from '@/i18n/client';
import { type Language } from '@/i18n/settings';
import { normalizeSearchText } from '@/lib/utils';
import { highlightText, stripHtml } from '@/lib/faq-search';
import { splitAnswerGroups } from '@/lib/faq-answer-groups';
import { FAQ_SECTION_ICONS, PUBLIC_FAQ_SECTIONS } from './faq-sections';

/**
 * Public landing FAQ (signed-out visitors) — speaks the landing's visual
 * language: icon section headers, card accordions, chip anchor rail. Content
 * comes verbatim from the shared `faq.sections.*` translations; the only
 * transformation is presentation (the long grouped answers render as
 * per-domain sub-accordions via splitAnswerGroups — content preserved, see
 * lib/__tests__/faq-answer-groups.test.ts).
 */

interface PublicFAQContentProps {
  lng: Language;
}

interface PublicFaqQuestion {
  section: string;
  questionKey: string;
  question: string;
  answer: string;
}

/** Typography for answer HTML from the locale files (links become visible). */
const ANSWER_PROSE_CLASS =
  'prose prose-sm dark:prose-invert max-w-none text-muted-foreground ' +
  '[&_a]:text-primary [&_a]:underline [&_a]:underline-offset-2';

/**
 * One answer body. Long grouped answers ("What can I ask LIA?") render as
 * collapsible per-domain groups; everything else renders as-is. While a
 * search is active the flat rendering (with highlights) always wins so no
 * match hides inside a collapsed group.
 */
function AnswerBody({ answer, searchQuery }: { answer: string; searchQuery: string }) {
  const searching = searchQuery.trim().length > 0;
  const grouped = searching ? null : splitAnswerGroups(answer);

  if (!grouped) {
    return (
      <div
        className={ANSWER_PROSE_CLASS}
        dangerouslySetInnerHTML={{
          __html: searching ? highlightText(answer, searchQuery) : answer,
        }}
      />
    );
  }

  return (
    <div className="space-y-3">
      {grouped.intro && (
        <div className={ANSWER_PROSE_CLASS} dangerouslySetInnerHTML={{ __html: grouped.intro }} />
      )}
      <div className="space-y-2">
        {/* Index keys are correct here: the list derives from one static
            translation string — never reordered, inserted into or filtered. */}
        {grouped.groups.map((group, groupIndex) => (
          <details
            key={groupIndex}
            className="group/domain rounded-lg border border-border/60 bg-background overflow-hidden"
          >
            <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-2.5 text-sm font-semibold hover:bg-muted/40 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring [&::-webkit-details-marker]:hidden">
              <span dangerouslySetInnerHTML={{ __html: group.heading }} />
              <ChevronDown
                aria-hidden="true"
                className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-open/domain:rotate-180"
              />
            </summary>
            <ul className="space-y-1.5 border-t border-border/40 px-4 py-3 text-sm text-muted-foreground [&_li]:pl-1 list-disc list-inside marker:text-primary">
              {group.items.map((item, itemIndex) => (
                <li key={itemIndex} dangerouslySetInnerHTML={{ __html: item }} />
              ))}
            </ul>
          </details>
        ))}
      </div>
    </div>
  );
}

export function PublicFAQContent({ lng }: PublicFAQContentProps) {
  const { t } = useTranslation(lng);
  const [searchQuery, setSearchQuery] = useState('');

  const faqData = useMemo(() => {
    const data: PublicFaqQuestion[] = [];
    PUBLIC_FAQ_SECTIONS.forEach(section => {
      const questionCount = parseInt(t(`faq.sections.${section}.count`));
      for (let i = 1; i <= questionCount; i++) {
        data.push({
          section,
          questionKey: `q${i}`,
          question: t(`faq.sections.${section}.questions.q${i}.question`),
          answer: t(`faq.sections.${section}.questions.q${i}.answer`),
        });
      }
    });
    return data;
  }, [t]);

  // Accent-insensitive filter over question + answer text (same semantics as
  // the dashboard FAQ — shared helpers).
  const filteredData = useMemo(() => {
    if (!searchQuery.trim()) return null;
    const normalizedQuery = normalizeSearchText(searchQuery.trim());
    return faqData.filter(
      item =>
        normalizeSearchText(item.question).includes(normalizedQuery) ||
        normalizeSearchText(stripHtml(item.answer)).includes(normalizedQuery)
    );
  }, [faqData, searchQuery]);

  const isSearching = searchQuery.trim().length > 0;
  const resultsCount = filteredData?.length ?? 0;

  const matchingBySection = useMemo(() => {
    const map = new Map<string, Set<string>>();
    filteredData?.forEach(item => {
      if (!map.has(item.section)) map.set(item.section, new Set());
      map.get(item.section)!.add(item.questionKey);
    });
    return map;
  }, [filteredData]);

  return (
    <div className="space-y-8">
      {/* Search */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <input
          type="text"
          value={searchQuery}
          onChange={e => setSearchQuery(e.target.value)}
          placeholder={t('faq.search.placeholder')}
          aria-label={t('faq.search.placeholder')}
          className="flex h-11 w-full rounded-xl border border-input bg-card pl-10 pr-10 py-2 text-base shadow-sm transition-all duration-200 placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:border-primary hover:border-primary/50 md:text-sm"
        />
        {searchQuery && (
          <button
            onClick={() => setSearchQuery('')}
            title={t('faq.search.clear')}
            className="absolute right-3 top-1/2 -translate-y-1/2 h-5 w-5 rounded-full bg-muted hover:bg-muted-foreground/20 flex items-center justify-center transition-colors"
          >
            <X className="h-3 w-3 text-muted-foreground" />
          </button>
        )}
        {isSearching && (
          <p className="mt-2 text-sm text-muted-foreground">
            {resultsCount > 0
              ? t('faq.search.results_count', { count: resultsCount })
              : t('faq.search.no_results', { query: searchQuery })}
          </p>
        )}
      </div>

      {/* Section anchor rail — the page's overview at a glance */}
      {!isSearching && (
        <nav aria-label={t('faq.title')} className="flex flex-wrap gap-2">
          {PUBLIC_FAQ_SECTIONS.map(section => {
            const Icon = FAQ_SECTION_ICONS[section];
            return (
              <a
                key={section}
                href={`#faq-${section}`}
                className="inline-flex items-center gap-1.5 rounded-full border border-border bg-card px-3.5 py-1.5 text-xs text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <Icon aria-hidden="true" className="h-3.5 w-3.5 text-primary" />
                {t(`faq.sections.${section}.title`)}
              </a>
            );
          })}
        </nav>
      )}

      {/* No results */}
      {isSearching && resultsCount === 0 && (
        <div className="rounded-xl border border-border bg-card p-8 text-center">
          <Search className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
          <p className="text-lg font-medium text-muted-foreground">
            {t('faq.search.no_results', { query: searchQuery })}
          </p>
          <p className="text-sm text-muted-foreground mt-1">{t('faq.search.no_results_hint')}</p>
        </div>
      )}

      {/* Sections */}
      {PUBLIC_FAQ_SECTIONS.map(section => {
        const Icon = FAQ_SECTION_ICONS[section];
        const questionCount = parseInt(t(`faq.sections.${section}.count`));
        const matchingKeys = matchingBySection.get(section);
        if (isSearching && !matchingKeys) return null;

        return (
          <section key={section} id={`faq-${section}`} className="scroll-mt-24">
            <div className="mb-4 flex items-center gap-3">
              <div className="rounded-lg bg-primary/10 p-2">
                <Icon aria-hidden="true" className="h-5 w-5 text-primary" />
              </div>
              <div>
                <h2 className="text-2xl font-semibold tracking-tight">
                  {t(`faq.sections.${section}.title`)}
                </h2>
                <p className="text-sm text-muted-foreground">
                  {t(`faq.sections.${section}.description`)}
                </p>
              </div>
            </div>

            <div className="space-y-3">
              {Array.from({ length: questionCount }, (_, i) => `q${i + 1}`).map(questionKey => {
                if (isSearching && matchingKeys && !matchingKeys.has(questionKey)) return null;
                const question = t(`faq.sections.${section}.questions.${questionKey}.question`);
                const answer = t(`faq.sections.${section}.questions.${questionKey}.answer`);

                return (
                  <details
                    key={`${section}-${questionKey}-${isSearching}`}
                    open={isSearching || undefined}
                    className="group rounded-xl border border-border/60 bg-card overflow-hidden transition-colors hover:border-primary/30"
                  >
                    <summary className="flex cursor-pointer list-none items-start justify-between gap-3 px-5 py-4 text-left font-medium hover:bg-muted/40 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring [&::-webkit-details-marker]:hidden">
                      {isSearching ? (
                        <span
                          dangerouslySetInnerHTML={{
                            __html: highlightText(question, searchQuery),
                          }}
                        />
                      ) : (
                        <span>{question}</span>
                      )}
                      <ChevronDown
                        aria-hidden="true"
                        className="mt-0.5 h-5 w-5 shrink-0 text-muted-foreground transition-transform group-open:rotate-180"
                      />
                    </summary>
                    <div className="border-t border-border/40 px-5 pb-5 pt-4">
                      <AnswerBody answer={answer} searchQuery={searchQuery} />
                    </div>
                  </details>
                );
              })}
            </div>
          </section>
        );
      })}
    </div>
  );
}
