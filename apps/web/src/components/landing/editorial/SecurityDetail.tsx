import Link from 'next/link';
import { Database, Landmark, Lock, ShieldCheck } from 'lucide-react';
import { buildLocalizedPath } from '@/utils/i18n-path-utils';
import type { Language } from '@/i18n/settings';
import type { Translate } from './FeatureCatalog';

/**
 * The former "Security & Privacy" section, preserved verbatim inside chapter
 * 04's catalog (reusing the existing `landing.security.*` copy ×6). Chapter
 * 04 carries the trust narrative; this block keeps every detail one click
 * away — and crawlable, since the disclosure keeps its content in the DOM.
 */

const SECURITY_BLOCKS = [
  { key: 'data_control', icon: Database },
  { key: 'bff', icon: Landmark },
  { key: 'encryption', icon: Lock },
  { key: 'gdpr', icon: ShieldCheck },
] as const;

export function SecurityDetail({ t, lng }: { t: Translate; lng: string }) {
  return (
    <div className="mt-6 border-t border-dashed border-border pt-5">
      <h4 className="text-sm font-semibold">{t('landing.security.title')}</h4>
      <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
        {t('landing.security.intro')}
      </p>
      <ul className="mt-4 grid list-none grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {SECURITY_BLOCKS.map(({ key, icon: Icon }) => (
          <li key={key} className="rounded-xl border border-border bg-background p-4">
            <h5 className="flex items-center gap-2 text-[13px] font-semibold">
              <Icon aria-hidden="true" className="h-4 w-4 shrink-0 text-primary" />
              {t(`landing.security.${key}.title`)}
            </h5>
            <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">
              {t(`landing.security.${key}.description`)}
            </p>
          </li>
        ))}
      </ul>
      <Link
        href={buildLocalizedPath('/privacy', lng as Language)}
        className="mt-4 inline-block text-xs font-medium text-primary hover:underline"
      >
        {t('landing.security.privacy_link')} →
      </Link>
    </div>
  );
}
