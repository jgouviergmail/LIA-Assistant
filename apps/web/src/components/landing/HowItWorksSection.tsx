import { initI18next } from '@/i18n';
import { MessageSquare, Brain, ShieldCheck, Zap } from 'lucide-react';
import { FadeInOnScroll } from './FadeInOnScroll';

interface HowItWorksSectionProps {
  lng: string;
}

const STEPS = [
  { key: 'step1', icon: MessageSquare, color: 'text-blue-500' },
  { key: 'step2', icon: Brain, color: 'text-purple-500' },
  { key: 'step3', icon: ShieldCheck, color: 'text-amber-500' },
  { key: 'step4', icon: Zap, color: 'text-green-500' },
] as const;

export async function HowItWorksSection({ lng }: HowItWorksSectionProps) {
  const { t } = await initI18next(lng);

  return (
    <section
      id="how-it-works"
      className="landing-section py-24 bg-card"
      aria-labelledby="how-it-works-title"
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <FadeInOnScroll>
          <div className="text-center mb-16">
            <h2
              id="how-it-works-title"
              className="text-3xl mobile:text-4xl font-bold tracking-tight mb-4"
            >
              {t('landing.how_it_works.title')}
            </h2>
            <p className="text-muted-foreground text-lg max-w-2xl mx-auto">
              {t('landing.how_it_works.subtitle')}
            </p>
          </div>
        </FadeInOnScroll>

        {/* Timeline */}
        <div className="relative">
          {/* Horizontal line (desktop) */}
          <div
            className="hidden mobile:block absolute top-10 left-[12%] right-[12%] h-0.5 bg-border"
            aria-hidden="true"
          >
            <div className="absolute inset-0 bg-gradient-to-r from-blue-500/30 via-purple-500/30 to-green-500/30" />
          </div>

          <div className="grid grid-cols-1 mobile:grid-cols-4 gap-8 mobile:gap-6">
            {STEPS.map(({ key, icon: Icon, color }, i) => (
              <FadeInOnScroll key={key} delay={i * 150}>
                <div className="relative flex flex-col items-center text-center">
                  {/* Step number + icon */}
                  <div className="relative z-10 mb-6">
                    <div className="w-20 h-20 rounded-full bg-background border-2 border-border flex items-center justify-center shadow-md">
                      <Icon className={`w-8 h-8 ${color}`} />
                    </div>
                  </div>

                  {/* Vertical line (mobile only) */}
                  {i < STEPS.length - 1 && (
                    <div
                      className="mobile:hidden w-0.5 h-8 bg-border -mt-2 mb-4"
                      aria-hidden="true"
                    />
                  )}

                  <h3 className="text-lg font-semibold mb-2">
                    {t(`landing.how_it_works.${key}.title`)}
                  </h3>
                  <p className="text-sm text-muted-foreground leading-relaxed max-w-xs">
                    {t(`landing.how_it_works.${key}.description`)}
                  </p>
                </div>
              </FadeInOnScroll>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
