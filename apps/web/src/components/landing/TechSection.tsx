import Link from 'next/link';
import { initI18next } from '@/i18n';
import {
  Blocks,
  Calculator,
  ClipboardList,
  CloudSun,
  ChevronDown,
  Cpu,
  GitBranch,
  KeyRound,
  Layers,
  Network,
  PhoneCall,
  Radio,
  Search,
  ScrollText,
  ShieldCheck,
  TabletSmartphone,
  TrendingUp,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { buildLocalizedPath } from '@/utils/i18n-path-utils';
import type { Language } from '@/i18n/settings';
import { formatNumber } from '@/lib/format';
import { FadeInOnScroll } from './FadeInOnScroll';
import { LANDING_STATS } from './constants';
import { ArchitectureDiagram } from './ArchitectureDiagram';

interface TechSectionProps {
  lng: string;
}

const TECH_ITEMS = [
  {
    // The registers open the section: what an assistant DID, and what it
    // looked at, is the question a reader brings before any other.
    key: 'transparency_registers',
    icon: ScrollText,
    iconBg: 'bg-gradient-to-br from-indigo-500/15 to-blue-500/15',
  },
  {
    key: 'semantic_layer',
    icon: Network,
    iconBg: 'bg-gradient-to-br from-teal-500/15 to-emerald-500/15',
  },
  {
    key: 'native_shells',
    icon: TabletSmartphone,
    iconBg: 'bg-gradient-to-br from-violet-500/15 to-fuchsia-500/15',
  },
  {
    key: 'scoped_state',
    icon: KeyRound,
    iconBg: 'bg-gradient-to-br from-amber-500/15 to-orange-500/15',
  },
  {
    key: 'structured_minutes',
    icon: ClipboardList,
    iconBg: 'bg-gradient-to-br from-sky-500/15 to-cyan-500/15',
  },
  {
    key: 'langgraph',
    icon: GitBranch,
    iconBg: 'bg-gradient-to-br from-emerald-500/15 to-green-500/15',
  },
  {
    key: 'llm_providers',
    icon: Cpu,
    iconBg: 'bg-gradient-to-br from-blue-500/15 to-indigo-500/15',
  },
  {
    key: 'bayesian',
    icon: TrendingUp,
    iconBg: 'bg-gradient-to-br from-amber-500/15 to-yellow-500/15',
  },
  {
    key: 'hybrid_search',
    icon: Search,
    iconBg: 'bg-gradient-to-br from-purple-500/15 to-violet-500/15',
  },
  { key: 'realtime', icon: Radio, iconBg: 'bg-gradient-to-br from-rose-500/15 to-pink-500/15' },
  {
    key: 'honest_enrichment',
    icon: CloudSun,
    iconBg: 'bg-gradient-to-br from-teal-500/15 to-emerald-500/15',
  },
  // Beside the honest enrichments: both are about a figure being true — the
  // one a provider publishes, the one a tool computes (ADR-318).
  {
    key: 'exact_answers',
    icon: Calculator,
    iconBg: 'bg-gradient-to-br from-lime-500/15 to-green-500/15',
  },
  { key: 'stack', icon: Layers, iconBg: 'bg-gradient-to-br from-cyan-500/15 to-sky-500/15' },
  {
    key: 'rich_skills',
    icon: Blocks,
    iconBg: 'bg-gradient-to-br from-fuchsia-500/15 to-pink-500/15',
  },
  {
    key: 'hitl',
    icon: ShieldCheck,
    iconBg: 'bg-gradient-to-br from-orange-500/15 to-red-500/15',
  },
  {
    key: 'telephony',
    icon: PhoneCall,
    iconBg: 'bg-gradient-to-br from-teal-500/15 to-emerald-500/15',
  },
];

const ENGINEERING_STEPS = [
  { key: 'context', icon: Network },
  { key: 'plan', icon: GitBranch },
  { key: 'verify', icon: Search },
  { key: 'control', icon: ShieldCheck },
] as const;

export async function TechSection({ lng }: TechSectionProps) {
  const { t } = await initI18next(lng);

  return (
    <section id="technology" className="landing-section py-24 bg-card" aria-labelledby="tech-title">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <FadeInOnScroll>
          <div className="mb-10 max-w-3xl">
            <h2 id="tech-title" className="text-3xl mobile:text-4xl font-bold tracking-tight mb-4">
              {t('landing.engineering.title')}
            </h2>
            <p className="max-w-[65ch] text-muted-foreground leading-relaxed">
              {t('landing.engineering.sub')}
            </p>
          </div>
        </FadeInOnScroll>

        <ol className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {ENGINEERING_STEPS.map(({ key, icon: Icon }, index) => (
            <li key={key} className="relative border-t-2 border-primary/25 pt-5">
              <div className="mb-4 flex items-center gap-3">
                <span className="flex size-10 items-center justify-center rounded-full border border-primary/25 bg-primary/10">
                  <Icon className="size-5 text-primary" aria-hidden="true" />
                </span>
                <span className="text-xs tabular-nums text-muted-foreground" aria-hidden="true">
                  {index + 1}
                </span>
              </div>
              <h3 className="text-base font-semibold">{t(`landing.engineering.${key}_title`)}</h3>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                {t(`landing.engineering.${key}_body`)}
              </p>
              <p className="mt-4 text-sm font-medium text-primary">
                {t(`landing.engineering.${key}_gain`)}
              </p>
            </li>
          ))}
        </ol>

        <details className="group/engineering mt-10 rounded-2xl border border-border bg-background/70 p-5 sm:p-6">
          <summary className="flex cursor-pointer list-none items-center gap-3 rounded-md py-1 text-base font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring [&::-webkit-details-marker]:hidden">
            <Cpu className="size-5 shrink-0 text-primary" aria-hidden="true" />
            {t('landing.engineering.details')}
            <ChevronDown
              className="ml-auto size-4 shrink-0 transition-transform group-open/engineering:rotate-180"
              aria-hidden="true"
            />
          </summary>
          <p className="mt-5 max-w-[80ch] whitespace-pre-line text-sm leading-relaxed text-muted-foreground">
            {t('landing.tech.intro')}
          </p>
          <div className="mt-6 grid items-start gap-3 md:grid-cols-2">
            {TECH_ITEMS.map(({ key, icon: Icon, iconBg }, i) => (
              <FadeInOnScroll key={key} delay={(i % 2) * 80}>
                <details className="group/tech rounded-xl border border-border bg-card">
                  <summary className="flex cursor-pointer list-none items-center gap-3 rounded-xl p-4 text-sm font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring [&::-webkit-details-marker]:hidden">
                    <span
                      className={cn(
                        'flex size-9 shrink-0 items-center justify-center rounded-lg',
                        iconBg
                      )}
                    >
                      <Icon className="size-4 text-primary" aria-hidden="true" />
                    </span>
                    {t(`landing.tech.${key}.title`)}
                    <ChevronDown
                      className="ml-auto size-4 shrink-0 text-muted-foreground transition-transform group-open/tech:rotate-180"
                      aria-hidden="true"
                    />
                  </summary>
                  <p className="px-4 pb-5 text-sm leading-6 text-muted-foreground">
                    {t(`landing.tech.${key}.description`)}
                  </p>
                </details>
              </FadeInOnScroll>
            ))}
          </div>
          <ArchitectureDiagram />
        </details>

        {/* Engineering numbers, re-targeted from the former proof section:
            this is their audience — the general public gets trust proofs in
            the transparency band instead. */}
        <FadeInOnScroll>
          <ul className="mt-12 flex list-none flex-wrap justify-center gap-2.5">
            {(
              [
                ['agents', `${LANDING_STATS.agents}+`],
                ['tools', `${LANDING_STATS.tools}`],
                ['providers', `${LANDING_STATS.providers}`],
                ['voice_languages', `${LANDING_STATS.voiceLanguages}+`],
                ['tests', `${formatNumber(LANDING_STATS.tests, lng as Language)}+`],
                // Exact counts (ADR files, CHANGELOG entries): no "+" — it would
                // claim one more than the repository actually holds. `tests` keeps
                // its "+" because that value is rounded DOWN by contract.
                ['adrs', `${LANDING_STATS.adrs}`],
                ['releases', `${LANDING_STATS.releases}`],
              ] as const
            ).map(([key, value]) => (
              <li
                key={key}
                className="rounded-lg border border-border bg-background px-3.5 py-2 text-xs text-muted-foreground"
              >
                <span className="mr-1.5 text-sm font-bold tabular-nums text-foreground">
                  {value}
                </span>
                {t(`landing.proof.items.${key}`)}
              </li>
            ))}
          </ul>
        </FadeInOnScroll>

        <FadeInOnScroll>
          <div className="text-center mt-8">
            <Link
              href={buildLocalizedPath('/how', lng as Language)}
              className="inline-flex items-center gap-1 text-sm text-primary hover:underline"
            >
              {t('landing.tech.deep_dive_link')} →
            </Link>
          </div>
        </FadeInOnScroll>
      </div>
    </section>
  );
}
