'use client';

/**
 * What the listener's radio spent over the rolling day, against the bound the
 * instance sets (ADR-324 decision 37) — past it, a start is refused, the
 * station goes quiet before its next programme, and an article is shown in its
 * own language. At the bound, the line says when the radio may play again. An
 * instance that sets no bound, or a figure not read yet, says nothing.
 */
import { Wallet } from 'lucide-react';

import { Disclosure } from '@/components/ui/disclosure';
import { useRadioBudget } from '@/hooks/useRadioBudget';
import { useTranslation } from '@/i18n/client';
import { radioBudgetAmount, radioBudgetInstant } from '@/lib/radio/format';
import type { BaseSettingsProps } from '@/types/settings';

export function RadioBudgetFields({ lng }: { lng: BaseSettingsProps['lng'] }) {
  const { t } = useTranslation(lng);
  const budget = useRadioBudget();
  if (budget === null || budget.limit_eur <= 0) return null;
  return (
    <Disclosure
      icon={Wallet}
      title={t('radio.settings.budget.title')}
      description={t('radio.settings.budget.description')}
      defaultOpen
    >
      <p className="text-sm">
        {t('radio.settings.budget.spent', {
          spent: radioBudgetAmount(budget.spent_eur, lng),
          limit: radioBudgetAmount(budget.limit_eur, lng),
          hours: budget.window_hours,
        })}
      </p>
      {budget.lifts_at !== null && (
        <p className="text-sm text-destructive">
          {t('radio.settings.budget.reached', {
            lifts: radioBudgetInstant(budget.lifts_at, lng),
          })}
        </p>
      )}
    </Disclosure>
  );
}
