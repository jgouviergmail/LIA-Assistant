'use client';

import { useState } from 'react';
import { Cpu, RefreshCw } from 'lucide-react';
import { Accordion } from '@/components/ui/accordion';
import { Button } from '@/components/ui/button';
import { useJevDebug } from '@/hooks/useJevDebug';
import { useTranslation } from '@/i18n/client';
import { formatEuro } from '@/lib/format';
import type { Language } from '@/i18n/settings';
import type { JevCallTrace, JevChoicePreview } from '@/types/jev';
import { DebugSection } from '../shared/DebugSection';
import { JevContext } from './JevContext';
import { JevCollectionCoverage } from './JevCollectionCoverage';
import { JevObservedResult } from './JevObservedResult';

const prefix = 'chat.debug_panel.jev.';

function callOutcomeText(call: JevCallTrace): string {
  const reason = call.invalid_response_reason ? ` · ${call.invalid_response_reason}` : '';
  const status = call.status_code ? ` · HTTP ${call.status_code}` : '';
  return call.outcome + reason + status;
}

function JevAnswer({ response, lng }: { response: JevChoicePreview; lng: Language }) {
  const { t } = useTranslation(lng);
  return (
    <>
      <p>
        {response.choice_label} <span className="font-mono">({response.choice})</span>
      </p>
      <p>{t(prefix + 'confidence', { value: (response.confidence * 100).toFixed(2) })}</p>
      <p className="text-muted-foreground">{t(prefix + 'confidenceHelp')}</p>
      <details>
        <summary className="cursor-pointer py-1 focus-visible:outline focus-visible:outline-ring">
          {t(prefix + 'probabilities')}
        </summary>
        <ul className="mt-2 space-y-2">
          {response.probabilities.map(item => (
            <li key={item.key}>
              <span className="font-mono">
                {item.key}: {(item.probability * 100).toFixed(2)} %
              </span>{' '}
              — {item.label}
            </li>
          ))}
        </ul>
      </details>
      {response.omitted_candidates > 0 && (
        <p className="text-muted-foreground">
          {t(prefix + 'omittedCandidates', { omitted: response.omitted_candidates })}
        </p>
      )}
    </>
  );
}

