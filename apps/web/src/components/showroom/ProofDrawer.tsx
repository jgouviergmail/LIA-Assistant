'use client';

/**
 * Proof drawer (P0 Task 5): every visible capability links to its source at
 * one immutable commit SHA. Without a valid release SHA the drawer degrades
 * honestly — repository-root links plus an explicit "not exact" notice; the
 * UI never claims "exact source" in that mode. Each entry separates
 * product-core evidence from P0-fixture evidence and warns that links open
 * GitHub (external navigation).
 */

import { ExternalLink } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type { ShowroomProofLinks } from '@/components/showroom/proof-links';
import { Badge } from '@/components/ui/badge';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';

export interface ProofDrawerProps {
  links: ShowroomProofLinks;
  /** Funnel intent: first open after completion (at-most-once upstream). */
  onOpened: () => void;
}

const KIND_LABEL_KEY = {
  'product-core': 'showroom.proof.kind.product_core',
  'p0-fixture': 'showroom.proof.kind.p0_fixture',
} as const;

export function ProofDrawer({ links, onOpened }: ProofDrawerProps) {
  const { t } = useTranslation();

  return (
    <Dialog
      onOpenChange={(open) => {
        if (open) onOpened();
      }}
    >
      <DialogTrigger asChild>
        {/* Default size on purpose: this trigger sits in the receipt action
            row next to default-size outline CTAs — a smaller control there
            read as a hierarchy that did not exist (owner feedback). */}
        <Button
          type="button"
          variant="outline"
          data-testid="showroom-proof-open"
        >
          {t('showroom.proof.open')}
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[80dvh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t('showroom.proof.title')}</DialogTitle>
          <DialogDescription>
            {links.isImmutable
              ? t('showroom.proof.exact')
              : t('showroom.proof.fallback')}{' '}
            {t('showroom.proof.external_warning')}
          </DialogDescription>
        </DialogHeader>
        <ul className="space-y-2">
          {links.links.map((link) => (
            <li key={link.id} className="flex items-center gap-2 text-sm">
              <Badge
                variant={link.kind === 'product-core' ? 'default' : 'outline'}
              >
                {t(KIND_LABEL_KEY[link.kind])}
              </Badge>
              <a
                href={link.url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex min-w-0 items-center gap-1 text-primary underline-offset-2 hover:underline"
              >
                <span className="truncate">{t(link.labelKey)}</span>
                <ExternalLink
                  className="h-3.5 w-3.5 shrink-0"
                  aria-hidden="true"
                />
              </a>
            </li>
          ))}
        </ul>
      </DialogContent>
    </Dialog>
  );
}
