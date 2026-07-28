/**
 * Mini-UI vocabulary of the /more animated scenes: the product's interface
 * language (composer, bubbles, toasts, setting rows…) in miniature.
 *
 * Rules:
 * - purely presentational — no state, no handlers, no interactive semantics
 *   (stages are aria-hidden decoration; a focusable element inside would be
 *   an unreachable stop for assistive tech);
 * - theme tokens only (bg-background, border-border, text-muted-foreground,
 *   bg-primary/10…), so dark mode is native and contrast follows the design
 *   system in both themes.
 */

import type { LucideIcon } from 'lucide-react';
import { MousePointer2 } from 'lucide-react';
import type { ReactNode } from 'react';

import { cn } from '@/lib/utils';

/** Shared stage frame of every scene (fixed height — CLS-safe). */
export const STAGE =
  'relative flex h-36 w-full flex-col items-center justify-center overflow-hidden rounded-t-xl bg-muted/40 px-4';

export function SkeletonLine({ w, className }: { w: string; className?: string }) {
  return <div className={cn('h-2 rounded-full bg-muted-foreground/15', w, className)} />;
}

export function MiniComposer({
  children,
  trailing,
  className,
}: {
  children?: ReactNode;
  trailing?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        'flex w-full items-center gap-2 rounded-full border border-border bg-background px-3 py-2 shadow-sm',
        className
      )}
    >
      <div className="min-w-0 flex-1">{children ?? <SkeletonLine w="w-2/3" />}</div>
      {trailing && (
        <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary/10">
          {trailing}
        </span>
      )}
    </div>
  );
}

export function MiniBubble({
  side,
  tone = 'default',
  children,
  className,
}: {
  side: 'user' | 'assistant';
  tone?: 'default' | 'destructive' | 'success';
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        'max-w-[85%] rounded-2xl border px-3 py-2 text-[10px] leading-snug',
        side === 'user'
          ? 'self-end rounded-br-[5px] border-primary/30 bg-primary/10'
          : 'self-start rounded-tl-[5px] border-border bg-background',
        tone === 'destructive' && 'border-destructive/40 bg-destructive/5',
        tone === 'success' && 'border-primary/40 bg-primary/5',
        className
      )}
    >
      {children}
    </div>
  );
}

export function MiniToast({
  icon: Icon,
  tone,
  children,
  className,
}: {
  icon: LucideIcon;
  tone: 'info' | 'warning' | 'success';
  children?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        'flex items-center gap-1.5 rounded-lg border bg-background px-2.5 py-1.5 text-[10px] font-medium shadow-sm',
        tone === 'warning' && 'border-warning/40 text-warning',
        tone === 'success' && 'border-primary/40 text-primary',
        tone === 'info' && 'border-border text-muted-foreground',
        className
      )}
    >
      <Icon className="h-3 w-3 shrink-0" />
      {children}
    </div>
  );
}

export function MiniSettingRow({
  icon: Icon,
  label,
  highlighted,
  className,
}: {
  icon: LucideIcon;
  label?: string;
  highlighted?: boolean;
  className?: string;
}) {
  return (
    <div
      className={cn(
        'flex w-full items-center gap-2 rounded-md border border-border bg-background px-2 py-1.5',
        highlighted && 'ring-2 ring-primary/60',
        className
      )}
    >
      <Icon className="h-3 w-3 shrink-0 text-muted-foreground" />
      {label ? (
        <span className="truncate text-[10px] text-foreground/80">{label}</span>
      ) : (
        <SkeletonLine w="w-1/2" />
      )}
    </div>
  );
}

export function MiniChip({
  children,
  pressed,
  className,
}: {
  children: ReactNode;
  pressed?: boolean;
  className?: string;
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full border border-border bg-background px-2.5 py-1 text-[10px] transition-colors',
        pressed && 'border-primary/50 bg-primary/10 text-primary',
        className
      )}
    >
      {children}
    </span>
  );
}

export function MiniGauge({
  pct,
  tone = 'default',
  className,
}: {
  pct: number;
  tone?: 'default' | 'warning';
  className?: string;
}) {
  return (
    <div
      className={cn('h-2 w-full overflow-hidden rounded-full bg-muted-foreground/15', className)}
    >
      <div
        data-fill
        className={cn(
          'h-full rounded-full transition-[width] duration-700 ease-out',
          tone === 'warning' ? 'bg-warning' : 'bg-primary'
        )}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

export function KeyCap({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <kbd
      className={cn(
        'inline-flex min-w-5 items-center justify-center rounded-md border border-border bg-background px-1.5 py-0.5 text-[10px] font-semibold text-foreground/80 shadow-[0_1px_0_1px] shadow-border',
        className
      )}
    >
      {children}
    </kbd>
  );
}

export function Cursor({ className }: { className?: string }) {
  return (
    <MousePointer2
      className={cn(
        'absolute h-3.5 w-3.5 fill-foreground/80 text-foreground/80 drop-shadow transition-all duration-500 ease-out',
        className
      )}
    />
  );
}

export function PhoneFrame({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div
      className={cn(
        'flex h-28 w-16 flex-col overflow-hidden rounded-xl border-2 border-border bg-background p-1.5 shadow-sm',
        className
      )}
    >
      <div className="mx-auto mb-1 h-0.5 w-6 rounded-full bg-muted-foreground/20" />
      <div className="min-h-0 flex-1">{children}</div>
    </div>
  );
}
