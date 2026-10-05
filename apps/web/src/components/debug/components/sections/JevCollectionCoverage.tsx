import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { JevCallTrace } from '@/types/jev';

const prefix = 'chat.debug_panel.jev.';

/** Counts come from the collection join, not the bounded diagnostic text. */
export function JevCollectionCoverage({ call, lng }: { call: JevCallTrace; lng: Language }) {
  const { t } = useTranslation(lng);
  const coverage = call.collection_coverage;
  if (!coverage) {
    return call.usage.startsWith('filter_') ? (
      <p className="text-muted-foreground">{t(prefix + 'coverageUnavailable')}</p>
    ) : null;
  }
  const counts = [
    ['coverageCandidates', coverage.candidate_count],
    ['coverageEvaluated', coverage.evaluated_count],
    ['coverageUnevaluated', coverage.unevaluated_count],
    ['coverageUnknown', coverage.unknown_count],
    ['coverageOmitted', coverage.omitted_count],
  ] as const;
  return (
    <section className="space-y-2 rounded bg-muted/50 p-2">
      <h3 className="font-semibold">{t(prefix + 'coverageTitle')}</h3>
      <dl className="grid grid-cols-2 gap-2 tabular-nums">
        {counts.map(([label, count]) => (
          <div key={label}>
            <dt>{t(prefix + label)}</dt>
            <dd>{count}</dd>
          </div>
        ))}
      </dl>
      <p className="text-muted-foreground">{t(prefix + 'coverageHelp')}</p>
      {coverage.batch_index != null && coverage.batch_count != null && (
        <p>
          {t(prefix + 'coverageBatch', {
            index: coverage.batch_index,
            total: coverage.batch_count,
          })}
        </p>
      )}
      {coverage.batch_count != null && coverage.batch_count > 1 && (
        <p className="text-muted-foreground">{t(prefix + 'coverageSharedHelp')}</p>
      )}
    </section>
  );
}
