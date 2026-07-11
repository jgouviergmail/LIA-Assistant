/**
 * PsycheMilestoneWatcher — headless observer celebrating relationship
 * milestones (micro-interactions batch I7).
 *
 * Watches the psyche store's relationship stage and fires a one-shot toast
 * when the stage moves FORWARD (stages are one-way by design). The initial
 * hydration never toasts: the previous stage only starts counting once the
 * store has been hydrated (lastUpdated non-null), and the ref primes itself
 * on that first hydrated render.
 */

'use client';

import { useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { usePsycheStore } from '@/stores/psycheStore';
import type { RelationshipStage } from '@/types/psyche';

const STAGE_ORDER: readonly RelationshipStage[] = [
  'ORIENTATION',
  'EXPLORATORY',
  'AFFECTIVE',
  'STABLE',
];

export function PsycheMilestoneWatcher(): null {
  const { t } = useTranslation();
  const stage = usePsycheStore(s => s.relationshipStage);
  const hydrated = usePsycheStore(s => s.lastUpdated !== null);
  const enabled = usePsycheStore(s => s.enabled);
  const prevStageRef = useRef<RelationshipStage | null>(null);

  useEffect(() => {
    if (!hydrated || !enabled) return;
    const prev = prevStageRef.current;
    prevStageRef.current = stage;
    if (prev === null || prev === stage) return;
    if (STAGE_ORDER.indexOf(stage) > STAGE_ORDER.indexOf(prev)) {
      toast.success(t(`psyche.milestone.${stage}`), { icon: '✨', duration: 8000 });
    }
  }, [stage, hydrated, enabled, t]);

  return null;
}
