'use client';

/**
 * « Send by e-mail » on a generated file's card in the chat (ADR-321).
 *
 * A chat card knows its file by URL (`/api/v1/attachments/{id}`); this reads the
 * attachment from it and renders nothing when the card points elsewhere (an
 * external image cannot be sent) or when the file's deadline has passed (the
 * card already says so, and the API would refuse). Kept out of the chat
 * message component, whose render sits under the complexity ratchet.
 */

import {
  EmailShareButton,
  type EmailShareButtonProps,
} from '@/components/email-share/EmailShareButton';
import { classifyImageExpiry } from '@/lib/image-expiry';
import { attachmentIdFromUrl } from '@/lib/peers/image-share';

export interface FileEmailShareButtonProps extends Pick<
  EmailShareButtonProps,
  'variant' | 'className' | 'labelName'
> {
  /** The card's URL, as the API emitted it. */
  url: string;
  /** What the file is called on its card. */
  name: string;
  /** Its size, when the card states it. */
  sizeBytes?: number;
  /** The card's deadline; a file past it is not offered. */
  expiresAt?: string | null;
}

export function FileEmailShareButton({
  url,
  name,
  sizeBytes,
  expiresAt,
  ...presentation
}: FileEmailShareButtonProps) {
  const attachmentId = attachmentIdFromUrl(url);
  const expired = classifyImageExpiry(expiresAt, new Date()).kind === 'expired';
  if (attachmentId === null || expired) return null;
  return (
    <EmailShareButton
      getSource={() => ({ kind: 'file', attachmentId, name, sizeBytes })}
      defaultSubject={name}
      {...presentation}
    />
  );
}
