'use client';

/**
 * The home page's comparison, staged as an arena: LIA faces ONE challenger at
 * a time (OpenClaw, Hermes Agent or Meta Muse; a four-way table was
 * unreadable, owner 2026-11-15). Three challenger tiles pick the duel, the
 * stage sets the two side by side around a « VS », and the six criteria say
 * everything at once — each contender's status in words, its head line, its
 * punchline and its facts. No reading filter and no fold (owner, 2026-11-15:
 * « afficher tout », « toujours afficher les faits »): the tiles are the only
 * controls.
 *
 * The criteria are ONE structure at every width: a list of items headed by
 * their criterion, one named group per contender. From `lg`, CSS lays each
 * item out as a row of three columns under a decorative header; below, the
 * groups stack, each opened by its contender's mark and name. Nothing is
 * rendered twice for two layouts.
 */

import { useId, useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  AudioLines,
  Bot,
  Check,
  Flame,
  Gauge,
  Gift,
  Leaf,
  Minus,
  MousePointerClick,
  ShieldCheck,
  Users,
  X,
  type LucideIcon,
} from '@/lib/icons';
import { cn } from '@/lib/utils';

import { ContenderMark } from './ContenderMark';
import {
  COMPARISON_REPORT_URL,
  COMPARISON_SOURCES,
  COMPETITOR_IDS,
  CONTENDER_NAMES,
  CONTENDER_SHORT_NAMES,
  CRITERIA,
  cellKeys,
  type CompetitorId,
  type ComparisonStatus,
  type ContenderId,
  type Criterion,
  type CriterionId,
} from './comparison-data';

/** The appetite badge of each contender card, and its tone. */
const METERS: Readonly<Record<ContenderId, { icon: LucideIcon; tone: string }>> = {
  lia: { icon: Leaf, tone: 'border-success/40 bg-success/10 text-success' },
  openclaw: { icon: Flame, tone: 'border-warning/40 bg-warning/10 text-warning' },
  hermes: { icon: Flame, tone: 'border-warning/40 bg-warning/10 text-warning' },
  muse: { icon: Gift, tone: 'border-destructive/40 bg-destructive/10 text-destructive' },
};

const CRITERION_ICONS: Readonly<Record<CriterionId, LucideIcon>> = {
  agentic: Bot,
  daily: MousePointerClick,
  family: Users,
  voice: AudioLines,
  memory: ShieldCheck,
  admin: Gauge,
};

const STATUSES: Readonly<Record<ComparisonStatus, { icon: LucideIcon; tone: string }>> = {
  yes: { icon: Check, tone: 'border-success/40 bg-success/10 text-success' },
  mid: { icon: Minus, tone: 'border-warning/40 bg-warning/10 text-warning' },
  no: { icon: X, tone: 'border-destructive/40 bg-destructive/10 text-destructive' },
};

/**
 * The three columns of a wide screen: the criterion, then the duel. From `lg`
 * only: at 768 px the criterion column left ~129 px, and « Amministrazione e
 * costi » or « Selbstständig handeln » overflowed into LIA's column (measured
 * 2026-11-15); a tablet reads the stacked cards.
 */
const COLUMNS = 'lg:grid lg:grid-cols-[24%_38%_38%]';

const COMPARISON = 'landing.comparison';
const LINK_CLASSNAME =
  'rounded-sm text-primary underline underline-offset-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring';

/**
 * @param readOn - the sources' reading day, already formatted in the page's
 *   language by the server section (`formatSourcesReadOn`).
 */
