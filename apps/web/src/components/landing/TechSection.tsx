import { initI18next } from '@/i18n';
import { GitBranch, Cpu, TrendingUp, Search, Radio, Layers } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import { FadeInOnScroll } from './FadeInOnScroll';

interface TechSectionProps {
  lng: string;
}

const TECH_ITEMS = [
  { key: 'langgraph', icon: GitBranch, iconBg: 'bg-gradient-to-br from-emerald-500/15 to-green-500/15' },
  { key: 'llm_providers', icon: Cpu, iconBg: 'bg-gradient-to-br from-blue-500/15 to-indigo-500/15' },
  { key: 'bayesian', icon: TrendingUp, iconBg: 'bg-gradient-to-br from-amber-500/15 to-yellow-500/15' },
  { key: 'hybrid_search', icon: Search, iconBg: 'bg-gradient-to-br from-purple-500/15 to-violet-500/15' },
  { key: 'realtime', icon: Radio, iconBg: 'bg-gradient-to-br from-rose-500/15 to-pink-500/15' },
  { key: 'stack', icon: Layers, iconBg: 'bg-gradient-to-br from-cyan-500/15 to-sky-500/15' },
];

export async function TechSection({ lng }: TechSectionProps) {
  const { t } = await initI18next(lng);

  return (
    <section id="technology" className="landing-section py-24 bg-card" aria-labelledby="tech-title">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <FadeInOnScroll>
          <div className="text-center mb-16">
            <h2 id="tech-title" className="text-3xl mobile:text-4xl font-bold tracking-tight mb-4">
              {t('landing.tech.title')}
            </h2>
            <p className="text-muted-foreground text-lg max-w-2xl mx-auto">
              {t('landing.tech.subtitle')}
            </p>
          </div>
        </FadeInOnScroll>

        {/* 2x3 grid with per-tech accent colors */}
        <div className="grid grid-cols-1 sm:grid-cols-2 mobile:grid-cols-3 gap-6">
          {TECH_ITEMS.map(({ key, icon: Icon, iconBg }, i) => (
            <FadeInOnScroll key={key} delay={i * 80}>
              <Card className="glass hover-lift hover-glow h-full border-border/60">
                <CardHeader className="space-y-3">
                  <div className={cn('w-12 h-12 rounded-xl flex items-center justify-center', iconBg)}>
                    <Icon className="w-6 h-6 text-primary" />
                  </div>
                  <CardTitle className="text-lg">
                    {t(`landing.tech.${key}.title`)}
                  </CardTitle>
                  <CardDescription className="text-sm leading-relaxed">
                    {t(`landing.tech.${key}.description`)}
                  </CardDescription>
                </CardHeader>
              </Card>
            </FadeInOnScroll>
          ))}
        </div>
      </div>
    </section>
  );
}
