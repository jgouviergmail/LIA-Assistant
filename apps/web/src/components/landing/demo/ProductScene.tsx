'use client';

import dynamic from 'next/dynamic';
import { Check, ClipboardList, FileText, LockKeyhole, Mail, Radio, Sparkles } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { SCENE_TONES } from './scene-tones';
import { ProductApproval } from './ProductApproval';
import { ClassicProductResult } from './ClassicProductResult';
import { productResultHtml } from './product-result-html';
import {
  PRODUCT_DEMO_KEY,
  HOME_PRODUCT_DEMO_KEY,
  productScene,
  type ProductSceneId,
  type ProductScenePhase,
} from './scenes';

interface ProductSceneProps {
  sceneId: ProductSceneId;
  /** Omit for a completed illustration; the player reveals the same scene in three beats. */
  phase?: ProductScenePhase;
  className?: string;
  /** Richer results and copy are scoped to the homepage. */
  home?: boolean;
}

const MarkdownContent = dynamic(
  () => import('@/components/chat/MarkdownContent').then(module => module.MarkdownContent),
  { loading: () => <div aria-hidden="true" className="h-40 rounded-lg bg-muted/40" /> }
);

/** The homepage uses a meeting, while the legacy scene remains a web search. */
const HOME_SOURCES = {
  decision: ['space', 'mail', 'meeting'],
  day: ['preferences', 'calendar', 'news'],
  watch: ['commitment', 'mail', 'routine'],
  call: ['calendar', 'preferences', 'approval'],
  research: ['meeting', 'transcript', 'notes'],
  relay: ['peer', 'scope', 'calendar'],
} satisfies Record<ProductSceneId, readonly string[]>;

export function ProductResult({ sceneId }: { sceneId: ProductSceneId }) {
  const { t } = useTranslation();
  if (sceneId === 'call') return <ProductApproval />;
  return (
    <div className="landing-product-result space-y-3 [--lia-text-secondary:var(--lia-text)]">
      {sceneId === 'day' && (
        <div className="flex h-9 items-center justify-center gap-1" aria-hidden="true">
          <Radio className="mr-3 h-5 w-5 text-primary" />
          {[8, 16, 24, 12, 28, 19, 32, 22, 14, 26, 32, 18, 10, 24, 16, 8].map((height, i) => (
            <span key={i} className="w-1.5 rounded-full bg-primary/60" style={{ height }} />
          ))}
        </div>
      )}
      <MarkdownContent content={productResultHtml(sceneId, t)} />
    </div>
  );
}

/** A readable product illustration, shared by the hero player and the chapters. */
export function ProductScene({ sceneId, phase = 2, className, home = false }: ProductSceneProps) {
  const { t } = useTranslation();
  const scene = productScene(sceneId);
  const Icon = home && sceneId === 'research' ? ClipboardList : scene.icon;
  const sources = home ? HOME_SOURCES[sceneId] : scene.sources;
  const demoKey = home ? HOME_PRODUCT_DEMO_KEY : PRODUCT_DEMO_KEY;
  const key = `${demoKey}.scenes.${scene.id}`;
  const tone = SCENE_TONES[sceneId];

  return (
    <div
      className={cn(
        'relative flex min-h-[550px] min-w-0 flex-col rounded-2xl border border-border bg-card text-left shadow-lg [overflow-wrap:anywhere] sm:min-h-[510px]',
        className
      )}
    >
      <div className="flex min-h-12 items-center gap-2 border-b border-border px-4 py-3">
        <Icon className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
        <p className="text-sm font-semibold">{t(`${key}.title`)}</p>
        <span className="ml-auto shrink-0 text-px-10 text-muted-foreground">
          {t(`${demoKey}.example`)}
        </span>
      </div>
      <div className="flex flex-1 flex-col gap-4 p-4">
        <div className="ml-5 rounded-2xl rounded-tr-sm bg-primary/10 px-3.5 py-3">
          <p className="text-sm leading-relaxed">{t(`${key}.request`)}</p>
        </div>
        <div
          aria-hidden={phase < 1}
          style={{ visibility: phase < 1 ? 'hidden' : undefined }}
          className={cn(
            'space-y-2 transition-opacity duration-500 motion-reduce:transition-none',
            phase < 1 && 'opacity-0'
          )}
        >
          <p className="flex items-center gap-1.5 text-px-11 font-medium text-muted-foreground">
            <Sparkles className="h-3.5 w-3.5 text-primary" aria-hidden="true" />
            {t(`${demoKey}.context`)}
          </p>
          <div className="grid grid-cols-3 gap-1.5">
            {sources.map((source, i) => (
              <div
                key={source}
                className="min-w-0 rounded-lg border border-border bg-background px-2 py-2"
              >
                <span className="mb-1 flex items-center gap-1 text-px-10 font-semibold leading-snug text-primary">
                  {home &&
                    (source === 'mail' ? (
                      <Mail className="h-3 w-3 shrink-0" aria-hidden="true" />
                    ) : (
                      <FileText className="h-3 w-3 shrink-0" aria-hidden="true" />
                    ))}
                  {t(`${demoKey}.sources.${source}`)}
                </span>
                <span className="mt-1 block text-px-11 leading-snug">
                  {t(`${key}.source_${i + 1}`)}
                </span>
              </div>
            ))}
          </div>
        </div>
        <div
          aria-hidden={phase < 2}
          style={{ visibility: phase < 2 ? 'hidden' : undefined }}
          className={cn(
            'flex-1 space-y-3 rounded-xl border bg-background p-3 transition-opacity duration-500 motion-reduce:transition-none',
            tone.border,
            phase < 2 && 'opacity-0'
          )}
        >
          <p
            className={cn('flex items-center gap-2 text-sm font-semibold leading-snug', tone.text)}
          >
            <Check className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
            {t(`${key}.result_title`)}
          </p>
          {home ? (
            <ProductResult key={sceneId} sceneId={sceneId} />
          ) : (
            <ClassicProductResult sceneId={sceneId} />
          )}
          <div className="flex items-start gap-1.5 border-t border-border pt-2 text-px-10 leading-relaxed text-muted-foreground">
            <LockKeyhole className="mt-0.5 h-3 w-3 shrink-0 text-primary" aria-hidden="true" />
            <span>{t(`${key}.guardrail`)}</span>
          </div>
        </div>
      </div>
      <p className="border-t border-border px-4 py-2 text-px-10 leading-snug text-muted-foreground">
        {t(`${demoKey}.illustrative`)}
      </p>
    </div>
  );
}
