import { initI18next } from '@/i18n';
import { Briefcase, Users, Code, Settings } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { FadeInOnScroll } from './FadeInOnScroll';

interface AudienceSectionProps {
  lng: string;
}

const AUDIENCES = [
  { key: 'freelance', icon: Briefcase },
  { key: 'family', icon: Users },
  { key: 'developer', icon: Code },
  { key: 'admin', icon: Settings },
] as const;

export async function AudienceSection({ lng }: AudienceSectionProps) {
  const { t } = await initI18next(lng);

  return (
    <section className="landing-section py-24" aria-labelledby="audience-title">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <FadeInOnScroll>
          <div className="text-center mb-16">
            <h2
              id="audience-title"
              className="text-3xl mobile:text-4xl font-bold tracking-tight mb-4"
            >
              {t('landing.audience.title')}
            </h2>
            <p className="text-muted-foreground text-lg max-w-2xl mx-auto">
              {t('landing.audience.subtitle')}
            </p>
          </div>
        </FadeInOnScroll>

        <div className="grid grid-cols-1 sm:grid-cols-2 mobile:grid-cols-4 gap-6">
          {AUDIENCES.map(({ key, icon: Icon }, i) => (
            <FadeInOnScroll key={key} delay={i * 100}>
              <Card className="hover-lift hover-glow h-full border-border/60">
                <CardHeader className="space-y-4 text-center">
                  <div className="w-14 h-14 rounded-xl bg-primary/10 flex items-center justify-center mx-auto">
                    <Icon className="w-7 h-7 text-primary" />
                  </div>
                  <CardTitle className="text-lg">
                    {t(`landing.audience.${key}.title`)}
                  </CardTitle>
                  <CardDescription className="text-sm leading-relaxed">
                    {t(`landing.audience.${key}.description`)}
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
