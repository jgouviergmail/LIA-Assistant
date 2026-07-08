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
    <section
      id="use-cases"
      className="landing-section py-20 bg-card"
      aria-labelledby="use-cases-title"
    >
      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
        <FadeInOnScroll>
          <div className="text-center mb-12">
            <h2
              id="use-cases-title"
              className="text-3xl mobile:text-4xl font-bold tracking-tight mb-4"
            >
              {t('landing.use_cases.title')}
            </h2>
            <p className="text-muted-foreground text-lg max-w-2xl mx-auto">
              {t('landing.use_cases.subtitle')}
            </p>
            <p className="text-muted-foreground text-sm max-w-2xl mx-auto mt-4 leading-relaxed">
              {t('landing.use_cases.intro')}
            </p>
          </div>
        </FadeInOnScroll>

        {/* Featured example + compact 2-column grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {EXAMPLES.map((key, i) => {
            const featured = i === 0;
            return (
              <FadeInOnScroll
                key={key}
                delay={i * 80}
                className={cn(featured && 'sm:col-span-2')}
              >
                <div
                  className={cn(
                    'h-full rounded-xl border border-border bg-background p-5 hover-lift',
                    featured && 'border-primary/30 bg-primary/[0.03]'
                  )}
                >
                  <div className="flex items-start gap-3 mb-3">
                    <Quote
                      className={cn(
                        'w-5 h-5 flex-shrink-0 mt-0.5 text-primary',
                        featured && 'w-6 h-6'
                      )}
                    />
                    <p
                      className={cn(
                        'font-medium leading-relaxed italic',
                        featured ? 'text-base' : 'text-sm'
                      )}
                    >
                      &ldquo;{t(`landing.use_cases.${key}.query`)}&rdquo;
                    </p>
                  </div>
                  <p className="text-xs text-muted-foreground pl-8 leading-relaxed">
                    {t(`landing.use_cases.${key}.description`)}
                  </p>
                </div>
              </FadeInOnScroll>
            );
          })}
        </div>
      </div>
    </section>
  );
}