export function ComparisonExplorer({ readOn }: { readOn: string }) {
  const { t } = useTranslation();
  const challengersLabelId = useId();
  // The owner's order: the first duel is OpenClaw's.
  const [rival, setRival] = useState<CompetitorId>('openclaw');
  const duel: readonly ContenderId[] = ['lia', rival];

  return (
    <div className="space-y-8">
      <div role="group" aria-labelledby={challengersLabelId}>
        <p
          id={challengersLabelId}
          className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground"
        >
          {t(`${COMPARISON}.view_label`)}
        </p>
        <div className="grid grid-cols-3 gap-2 sm:gap-4">
          {COMPETITOR_IDS.map(id => (
            <ChallengerTile key={id} id={id} active={rival === id} onSelect={() => setRival(id)} />
          ))}
        </div>
      </div>

      <div
        key={rival}
        role="group"
        aria-label={t(`${COMPARISON}.contenders_label`)}
        className="animate-fade-in-up grid items-stretch gap-3 md:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] md:gap-5"
      >
        <ContenderCard id="lia" />
        <VersusMedallion />
        <ContenderCard id={rival} />
      </div>

      <div>
        {/* A picture of the groups' names for the eye: each group carries its own. */}
        <div aria-hidden="true" className={cn('hidden px-px pb-1 lg:items-end', COLUMNS)}>
          <span className="px-5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            {t(`${COMPARISON}.criterion_header`)}
          </span>
          {duel.map(id => (
            <span
              key={id}
              className={cn(
                'px-5 text-sm font-semibold',
                id === 'lia' ? 'text-primary' : 'text-foreground'
              )}
            >
              <ContenderName id={id} />
            </span>
          ))}
        </div>
        <ol
          aria-label={t(`${COMPARISON}.caption`, { name: CONTENDER_NAMES[rival] })}
          className="space-y-3 lg:mt-3"
        >
          {CRITERIA.map(criterion => (
            <li
              key={criterion.id}
              className={cn(
                'rounded-2xl border border-border/70 bg-background/80 p-4 shadow-sm lg:p-0 lg:shadow-none',
                COLUMNS
              )}
            >
              <h3 className="text-base font-semibold text-foreground lg:p-5">
                <CriterionLabel criterion={criterion} />
              </h3>
              {duel.map(id => (
                <div
                  key={id}
                  role="group"
                  aria-label={CONTENDER_NAMES[id]}
                  className={cn(
                    'mt-3 min-w-0 rounded-xl border p-3 lg:mt-0 lg:rounded-none lg:border-0 lg:p-5',
                    // An opaque tint from `lg`: the attention canvas must not draw through LIA's column.
                    id === 'lia'
                      ? 'border-primary/40 bg-primary/5 lg:bg-[color-mix(in_srgb,var(--color-primary)_7%,var(--color-background))]'
                      : 'border-border/60'
                  )}
                >
                  <p
                    aria-hidden="true"
                    className={cn(
                      'mb-2 text-sm font-semibold lg:hidden',
                      id === 'lia' ? 'text-primary' : 'text-foreground'
                    )}
                  >
                    <ContenderName id={id} />
                  </p>
                  <ComparisonCell criterion={criterion} contender={id} />
                </div>
              ))}
            </li>
          ))}
        </ol>
      </div>

      <div className="space-y-2 text-xs leading-5 text-muted-foreground">
        <h3 className="text-sm font-semibold text-foreground">
          {t(`${COMPARISON}.sources_title`)}
        </h3>
        <p>{t(`${COMPARISON}.sources_body`, { date: readOn })}</p>
        <ul className="flex flex-wrap gap-x-4 gap-y-1">
          {COMPARISON_SOURCES.map(source => (
            <li key={source.key}>
              <a href={source.href} target="_blank" rel="noopener noreferrer" className={LINK_CLASSNAME}>
                {t(`${COMPARISON}.sources.${source.key}`)}
              </a>
            </li>
          ))}
        </ul>
        <p>
          {t(`${COMPARISON}.sources_note`)}{' '}
          <a
            href={COMPARISON_REPORT_URL}
            target="_blank"
            rel="noopener noreferrer"
            className={LINK_CLASSNAME}
          >
            {t(`${COMPARISON}.sources_report`)}
          </a>
        </p>
      </div>
    </div>
  );
}

/** A challenger's tile: its mark and short name; the chosen one lights up. */
function ChallengerTile({
  id,
  active,
  onSelect,
}: {
  id: CompetitorId;
  active: boolean;
  onSelect: () => void;
}) {
  const { t } = useTranslation();
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onSelect}
      className={cn(
        'group relative flex min-h-11 min-w-0 flex-col items-center gap-2 overflow-hidden rounded-2xl border px-2 pt-3 pb-4 text-center transition-[background-color,border-color,box-shadow] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:flex-row sm:gap-3 sm:px-4 sm:text-left',
        active
          ? 'border-primary/50 bg-primary/10 shadow-[0_10px_32px_-12px_var(--color-primary)]'
          : 'border-border/70 bg-background/80 hover:border-primary/40 hover:bg-primary/5'
      )}
    >
      <ContenderMark id={id} size="md" />
      <span className="min-w-0">
        <span
          className={cn(
            'block text-sm font-semibold sm:text-base',
            active ? 'text-primary' : 'text-foreground'
          )}
        >
          {CONTENDER_SHORT_NAMES[id]}
        </span>
        <span aria-hidden="true" className="hidden text-xs text-muted-foreground md:block">
          {t(`${COMPARISON}.contenders.${id}.role`)}
        </span>
      </span>
      <span
        aria-hidden="true"
        className={cn(
          'absolute inset-x-3 bottom-0 h-1 rounded-full transition-opacity [background:var(--cosmos-grad)]',
          active ? 'opacity-100' : 'opacity-0'
        )}
      />
    </button>
  );
}

