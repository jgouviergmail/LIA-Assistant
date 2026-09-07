'use client';

import { useTranslation } from 'react-i18next';
import { formatEuro, formatNumber } from '@/lib/format';
import type { Language } from '@/i18n/settings';
import type { LLMUsage } from '@/types/llm-usage';

interface LLMUsageBadgeProps {
  usage: LLMUsage;
  className?: string;
}

/**
 * Compact "tokens · cost" badge — shown next to the timestamp of anything an
 * LLM wrote, mirroring the chat's debug strip but discreetly: no colours, no
 * emoji, just total tokens · cost, with the breakdown in the tooltip.
 *
 * It lived in `components/dashboard/` while the briefing and the hero card were
 * its only callers. The relationship debrief is the third, from another domain
 * — a generic primitive owned by whoever mounted it first is exactly what
 * `genericity-boundary.guard` refuses.
 *
 * It resolves its own strings and does NOT decide whether it is mounted. Its
 * three callers are the surfaces where LIA WROTE something and the cost belongs
 * beside the words, so they mount it unconditionally — deliberately not behind
 * `tokens_display_enabled`, which gates the chat's per-message debug strip (an
 * inspection aid on every turn), not the price of one artefact. Keeping the two
 * apart is what stops a reader from meeting the same figure under two rules.
 */
export function LLMUsageBadge({ usage, className }: LLMUsageBadgeProps) {
  const { t, i18n } = useTranslation();
  const locale = (i18n.language || 'fr') as Language;

  const totalTokens = usage.tokens_in + usage.tokens_out + usage.tokens_cache;
  const costLabel = formatEuro(usage.cost_eur, 6, locale);
  // i18next chooses singular/plural form via `count`; `formatted` carries the
  // locale-formatted display value so the template stays free of formatting.
  const tokensLabel = t('common.llm_usage.tokens', {
    count: totalTokens,
    formatted: formatNumber(totalTokens, locale),
  });

  const tooltip = t('common.llm_usage.tooltip', {
    tokens_in: formatNumber(usage.tokens_in, locale),
    tokens_out: formatNumber(usage.tokens_out, locale),
    tokens_cache: formatNumber(usage.tokens_cache, locale),
    cost: costLabel,
    model: usage.model_name ?? '—',
  });

  return (
    <span
      title={tooltip}
      className={`inline-flex items-center gap-1 text-[10px] tabular-nums text-muted-foreground ${className ?? ''}`}
    >
      <span>{tokensLabel}</span>
      <span aria-hidden="true">·</span>
      <span>{costLabel}</span>
    </span>
  );
}
