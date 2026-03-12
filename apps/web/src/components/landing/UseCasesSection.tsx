import { initI18next } from '@/i18n';
import { Quote } from 'lucide-react';
import { cn } from '@/lib/utils';
import { FadeInOnScroll } from './FadeInOnScroll';

interface UseCasesSectionProps {
  lng: string;
}

const EXAMPLES = ['example1', 'example2', 'example3', 'example4', 'example5'] as const;

export async function UseCasesSection({ lng }: UseCasesSectionProps) {
  const { t } = await initI18next(lng);

  return (
    <section id="use-cases" className="landing-section py-24 bg-card" aria-labelledby="use-cases-title">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
        <FadeInOnScroll>
          <div className="text-center mb-16">
            <h2 id="use-cases-title" className="text-3xl mobile:text-4xl font-bold tracking-tight mb-4">
              {t('landing.use_cases.title')}
            </h2>
            <p className="text-muted-foreground text-lg max-w-2xl mx-auto">
              {t('landing.use_cases.subtitle')}
            </p>
          </div>
        </FadeInOnScroll>

        {/* Alternating conversation cards with vertical connector */}
        <div className="relative">
          {/* Vertical line */}
          <div className="absolute left-1/2 top-0 bottom-0 w-px bg-border hidden mobile:block" aria-hidden="true" />

          <div className="space-y-8">
            {EXAMPLES.map((key, i) => {
              const isLeft = i % 2 === 0;
              return (
                <FadeInOnScroll key={key} delay={i * 120}>
                  <div
                    className={cn(
                      'relative mobile:w-[48%]',
                      isLeft ? 'mobile:mr-auto mobile:pr-8' : 'mobile:ml-auto mobile:pl-8'
                    )}
                  >
                    {/* Connector dot */}
                    <div
                      className={cn(
                        'hidden mobile:block absolute top-6 w-3 h-3 rounded-full bg-primary border-2 border-background',
                        isLeft ? '-right-1.5' : '-left-1.5'
                      )}
                      aria-hidden="true"
                    />

                    <div className="rounded-xl border border-border bg-background p-5 hover-lift">
                      <div className="flex items-start gap-3 mb-3">
                        <Quote className="w-5 h-5 text-primary flex-shrink-0 mt-0.5" />
                        <p className="text-sm font-medium leading-relaxed italic">
                          &ldquo;{t(`landing.use_cases.${key}.query`)}&rdquo;
                        </p>
                      </div>
                      <p className="text-xs text-muted-foreground pl-8">
                        {t(`landing.use_cases.${key}.description`)}
                      </p>
                    </div>
                  </div>
                </FadeInOnScroll>
              );
            })}
          </div>
        </div>
      </div>
    </section>
  );
}
