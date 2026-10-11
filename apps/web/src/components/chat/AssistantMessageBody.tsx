'use client';

import { LayoutList } from 'lucide-react';
import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';

import { Disclosure } from '@/components/ui/disclosure';
import { htmlToPlainText } from '@/lib/html-plain-text';
import { splitTrailingCards } from '@/lib/trailing-cards';
import { normalizeSearchText } from '@/lib/utils';
import { MarkdownContent } from './MarkdownContent';

interface AssistantMessageBodyProps {
  /** The assistant message as stored: words, then the cards appended after them. */
  content: string;
  /** The history-search term, highlighted in both parts. */
  searchHighlight?: string;
}

/** Whether a history-search term occurs in the cards' readable text. */
function cardsMatchSearch(cards: string, searchHighlight: string | undefined): boolean {
  const query = normalizeSearchText(searchHighlight?.trim() ?? '');
  return query !== '' && normalizeSearchText(htmlToPlainText(cards)).includes(query);
}

/**
 * An assistant answer, its data cards folded under one « Show details »
 * disclosure, closed by default.
 *
 * The cards are the server-rendered block the response node appends after the
 * model's words in the card display modes (`splitTrailingCards` recognises it,
 * conservatively); the words stay in view. A history-search match inside the
 * cards opens the fold — a closed `Disclosure` mounts nothing, so a match would
 * otherwise be invisible, the same rule as the cards' own « see more ». An
 * answer the split refuses (cards alone, a HITL draft card, prose only) renders
 * exactly as before.
 */
export function AssistantMessageBody({ content, searchHighlight }: AssistantMessageBodyProps) {
  const { t } = useTranslation();
  const split = useMemo(() => splitTrailingCards(content), [content]);

  if (!split) {
    return <MarkdownContent content={content} isUser={false} searchHighlight={searchHighlight} />;
  }
  const revealed = cardsMatchSearch(split.cards, searchHighlight);
  return (
    <>
      <MarkdownContent content={split.prose} isUser={false} searchHighlight={searchHighlight} />
      {/* Keyed on the reveal: a search that starts matching opens the fold,
          and one that stops hands it back closed. */}
      <Disclosure
        key={revealed ? 'revealed' : 'folded'}
        icon={LayoutList}
        title={t('chat.card_group.summary')}
        defaultOpen={revealed}
        className="lia-card-group mt-3"
      >
        <MarkdownContent content={split.cards} isUser={false} searchHighlight={searchHighlight} />
      </Disclosure>
    </>
  );
}
