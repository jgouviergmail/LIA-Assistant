'use client';
/** Show the actual search service and its sources without executing provider markup. */
import type { ComponentProps } from 'react';
import { useTranslation } from '@/i18n/client';
import type { ResearchProposal } from '@/lib/selection-assist/contracts';
import { SelectionAnswerView } from './SelectionAnswerView';

export function SelectionResearch({
  proposal,
  ...view
}: Omit<ComponentProps<typeof SelectionAnswerView>, 'text' | 'children'> & {
  proposal: ResearchProposal;
}) {
  const { t } = useTranslation(view.lng);
  const provider = t(`selectionAssist.providers.${proposal.provider}`);
  const text = [
    provider,
    proposal.query,
    proposal.summary,
    ...proposal.sources.map(
      (source, index) => `[${index + 1}] ${source.title}\n${source.excerpt}\n${source.url}`
    ),
    !proposal.sources.length ? t('selectionAssist.no_sources') : null,
  ]
    .filter(Boolean)
    .join('\n\n');
  return (
    <SelectionAnswerView {...view} text={text}>
      <div className="space-y-3 break-words text-sm leading-relaxed">
        <p className="text-muted-foreground">
          {provider} · {proposal.query}
        </p>
        {proposal.summary && <p className="whitespace-pre-wrap">{proposal.summary}</p>}
        {proposal.sources.length ? (
          <ol aria-label={t('selectionAssist.sources')} className="list-decimal space-y-3 pl-5">
            {proposal.sources.map((source, index) => (
              <li key={`${index}:${source.url}`}>
                <a
                  href={source.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-primary underline underline-offset-2"
                >
                  {source.title}
                </a>
                {source.excerpt && <p className="mt-1">{source.excerpt}</p>}
              </li>
            ))}
          </ol>
        ) : (
          <p role="status">{t('selectionAssist.no_sources')}</p>
        )}
      </div>
    </SelectionAnswerView>
  );
}
