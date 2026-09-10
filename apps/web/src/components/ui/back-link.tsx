'use client';

/**
 * The way back from a screen several doors lead to.
 *
 * A ghost button with a left arrow, above the title — the shape the meeting
 * detail and the space detail already used, written once so a third and a
 * fourth cannot each invent their own spacing.
 *
 * It is a real `<button>` driving the router rather than an `<a>`: the target
 * is resolved from a token at render time (`lib/back-origin.ts`), and the
 * pages that use it also localize the route through their own router.
 */

import { ArrowLeft } from 'lucide-react';

import { Button } from '@/components/ui/button';

export interface BackLinkProps {
  /** Already-translated label, e.g. « Retour au chat ». */
  label: string;
  onClick: () => void;
}

export function BackLink({ label, onClick }: BackLinkProps) {
  return (
    <Button type="button" variant="ghost" size="sm" className="-ml-2" onClick={onClick}>
      <ArrowLeft className="mr-1 h-4 w-4" aria-hidden="true" />
      {label}
    </Button>
  );
}