function JevCall({ call, lng }: { call: JevCallTrace; lng: Language }) {
  const { t } = useTranslation(lng);
  // Retained traces from the previous version used "selected" for a preview.
  const action =
    call.action === 'selected' && call.action_target === 'result_preview' ? 'preview' : call.action;
  return (
    <article className="min-w-0 space-y-3 rounded-lg border p-3 text-xs [overflow-wrap:anywhere]">
      <header className="space-y-2">
        <h3 className="text-sm font-semibold">
          {t(`settings.admin.jev.usages.${call.usage}`, { defaultValue: call.caller })}
        </h3>
        <p className="font-semibold">{t(prefix + 'actions.' + action)}</p>
        <p className="text-muted-foreground">{t(prefix + 'actionHelp.' + action)}</p>
        <p className="text-muted-foreground">
          <time dateTime={call.started_at}>{new Date(call.started_at).toLocaleString(lng)}</time>
        </p>
      </header>
      <dl className="grid grid-cols-2 gap-2 rounded bg-muted/50 p-2 tabular-nums">
        <div>
          <dt>{t(prefix + 'nativeDuration')}</dt>
          <dd>{call.duration_ms.toFixed(0)} ms</dd>
        </div>
        <div>
          <dt>{t(prefix + 'cost')}</dt>
          <dd>
            {call.cost_eur === null ? t(prefix + 'unknownCost') : formatEuro(call.cost_eur, 8, lng)}
          </dd>
        </div>
      </dl>
      <p className="text-muted-foreground">{t(prefix + 'nativeDurationHelp')}</p>
      <details>
        <summary className="cursor-pointer py-1 font-semibold focus-visible:outline focus-visible:outline-ring">
          {t(prefix + 'technical')}
        </summary>
        <dl className="mt-2 space-y-1">
          <div>
            <dt className="font-semibold">{t(prefix + 'caller')}</dt>
            <dd>{call.caller}</dd>
          </div>
          <div>
            <dt className="font-semibold">{t(prefix + 'run')}</dt>
            <dd className="font-mono">{call.run_id}</dd>
          </div>
          <div>
            <dt className="font-semibold">{t(prefix + 'model')}</dt>
            <dd>
              {call.requested_model}
              {call.reported_model && call.reported_model !== call.requested_model
                ? ` → ${call.reported_model}`
                : ''}
            </dd>
          </div>
          <div>
            <dt className="font-semibold">{t(prefix + 'action')}</dt>
            {call.action_target && <dd className="font-mono">{call.action_target}</dd>}
          </div>
          <div>
            <dt className="font-semibold">{t(prefix + 'outcome')}</dt>
            <dd>{callOutcomeText(call)}</dd>
          </div>
          {call.input_tokens !== null && (
            <div>
              <dt className="font-semibold">{t(prefix + 'tokens')}</dt>
              <dd>
                {call.input_tokens} / {call.output_tokens ?? '—'}
              </dd>
            </div>
          )}
        </dl>
      </details>
      <JevContext context={call.context} lng={lng} />
      <JevCollectionCoverage call={call} lng={lng} />
      <div className="space-y-2">
        <h3 className="font-semibold">{t(prefix + 'response')}</h3>
        {call.response ? (
          <JevAnswer response={call.response} lng={lng} />
        ) : Object.keys(call.responses ?? {}).length ? (
          Object.entries(call.responses ?? {}).map(([key, response]) => (
            <div key={key} className="space-y-2 border-t pt-2">
              <p className="font-semibold">{call.decision_labels?.[key] ?? key}</p>
              {call.applied_decisions?.[key] && (
                <p className="rounded bg-muted p-2 font-semibold">
                  {t(prefix + 'appliedDecision', {
                    verdict: t('chat.result_preview.' + call.applied_decisions[key]),
                  })}
                </p>
              )}
              <JevAnswer response={response} lng={lng} />
            </div>
          ))
        ) : (
          <p className="text-muted-foreground">{t(prefix + 'noResponse')}</p>
        )}
      </div>
      <JevObservedResult call={call} lng={lng} />
    </article>
  );
}

function JevFeed({ lng }: { lng: Language }) {
  const { t } = useTranslation(lng);
  const { data, loading, error, refetch } = useJevDebug();
  return (
    <div className="max-h-[45dvh] space-y-3 overflow-y-auto pr-1" aria-busy={loading}>
      <div className="flex flex-wrap items-center gap-2">
        <Button
          type="button"
          size="sm"
          variant="outline"
          aria-disabled={loading}
          onClick={() => {
            if (!loading) void refetch();
          }}
        >
          <RefreshCw aria-hidden="true" />
          {t(prefix + 'refresh')}
        </Button>
        {loading && (
          <span role="status" className="text-xs text-muted-foreground">
            {t('common.loading')}
          </span>
        )}
      </div>
      <p className="text-xs text-muted-foreground">{t(prefix + 'scope')}</p>
      {data && (
        <p className="text-xs text-muted-foreground">
          {t(prefix + 'retention', { limit: data.limit, minutes: data.retention_seconds / 60 })}
        </p>
      )}
      {error && (
        <p role="alert" className="text-xs text-destructive">
          {t(prefix + 'error')}
        </p>
      )}
      {data?.calls.length === 0 && (
        <p className="text-xs text-muted-foreground">{t(prefix + 'empty')}</p>
      )}
      {!error && data?.calls.map(call => <JevCall key={call.id} call={call} lng={lng} />)}
    </div>
  );
}

/** Outside chat metrics: background calls remain visible before any chat turn. */
export function JevDebugSection({ lng }: { lng: Language }) {
  const { t } = useTranslation(lng);
  const [expanded, setExpanded] = useState('');
  return (
    <Accordion
      type="single"
      collapsible
      value={expanded}
      onValueChange={setExpanded}
      className="shrink-0 px-3"
    >
      <DebugSection value="jev" title={t(prefix + 'title')} icon={Cpu}>
        {expanded === 'jev' && <JevFeed lng={lng} />}
      </DebugSection>
    </Accordion>
  );
}
