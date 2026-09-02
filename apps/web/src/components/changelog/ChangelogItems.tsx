/**
 * One release's bullets — the body every changelog surface renders.
 *
 * Three surfaces quote a release: the landing band (`ChangelogSection`), this
 * page's history (`ChangelogHistory`) and the dashboard FAQ (`FAQContent`).
 * All three had their own copy of this list, and copies of a rule drift — the
 * doctrine "an unusable count renders NO bullet rather than a row of empty
 * ones" was enforced in two of them, and the decorative glyph was hidden from
 * assistive technology in two as well (the FAQ's was not, so a screen reader
 * announced a bullet for each of the ~800 items of the full history).
 *
 * `t` is a PROP, not a hook. The band and the history page are SERVER
 * components resolving translations through `initI18next`; the dashboard FAQ is
 * a CLIENT component using `useTranslation`. Taking the resolver is what keeps
 * one implementation usable by both — the same reason `Skeleton` takes its
 * label rather than reading a hook.
 *
 * The item bodies are `dangerouslySetInnerHTML`, as they are on every changelog
 * surface: app-controlled editorial text compiled from the repo's own locale
 * files (`<b>`, `<br>`, `<code>`, `<em>`), never user or model output — the
 * frontend XSS boundary is unchanged.
 *
 * The body carries `min-w-0 break-words` because it is a FLEX child, and a flex
 * child defaults to `min-width: auto`: it refuses to shrink below its longest
 * unbreakable word. Measured in CI on 2026-09-02 — an entry quoting
 * `accounts__list_financial_accounts` pushed three elements past the right edge
 * of the landing page at 320px and failed the WCAG reflow floor. The rule lives
 * here so all three surfaces inherit it, whatever a future release quotes.
 */

import { changelogCountKey, changelogItemCount, changelogItemKeys } from '@/lib/changelog';
import { cn } from '@/lib/utils';

interface ChangelogItemsProps {
  /** Release key, e.g. `v1_30_10`. */
  version: string;
  /** Translation resolver of the calling surface (server or client). */
  t: (key: string) => string;
  /** Extra list classes — spacing and framing differ per surface. */
  className?: string;
}

export function ChangelogItems({ version, t, className }: ChangelogItemsProps) {
  const itemKeys = changelogItemKeys(version, changelogItemCount(t(changelogCountKey(version))));

  return (
    <ul className={cn('space-y-2 text-sm leading-relaxed text-muted-foreground', className)}>
      {itemKeys.map(itemKey => (
        <li key={itemKey} className="flex gap-2">
          <span className="mt-0.5 text-primary" aria-hidden="true">
            •
          </span>
          <span className="min-w-0 break-words" dangerouslySetInnerHTML={{ __html: t(itemKey) }} />
        </li>
      ))}
    </ul>
  );
}
