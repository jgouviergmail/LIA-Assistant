'use client';

import { useRef, useState } from 'react';
import { EyeOff, RefreshCw, Trash2 } from 'lucide-react';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Badge } from '@/components/ui/badge';
import { DiscussionPurgeDialog, type DiscussionPurgeReview } from './DiscussionPurgeDialog';
import { discussionContextSchema } from '@/types/proactive-discussions';
import { contextUsability } from '@/lib/discussion-context';
import { rebuildInFlight, type useProactiveDiscussions } from '@/hooks/useProactiveDiscussions';
import { DiscussionContextFilters } from './DiscussionContextFilters';
import { DiscussionRebuildStatus } from './DiscussionRebuildStatus';
import { DiscussionActivityPanel } from './DiscussionActivityPanel';
import { DiscussionContextTimeline } from './DiscussionContextTimeline';

type DiscussionControlsState = ReturnType<typeof useProactiveDiscussions>;

/** Said while the context read is pending, or once it failed — never an empty panel. */
function ContextLoading({ lng, controls }: { lng: Language; controls: DiscussionControlsState }) {
  const { t } = useTranslation(lng);
  return (
    <p role="status">
      {t(
        controls.context.error || controls.context.data
          ? 'discussions.load_error'
          : 'common.loading'
      )}
    </p>
  );
}

/**
 * « Contexte » — where the context work stands: the rebuild, why a requested
 * one waits, when the context was last rebuilt and updated, and the last run.
 * Its own panel, apart from the data it describes (owner request 2026-10-21).
 */
export function DiscussionContextStatus({
  lng,
  controls,
}: {
  lng: Language;
  controls: DiscussionControlsState;
}) {
  const { t } = useTranslation(lng);
  const parsed = discussionContextSchema.safeParse(controls.context.data);
  const data = parsed.success ? parsed.data : undefined;
  if (!data) return <ContextLoading lng={lng} controls={controls} />;
  // A second request would only re-wake the run already serving the first one.
  const rebuilding = data.refresh_requested || rebuildInFlight(controls.activity.data);
  const rebuildBusy = controls.saving || rebuilding;
  // A blocked request is busy (asking again changes nothing) but nothing turns.
  const rebuildTurning = controls.rebuildActive;
  return (
    <div className="min-w-0 space-y-4 pt-2" aria-busy={controls.saving}>
      <div className="flex flex-wrap gap-2">
        <Button
          variant="default"
          size="sm"
          aria-disabled={rebuildBusy}
          onClick={() => {
            if (!rebuildBusy) void controls.contextAction('rebuild');
          }}
        >
          <RefreshCw
            aria-hidden="true"
            className={`h-4 w-4 ${rebuildTurning ? 'motion-safe:animate-spin' : ''}`}
          />
          {t('discussions.rebuild')}
        </Button>
      </div>
      <DiscussionRebuildStatus
        lng={lng}
        settings={controls.settings.data}
        activity={controls.activity.data}
        requested={data.refresh_requested}
      />
      <DiscussionActivityPanel lng={lng} activity={controls.activity.data} />
    </div>
  );
}

/**
 * « Données du contexte » — what LIA keeps to open a discussion: the filters,
 * the elements with their own switch, the choices of non-use, and the purge.
 */
