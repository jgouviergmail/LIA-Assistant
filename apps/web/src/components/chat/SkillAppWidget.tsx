'use client';

/**
 * SkillAppWidget — Interactive widget for skill rich outputs (frames + images).
 *
 * Mounted by `MarkdownContent` when it detects a
 * `<div class="lia-skill-app" data-registry-id="...">` sentinel in the chat.
 * Looks up the SKILL_APP payload in the registry and renders one or both of:
 *   - An image (`<img>` + lightbox) when `payload.image_url` is present
 *   - An iframe (srcDoc or src) when `payload.html_content` or `frame_url`
 *     is present
 *
 * Order: image is rendered BEFORE the frame, so frames (typically larger and
 * more interactive) appear below images in the response. This matches the
 * expected reading order (visual artifact first, interactive widget last).
 *
 * Security:
 * - Base sandbox: `allow-scripts allow-popups`. Parent LIA cookies/storage
 *   stay unreachable regardless of iframe source — the parent is always
 *   cross-origin to the iframe, so SOP protects it even if the iframe runs
 *   under its real origin.
 * - `allow-same-origin` is added ONLY for `frame_url` coming from a trusted
 *   `is_system_skill`. This lets the embedded page (e.g. Google Maps) talk
 *   to its own backend over XHR/fetch with credentials — required for
 *   tiles/data to load. Granting it does NOT give the iframe access to
 *   parent data, because the parent origin differs.
 * - User-skill `html_content` keeps the strict sandbox AND receives a CSP
 *   meta tag injected backend-side (blocks outbound fetch, nested iframes).
 * - User-owned `frame_url` (if any) also keeps the strict sandbox — we do
 *   not extend trust to arbitrary URLs emitted by user skills.
 */

import { lazy, Suspense, useRef, useState } from 'react';
import { useRegistryItem } from '@/lib/registry-context';
import { useSkillAppBridge } from '@/hooks/useSkillAppBridge';
import { useTranslation } from 'react-i18next';
import type { SkillAppRegistryPayload } from '@/types/skill-apps';

const ImageLightbox = lazy(() =>
  import('@/components/ui/image-lightbox').then(m => ({ default: m.ImageLightbox }))
);

interface SkillAppWidgetProps {
  registryId: string;
}

export function SkillAppWidget({ registryId }: SkillAppWidgetProps) {
  const item = useRegistryItem(registryId);
  const { t } = useTranslation();

  if (!item || item.type !== 'SKILL_APP') {
    return (
      <div className="lia-skill-app__placeholder">
        <span className="text-sm text-muted-foreground">
          {t('skill_apps.error', { defaultValue: 'Skill widget unavailable' })}
        </span>
      </div>
    );
  }

  const payload = item.payload as unknown as SkillAppRegistryPayload;

  const hasImage = Boolean(payload.image_url);
  const hasFrame = Boolean(payload.html_content || payload.frame_url);

  return (
    <div className="lia-skill-app-widget">
      <div className="lia-skill-app-widget__header">
        <span className="lia-badge lia-badge--accent">
          {payload.title || payload.skill_name}
        </span>
        {payload.frame_url ? (
          <span className="lia-skill-app-widget__external-badge" title={payload.frame_url}>
            {t('skill_apps.external_frame', { defaultValue: 'External' })}
          </span>
        ) : null}
      </div>

      {hasImage ? (
        <SkillImageCard url={payload.image_url!} alt={payload.image_alt || ''} />
      ) : null}

      {hasFrame ? <SkillFrameCard payload={payload} /> : null}
    </div>
  );
}

function SkillImageCard({ url, alt }: { url: string; alt: string }) {
  const [isLightboxOpen, setLightboxOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        className="lia-skill-app-widget__image-button"
        onClick={() => setLightboxOpen(true)}
        aria-label={alt || 'Open image'}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={url}
          alt={alt}
          className="lia-skill-app-widget__image"
          loading="lazy"
        />
      </button>
      {isLightboxOpen ? (
        <Suspense fallback={null}>
          <ImageLightbox
            src={url}
            alt={alt}
            isOpen={isLightboxOpen}
            onClose={() => setLightboxOpen(false)}
          />
        </Suspense>
      ) : null}
    </>
  );
}

function SkillFrameCard({ payload }: { payload: SkillAppRegistryPayload }) {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  // The bridge only listens to event.origin === 'null' (srcDoc iframes).
  // External URL iframes are isolated by SOP — the bridge is a no-op for them.
  useSkillAppBridge(iframeRef, payload);

  const aspect = payload.aspect_ratio && payload.aspect_ratio > 0 ? payload.aspect_ratio : 1.333;
  const title = payload.title || payload.skill_name;
  // Trusted external embeds (system-skill frame_url) need `allow-same-origin`
  // so the embedded page can load its own XHR/tile data under its real origin.
  // The parent LIA is still cross-origin to the iframe, so SOP protects it.
  const isTrustedExternalFrame = Boolean(payload.frame_url) && payload.is_system_skill === true;
  const sandbox = isTrustedExternalFrame
    ? 'allow-scripts allow-popups allow-same-origin'
    : 'allow-scripts allow-popups';
  const commonProps = {
    className: 'lia-skill-app-widget__iframe',
    title: `Skill: ${title}`,
    sandbox,
    // background: transparent so the parent (LIA) page shows through the
    // iframe when the skill's own <body> is transparent. Without this the
    // browser default (white) leaks through in dark mode.
    style: { aspectRatio: String(aspect), background: 'transparent' },
  } as const;

  if (payload.html_content) {
    return <iframe ref={iframeRef} srcDoc={payload.html_content} {...commonProps} />;
  }
  if (payload.frame_url) {
    return <iframe ref={iframeRef} src={payload.frame_url} {...commonProps} />;
  }
  return null;
}
