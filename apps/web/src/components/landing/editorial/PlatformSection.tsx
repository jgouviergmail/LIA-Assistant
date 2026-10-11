import Link from 'next/link';
import { Activity, Cpu, BellRing, Users } from 'lucide-react';
import { initI18next } from '@/i18n';
import { buildLocalizedPath } from '@/utils/i18n-path-utils';
import type { Language } from '@/i18n/settings';
import { buttonVariants } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { ScreenshotsSection } from '../ScreenshotsSection';

const PLATFORM_PROOFS = [
  { key: 'accounts', icon: Users },
  { key: 'models', icon: Cpu },
  { key: 'monitoring', icon: Activity },
  { key: 'alerts', icon: BellRing },
] as const;
const OBSERVABILITY_SOURCE =
  'https://github.com/jgouviergmail/LIA-Assistant/tree/main/infrastructure/observability';
const PLATFORM_LINK_CLASSNAME =
  'h-auto min-h-11 w-full whitespace-normal px-5 py-3 text-center leading-5 sm:w-auto';

/** Visible operator evidence, with real provisioned Grafana captures. */
export async function PlatformSection({ lng }: { lng: string }) {
  const { t } = await initI18next(lng);
  return (
    <section
      id="platform"
      aria-labelledby="platform-title"
      className="landing-section scroll-mt-24 border-y border-border/60 bg-card py-16 sm:py-24"
    >
      <div className="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8">
        <div>
          <h2 id="platform-title" className="text-3xl font-bold tracking-tight sm:text-4xl">
            {t('landing.platform.title')}
          </h2>
          <p className="mt-4 max-w-[68ch] leading-7 text-muted-foreground">
            {t('landing.platform.sub')}
          </p>
        </div>
        <h3 className="mt-8 mb-4 text-xl font-semibold">{t('landing.platform.dashboard_title')}</h3>
        <ScreenshotsSection monitoring />
        <p className="mx-auto mt-3 max-w-3xl text-center text-xs leading-6 text-muted-foreground">
          {t('landing.platform.dashboard_note')}
        </p>
        <div className="mt-8 grid gap-x-10 gap-y-7 sm:grid-cols-2">
          {PLATFORM_PROOFS.map(({ key, icon: Icon }) => (
            <article key={key} className="border-t border-border pt-5">
              <h3 className="flex items-center gap-3 text-base font-semibold">
                <Icon className="size-5 shrink-0 text-primary" aria-hidden="true" />
                {t(`landing.platform.${key}.title`)}
              </h3>
              <p className="mt-3 text-sm leading-7 text-muted-foreground">
                {t(`landing.platform.${key}.body`)}
              </p>
            </article>
          ))}
        </div>
        <div className="mt-9 border-l-2 border-primary/40 pl-5 sm:pl-6">
          <h3 className="text-xl font-semibold">{t('landing.platform.business_title')}</h3>
          <p className="mt-3 max-w-[92ch] text-sm leading-7 text-muted-foreground">
            {t('landing.platform.business_body')}
          </p>
          <p className="mt-3 max-w-[92ch] text-sm leading-7 text-muted-foreground">
            {t('landing.platform.business_scope')}
          </p>
        </div>
        <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
          <a
            className={cn(buttonVariants(), PLATFORM_LINK_CLASSNAME)}
            href="https://github.com/jgouviergmail/LIA-Assistant/blob/main/docs/GETTING_STARTED.md"
            target="_blank"
            rel="noopener noreferrer"
          >
            {t('landing.platform.install_link')}
          </a>
          <Link
            className={cn(buttonVariants({ variant: 'outline' }), PLATFORM_LINK_CLASSNAME)}
            href={buildLocalizedPath('/how', lng as Language)}
          >
            {t('landing.platform.docs_link')}
          </Link>
          <a
            className={cn(buttonVariants({ variant: 'outline' }), PLATFORM_LINK_CLASSNAME)}
            href={OBSERVABILITY_SOURCE}
            target="_blank"
            rel="noopener noreferrer"
          >
            {t('landing.platform.code_link')}
          </a>
        </div>
      </div>
    </section>
  );
}
