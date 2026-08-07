'use client';

import { useTranslation } from 'react-i18next';
import { Wallet } from 'lucide-react';

import { formatEuro } from '@/lib/format';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { useInstanceBudget } from '@/hooks/useInstanceBudget';

function toNumber(value: string | null | undefined): number | null {
  if (value === null || value === undefined || value === '') return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

interface AdminInstanceBudgetCardProps {
  /** Display locale, forwarded to the currency formatter. */
  lng?: string;
}

/**
 * Daily spend ceiling for the whole instance.
 *
 * Per-user limits bound what ONE account consumes; this bounds what the
 * deployment spends in a UTC day — the only protection that holds when every
 * visitor gets their own account, as on a public demonstrator.
 *
 * The card shows what is ENFORCED rather than only what was typed: an
 * operator value above the deployment bound never applies, and displaying it
 * alone would be a fiction. Fetching and validation live in
 * ``useInstanceBudget`` so this stays a rendering concern.
 */
export function AdminInstanceBudgetCard({ lng }: AdminInstanceBudgetCardProps = {}) {
  const { t } = useTranslation();
  const { data, draft, setDraft, error, saving, save } = useInstanceBudget();

  const locale = lng as Parameters<typeof formatEuro>[2] | undefined;
  const effective = toNumber(data?.effective_ceiling_eur);
  const typed = toNumber(data?.ceiling_eur);
  const spent = toNumber(data?.spent_today_eur) ?? 0;
  const isCapped = typed !== null && effective !== null && typed > effective;

  return (
    <div className="mb-6 rounded-lg border bg-muted/20 p-4">
      <div className="mb-3 flex items-center gap-2">
        <Wallet className="h-4 w-4 text-primary" aria-hidden="true" />
        <h3 className="text-sm font-medium">{t('usage_limits.instance_budget.title')}</h3>
      </div>

      <p className="mb-3 text-xs text-muted-foreground">
        {t('usage_limits.instance_budget.description')}
      </p>

      <dl className="mb-4 grid grid-cols-1 gap-3 text-xs sm:grid-cols-3">
        <div>
          <dt className="text-muted-foreground">{t('usage_limits.instance_budget.enforced')}</dt>
          <dd className="font-medium">
            {effective === null
              ? t('usage_limits.instance_budget.no_ceiling')
              : formatEuro(effective, 2, locale)}
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground">{t('usage_limits.instance_budget.spent_today')}</dt>
          <dd className="font-medium">{formatEuro(spent, 2, locale)}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">{t('usage_limits.instance_budget.runs_today')}</dt>
          <dd className="font-medium">{data?.runs_today ?? 0}</dd>
        </div>
      </dl>

      {isCapped && (
        <p className="mb-3 text-xs text-amber-600 dark:text-amber-500">
          {t('usage_limits.instance_budget.capped_notice')}
        </p>
      )}

      <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
        <div className="flex-1">
          <Input
            label={t('usage_limits.instance_budget.field_label')}
            value={draft}
            onChange={event => setDraft(event.target.value)}
            placeholder={t('usage_limits.instance_budget.field_placeholder')}
            inputMode="decimal"
            error={error ?? undefined}
          />
        </div>
        <Button onClick={() => void save()} disabled={saving} className="sm:w-auto">
          {t('common.save')}
        </Button>
      </div>
    </div>
  );
}
