import { initI18next } from '@/i18n';
import { EyeOff, Shield, KeyRound, Scale } from 'lucide-react';
import { FadeInOnScroll } from './FadeInOnScroll';

interface SecuritySectionProps {
  lng: string;
}

const PILLARS = [
  { key: 'data_control', icon: EyeOff },
  { key: 'bff', icon: Shield },
  { key: 'encryption', icon: KeyRound },
  { key: 'gdpr', icon: Scale },
] as const;

export async function SecuritySection({ lng }: SecuritySectionProps) {
  const { t } = await initI18next(lng);

  return (
    <section id="security" className="landing-section py-24" aria-labelledby="security-title">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="grid grid-cols-1 mobile:grid-cols-2 gap-16 items-center">
          {/* Left: Shield visual + tagline */}
          <FadeInOnScroll>
            <div className="flex flex-col items-center mobile:items-start text-center mobile:text-left">
              <div className="relative mb-8">
                <div className="w-32 h-32 rounded-full bg-primary/10 flex items-center justify-center">
                  <Shield className="w-16 h-16 text-primary" />
                </div>
                {/* Animated ring */}
                <div className="absolute inset-0 rounded-full border-2 border-primary/20 motion-safe:animate-ping" style={{ animationDuration: '3s' }} aria-hidden="true" />
              </div>
              <h2 id="security-title" className="text-3xl mobile:text-4xl font-bold tracking-tight mb-4">
                {t('landing.security.title')}
              </h2>
              <p className="text-lg text-muted-foreground italic">
                {t('landing.security.subtitle')}
              </p>
            </div>
          </FadeInOnScroll>

          {/* Right: 4 pillars */}
          <div className="space-y-6">
            {PILLARS.map(({ key, icon: Icon }, i) => (
              <FadeInOnScroll key={key} delay={i * 100}>
                <div className="flex items-start gap-4 p-4 rounded-xl border border-border/60 bg-card hover-lift">
                  <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0">
                    <Icon className="w-5 h-5 text-primary" />
                  </div>
                  <div>
                    <h3 className="font-semibold mb-1">
                      {t(`landing.security.${key}.title`)}
                    </h3>
                    <p className="text-sm text-muted-foreground leading-relaxed">
                      {t(`landing.security.${key}.description`)}
                    </p>
                  </div>
                </div>
              </FadeInOnScroll>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
