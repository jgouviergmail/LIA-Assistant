import { ArrowUpRight } from 'lucide-react';

import type { LandingVideoDescriptor } from '@/lib/landing/media';

import type { LandingVideoSlotLabels } from './LandingVideo';

type CaptionLabels = Pick<LandingVideoSlotLabels, 'aiDisclosure' | 'creditPrefix' | 'externalLink'>;

/** Under the frame: the AI-generated disclosure and the author's credit (ADR-330). */
export function LandingVideoCaption({
  video,
  labels,
}: {
  video: LandingVideoDescriptor;
  labels: CaptionLabels;
}) {
  if (!video.aiGenerated && !video.credit) return null;
  return (
    <p className="mt-3 text-xs text-muted-foreground">
      {video.aiGenerated && <span>{labels.aiDisclosure}</span>}
      {video.aiGenerated && video.credit && <span aria-hidden="true"> · </span>}
      {video.credit && (
        <span>
          {labels.creditPrefix}
          <a
            href={video.credit.url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-0.5 font-medium text-foreground/80 underline-offset-4 hover:text-foreground hover:underline"
          >
            {video.credit.label}
            <ArrowUpRight className="size-3" aria-hidden="true" />
            <span className="sr-only">{labels.externalLink}</span>
          </a>
        </span>
      )}
    </p>
  );
}
