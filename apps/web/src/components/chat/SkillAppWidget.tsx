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
 * - iframe `sandbox="allow-scripts allow-popups"` — never `allow-same-origin`.
 *   Parent cookies/storage are unreachable regardless of frame source.
 * - User skills have a CSP meta tag injected backend-side into `html_content`
 *   to block outbound fetch/XHR and nested iframes.
 * - External `frame_url` is used only for trusted URLs emitted by system
 *   skills (sandbox + SOP provide isolation). User skills can also emit
 *   `frame_url` — sandbox defends the parent in both cases.
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
  const commonProps = {
    className: 'lia-skill-app-widget__iframe',
    title: `Skill: ${title}`,
    sandbox: 'allow-scripts allow-popups',
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