/** The duel's centre: a « VS » medallion in the cosmos gradient. Decorative. */
function VersusMedallion() {
  return (
    <div aria-hidden="true" className="flex items-center justify-center">
      <span className="flex size-12 items-center justify-center rounded-full text-sm font-extrabold tracking-wider text-white shadow-[0_8px_30px_-6px_var(--color-primary)] [background:var(--cosmos-grad)] md:size-16 md:text-base">
        VS
      </span>
    </div>
  );
}

/** A contender's mark and full name. */
function ContenderName({ id }: { id: ContenderId }) {
  return (
    <span className="inline-flex items-center gap-2">
      <ContenderMark id={id} size="sm" />
      {CONTENDER_NAMES[id]}
    </span>
  );
}

/** A criterion's icon and name. */
function CriterionLabel({ criterion }: { criterion: Criterion }) {
  const { t } = useTranslation();
  const Icon = CRITERION_ICONS[criterion.id];
  return (
    <span className="flex items-center gap-2 font-semibold text-foreground">
      <Icon className="size-5 shrink-0 text-primary" aria-hidden="true" />
      {t(`${COMPARISON}.rows.${criterion.id}.label`)}
    </span>
  );
}

/** One contender on the stage: who it is, its humour, and its appetite. */
function ContenderCard({ id }: { id: ContenderId }) {
  const { t } = useTranslation();
  const meter = METERS[id];
  const MeterIcon = meter.icon;
  return (
    <article
      aria-label={CONTENDER_NAMES[id]}
      className={cn(
        'flex flex-col gap-3 rounded-2xl border p-5 shadow-sm',
        id === 'lia' ? 'border-primary/50 bg-primary/10' : 'border-border/70 bg-background/80'
      )}
    >
      <div className="flex items-center gap-3">
        <ContenderMark id={id} size="lg" />
        <div className="min-w-0">
          <p
            className={cn(
              'text-lg font-semibold tracking-tight',
              id === 'lia' ? 'text-primary' : 'text-foreground'
            )}
          >
            {CONTENDER_NAMES[id]}
          </p>
          <p className="text-sm text-muted-foreground">{t(`${COMPARISON}.contenders.${id}.role`)}</p>
        </div>
      </div>
      <p className="text-sm italic leading-6 text-foreground/90">
        {t(`${COMPARISON}.contenders.${id}.quote`)}
      </p>
      <p
        className={cn(
          'mt-auto inline-flex w-fit max-w-full items-center gap-1.5 rounded-xl border px-2.5 py-1 text-xs font-medium leading-5',
          meter.tone
        )}
      >
        <MeterIcon className="size-3.5 shrink-0" aria-hidden="true" />
        {t(`${COMPARISON}.contenders.${id}.meter`)}
      </p>
    </article>
  );
}

/** One cell, said whole: its status in words, its head line, its punchline, its facts. */
function ComparisonCell({ criterion, contender }: { criterion: Criterion; contender: ContenderId }) {
  const { t } = useTranslation();
  const keys = cellKeys(criterion.id, contender);
  const status = criterion.status[contender];
  const StatusIcon = STATUSES[status].icon;
  return (
    <div className="flex flex-col gap-2">
      <span
        className={cn(
          'inline-flex w-fit items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-semibold',
          STATUSES[status].tone
        )}
      >
        <StatusIcon className="size-3.5 shrink-0" aria-hidden="true" />
        {t(`${COMPARISON}.status.${status}`)}
      </span>
      <p className="text-base font-semibold leading-snug text-foreground">{t(keys.head)}</p>
      <p className="rounded-lg border-l-2 border-primary/50 bg-primary/5 px-3 py-2 text-sm italic leading-6 text-foreground/90">
        {t(keys.punch)}
      </p>
      <ul className="list-disc space-y-1 pl-4 text-sm leading-6 text-muted-foreground">
        {keys.bullets.map(key => (
          <li key={key}>{t(key)}</li>
        ))}
      </ul>
    </div>
  );
}
