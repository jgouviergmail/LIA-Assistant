'use client';

/**
 * The chrome both transparency registers wear (ADR-263, ADR-270).
 *
 * The action journal and the consultation journal had grown the SAME title
 * block, the SAME refresh button, the SAME export rule and the SAME pair of
 * emptiness wordings — each written twice, and each one a branch its reading
 * component had to carry. Measured by the complexity ratchet after the
 * initiative tab landed: both components crossed the hotspot threshold in the
 * same pass, on branches neither of them owns.
 *
 * Extracted here rather than absorbed: two copies of a rule are two places for
 * it to be changed in one of them only, and that is exactly how the two tabs
 * once came to start at two different heights.
 *
 * Nothing here decides WHAT to read — that stays with each journal, which is
 * the only thing they genuinely do differently.
 */

import { RefreshCw } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

import { RegisterExportButton } from '@/components/effects/RegisterExportButton';
import type { RegisterExportKind } from '@/components/effects/RegisterExportButton';
import { RegisterHeader } from '@/components/effects/RegisterJournalStates';
import { Button } from '@/components/ui/button';
import type { RegisterOrigin } from '@/types/register-origin';

/** Optional wording a container may impose over the journal's own. */
export interface RegisterHeadingOverride {
  title: string;
  description: string;
}

export interface RegisterJournalTitleProps {
  /** Decorative glyph beside the title. */
  icon: LucideIcon;
  /** The journal's own title, used when no container overrides it. */
  title: string;
  /** The journal's own description, same rule. */
  description: string;
  /**
   * Wording imposed by a container. The initiative tab stacks both registers
   * under its own headings; without this each list carried TWO titles — the
   * tab's and the journal's own — over one set of rows.
   */
  heading?: RegisterHeadingOverride;
  /** Which register the export button takes out. */
  exportKind: RegisterExportKind;
  /** Which authorship this reading covers; gates the export button. */
  origin: RegisterOrigin;
  /** Translated label of the refresh control. */
  refreshLabel: string;
  onRefresh: () => void;
  /** First load in flight: the refresh control is not yet meaningful. */
  firstLoad: boolean;
  /** A refetch is in flight over a populated list: spin, never unmount. */
  loading: boolean;
}

/**
 * The title row: glyph, heading, description, export and refresh.
 *
 * The export takes the WHOLE register out, by design (ADR-263): it is the
 * account's archive, not the list on screen. It is withheld only from the
 * initiative reading — a tab a person opens precisely to see a SUBSET, where a
 * new export button would read as "export this". Gated on `!== 'initiative'`
 * and not on `=== 'all'`: the two main tabs read `mine`, so the narrower test
 * would have removed the button from the real page while every component test
 * — which renders the default — stayed green.
 */
export function RegisterJournalTitle({
  icon: Icon,
  title,
  description,
  heading,
  exportKind,
  origin,
  refreshLabel,
  onRefresh,
  firstLoad,
  loading,
}: RegisterJournalTitleProps) {
  const spinning = loading && !firstLoad;
  return (
    <RegisterHeader
      actions={
        <>
          {origin !== 'initiative' && <RegisterExportButton register={exportKind} />}
          <Button variant="outline" size="sm" onClick={onRefresh} disabled={firstLoad}>
            <RefreshCw className={spinning ? 'h-4 w-4 animate-spin' : 'h-4 w-4'} aria-hidden="true" />
            {refreshLabel}
          </Button>
        </>
      }
    >
      {/* h2: the page shell owns the h1, so the two registers sit at the same
          heading level and the outline stays readable. */}
      <h2 className="flex items-center gap-2 text-xl font-bold">
        <Icon className="h-5 w-5 text-primary" aria-hidden="true" />
        {heading?.title ?? title}
      </h2>
      <p className="mt-1 text-sm text-muted-foreground">{heading?.description ?? description}</p>
    </RegisterHeader>
  );
}

/** What `RegisterJournalBody` needs to render an empty list. */
export interface RegisterEmptyState {
  icon: LucideIcon;
  title: string;
  description: string;
  reason: 'no-data' | 'no-match';
  action: { label: string; href: string };
}

/**
 * The two emptinesses, told apart.
 *
 * A filter that matches nothing is a DIFFERENT emptiness from a register with
 * no rows: one says "narrow your reading", the other says "nothing happened".
 * Both journals answered that with the same four ternaries; they are one
 * function now, keyed on each journal's own i18n prefix.
 */
export function registerEmptyState(
  t: (key: string) => string,
  options: {
    icon: LucideIcon;
    /** i18n prefix, e.g. `effects.journal` or `treatments.journal`. */
    prefix: string;
    /** Whether a filter is currently applied. */
    filtered: boolean;
    /** URL locale segment, for the call-to-action link. */
    lng: string;
  }
): RegisterEmptyState {
  const { icon, prefix, filtered, lng } = options;
  const suffix = filtered ? '_filtered' : '';
  return {
    icon,
    title: t(`${prefix}.empty${suffix}_title`),
    description: t(`${prefix}.empty${suffix}_description`),
    reason: filtered ? 'no-match' : 'no-data',
    action: { label: t(`${prefix}.empty_action`), href: `/${lng}/dashboard/chat` },
  };
}

/**
 * The exact server-side total, or nothing while it is unknown.
 *
 * `undefined` is not zero: a count shown to a reader is exact or it does not
 * exist (ADR-185), so an unknown total renders no line at all rather than a
 * "0" nobody measured.
 */
export function registerTotalLabel(
  t: (key: string, options: { count: number }) => string,
  key: string,
  total: number | undefined
): string | undefined {
  return total === undefined ? undefined : t(key, { count: total });
}
