'use client';

/**
 * DetailClose — the way out of a detail (ADR-369): one button, the same on every tool.
 *
 * Beside the list a cross closes the pane; where the detail takes the whole screen, the button says
 * where it goes back to, as the mail's reader does. One element either way, so the focus a tool
 * hands it stays on it whatever the width. That name takes what the bar leaves it, its whole width
 * at most and none of it at the least: a tool's name gives way before any act does, and the chevron
 * stays a target a finger can find.
 */
import { ChevronLeft, X } from 'lucide-react';
import type { Ref } from 'react';

import { Button } from '@/components/ui/button';
import { useMediaQuery } from '@/hooks/useMediaQuery';
import { WORKBENCH_DESKTOP } from '@/lib/workbench/tools';

export interface DetailCloseProps {
  /** What the cross is called. */
  closeLabel: string;
  /** Where it goes back to: the tool's name. */
  backLabel: string;
  onClose: () => void;
  buttonRef?: Ref<HTMLButtonElement>;
}

export function DetailClose({ closeLabel, backLabel, onClose, buttonRef }: DetailCloseProps) {
  const beside = useMediaQuery(WORKBENCH_DESKTOP);
  if (beside) {
    return (
      <Button
        ref={buttonRef}
        variant="ghost"
        size="icon"
        onClick={onClose}
        aria-label={closeLabel}
        className="shrink-0"
      >
        <X className="h-4 w-4" aria-hidden="true" />
      </Button>
    );
  }
  return (
    <Button
      ref={buttonRef}
      variant="ghost"
      onClick={onClose}
      className="min-w-6 max-w-max flex-1 gap-1 px-2"
    >
      <ChevronLeft className="h-4 w-4" aria-hidden="true" />
      <span className="min-w-0 max-w-[12rem] truncate">{backLabel}</span>
    </Button>
  );
}
