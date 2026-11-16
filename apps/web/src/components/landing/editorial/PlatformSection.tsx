import Link from 'next/link';
import { Activity, BellRing, Building2, Cpu, Users, type LucideIcon } from '@/lib/icons';
import { initI18next } from '@/i18n';
import { buildLocalizedPath } from '@/utils/i18n-path-utils';
import type { Language } from '@/i18n/settings';
import { buttonVariants } from '@/components/ui/button-variants';
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

/** A tile's title beside its icon, in the theme's round chip. */
function TileHeading({
  icon: Icon,
  className,
  children,
}: {
  icon: LucideIcon;
  className: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center gap-3">
      <span className="flex size-10 shrink-0 items-center justify-center rounded-full border border-primary/25 bg-primary/10">
        <Icon className="size-5 text-primary" aria-hidden="true" />
      </span>
      <h3 className={cn('min-w-0 break-words font-semibold', className)}>{children}</h3>
    </div>
  );
}

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
          <h2 id="platform-title" className="text-3xl font-bold tracking-tight mobile:text-4xl">
            {t('landing.platform.title')}
          </h2>
          <p className="mt-4 leading-7 text-muted-foreground">{t('landing.platform.sub')}</p>
        </div>
        <h3 className="mt-8 mb-4 text-xl font-semibold">{t('landing.platform.dashboard_title')}</h3>
        <ScreenshotsSection monitoring />
        <p className="mt-3 text-center text-xs leading-5 text-muted-foreground">
          {t('landing.platform.dashboard_note')}
        </p>
        {/* Tiles (owner, 2026-11-15: « plus lisible et conforme au thème »): each
            opens on its icon beside its title; the business base closes the
            mosaic across the full width, in the theme's tint. */}
        <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2">
          {PLATFORM_PROOFS.map(({ key, icon }) => (
            <article
              key={key}
              className="rounded-2xl border border-border bg-background p-5 sm:p-6"
            >
              <TileHeading icon={icon} className="text-base">
                {t(`landing.platform.${key}.title`)}
              </TileHeading>
              <p className="mt-3 text-sm leading-6 text-muted-foreground">
                {t(`landing.platform.${key}.body`)}
              </p>
            </article>
          ))}
          <article className="rounded-2xl border border-primary/40 bg-[color-mix(in_srgb,var(--color-primary)_7%,var(--color-background))] p-5 sm:col-span-2 sm:p-6">
            <TileHeading icon={Building2} className="text-xl">
              {t('landing.platform.business_title')}
            </TileHeading>
            <p className="mt-3 text-sm leading-6 text-muted-foreground">
              {t('landing.platform.business_body')}
            </p>
            <p className="mt-3 text-sm leading-6 text-muted-foreground">
              {t('landing.platform.business_scope')}
            </p>
          </article>
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
