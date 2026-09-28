'use client';

/**
 * The table elements of the chat's Markdown pipeline (B2).
 *
 * Module-level, and not inline in `MarkdownContent`'s `components` map: that
 * map is rebuilt on every render, so an inline component is a NEW type on
 * every streamed token and React remounts its whole subtree — a table (and its
 * layout measurement) rebuilt token after token.
 *
 * They forward what the pipeline put on the element — the explicit roles and
 * `data-label` written by `rehype-table-labels`, `colSpan` / `rowSpan`, and a
 * model's class — which the previous inline versions silently dropped (a
 * `colspan` written by the model never reached the page). A free `style` is
 * NOT forwarded: the model may write `style="white-space:nowrap"`, which is
 * the very defect this rendering fixes. Only a cell's text alignment passes —
 * the one style GFM itself produces (`| :---: |`) — and it travels as
 * `data-align`, never as an inline style: an inline style beats every sheet,
 * and a centred price must read left-aligned once its row becomes a card.
 */

import type { ComponentPropsWithoutRef, CSSProperties } from 'react';
import type { ExtraProps } from 'react-markdown';

import { cn } from '@/lib/utils';
import { ResponsiveTable } from './ResponsiveTable';

type MarkdownProps<Tag extends 'table' | 'thead' | 'tbody' | 'tr' | 'th' | 'td'> =
  ComponentPropsWithoutRef<Tag> & ExtraProps;

/** The alignments a column may declare, as the stylesheet names them. */
const CELL_ALIGNMENTS = new Set(['left', 'center', 'right']);

/** A cell's declared alignment (GFM or the model's), or undefined. */
function cellAlignment(style: CSSProperties | undefined): string | undefined {
  const align = style?.textAlign;
  return typeof align === 'string' && CELL_ALIGNMENTS.has(align) ? align : undefined;
}

export function MarkdownTable({ node: _node, style: _style, ...props }: MarkdownProps<'table'>) {
  return <ResponsiveTable {...props} />;
}

export function MarkdownTableHead({
  node: _node,
  style: _style,
  className,
  ...props
}: MarkdownProps<'thead'>) {
  return <thead {...props} className={cn('bg-muted/30', className)} />;
}

export function MarkdownTableBody({
  node: _node,
  style: _style,
  className,
  ...props
}: MarkdownProps<'tbody'>) {
  return <tbody {...props} className={cn('divide-y divide-border/30 bg-card/30', className)} />;
}

export function MarkdownTableRow({
  node: _node,
  style: _style,
  className,
  ...props
}: MarkdownProps<'tr'>) {
  return <tr {...props} className={cn('hover:bg-muted/20 transition-colors', className)} />;
}

export function MarkdownTableHeaderCell({
  node: _node,
  style,
  className,
  ...props
}: MarkdownProps<'th'>) {
  return (
    <th
      {...props}
      data-align={cellAlignment(style)}
      className={cn('px-4 py-2 text-left font-semibold text-foreground', className)}
    />
  );
}

export function MarkdownTableCell({
  node: _node,
  style,
  className,
  ...props
}: MarkdownProps<'td'>) {
  return (
    <td
      {...props}
      data-align={cellAlignment(style)}
      className={cn('px-3 py-2 text-foreground sm:px-4', className)}
    />
  );
}
