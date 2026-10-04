import type { ImgHTMLAttributes } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';

export function MarkdownCardImage({
  loaded,
  failed,
  ...props
}: ImgHTMLAttributes<HTMLImageElement> & { loaded: boolean; failed: boolean }) {
  const { t } = useTranslation();
  if (failed)
    return props.alt ? (
      <span
        className={cn(props.className, 'lia-card-image-fallback')}
        role="img"
        aria-label={`${props.alt} — ${t('gallery.image_unavailable')}`}
      >
        {t('gallery.image_unavailable')}
      </span>
    ) : null;
  // Card proxies own authorization and billing; Next Image must not fetch them server-side.
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      {...props}
      alt={props.alt ?? ''}
      loading={props.loading ?? 'lazy'}
      referrerPolicy="no-referrer"
      style={{ opacity: loaded ? 1 : 0 }}
    />
  );
}
