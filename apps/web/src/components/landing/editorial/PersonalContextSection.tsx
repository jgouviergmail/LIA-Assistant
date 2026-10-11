import {
  Brain,
  CalendarCheck,
  HeartHandshake,
  MessageCircle,
  BellRing,
  Settings2,
  ShieldCheck,
} from 'lucide-react';
import { initI18next } from '@/i18n';

const CONTEXT_SOURCES = [
  { key: 'memory', icon: Brain },
  { key: 'people', icon: HeartHandshake },
  { key: 'commitments', icon: CalendarCheck },
  { key: 'preferences', icon: Settings2 },
] as const;
const CONTEXT_USES = [
  { key: 'respond', icon: MessageCircle },
  { key: 'anticipate', icon: BellRing },
  { key: 'act', icon: ShieldCheck },
] as const;

/** The personal context is the product's center, rather than a tool inventory. */
export async function PersonalContextSection({ lng }: { lng: string }) {
  const { t } = await initI18next(lng);
  return (
    <section
      id="personal-context"
      aria-labelledby="personal-context-title"
      className="landing-section scroll-mt-24 py-12 sm:py-20"
    >
      <div className="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8">
        <div>
          <h2 id="personal-context-title" className="text-3xl font-bold tracking-tight sm:text-4xl">
            {t('landing.context.title')}
          </h2>
          <p className="mt-4 max-w-[68ch] leading-7 text-muted-foreground">
            {t('landing.context.sub')}
          </p>
        </div>
        <dl className="mt-8 grid grid-cols-2 gap-x-5 gap-y-6 lg:grid-cols-4">
          {CONTEXT_SOURCES.map(({ key, icon: Icon }) => (
            <div key={key} className="border-t border-border pt-4">
              <dt className="flex items-center gap-2 text-sm font-semibold">
                <Icon className="size-5 shrink-0 text-primary" aria-hidden="true" />
                {t(`landing.context.${key}.title`)}
              </dt>
              <dd className="mt-3 text-sm leading-6 text-muted-foreground">
                {t(`landing.context.${key}.body`)}
              </dd>
            </div>
          ))}
        </dl>
        <div className="relative my-8 rounded-2xl border border-primary/30 bg-card px-5 py-5 sm:px-8">
          <div
            aria-hidden="true"
            className="absolute -top-5 left-1/2 h-5 border-l-2 border-primary/30"
          />
          <h3 className="flex items-center gap-3 text-lg font-semibold">
            <Brain className="size-6 shrink-0 text-primary" aria-hidden="true" />
            {t('landing.context.center_title')}
          </h3>
          <p className="mt-3 max-w-[75ch] text-sm leading-7 text-muted-foreground">
            {t('landing.context.center_body')}
          </p>
          <div
            aria-hidden="true"
            className="absolute -bottom-5 left-1/2 h-5 border-l-2 border-primary/30"
          />
        </div>
        <dl className="grid gap-6 md:grid-cols-3">
          {CONTEXT_USES.map(({ key, icon: Icon }) => (
            <div key={key}>
              <dt className="flex items-center gap-2 text-base font-semibold">
                <Icon className="size-5 shrink-0 text-primary" aria-hidden="true" />
                {t(`landing.context.${key}.title`)}
              </dt>
              <dd className="mt-2 text-sm leading-6 text-muted-foreground">
                {t(`landing.context.${key}.body`)}
              </dd>
            </div>
          ))}
        </dl>
        <p className="mt-7 max-w-[90ch] text-xs leading-6 text-muted-foreground">
          {t('landing.context.control')}
        </p>
      </div>
    </section>
  );
}
