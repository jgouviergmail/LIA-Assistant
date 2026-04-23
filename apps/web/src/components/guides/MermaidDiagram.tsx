'use client';

import { useEffect, useRef, useState } from 'react';
import { useTheme } from 'next-themes';

interface MermaidDiagramProps {
  /** Raw Mermaid source (without the ```mermaid fences). */
  chart: string;
}

/**
 * Client-side Mermaid renderer for guide markdown blocks.
 *
 * - Mermaid is heavy (~3 MB) so it is dynamically imported on mount,
 *   never on the server (SSR would crash on `document` access).
 * - Re-renders on theme change so the diagram tracks dark/light mode.
 * - Each instance gets a stable id so concurrent renders on the same
 *   page don't collide (`mermaid.render` requires a unique element id).
 *
 * Used by `GuideMarkdown` to convert ```mermaid fenced blocks into SVG.
 */
export function MermaidDiagram({ chart }: MermaidDiagramProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const idRef = useRef(`mermaid-${Math.random().toString(36).slice(2, 11)}`);
  const { resolvedTheme } = useTheme();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
        const mermaid = (await import('mermaid')).default;
        mermaid.initialize({
          startOnLoad: false,
          theme: resolvedTheme === 'dark' ? 'dark' : 'default',
          securityLevel: 'strict',
          fontFamily: 'inherit',
        });
        const { svg } = await mermaid.render(idRef.current, chart.trim());
        if (!cancelled && containerRef.current) {
          containerRef.current.innerHTML = svg;
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Mermaid render failed');
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [chart, resolvedTheme]);

  if (error) {
    return (
      <pre className="text-xs text-destructive whitespace-pre-wrap p-4 rounded-md border border-destructive/30 bg-destructive/5">
        Mermaid render error: {error}
        {'\n\n'}
        {chart}
      </pre>
    );
  }

  return (
    <div
      ref={containerRef}
      className="my-6 flex justify-center [&_svg]:max-w-full [&_svg]:h-auto"
      aria-label="Diagram"
      role="img"
    />
  );
}
