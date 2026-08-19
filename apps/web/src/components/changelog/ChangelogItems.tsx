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
 * files (`<b>`, `<br>` and nothing else), never user or model output — the
 * frontend XSS boundary is unchanged.
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
          <span dangerouslySetInnerHTML={{ __html: t(itemKey) }} />
        </li>
      ))}
    </ul>
  );
}
