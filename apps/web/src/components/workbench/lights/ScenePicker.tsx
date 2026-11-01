'use client';

/**
 * ScenePicker — the scenes of one room (ADR-369).
 *
 * A scene is a button that shows it; the one the bridge shows now is pressed
 * (`aria-pressed`). A scene moves many lamps, so the bridge is re-read after.
 * A scene asked while another is on its way is not sent twice.
 */
import { Sparkles } from 'lucide-react';
import { useState } from 'react';

import { Button } from '@/components/ui/button';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { WorkbenchScene } from '@/lib/workbench/types';

export interface ScenePickerProps {
  lng: Language;
  scenes: readonly WorkbenchScene[];
  /** Show a scene; resolves once shown and re-read, rejects (already said) when refused. */
  onRecall: (scene: WorkbenchScene) => Promise<void>;
}

export function ScenePicker({ lng, scenes, onRecall }: ScenePickerProps) {
  const { t } = useTranslation(lng);
  const [asked, setAsked] = useState<string | null>(null);
  if (scenes.length === 0) return null;

  return (
    <section aria-label={t('workbench.lights.scenes')} className="space-y-2">
      <p className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-muted-foreground">
        <Sparkles className="h-3.5 w-3.5 text-primary" aria-hidden="true" />
        {t('workbench.lights.scenes')}
      </p>
      <div className="flex flex-wrap gap-2">
        {scenes.map(scene => (
          <Button
            key={scene.id}
            type="button"
            size="sm"
            // The scene shown now is tinted; the others are neutral (grey = not shown).
            variant={scene.active ? 'softPrimary' : 'secondary'}
            aria-pressed={scene.active}
            isLoading={asked === scene.id}
            onClick={() => {
              if (asked) return;
              setAsked(scene.id);
              void onRecall(scene)
                .catch(() => undefined)
                .finally(() => setAsked(null));
            }}
          >
            {scene.name}
          </Button>
        ))}
      </div>
    </section>
  );
}
