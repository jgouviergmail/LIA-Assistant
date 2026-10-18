'use client';

import type { CSSProperties, ComponentPropsWithoutRef } from 'react';
import { useCallback, useSyncExternalStore } from 'react';
import { ShieldAlert } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { readClassification } from '@/lib/content-classification';
import { classificationTone } from '@/lib/status-tone';
import { Badge } from '@/components/ui/badge';

const subscribe = () => () => {};
const clientSnapshot = () => true;
const serverSnapshot = () => false;

function useCurrentClassification(until?: string) {
  const expires = Date.parse(until ?? '');
  const subscribeUntil = useCallback(
    (notify: () => void) => {
      if (!Number.isFinite(expires)) return () => {};
      const timer = window.setTimeout(
        notify,
        Math.max(0, Math.min(expires - Date.now(), 2147483647))
      );
      return () => window.clearTimeout(timer);
    },
    [expires]
  );
  const snapshot = useCallback(() => Number.isFinite(expires) && expires > Date.now(), [expires]);
  return useSyncExternalStore(subscribeUntil, snapshot, serverSnapshot);
}

/** Wall-clock anchored: remounts and archived messages cannot replay attention. */
export function classificationAttentionStyle(
  evaluatedAt?: string,
  now = Date.now()
): CSSProperties {
  const elapsed = evaluatedAt ? (now - Date.parse(evaluatedAt)) / 1000 : NaN;
  if (!Number.isFinite(elapsed) || elapsed < 0 || elapsed >= 4) return {};
  return { animation: 'classification-attention 1s ease-in-out 4', animationDelay: `-${elapsed}s` };
}

export function ClassificationBadges({ value }: { value: unknown }) {
  const { t } = useTranslation();
  const hydrated = useSyncExternalStore(subscribe, clientSnapshot, serverSnapshot);
  const annotation = readClassification(value);
  const current = useCurrentClassification(annotation?.valid_until);
  if (!annotation || !current) return null;
  const labels = [];
  if (annotation.category !== 'unknown') labels.push(annotation.category);
  if (
    annotation.kind === 'email' &&
    annotation.priority !== 'unknown' &&
    annotation.priority !== 'normal'
  )
    labels.push(annotation.priority);
  if (!labels.length) return null;
  return (
    <span className="inline-flex max-w-full flex-wrap gap-1.5">
      {labels.map(label => (
        <Badge
          key={label}
          variant={classificationTone(label)}
          className={`content-classification-badge${label === 'phishing_scam' || label === 'critical' ? ' content-classification-badge--alert' : ''}`}
          style={
            hydrated && label === 'phishing_scam'
              ? classificationAttentionStyle(annotation.evaluated_at)
              : undefined
          }
        >
          {label === 'phishing_scam' && (
            <ShieldAlert className="size-3.5 shrink-0" aria-hidden="true" />
          )}
          {t(`classification.${label}`)}
        </Badge>
      ))}
    </span>
  );
}

type MarkdownSpanProps = ComponentPropsWithoutRef<'span'> & {
  node?: unknown;
  'data-classified-at'?: string;
};
export function MarkdownClassificationSpan({ node: _node, ...props }: MarkdownSpanProps) {
  const hydrated = useSyncExternalStore(subscribe, clientSnapshot, serverSnapshot);
  const attention = props.className
    ?.split(/\s+/)
    .includes('content-classification-badge--phishing');
  return (
    <span
      {...props}
      style={
        hydrated && attention
          ? { ...props.style, ...classificationAttentionStyle(props['data-classified-at']) }
          : props.style
      }
    />
  );
}
