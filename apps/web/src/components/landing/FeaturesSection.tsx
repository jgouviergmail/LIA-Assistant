import { initI18next } from '@/i18n';
import {
  Bot,
  Mail,
  Mic,
  ShieldCheck,
  BellRing,
  Brain,
  MessageCircle,
  Puzzle,
  Smile,
  Lock,
  LayoutGrid,
  Globe,
  Palette,
  MessageSquareText,
  Compass,
  CalendarClock,
  MousePointerClick,
  Star,
  AppWindow,
  PenTool,
  Paperclip,
  ImagePlus,
  Blocks,
  Library,
  Monitor,
  Smartphone,
  HelpCircle,
  BookOpen,
  Lightbulb,
  Gauge,
  Terminal,
  Heart,
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

interface FeatureGroup {
  key: string;
  icon: React.ComponentType<{ className?: string }>;
  headerIconBg: string;
  headerIconColor: string;
  cardIconBg: string;
  cardIconColor: string;
  cardHoverBorder: string;
  features: FeatureItem[];
}

// Hero cards — main functional highlights with unique accent colors
const HERO_FEATURES: HeroFeatureItem[] = [
  {
    key: 'connected_services',
    icon: Mail,
    accent: 'bg-gradient-to-r from-red-500 to-orange-500',
    iconBg: 'bg-gradient-to-br from-red-500/15 to-orange-500/15',
  },
  {
    key: 'smart_home',
    icon: Lightbulb,
    accent: 'bg-gradient-to-r from-yellow-500 to-amber-500',
    iconBg: 'bg-gradient-to-br from-yellow-500/15 to-amber-500/15',
  },
  {
    key: 'web_intelligence',
    icon: Compass,
    accent: 'bg-gradient-to-r from-blue-500 to-cyan-500',
    iconBg: 'bg-gradient-to-br from-blue-500/15 to-cyan-500/15',
  },
  {
    key: 'voice_mode',
    icon: Mic,
    accent: 'bg-gradient-to-r from-violet-500 to-pink-500',
    iconBg: 'bg-gradient-to-br from-violet-500/15 to-pink-500/15',
  },
];

// Grouped functional capabilities with static Tailwind classes
const FEATURE_GROUPS: FeatureGroup[] = [
  {
    key: 'group_conversation',
    icon: MessageSquareText,
    headerIconBg: 'bg-gradient-to-br from-blue-500/15 to-cyan-500/15',
    headerIconColor: 'text-blue-600 dark:text-blue-400',
    cardIconBg: 'bg-gradient-to-br from-blue-500/10 to-cyan-500/10',
    cardIconColor: 'text-blue-600 dark:text-blue-400',
    cardHoverBorder: 'hover:border-blue-500/30',
    features: [
      { key: 'natural_language', icon: MessageSquareText },
      { key: 'multi_agent', icon: Bot },
      { key: 'rich_responses', icon: LayoutGrid },
      { key: 'multichannel', icon: MessageCircle },
      { key: 'languages', icon: Globe },
    ],
  },
  {
    key: 'group_personality',
    icon: Heart,
    headerIconBg: 'bg-gradient-to-br from-violet-500/15 to-pink-500/15',
    headerIconColor: 'text-violet-600 dark:text-violet-400',
    cardIconBg: 'bg-gradient-to-br from-violet-500/10 to-pink-500/10',
    cardIconColor: 'text-violet-600 dark:text-violet-400',
    cardHoverBorder: 'hover:border-violet-500/30',
    features: [
      { key: 'memory', icon: Brain },
      { key: 'personalities', icon: Smile },
      { key: 'psyche', icon: Heart },
      { key: 'self_knowledge', icon: HelpCircle },
      { key: 'journals', icon: BookOpen },
    ],
  },
  {
    key: 'group_automation',
    icon: CalendarClock,
    headerIconBg: 'bg-gradient-to-br from-emerald-500/15 to-teal-500/15',
    headerIconColor: 'text-emerald-600 dark:text-emerald-400',
    cardIconBg: 'bg-gradient-to-br from-emerald-500/10 to-teal-500/10',
    cardIconColor: 'text-emerald-600 dark:text-emerald-400',
    cardHoverBorder: 'hover:border-emerald-500/30',
    features: [
      { key: 'proactive', icon: BellRing },
      { key: 'interests', icon: Star },
      { key: 'reminders_scheduling', icon: CalendarClock },
      { key: 'skills', icon: Blocks },
    ],
  },
  {
    key: 'group_creation',
    icon: ImagePlus,
    headerIconBg: 'bg-gradient-to-br from-orange-500/15 to-amber-500/15',
    headerIconColor: 'text-orange-600 dark:text-orange-400',
    cardIconBg: 'bg-gradient-to-br from-orange-500/10 to-amber-500/10',
    cardIconColor: 'text-orange-600 dark:text-orange-400',
    cardHoverBorder: 'hover:border-orange-500/30',
    features: [
      { key: 'excalidraw', icon: PenTool },
      { key: 'image_generation', icon: ImagePlus },
      { key: 'attachments', icon: Paperclip },
      { key: 'mcp_apps', icon: AppWindow },
    ],
  },
  {
    key: 'group_power',
    icon: Puzzle,
    headerIconBg: 'bg-gradient-to-br from-indigo-500/15 to-slate-500/15',
    headerIconColor: 'text-indigo-600 dark:text-indigo-400',
    cardIconBg: 'bg-gradient-to-br from-indigo-500/10 to-slate-500/10',
    cardIconColor: 'text-indigo-600 dark:text-indigo-400',
    cardHoverBorder: 'hover:border-indigo-500/30',
    features: [
      { key: 'mcp', icon: Puzzle },
      { key: 'rag_spaces', icon: Library },
      { key: 'sub_agents', icon: Bot },
      { key: 'browser_control', icon: Monitor },
      { key: 'devops_cli', icon: Terminal },
    ],
  },
];

// Responsible & simple
const RESPONSIBLE_FEATURES: FeatureItem[] = [
  { key: 'control', icon: ShieldCheck },
  { key: 'usage_limits', icon: Gauge },
  { key: 'privacy', icon: Lock },
  { key: 'responsive', icon: Smartphone },
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
            <h2
              id="features-title"
              className="text-3xl mobile:text-4xl font-bold tracking-tight mb-4"
            >
              {t('landing.features.title')}
            </h2>
            <p className="text-muted-foreground text-lg max-w-2xl mx-auto">
              {t('landing.features.subtitle')}
            </p>
          </div>
        </FadeInOnScroll>

        {/* Hero features — connectors & tools with accent colors */}
        <div className="grid grid-cols-1 sm:grid-cols-2 mobile:grid-cols-4 gap-6 mb-14">
          {HERO_FEATURES.map(({ key, icon: Icon, accent, iconBg }, i) => (
            <FadeInOnScroll key={key} delay={i * 100}>
              <Card className="hover-lift hover-glow h-full border-border/60 overflow-hidden">
                <div className={cn('h-1', accent)} aria-hidden="true" />
                <CardHeader className="space-y-4 items-center text-center">
                  <div
                    className={cn('w-14 h-14 rounded-xl flex items-center justify-center', iconBg)}
                  >
                    <Icon className="w-7 h-7 text-primary" />
                  </div>
                  <CardTitle className="text-xl">{t(`landing.features.${key}.title`)}</CardTitle>
                  <CardDescription className="text-sm leading-relaxed">
                    {t(`landing.features.${key}.description`)}
                  </CardDescription>
                </CardHeader>
              </Card>
            </FadeInOnScroll>
          ))}
        </div>

        {/* Grouped functional features */}
        <div className="space-y-10">
          {FEATURE_GROUPS.map((group, gi) => {
            const {
              key: groupKey,
              icon: GroupIcon,
              headerIconBg,
              headerIconColor,
              cardIconBg,
              cardIconColor,
              cardHoverBorder,
              features,
            } = group;

            return (
              <FadeInOnScroll key={groupKey} delay={gi * 80}>
                <div>
                  {/* Group header */}
                  <div className="flex flex-col items-center gap-2 mb-6 text-center">
                    <div
                      className={cn(
                        'w-10 h-10 rounded-lg flex items-center justify-center',
                        headerIconBg
                      )}
                    >
                      <GroupIcon className={cn('w-5 h-5', headerIconColor)} />
                    </div>
                    <div>
                      <h3 className="text-lg font-semibold tracking-tight">
                        {t(`landing.features.${groupKey}.title`)}
                      </h3>
                      <p className="text-xs text-muted-foreground">
                        {t(`landing.features.${groupKey}.description`)}
                      </p>
                    </div>
                  </div>

                  {/* Group feature cards */}
                  <div
                    className={cn(
                      'grid grid-cols-1 sm:grid-cols-2 gap-3',
                      features.length === 5 ? 'mobile:grid-cols-5' : 'mobile:grid-cols-4'
                    )}
                  >
                    {features.map(({ key, icon: Icon }) => (
                      <Card
                        key={key}
                        className={cn(
                          'hover-lift hover-glow h-full border-border/60',
                          cardHoverBorder
                        )}
                      >
                        <CardHeader className="space-y-3 p-5">
                          <div className="flex items-center gap-3">
                            <div
                              className={cn(
                                'w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0',
                                cardIconBg
                              )}
                            >
                              <Icon className={cn('w-5 h-5', cardIconColor)} />
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
                    ))}
                  </div>
                </div>
              </FadeInOnScroll>
            );
          })}
        </div>

        {/* Responsible & simple — prominent sub-section */}
        <FadeInOnScroll>
          <div className="mt-16 mb-8 flex flex-col items-center text-center">
            <div className="relative mb-4">
              <div className="w-14 h-14 rounded-full bg-primary/10 flex items-center justify-center">
                <ShieldCheck className="w-7 h-7 text-primary" />
              </div>
              <div
                className="absolute inset-0 rounded-full border-2 border-primary/20 motion-safe:animate-ping"
                style={{ animationDuration: '3s' }}
                aria-hidden="true"
              />
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
