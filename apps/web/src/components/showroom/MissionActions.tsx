'use client';

/**
 * End-of-mission actions, ADR-207 altitudes — owner-arbitrated order
 * (2026-08-06): no beta CTA here (the demo funnels to self-hosting, not to
 * the hosted beta), the install guide is THE solid primary, then the
 * outline secondaries at the SAME geometry (releases, source, proof
 * drawer), then the ghost utilities on their own row (replay, back to the
 * mission list).
 *
 * Centred and spaced (owner request 2026-08-07): this block CLOSES a mission,
 * so it reads as a conclusion rather than as a left-aligned toolbar continuing
 * the storyboard above it. Both rows wrap, so a phone folds them instead of
 * clipping a control off the edge.
 */

import { LayoutGrid, RotateCcw } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { ProofDrawer } from '@/components/showroom/ProofDrawer';
import type { ShowroomProofLinks } from '@/components/showroom/proof-links';
import type { ShowroomCtaKind } from '@/components/showroom/useShowroomMission';
import { Button } from '@/components/ui/button';

const GITHUB_URL = 'https://github.com/jgouviergmail/LIA-Assistant';

export interface MissionActionsProps {
  proofLinks: ShowroomProofLinks;
  onRestart: () => void;
  onChangeMission: () => void;
  onProofOpened: () => void;
  onCta: (kind: ShowroomCtaKind) => void;
}

export function MissionActions({
  proofLinks,
  onRestart,
  onChangeMission,
  onProofOpened,
  onCta,
}: MissionActionsProps) {
  const { t } = useTranslation();
  return (
    <div className="space-y-5 pt-2">
      <h4 className="text-center text-sm font-semibold text-foreground">
        {t('showroom.actions.title')}
      </h4>
      <div
        data-testid="showroom-actions-row-primary"
        className="flex flex-wrap items-center justify-center gap-3"
      >
        <Button asChild type="button">
          <a
            href={`${GITHUB_URL}#quick-start`}
            target="_blank"
            rel="noopener noreferrer"
            data-testid="showroom-cta-install"
            onClick={() => onCta('install_guide')}
          >
            {t('showroom.cta.install')}
          </a>
        </Button>
        <Button asChild type="button" variant="outline">
          <a
            href={`${GITHUB_URL}/releases`}
            target="_blank"
            rel="noopener noreferrer"
            data-testid="showroom-cta-release"
            onClick={() => onCta('release')}
          >
            {t('showroom.cta.release')}
          </a>
        </Button>
        <Button asChild type="button" variant="outline">
          <a
            href={GITHUB_URL}
            target="_blank"
            rel="noopener noreferrer"
            data-testid="showroom-cta-source"
            onClick={() => onCta('source')}
          >
            {t('showroom.cta.source')}
          </a>
        </Button>
        <ProofDrawer links={proofLinks} onOpened={onProofOpened} />
      </div>
      <div
        data-testid="showroom-actions-row-utility"
        className="flex flex-wrap items-center justify-center gap-3"
      >
        <Button type="button" variant="ghost" data-testid="showroom-restart" onClick={onRestart}>
          <RotateCcw className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
          {t('showroom.restart')}
        </Button>
        <Button
          type="button"
          variant="ghost"
          data-testid="showroom-change-mission"
          onClick={onChangeMission}
        >
          <LayoutGrid className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
          {t('showroom.change_mission')}
        </Button>
      </div>
    </div>
  );
}
