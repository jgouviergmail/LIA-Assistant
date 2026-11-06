'use client';

/**
 * Dragging an event in the grid (ADR-369, lot 2), from `lg` (the workboard's
 * rule: below it nothing drags, a finger scrolls).
 *
 * A chip moves by its body and stretches by its bottom edge; each day is a
 * place to land. What dnd-kit reports becomes a drop (`lib/workbench/calendar/
 * drag`), and the screen decides what a drop does. A short press stays a click
 * on the event's link; the click that ends a drag is swallowed, since dnd-kit
 * only stops its propagation and the browser would follow the link. The
 * pointer is the only way in: an event's editor is the keyboard's way, and the
 * single-pointer one (WCAG 2.5.7).
 */
import {
  DndContext,
  PointerSensor,
  pointerWithin,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core';
import type { CSSProperties, ReactNode } from 'react';

import { cn } from '@/lib/utils';
import { snappedMinutes, type EventDrop } from '@/lib/workbench/calendar/drag';
import type { ShownEvent } from '@/lib/workbench/calendar/events';

import { EventChip, type EventChipProps } from './EventChip';

/** How far a press travels before it is a drag: under this it stays a click. */
const DRAG_START_PX = 6;
/** How long the click that ends a drag is waited for. */
const CLICK_WAIT_MS = 50;
/** The grid scrolls under a drag at its very edge, so a short move stays where it is dropped. */
const EDGE_SCROLL = { threshold: { x: 0, y: 0.08 } };

export interface EventDrag {
  /** Whether the person may drag this event. */
  allows: (event: ShownEvent) => boolean;
  onDrop: (event: ShownEvent, drop: EventDrop) => void;
}

interface DragData {
  event: ShownEvent;
  edge: EventDrop['edge'];
}

function swallow(click: Event): void {
  click.preventDefault();
  click.stopPropagation();
}

/** Takes the click a drag ends on (none comes when the pointer left the chip). */
function swallowDragClick(): void {
  window.addEventListener('click', swallow, { capture: true, once: true });
}

function stopSwallowing(): void {
  window.setTimeout(
    () => window.removeEventListener('click', swallow, { capture: true }),
    CLICK_WAIT_MS
  );
}

export function CalendarDragSurface({
  drag,
  hourPx,
  children,
}: {
  drag: EventDrag;
  hourPx: number;
  children: ReactNode;
}) {
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: DRAG_START_PX } })
  );
  const onDragEnd = ({ active, delta, over }: DragEndEvent) => {
    stopSwallowing();
    const data = active.data.current as DragData | undefined;
    const day: unknown = over?.data.current?.day;
    if (!data || typeof day !== 'string') return;
    drag.onDrop(data.event, { edge: data.edge, minutes: snappedMinutes(delta.y, hourPx), day });
  };
  return (
    <DndContext
      sensors={sensors}
      collisionDetection={pointerWithin}
      autoScroll={EDGE_SCROLL}
      onDragStart={swallowDragClick}
      onDragCancel={stopSwallowing}
      onDragEnd={onDragEnd}
    >
      {children}
    </DndContext>
  );
}

/** A day of the grid, a place to land. */
export function DropColumn({
  day,
  height,
  children,
}: {
  day: string;
  height: number;
  children: ReactNode;
}) {
  const { setNodeRef, isOver } = useDroppable({ id: `day|${day}`, data: { day } });
  return (
    <div
      ref={setNodeRef}
      className={cn('relative border-l', isOver && 'bg-primary/5')}
      style={{ height }}
    >
      {children}
    </div>
  );
}

/** A chip the pointer can move and stretch: it follows the pointer, the drop decides. */
export function DraggableChip({
  event,
  day,
  chip,
}: {
  event: ShownEvent;
  day: string;
  chip: EventChipProps;
}) {
  const data: DragData = { event, edge: 'move' };
  const move = useDraggable({ id: `move|${event.key}|${day}`, data });
  const resize = useDraggable({
    id: `end|${event.key}|${day}`,
    data: { ...data, edge: 'end' } satisfies DragData,
  });
  const style: CSSProperties = { ...chip.style };
  if (move.transform) {
    style.transform = `translate3d(${move.transform.x}px, ${move.transform.y}px, 0)`;
    style.zIndex = 20;
  }
  if (resize.transform) {
    style.height = Number(chip.style?.height ?? 0) + resize.transform.y;
    style.zIndex = 20;
  }
  return (
    <EventChip
      {...chip}
      style={style}
      setFrame={move.setNodeRef}
      frameListeners={move.listeners}
      setEdge={resize.setNodeRef}
      edgeListeners={resize.listeners}
    />
  );
}
