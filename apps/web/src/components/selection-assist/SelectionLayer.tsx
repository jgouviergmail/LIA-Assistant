'use client';
/** Nested Radix focus ownership, body portal geometry, and native selection kept until a click. */
import * as Dialog from '@radix-ui/react-dialog';
import { useCallback, useLayoutEffect, type ReactNode } from 'react';
import { useSelectionMenuPosition } from '@/hooks/useSelectionMenuPosition';
import {
  currentTargetRect,
  focusSelectionTarget,
  type SelectionTarget,
} from '@/lib/selection-assist/targets';

interface Props {
  target: SelectionTarget;
  title: string;
  toolbar?: boolean;
  children: ReactNode;
  onClose: () => void;
  restoreFocus: () => boolean;
}
export function SelectionLayer(props: Props) {
  return (
    <Dialog.Root
      open
      modal={false}
      onOpenChange={open => {
        if (!open) props.onClose();
      }}
    >
      <Dialog.Portal>
        <LayerContent {...props} />
      </Dialog.Portal>
    </Dialog.Root>
  );
}
function LayerContent({ target, title, toolbar = false, children, restoreFocus }: Props) {
  const anchorOf = useCallback(() => currentTargetRect(target), [target]);
  const position = useSelectionMenuPosition(anchorOf);
  useLayoutEffect(() => {
    if (toolbar) return;
    const focusIfNeeded = () => {
      const panel = position.current;
      if (panel && (document.activeElement === panel || !panel.contains(document.activeElement)))
        panel.querySelector<HTMLElement>('[data-selection-close]')?.focus({ preventScroll: true });
    };
    focusIfNeeded();
    // WebKit settles a removed field's focus after layout; placement may also reveal the panel.
    const frame = requestAnimationFrame(focusIfNeeded);
    return () => cancelAnimationFrame(frame);
  }, [position, toolbar, children]);
  return (
    <Dialog.Content
      role={toolbar ? 'toolbar' : 'dialog'}
      aria-label={title}
      aria-keyshortcuts={toolbar ? 'Alt+Enter' : undefined}
      aria-describedby={undefined}
      ref={position}
      onOpenAutoFocus={event => event.preventDefault()}
      onCloseAutoFocus={event => {
        event.preventDefault();
        if (!restoreFocus()) return;
        const active = document.activeElement;
        if (
          active &&
          active !== document.body &&
          !active.closest('[data-selection-assist-ui]') &&
          !target.element.contains(active)
        )
          return;
        focusSelectionTarget(target);
      }}
      onEscapeKeyDown={event => event.stopPropagation()}
      data-selection-assist-ui=""
      data-selection-assist="off"
      onKeyDown={event => {
        if (!toolbar || !['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
        const buttons = Array.from(
          event.currentTarget.querySelectorAll<HTMLButtonElement>('button')
        );
        const current = buttons.findIndex(button => button === document.activeElement);
        const index = toolbarIndex(event.key, current, buttons.length);
        if (buttons[index]) {
          event.preventDefault();
          buttons[index].focus();
        }
      }}
      style={{ visibility: 'hidden', pointerEvents: 'auto' }}
      className={
        toolbar
          ? 'fixed z-[60] flex w-max flex-wrap items-center gap-0.5 overflow-auto overscroll-contain rounded-xl border border-border/60 bg-popover p-1 text-popover-foreground shadow-xl [--selection-max-width:40rem]'
          : 'fixed z-[60] w-[min(24rem,calc(100vw-1rem))] overflow-auto overscroll-contain rounded-2xl border border-border/60 bg-popover p-3 text-popover-foreground shadow-xl [--selection-max-width:24rem]'
      }
    >
      <Dialog.Title className="sr-only">{title}</Dialog.Title>
      {children}
    </Dialog.Content>
  );
}

function toolbarIndex(key: string, current: number, count: number): number {
  if (key === 'Home') return 0;
  if (key === 'End') return count - 1;
  return (current + (key === 'ArrowRight' ? 1 : -1) + count) % count;
}
