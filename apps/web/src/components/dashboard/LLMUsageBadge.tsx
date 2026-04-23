'use client';

import { useTranslation } from 'react-i18next';
import { formatEuro, formatNumber } from '@/lib/format';
import type { Language } from '@/i18n/settings';
import type { LLMUsage } from '@/types/briefing';

interface LLMUsageBadgeProps {
  usage: LLMUsage;
  className?: string;
}

/**
 * Compact "tokens · cost" badge — displayed next to the UpdatedAtBadge on
 * briefing greeting / synthesis, mirroring the chat ChatMessage debug strip
 * but discreetly: no colors, no emojis, just `IN/OUT/CACHE · cost`.
 */
export function LLMUsageBadge({ usage, className }: LLMUsageBadgeProps) {
  const { t, i18n } = useTranslation();
  const locale = (i18n.language || 'fr') as Language;

  const totalTokens = usage.tokens_in + usage.tokens_out + usage.tokens_cache;
  const costLabel = formatEuro(usage.cost_eur, 6, locale);
  // i18next chooses singular/plural form via `count`; `formatted` carries the
  // locale-formatted display value so the template stays free of formatting.
  const tokensLabel = t('dashboard.briefing.usage_tokens', {
    count: totalTokens,
    formatted: formatNumber(totalTokens, locale),
  });

  const tooltip = t('dashboard.briefing.usage_tooltip', {
    tokens_in: formatNumber(usage.tokens_in, locale),
    tokens_out: formatNumber(usage.tokens_out, locale),
    tokens_cache: formatNumber(usage.tokens_cache, locale),
    cost: costLabel,
    model: usage.model_name ?? '—',
  });

  return (
    <span
      title={tooltip}
      className={`inline-flex items-center gap-1 text-[10px] tabular-nums text-muted-foreground/60 ${className ?? ''}`}
    >
      <span>{tokensLabel}</span>
      <span aria-hidden="true">·</span>
      <span>{costLabel}</span>
    </span>
  );
}
