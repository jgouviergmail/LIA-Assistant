'use client';

/**
 * CodeBlock — syntax-highlighted code block with copy-to-clipboard.
 *
 * Used by MarkdownContent to render every `pre > code` block — a fence with or
 * without a language, an indented block, a raw <pre><code>.
 *
 * Features:
 * - Lazy-loaded PrismAsyncLight highlighter + per-language registration
 * - Dark/light theme auto-detected via next-themes
 * - Copy button (Copy → Check toggle) with toast + i18n
 * - Graceful fallback: plain <pre> while highlighter loads or on unknown langs
 * - A long line stays reachable AND says so: the scroll box wears a classic,
 *   always-visible scrollbar (`.code-scroll`) and the frame announces its
 *   overflow (`data-overflowing`, `data-scrolled-end`) so the stylesheet can
 *   fade the right edge while there is more to the right — measured
 *   2026-09-17: the box scrolled, and nothing showed it.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { Copy, Check } from 'lucide-react';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import { useTheme } from 'next-themes';
import { Tooltip, TooltipTrigger, TooltipContent } from '@/components/ui/tooltip';
import { SyntaxHighlighter, LANGUAGE_LOADERS, loadStyle, type PrismStyle } from './codeblock-lazy';

interface CodeBlockProps {
  language: string;
  children: string;
}

/** What the frame announces about its scroll box. */
interface OverflowState {
  overflowing: boolean;
  scrolledEnd: boolean;
}

/**
 * Pixels that may remain to the right and still count as « the end ». The
 * reserved scrollbar gutter is not part of the scrollable range: measured
 * 2026-09-17, the box stopped 10 px short of `scrollWidth - clientWidth`, so
 * an exact equality never turned the cue off.
 */
const SCROLL_END_TOLERANCE_PX = 16;

function readOverflow(box: HTMLElement): OverflowState {
  const overflowing = box.scrollWidth > box.clientWidth + 1;
  const remaining = box.scrollWidth - (box.scrollLeft + box.clientWidth);
  return { overflowing, scrolledEnd: !overflowing || remaining <= SCROLL_END_TOLERANCE_PX };
}

/**
 * Track whether the frame's `<pre>` overflows horizontally and whether it is
 * scrolled to its end. The `<pre>` is found by query because the highlighter
 * owns it: re-measured when the highlighter swaps in for the fallback
 * (`highlighted` flips), when the code changes (streaming), on resize, and on
 * scroll.
 */
function useScrollBoxOverflow(
  highlighted: boolean,
  code: string
): {
  frameRef: React.RefObject<HTMLDivElement | null>;
  state: OverflowState;
} {
  const frameRef = useRef<HTMLDivElement | null>(null);
  const [state, setState] = useState<OverflowState>({ overflowing: false, scrolledEnd: true });

  useEffect(() => {
    const box = frameRef.current?.querySelector<HTMLElement>('.code-scroll');
    if (!box) return;
    // Same values, same object: a streaming block re-measures on every token
    // and must not re-render the frame when nothing changed.
    const measure = () =>
      setState(prev => {
        const next = readOverflow(box);
        return prev.overflowing === next.overflowing && prev.scrolledEnd === next.scrolledEnd
          ? prev
          : next;
      });
    measure();
    box.addEventListener('scroll', measure, { passive: true });
    const observer =
      typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(() => measure());
    observer?.observe(box);
    return () => {
      box.removeEventListener('scroll', measure);
      observer?.disconnect();
    };
  }, [highlighted, code]);

  return { frameRef, state };
}

export function CodeBlock({ language, children }: CodeBlockProps) {
  const { t } = useTranslation();
  const { resolvedTheme } = useTheme();
  const [copied, setCopied] = useState(false);
  const [style, setStyle] = useState<PrismStyle | null>(null);
  const [langReady, setLangReady] = useState(false);

  // Load theme (dark/light) and register the language lazily.
  // Re-runs on theme change but not on content change, so it does not thrash
  // during token-by-token SSE streaming.
  useEffect(() => {
    let cancelled = false;
    loadStyle(resolvedTheme === 'dark').then(loaded => {
      if (!cancelled) setStyle(loaded);
    });
    const langKey = language.toLowerCase();
    const loader = LANGUAGE_LOADERS[langKey];
    if (loader) {
      loader().then(mod => {
        if (!cancelled) {
          SyntaxHighlighter.registerLanguage(langKey, mod.default);
          setLangReady(true);
        }
      });
    } else {
      // Unknown language — skip highlighting, fall back to plain <pre>
      if (!cancelled) setLangReady(true);
    }
    return () => {
      cancelled = true;
    };
  }, [language, resolvedTheme]);

  const langKnown = Boolean(LANGUAGE_LOADERS[language.toLowerCase()]);
  const highlighted = Boolean(style) && langReady && langKnown;
  const { frameRef, state } = useScrollBoxOverflow(highlighted, children);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(children);
      setCopied(true);
      toast.success(t('chat.code.copied'));
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error(t('chat.message.error'));
    }
  }, [children, t]);

  const fallback = (
    <pre className="code-scroll p-3 bg-muted/20">
      <code className="text-sm font-mono text-foreground block">{children}</code>
    </pre>
  );

  return (
    <div
      data-code-block=""
      className="my-3 rounded-lg overflow-hidden border border-border/50 shadow-sm"
    >
      <div className="flex items-center justify-between px-3 py-1 text-xs font-mono bg-muted/50 text-muted-foreground border-b border-border/50">
        <span>{language}</span>
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              onClick={handleCopy}
              className="p-1 rounded hover:bg-muted transition-colors"
              aria-label={t('chat.code.copy')}
            >
              {copied ? <Check className="h-3 w-3 text-green-600" /> : <Copy className="h-3 w-3" />}
            </button>
          </TooltipTrigger>
          <TooltipContent>{t('chat.code.copy')}</TooltipContent>
        </Tooltip>
      </div>
      <div
        ref={frameRef}
        className="code-scroll-frame"
        data-overflowing={state.overflowing ? 'true' : 'false'}
        data-scrolled-end={state.scrolledEnd ? 'true' : 'false'}
      >
        {highlighted && style ? (
          <SyntaxHighlighter
            language={language.toLowerCase()}
            style={style}
            className="code-scroll"
            customStyle={{
              margin: 0,
              padding: '0.75rem',
              background: 'transparent',
              fontSize: '0.875rem',
            }}
            codeTagProps={{ className: 'font-mono' }}
          >
            {children}
          </SyntaxHighlighter>
        ) : (
          fallback
        )}
      </div>
    </div>
  );
}
