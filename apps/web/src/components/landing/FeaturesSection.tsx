import { initI18next } from '@/i18n';
import {
  Bot, Mail, Mic, ShieldCheck, BellRing, Brain,
  MessageCircle, Puzzle, Smile, Lock, LayoutGrid,
  Globe, Palette, MessageSquareText, Compass,
  CalendarClock, MousePointerClick, Star,
  AppWindow, PenTool, Paperclip, Blocks, Library, Monitor,
} from 'lucide-react';
import { Card, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import { FadeInOnScroll } from './FadeInOnScroll';

interface FeaturesSectionProps {
  lng: string;
}

interface FeatureItem {
  key: string;
  icon: React.ComponentType<{ className?: string }>;
}

interface HeroFeatureItem extends FeatureItem {
  accent: string;
  iconBg: string;
}

// Hero cards — main functional highlights with unique accent colors
const HERO_FEATURES: HeroFeatureItem[] = [
  { key: 'connected_services', icon: Mail, accent: 'bg-gradient-to-r from-red-500 to-orange-500', iconBg: 'bg-gradient-to-br from-red-500/15 to-orange-500/15' },
  { key: 'web_intelligence', icon: Compass, accent: 'bg-gradient-to-r from-blue-500 to-cyan-500', iconBg: 'bg-gradient-to-br from-blue-500/15 to-cyan-500/15' },
  { key: 'voice_mode', icon: Mic, accent: 'bg-gradient-to-r from-violet-500 to-pink-500', iconBg: 'bg-gradient-to-br from-violet-500/15 to-pink-500/15' },
];

// All functional capabilities
const FUNCTIONAL_FEATURES: FeatureItem[] = [
  { key: 'natural_language', icon: MessageSquareText },
  { key: 'multi_agent', icon: Bot },
  { key: 'proactive', icon: BellRing },
  { key: 'interests', icon: Star },
  { key: 'reminders_scheduling', icon: CalendarClock },
  { key: 'memory', icon: Brain },
  { key: 'rich_responses', icon: LayoutGrid },
  { key: 'multichannel', icon: MessageCircle },
  { key: 'personalities', icon: Smile },
  { key: 'mcp', icon: Puzzle },
  { key: 'languages', icon: Globe },
  { key: 'mcp_apps', icon: AppWindow },
  { key: 'excalidraw', icon: PenTool },
  { key: 'attachments', icon: Paperclip },
  { key: 'skills', icon: Blocks },
  { key: 'rag_spaces', icon: Library },
  { key: 'sub_agents', icon: Bot },
  { key: 'browser_control', icon: Monitor },
];

// Responsible & simple
const RESPONSIBLE_FEATURES: FeatureItem[] = [
  { key: 'control', icon: ShieldCheck },
  { key: 'privacy', icon: Lock },
  { key: 'simplicity', icon: MousePointerClick },
  { key: 'themes', icon: Palette },
];

export async function FeaturesSection({ lng }: FeaturesSectionProps) {
  const { t } = await initI18next(lng);

  return (
    <section id="features" className="landing-section py-24" aria-labelledby="features-title">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <FadeInOnScroll>
          <div className="text-center mb-16">
            <h2 id="features-title" className="text-3xl mobile:text-4xl font-bold tracking-tight mb-4">
              {t('landing.features.title')}
            </h2>
            <p className="text-muted-foreground text-lg max-w-2xl mx-auto">
              {t('landing.features.subtitle')}
            </p>
          </div>
        </FadeInOnScroll>

        {/* Hero features — connectors & tools with accent colors */}
        <div className="grid grid-cols-1 mobile:grid-cols-3 gap-6 mb-6">
          {HERO_FEATURES.map(({ key, icon: Icon, accent, iconBg }, i) => (
            <FadeInOnScroll key={key} delay={i * 100}>
              <Card className="hover-lift hover-glow h-full border-border/60 overflow-hidden">
                <div className={cn('h-1', accent)} aria-hidden="true" />
                <CardHeader className="space-y-4">
                  <div className={cn('w-14 h-14 rounded-xl flex items-center justify-center', iconBg)}>
                    <Icon className="w-7 h-7 text-primary" />
                  </div>
                  <CardTitle className="text-xl">
                    {t(`landing.features.${key}.title`)}
                  </CardTitle>
                  <CardDescription className="text-sm leading-relaxed">
                    {t(`landing.features.${key}.description`)}
                  </CardDescription>
                </CardHeader>
              </Card>
            </FadeInOnScroll>
          ))}
        </div>

        {/* All functional features */}
        <div className="grid grid-cols-1 sm:grid-cols-2 mobile:grid-cols-3 gap-4">
          {FUNCTIONAL_FEATURES.map(({ key, icon: Icon }, i) => (
            <div key={key}>
              <FadeInOnScroll delay={i * 60}>
                <Card className="hover-lift hover-glow h-full border-border/60">
                  <CardHeader className="space-y-3 p-5">
                    <div className="flex items-center gap-3">
                      <div className="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0">
                        <Icon className="w-5 h-5 text-primary" />
                      </div>
                      <CardTitle className="text-base">
                        {t(`landing.features.${key}.title`)}
                      </CardTitle>
                    </div>
                    <CardDescription className="text-xs leading-relaxed">
                      {t(`landing.features.${key}.description`)}
                    </CardDescription>
                  </CardHeader>
                </Card>
              </FadeInOnScroll>
            </div>
          ))}
        </div>

        {/* Responsible & simple — prominent sub-section */}
        <FadeInOnScroll>
          <div className="mt-16 mb-8 flex flex-col items-center text-center">
            <div className="relative mb-4">
              <div className="w-14 h-14 rounded-full bg-primary/10 flex items-center justify-center">
                <ShieldCheck className="w-7 h-7 text-primary" />
              </div>
              <div className="absolute inset-0 rounded-full border-2 border-primary/20 motion-safe:animate-ping" style={{ animationDuration: '3s' }} aria-hidden="true" />
            </div>
            <h3 className="text-2xl font-bold tracking-tight mb-2">
              {t('landing.features.subtitle_responsible')}
            </h3>
            <p className="text-muted-foreground text-sm max-w-lg">
              {t('landing.features.responsible_desc')}
            </p>
          </div>
        </FadeInOnScroll>

        <div className="grid grid-cols-1 sm:grid-cols-2 mobile:grid-cols-4 gap-4">
          {RESPONSIBLE_FEATURES.map(({ key, icon: Icon }, i) => (
            <FadeInOnScroll key={key} delay={i * 60}>
              <Card className={cn('hover-lift hover-glow h-full border-primary/20 bg-primary/5')}>
                <CardHeader className="space-y-3 p-5">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-lg bg-primary/15 flex items-center justify-center flex-shrink-0">
                      <Icon className="w-5 h-5 text-primary" />
                    </div>
                    <CardTitle className="text-base">
                      {t(`landing.features.${key}.title`)}
                    </CardTitle>
                  </div>
                  <CardDescription className="text-xs leading-relaxed">
                    {t(`landing.features.${key}.description`)}
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
