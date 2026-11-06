'use client';

/**
 * Dragging messages to a folder of the pane (ADR-369, lot 4), from `lg`, with a mouse
 * (the workboard's rule: below it nothing drags, a finger scrolls).
 *
 * A row is carried by its body; each folder that takes it is a place to land
 * (`takesDrop`). A short press stays a click on the row's link, and the click that
 * ends a drag is swallowed: dnd-kit only stops its propagation, and the browser would
 * follow the link. The pointer is the only way in: « Move to » is the keyboard's way,
 * and the single-pointer one (WCAG 2.5.7).
 */
import {
  DndContext,
  DragOverlay,
  PointerSensor,
  pointerWithin,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from '@dnd-kit/core';
import { useState, type ReactNode } from 'react';

import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { draggedIds } from '@/lib/workbench/mail';

/** How far a press travels before it is a drag: under this it stays a click. */
const DRAG_START_PX = 6;
/** How long the click that ends a drag is waited for. */
const CLICK_WAIT_MS = 50;

function swallow(click: Event): void {
  click.preventDefault();
  click.stopPropagation();
}

export interface MailDragProps {
  lng: Language;
  selected: ReadonlySet<string>;
  /** The messages a row stands for: itself, or a conversation's loaded ones. */
  membersOf: (id: string) => readonly string[];
  onDrop: (ids: readonly string[], folder: string) => void;
  children: ReactNode;
}

export function MailDrag({ lng, selected, membersOf, onDrop, children }: MailDragProps) {
  const { t } = useTranslation(lng);
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: DRAG_START_PX } })
  );
  const [carried, setCarried] = useState<string[] | null>(null);
  const onDragStart = ({ active }: DragStartEvent) => {
    setCarried(draggedIds(String(active.id), selected).flatMap(membersOf));
    window.addEventListener('click', swallow, { capture: true, once: true });
  };
  const finish = () => {
    setCarried(null);
    window.setTimeout(
      () => window.removeEventListener('click', swallow, { capture: true }),
      CLICK_WAIT_MS
    );
  };
  const onDragEnd = ({ over }: DragEndEvent) => {
    if (over && carried) onDrop(carried, String(over.id));
    finish();
  };
  return (
    <DndContext
      sensors={sensors}
      collisionDetection={pointerWithin}
      autoScroll={false}
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      onDragCancel={finish}
    >
      {children}
      <DragOverlay dropAnimation={null}>
        {carried && (
          <span className="inline-flex rounded-full bg-primary px-3 py-1 text-sm font-medium text-primary-foreground shadow-lg">
            {t('workbench.mail.dragging', { count: carried.length })}
          </span>
        )}
      </DragOverlay>
    </DndContext>
  );
}