export function DiscussionContext({
  lng,
  controls,
}: {
  lng: Language;
  controls: DiscussionControlsState;
}) {
  const { t } = useTranslation(lng);
  const [purge, setPurge] = useState<DiscussionPurgeReview | null>(null);
  const previewToken = useRef(0);
  const purgeAllButton = useRef<HTMLButtonElement>(null);
  const purgeTrigger = useRef<HTMLButtonElement | null>(null);
  const parsed = discussionContextSchema.safeParse(controls.context.data);
  const data = parsed.success ? parsed.data : undefined;
  if (!data) return <ContextLoading lng={lng} controls={controls} />;
  const shown = new Set(data.items.map(item => item.id));
  const reviewedEpoch = data.context_epoch;
  const reviewedGeneration = data.generation;
  async function beginPurge(selection: string[] | undefined) {
    const token = ++previewToken.current;
    const expected = { expected_epoch: reviewedEpoch, expected_generation: reviewedGeneration };
    setPurge({
      scope: selection ?? 'all',
      ...expected,
      affected_count: null,
      pending: true,
      failed: false,
      token,
    });
    try {
      const result = await controls.previewPurge(selection, expected);
      if (!result) throw new Error('Purge preview unavailable');
      setPurge(current =>
        current?.token === token
          ? { ...current, affected_count: result.affected_count, pending: false }
          : current
      );
    } catch {
      setPurge(current =>
        current?.token === token ? { ...current, pending: false, failed: true } : current
      );
      void controls.refresh().catch(() => undefined);
    }
  }
  return (
    <div className="min-w-0 space-y-4 pt-2" aria-busy={controls.saving}>
      <p className="text-sm text-muted-foreground">{t('discussions.context_hint')}</p>
      <DiscussionContextFilters
        lng={lng}
        filters={controls.filters}
        onChange={controls.setFilters}
      />
      <div className="flex flex-wrap gap-2">
        <Button
          variant="destructive"
          size="sm"
          aria-disabled={controls.saving}
          onClick={() => {
            if (!controls.saving) {
              purgeTrigger.current = purgeAllButton.current;
              void beginPurge(undefined);
            }
          }}
          ref={purgeAllButton}
        >
          {t('discussions.purge_all')}
        </Button>
      </div>
      {data.items.length === 0 && (
        <p className="text-sm text-muted-foreground">{t('discussions.context_empty')}</p>
      )}
      <ul className="space-y-3">
        {data.items.map(item => {
          const usability = contextUsability(
            item,
            data.exclusions,
            controls.settings.data?.policy.sources ?? [],
            controls.settings.data?.policy.sensitive_topics ?? []
          );
          const excluded = usability === 'excluded';
          const explicit =
            item.explicitly_excluded ?? data.exclusions.some(choice => choice.item_id === item.id);
          return (
            <li key={item.id} className="min-w-0 space-y-3 rounded-lg border bg-card p-3">
              <div className="flex flex-wrap gap-2">
                {/* A live trait takes the theme tone; grey says « not in use » alone. */}
                <Badge variant="default">{t(`discussions.kinds.${item.kind}`)}</Badge>
                <Badge variant="outline">
                  {t(`discussions.qualifications.${item.qualification}`)}
                </Badge>
                {usability !== 'usable' && (
                  <Badge variant="secondary">{t(`discussions.${usability}`)}</Badge>
                )}
              </div>
              <p
                id={`context-summary-${item.id}`}
                className="whitespace-pre-wrap break-words text-sm"
              >
                {item.summary}
              </p>
              <p className="text-xs text-muted-foreground">
                {[
                  ...new Set(item.proofs.map(proof => t(`discussions.sources.${proof.source}`))),
                ].join(' · ')}
              </p>
              <DiscussionContextTimeline lng={lng} item={item} />
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  {/* A short label, and the item it acts on as its description. */}
                  <Switch
                    id={`context-${item.id}`}
                    checked={!explicit}
                    aria-describedby={`context-summary-${item.id}`}
                    aria-disabled={controls.saving}
                    onCheckedChange={usable => {
                      if (!controls.saving) void controls.setUsable(item.id, usable, item.revision);
                    }}
                  />
                  <Label htmlFor={`context-${item.id}`}>{t('discussions.allow_item')}</Label>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-destructive"
                  aria-describedby={`context-summary-${item.id}`}
                  aria-disabled={controls.saving}
                  onClick={event => {
                    if (!controls.saving) {
                      purgeTrigger.current = event.currentTarget;
                      void beginPurge([item.id]);
                    }
                  }}
                >
                  <Trash2 aria-hidden="true" />
                  {t('discussions.purge_item')}
                </Button>
              </div>
              {excluded && !explicit && (
                <p className="text-xs text-muted-foreground">
                  {t('discussions.inherited_exclusion')}
                </p>
              )}
            </li>
          );
        })}
      </ul>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-muted-foreground">
          {t('discussions.context_total', { count: data.total })}
        </p>
        {controls.cursor && (
          <Button variant="outline" size="sm" onClick={() => controls.setCursor(undefined)}>
            {t('discussions.first_page')}
          </Button>
        )}
        {data.next_cursor && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => controls.setCursor(data.next_cursor ?? undefined)}
          >
            {t('discussions.next_page')}
          </Button>
        )}
      </div>
      <section aria-labelledby="discussion-exclusions-title" className="space-y-3">
        <h4
          id="discussion-exclusions-title"
          className="flex items-center gap-2 text-sm font-medium"
        >
          <EyeOff aria-hidden="true" className="h-4 w-4 shrink-0 text-primary" />
          {t('discussions.exclusions_title')}
        </h4>
        {data.exclusions
          .filter(exclusion => !shown.has(exclusion.item_id))
          .map((exclusion, index) => (
            <div
              key={exclusion.item_id}
              className="flex flex-wrap items-center justify-between gap-3 rounded-lg border bg-card p-3"
            >
              <p className="text-sm">
                {t('discussions.retained_exclusion', { number: index + 1 })}
              </p>
              <Button
                size="sm"
                variant="outline"
                aria-disabled={controls.saving}
                onClick={() => {
                  if (!controls.saving) void controls.setUsable(exclusion.item_id, true, null);
                }}
              >
                {t('discussions.restore')}
              </Button>
            </div>
          ))}
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-xs text-muted-foreground">
            {t('discussions.exclusions_total', { count: data.exclusions_total })}
          </p>
          {controls.exclusionsCursor && (
            <Button
              size="sm"
              variant="outline"
              onClick={() => controls.setExclusionsCursor(undefined)}
            >
              {t('discussions.first_page')}
            </Button>
          )}
          {data.exclusions_next_cursor && (
            <Button
              size="sm"
              variant="outline"
              onClick={() => controls.setExclusionsCursor(data.exclusions_next_cursor ?? undefined)}
            >
              {t('discussions.next_page')}
            </Button>
          )}
        </div>
      </section>
      <DiscussionPurgeDialog
        lng={lng}
        review={purge}
        controls={controls}
        onClose={() => setPurge(null)}
        restoreFocus={() => {
          const target = purgeTrigger.current?.isConnected
            ? purgeTrigger.current
            : purgeAllButton.current;
          if (target?.isConnected) target.focus();
        }}
      />
    </div>
  );
}
