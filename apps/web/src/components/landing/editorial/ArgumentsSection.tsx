import { initI18next } from '@/i18n';
import { FadeInOnScroll } from '../FadeInOnScroll';
import { ARGUMENT_IDS, type ArgumentId } from '../comparison/comparison-data';
import { ArgumentVignette } from './ArgumentVignettes';

/**
 * Where each tile sits. On a wide screen the first three share the first row
 * and the last two share the second equally (owner, 2026-11-15); on two
 * columns the last one takes the full width.
 */
const ARGUMENT_SPANS: Readonly<Record<ArgumentId, string>> = {
  agentic: 'lg:col-span-2',
  manual: 'lg:col-span-2',
  family: 'lg:col-span-2',
  voice: 'lg:col-span-3',
  governance: 'md:col-span-2 lg:col-span-3',
};

/**
 * The five arguments, after the video: a mosaic of the landing's glass cards,
 * each opened by a vignette of its own idea (`ArgumentVignettes`).
 */
export async function ArgumentsSection({ lng }: { lng: string }) {
  const { t } = await initI18next(lng);

  return (
    <section
      id="arguments"
      aria-labelledby="arguments-title"
      className="landing-section scroll-mt-24 py-12 sm:py-20"
    >
      <div className="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8">
        <FadeInOnScroll>
          <h2
            id="arguments-title"
            className="text-3xl font-bold tracking-tight text-foreground mobile:text-4xl"
          >
            {t('landing.arguments.title')}
          </h2>
          <p className="mt-4 leading-7 text-muted-foreground">{t('landing.arguments.lede')}</p>
        </FadeInOnScroll>

        <div className="mt-8 grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-6">
          {ARGUMENT_IDS.map(id => (
            <FadeInOnScroll key={id} className={ARGUMENT_SPANS[id]}>
              <article className="cosmos-glass h-full p-5 sm:p-6">
                <ArgumentVignette id={id} />
                <h3 className="text-lg font-semibold tracking-tight text-foreground">
                  {t(`landing.arguments.items.${id}.title`)}
                </h3>
                <p className="mt-3 text-sm leading-6 text-muted-foreground">
                  {t(`landing.arguments.items.${id}.body`)}
                </p>
              </article>
            </FadeInOnScroll>
          ))}
        </div>
      </div>
    </section>
  );
}
