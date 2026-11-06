'use client';

/**
 * ScenePicker — the scenes of one room, or those no room holds (ADR-369).
 *
 * A scene is a button that shows it; the one the bridge shows now is pressed
 * (`aria-pressed`). One whose palette can play has a second button beside it that
 * starts its motion, pressed while it plays, and holds it still when pressed again.
 * A scene moves many lamps, so the bridge is re-read after. A scene asked while
 * another is on its way is not sent twice.
 */
import { Sparkles, Waves } from 'lucide-react';
import { useState } from 'react';

import { Button } from '@/components/ui/button';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { WorkbenchScene } from '@/lib/workbench/types';

/** Show a scene; resolves once shown and re-read, rejects (already said) when refused. */
export type SceneRecallAct = (scene: WorkbenchScene, play?: boolean) => Promise<void>;

export interface ScenePickerProps {
  lng: Language;
  scenes: readonly WorkbenchScene[];
  /** What the group is called. */
  labelKey?: string;
  onRecall: SceneRecallAct;
}

export function ScenePicker({
  lng,
  scenes,
  labelKey = 'workbench.lights.scenes',
  onRecall,
}: ScenePickerProps) {
  const { t } = useTranslation(lng);
  const [asked, setAsked] = useState<string | null>(null);
  if (scenes.length === 0) return null;
  const recall = (scene: WorkbenchScene, play?: boolean) => {
    if (asked) return;
    setAsked(scene.id);
    void onRecall(scene, play)
      .catch(() => undefined)
      .finally(() => setAsked(null));
  };

  return (
    <section aria-label={t(labelKey)} className="space-y-2">
      <p className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-muted-foreground">
        <Sparkles className="h-3.5 w-3.5 text-primary" aria-hidden="true" />
        {t(labelKey)}
      </p>
      <div className="flex flex-wrap gap-2">
        {scenes.map(scene => (
          <div key={scene.id} className="inline-flex items-center gap-1">
            <Button
              type="button"
              size="sm"
              // The scene shown now is tinted; the others are neutral (grey = not shown).
              variant={scene.active ? 'softPrimary' : 'secondary'}
              aria-pressed={scene.active}
              isLoading={asked === scene.id}
              onClick={() => recall(scene)}
            >
              {scene.name}
            </Button>
            {scene.dynamic && (
              <Button
                type="button"
                size="icon"
                variant={scene.playing ? 'softPrimary' : 'secondary'}
                aria-pressed={scene.playing}
                aria-label={t('workbench.lights.scene_motion', { scene: scene.name })}
                onClick={() => recall(scene, !scene.playing)}
              >
                <Waves className="h-4 w-4" aria-hidden="true" />
              </Button>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}
