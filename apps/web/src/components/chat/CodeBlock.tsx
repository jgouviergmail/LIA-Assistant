'use client';

/**
 * CodeBlock — syntax-highlighted code block with copy-to-clipboard.
 *
 * Used by MarkdownContent to render fenced code blocks (```lang ... ```).
 *
 * Features:
 * - Lazy-loaded PrismAsyncLight highlighter + per-language registration
 * - Dark/light theme auto-detected via next-themes
 * - Copy button (Copy → Check toggle) with toast + i18n
 * - Graceful fallback: plain <pre> while highlighter loads or on unknown langs
 */

import { useCallback, useEffect, useState } from 'react';
import { Copy, Check } from 'lucide-react';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import { useTheme } from 'next-themes';
import { Tooltip, TooltipTrigger, TooltipContent } from '@/components/ui/tooltip';
import {
  SyntaxHighlighter,
  LANGUAGE_LOADERS,
  loadStyle,
  type PrismStyle,
} from './codeblock-lazy';

interface CodeBlockProps {
  language: string;
  children: string;
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
    <pre className="p-3 overflow-x-auto bg-muted/20">
      <code className="text-sm font-mono text-foreground block">{children}</code>
    </pre>
  );

  const langKnown = Boolean(LANGUAGE_LOADERS[language.toLowerCase()]);

  return (
    <div className="my-3 rounded-lg overflow-hidden border border-border/50 shadow-sm">
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
              {copied ? (
                <Check className="h-3 w-3 text-green-600" />
              ) : (
                <Copy className="h-3 w-3" />
              )}
            </button>
          </TooltipTrigger>
          <TooltipContent>{t('chat.code.copy')}</TooltipContent>
        </Tooltip>
      </div>
      {style && langReady && langKnown ? (
        <SyntaxHighlighter
          language={language.toLowerCase()}
          style={style}
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
  );
}
