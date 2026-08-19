/**
 * The full release history, on a public page.
 *
 * The landing band teases the last three releases and hands the reader "see
 * the full history". That promise used to point at `/faq` — where the PUBLIC
 * FAQ (`PublicFAQContent`) carries no changelog at all: the history only ever
 * existed in the signed-in dashboard FAQ (`FAQContent`), so a visitor who
 * followed the button met a page without it, and a signed-out reader could
 * reach the full history nowhere. This component IS that destination.
 *
 * A SERVER component, like the band that sends the reader here and like every
 * other public content page: the text is static editorial content compiled
 * from the repo's locale files, so it costs no client bundle, and — the reason
 * that matters for a page whose whole job is to be findable — it is indexable.
 * The collapsibles are native `<details>`, so nothing here needs JavaScript to
 * open: the same idiom the public FAQ already uses.
 *
 * It reads the SAME list as every other changelog surface (`lib/changelog.ts`)
 * and renders ALL of it. A slice here would recreate the original defect one
 * level down.
 *
 * The bullets themselves come from the shared `ChangelogItems`, so the three
 * surfaces that quote a release enforce the same rules with one implementation.
 */

import { ChevronDown, Tag } from 'lucide-react';

import { initI18next } from '@/i18n';
import {
  CHANGELOG_VERSION_KEYS,
  changelogDateKey,
  changelogTitleKey,
  groupChangelogBySeries,
} from '@/lib/changelog';

import { ChangelogItems } from './ChangelogItems';

export async function ChangelogHistory({ lng }: { lng: string }) {
  const { t } = await initI18next(lng);
  const series = groupChangelogBySeries(CHANGELOG_VERSION_KEYS);
  const [newest] = CHANGELOG_VERSION_KEYS;

  return (
    <div className="space-y-10">
      {/* Series rail — 166 releases in one column is a wall; the series is
          what a reader actually navigates by. Same chip idiom as the FAQ. */}
      <nav aria-label={t('faq.changelog.title')} className="flex flex-wrap gap-2">
        {series.map(({ label, id }) => (
          <a
            key={id}
            href={`#${id}`}
            className="inline-flex items-center gap-1.5 rounded-full border border-border bg-card px-3.5 py-1.5 text-xs text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            {label}
          </a>
        ))}
      </nav>

      {series.map(({ label, id, versions }) => (
        <section key={id} id={id} aria-labelledby={`${id}-title`} className="scroll-mt-24">
          <h2
            id={`${id}-title`}
            className="mb-4 flex items-center gap-2 text-2xl font-semibold tracking-tight"
          >
            <Tag aria-hidden="true" className="h-5 w-5 text-primary" />
            {label}
          </h2>

          <div className="space-y-3">
            {versions.map(version => (
              <details
                key={version}
                open={version === newest || undefined}
                className="group rounded-xl border border-border/60 bg-card overflow-hidden transition-colors hover:border-primary/30"
              >
                <summary className="flex cursor-pointer list-none items-start justify-between gap-3 px-5 py-4 text-left font-medium hover:bg-muted/40 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring [&::-webkit-details-marker]:hidden">
                  <span className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                    <span>{t(changelogTitleKey(version))}</span>
                    <span className="text-xs font-normal text-muted-foreground">
                      {t(changelogDateKey(version))}
                    </span>
                  </span>
                  <ChevronDown
                    aria-hidden="true"
                    className="mt-0.5 h-5 w-5 shrink-0 text-muted-foreground transition-transform group-open:rotate-180"
                  />
                </summary>
                <ChangelogItems
                  version={version}
                  t={t}
                  className="border-t border-border/40 px-5 pb-5 pt-4"
                />
              </details>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
