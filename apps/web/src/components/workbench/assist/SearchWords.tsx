'use client';

/**
 * SearchWords — a search said in a sentence (ADR-372).
 *
 * It stands inside the box and only once the box holds a sentence: a plain search shows nothing new.
 * The answer is criteria, not results: the words and the chips change on screen, where the person
 * sees and corrects them, and the listing runs as it does for anything they typed. Words typed
 * while LIA read are the person's: an answer about the old ones never replaces them.
 */
import { Button } from '@/components/ui/button';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { ASSIST_PATHS, type ProposedSearch, type SearchAnswer } from '@/lib/workbench/assist';

import { useAssistBounds } from '../WorkbenchShell';
import { AssistStars } from '@/components/selection-assist/AssistStars';
import { tellCost, useToldFailure } from './tellings';
import { useAssistCall, useLatest } from '@/hooks/useAssistCall';

export interface SearchWordsProps {
  lng: Language;
  /** What the box holds. */
  words: string;
  onRead: (search: ProposedSearch) => void;
}

export function SearchWords({ lng, words, onRead }: SearchWordsProps) {
  const { t } = useTranslation(lng);
  const bounds = useAssistBounds();
  const call = useAssistCall<SearchAnswer>();
  useToldFailure(lng, call.state);
  const sentence = words.trim();
  const inTheBox = useLatest(sentence);
  if (!bounds || !sentence.includes(' ')) return null;
  const label = t('workbench.assist.mail.search_words');
  const read = async () => {
    const answer = await call.run(ASSIST_PATHS.mailSearch, {
      sentence: sentence.slice(0, bounds.instructionMax),
    });
    if (!answer) return;
    tellCost(answer.usage);
    if (inTheBox.current === sentence) onRead(answer.search);
  };
  return (
    <Button
      type="button"
      variant="ghost"
      size="icon"
      className="h-8 w-8"
      isLoading={call.state.status === 'running'}
      aria-label={label}
      title={label}
      onClick={() => void read()}
    >
      <AssistStars className="h-4 w-4" aria-hidden="true" />
    </Button>
  );
}
