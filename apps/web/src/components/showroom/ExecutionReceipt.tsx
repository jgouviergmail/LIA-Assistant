'use client';

/**
 * Simulation receipt: what was read, proposed, applied, and refused — plus
 * the explicit "no external action occurred" line. A refusal renders as a
 * respected outcome, never as an error. Purely presentational; every string
 * resolves from the active locale and every row comes from the mission
 * definition (one row per decided step).
 */

import {
  Bell,
  CalendarClock,
  Check,
  CircleSlash,
  ListChecks,
  Mail,
  Phone,
  Settings2,
  ShieldCheck,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type {
  ShowroomDecisionIcon,
  ShowroomDecisionKind,
  ShowroomMissionDefinition,
} from '@/components/showroom/types';

export interface ExecutionReceiptProps {
  def: ShowroomMissionDefinition;
  decisions: readonly (ShowroomDecisionKind | null)[];
}

const DECISION_ICONS: Record<
  ShowroomDecisionIcon,
  typeof Mail
> = {
  mail: Mail,
  calendar: CalendarClock,
  phone: Phone,
  bell: Bell,
  settings: Settings2,
  task: ListChecks,
};

export function ExecutionReceipt({ def, decisions }: ExecutionReceiptProps) {
  const { t } = useTranslation();
  const refusalRespected = decisions.some((d) => d === 'cancel');

  return (
    <section
      aria-label={t('showroom.receipt.title')}
      className="rounded-2xl border border-border/60 bg-card/70 p-4 backdrop-blur-sm"
    >
      <h4 className="flex items-center gap-2 text-sm font-semibold text-foreground">
        <ShieldCheck className="h-4 w-4 text-primary" aria-hidden="true" />
        {t('showroom.receipt.title')}
      </h4>
      <dl className="mt-3 space-y-2 text-sm">
        <div className="flex items-start gap-2">
          <dt className="shrink-0 font-medium text-muted-foreground">
            {t('showroom.receipt.reads_label')}
          </dt>
          <dd>{t(def.receipt.readsKey)}</dd>
        </div>
        <div className="flex items-start gap-2">
          <dt className="shrink-0 font-medium text-muted-foreground">
            {t('showroom.receipt.proposed_label')}
          </dt>
          <dd>{t(def.receipt.proposedKey)}</dd>
        </div>
        {def.decisions.map((spec, index) => {
          const decision = decisions[index];
          if (!decision) return null;
          const Icon = DECISION_ICONS[spec.icon];
          const outcomeKey =
            decision === 'cancel'
              ? spec.outcome.cancel
              : decision === 'edit'
                ? (spec.outcome.edit ?? spec.outcome.confirm)
                : spec.outcome.confirm;
          return (
            <div key={spec.id} className="flex items-start gap-2">
              <dt className="flex shrink-0 items-center gap-1.5 font-medium text-muted-foreground">
                <Icon className="h-3.5 w-3.5" aria-hidden="true" />
                {t(spec.receiptLabelKey)}
              </dt>
              <dd className="flex items-start gap-1.5">
                {decision === 'cancel' ? (
                  <CircleSlash
                    className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground"
                    aria-hidden="true"
                  />
                ) : (
                  <Check
                    className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary"
                    aria-hidden="true"
                  />
                )}
                {t(outcomeKey)}
              </dd>
            </div>
          );
        })}
        {refusalRespected && (
          <div className="flex items-start gap-2">
            <dt className="shrink-0 font-medium text-muted-foreground">
              {t('showroom.receipt.refusal_label')}
            </dt>
            <dd>{t('showroom.receipt.refusal_respected')}</dd>
          </div>
        )}
        <div className="flex items-start gap-2">
          <dt className="shrink-0 font-medium text-muted-foreground">
            {t('showroom.receipt.external_label')}
          </dt>
          <dd>{t('showroom.receipt.no_external')}</dd>
        </div>
      </dl>
    </section>
  );
}
