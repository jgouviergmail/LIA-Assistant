'use client';

/**
 * useRadioArticle — a story's article on the radio page (ADR-324).
 *
 * Read when its panel opens: the panel mounts its reader only while open, so a
 * folded article costs nothing. The API answers with the whole article when
 * its newsroom could read it, else the outlet's summary, translated into the
 * listener's language when its feed speaks another — billed once per story and
 * language, so opening it again reads the translation back at no cost.
 */

import { useApiQuery } from '@/hooks/useApiQuery';
import { RADIO_ARTICLE_TIMEOUT_MS } from '@/lib/constants';
import { RADIO_ENDPOINTS } from '@/lib/radio/api';
import type { RadioArticle } from '@/lib/radio/types';

export interface UseRadioArticleReturn {
  article: RadioArticle | undefined;
  loading: boolean;
  /** The article could not be read (the network, or a story no longer served). */
  failed: boolean;
  retry: () => Promise<void>;
}

const COMPONENT = 'useRadioArticle';

export function useRadioArticle(articleId: string): UseRadioArticleReturn {
  const { data, loading, error, refetch } = useApiQuery<RadioArticle>(
    RADIO_ENDPOINTS.article(articleId),
    { componentName: COMPONENT, config: { timeout: RADIO_ARTICLE_TIMEOUT_MS } }
  );
  return { article: data, loading, failed: error !== null, retry: refetch };
}
