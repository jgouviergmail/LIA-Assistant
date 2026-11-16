'use client';

/**
 * OriginalLayout — a message as its author laid it out, with what the reader says of it (ADR-369,
 * D3). One view for every place a message is read in full: the Tools' reader, and a mail card of
 * the chat (owner, 2026-11-14).
 *
 * Above the frame: that links open from the text where an Android shell cannot open them from a
 * sandboxed frame, and that the layout was cut at its ceiling. The frame's own line carries what
 * the place offers first (`lead`: the way to the text). Under it: how many of its own images could
 * not come. Whether the remote images were asked for is the caller's, kept above the swap to the
 * text so a look at the text does not take it back.
 */
import dynamic from 'next/dynamic';
import { useEffect, useState, type ReactNode } from 'react';

import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { isAndroidShell, shellCapability } from '@/lib/native/shell';
import type { MailHtml, MailInlineImage, MailInlineImages } from '@/lib/workbench/types';

// The original-layout reader parses an inert document with browser DOM APIs.
const AuthoredHtmlFrame = dynamic(
  () => import('../AuthoredHtmlFrame').then(module => module.AuthoredHtmlFrame),
  {
    ssr: false,
  }
);

const NO_IMAGES: readonly MailInlineImage[] = [];

/**
 * Whether the reader says the links open from the text: measured, an Android shell older than
 * its `frameLinks` capability opens nothing from a sandboxed frame.
 */
function useLinksInText(): boolean {
  const [frameLinks, setFrameLinks] = useState(false);
  useEffect(() => {
    void shellCapability('frameLinks').then(setFrameLinks);
  }, []);
  return isAndroidShell() && !frameLinks;
}

export interface OriginalLayoutProps {
  lng: Language;
  /** The layout, as read: its `html` is the author's. */
  original: MailHtml & { html: string };
  /** The images it carries, once read. */
  inline: MailInlineImages | undefined;
  /** The reader asked for its remote images. */
  images: boolean;
  onShowImages: () => void;
  /** What the place offers first on the frame's line. */
  lead: ReactNode;
  /** The frame's height, where the default does not suit. */
  frameClassName?: string;
}

export function OriginalLayout({
  lng,
  original,
  inline,
  images,
  onShowImages,
  lead,
  frameClassName,
}: OriginalLayoutProps) {
  const { t } = useTranslation(lng);
  const linksInText = useLinksInText();
  return (
    <div className="space-y-2">
      {linksInText && (
        <p className="text-xs text-muted-foreground">{t('workbench.mail.links_in_text')}</p>
      )}
      {original.truncated && (
        <p className="text-xs text-muted-foreground">{t('workbench.mail.html_truncated')}</p>
      )}
      <AuthoredHtmlFrame
        lng={lng}
        html={original.html}
        title={t('workbench.mail.html_frame_title')}
        images={images}
        onShowImages={onShowImages}
        inline={inline?.images ?? NO_IMAGES}
        lead={lead}
        className={frameClassName}
      />
      {Boolean(inline?.skipped) && (
        <p className="text-xs text-muted-foreground">
          {t('workbench.mail.inline_skipped', { count: inline?.skipped })}
        </p>
      )}
    </div>
  );
}
