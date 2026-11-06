'use client';

/**
 * MarkdownViewer — a Markdown file laid out (ADR-369, lot 14).
 *
 * The words are somebody else's, and React draws them: HTML the file writes is left out, a link
 * survives only as an address `safeAddress` follows, in a tab that cannot reach back. Opening a
 * file tells nobody: a picture shows its caption rather than asking its host for the image.
 */
import type { ComponentProps } from 'react';
import ReactMarkdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';

import { safeAddress } from '@/lib/text-links';
import { cn } from '@/lib/utils';

export interface MarkdownViewerProps {
  text: string;
  /** The document's name: what the region is called. */
  name: string;
  /** Its height. */
  className?: string;
}

const PLUGINS = [remarkGfm];

function Link({ href, children }: ComponentProps<'a'>) {
  const address = href ? safeAddress(href) : null;
  if (!address) return <span>{children}</span>;
  return (
    <a href={address.href} target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  );
}

function Picture({ alt }: ComponentProps<'img'>) {
  return <span className="italic text-muted-foreground">{alt}</span>;
}

const COMPONENTS: Components = { a: Link, img: Picture };

export function MarkdownViewer({ text, name, className }: MarkdownViewerProps) {
  return (
    <div
      tabIndex={0}
      role="region"
      aria-label={name}
      className={cn(
        'prose prose-sm max-w-none overflow-auto rounded-md border bg-card p-4 dark:prose-invert',
        className
      )}
    >
      <ReactMarkdown remarkPlugins={PLUGINS} skipHtml components={COMPONENTS}>
        {text}
      </ReactMarkdown>
    </div>
  );
}
