/** Preserve sanitized card list classes while styling ordinary Markdown lists. */
import type { ComponentPropsWithoutRef } from 'react';
import { cn } from '@/lib/utils';

function listClasses(className: string | undefined, proseClasses: string): string {
  return className?.startsWith('lia-') ? className : cn(proseClasses, className);
}

export function MarkdownUnorderedList({ className, children }: ComponentPropsWithoutRef<'ul'>) {
  return (
    <ul
      className={listClasses(className, 'list-disc list-outside pl-5 mb-2 space-y-1.5 last:mb-0')}
    >
      {children}
    </ul>
  );
}

export function MarkdownOrderedList({
  className,
  children,
  start,
}: ComponentPropsWithoutRef<'ol'>) {
  return (
    <ol
      start={start}
      className={listClasses(className, 'list-decimal list-outside pl-5 mb-2 space-y-3 last:mb-0')}
    >
      {children}
    </ol>
  );
}

export function MarkdownListItem({ className, children, value }: ComponentPropsWithoutRef<'li'>) {
  return (
    <li value={value} className={listClasses(className, 'pl-1 leading-normal')}>
      {children}
    </li>
  );
}
