'use client';

import { useEffect, useId, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

export function ExpandableDescription({ text }: { text: string }) {
  const { t } = useTranslation();
  const id = useId();
  const ref = useRef<HTMLParagraphElement>(null);
  const [expanded, setExpanded] = useState(false);
  const [overflows, setOverflows] = useState(false);

  useEffect(() => {
    const element = ref.current;
    // Expanded, nothing is clipped: keep the last verdict so "show less" stays.
    if (!element || expanded || typeof ResizeObserver === 'undefined') return;
    // A ResizeObserver reports every observed element once on `observe()`, so
    // the first measurement needs no synchronous call here.
    const observer = new ResizeObserver(() => {
      setOverflows(element.scrollHeight > element.clientHeight + 1);
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [text, expanded]);

  return (
    <div>
      <p
        ref={ref}
        id={id}
        title={text}
        className={`whitespace-pre-line break-words text-sm text-muted-foreground ${
          expanded ? '' : 'line-clamp-3'
        }`}
      >
        {text}
      </p>
      {overflows && (
        <button
          type="button"
          aria-expanded={expanded}
          aria-controls={id}
          onClick={event => {
            event.stopPropagation();
            setExpanded(value => !value);
          }}
          className="mt-1 text-xs font-medium text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded"
        >
          {expanded ? t('common.show_less') : t('common.show_more')}
        </button>
      )}
    </div>
  );
}
