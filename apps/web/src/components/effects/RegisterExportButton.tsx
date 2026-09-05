'use client';

/**
 * RegisterExportButton — taking a register out of the application (ADR-263).
 *
 * Three formats, and the third answers a different question. Markdown and CSV
 * carry the reader's own wording — their record, for them. JSON Lines carries
 * the same events with no content at all and every identifier pseudonymised:
 * the file to attach to a bug report, a complaint or a portability request
 * without handing over what was said. It is the administrator's own contract,
 * reused rather than reinvented, so the two can never disagree about what a
 * register may show.
 *
 * Both formats are ANCHORS, never buttons: a download is a navigation, and a
 * top-level same-site GET carries the session cookie on its own. Fetching the
 * document into a blob would work today and break the moment a register grows
 * past what a tab wants to hold in memory — the account-export lesson, applied
 * to a document that grows with every turn.
 *
 * The href is built with `apiEndpointUrl`: a relative `/api/v1/...` would hit
 * the FRONTEND origin, which has no such route (found live once already).
 */

import { Download } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { apiEndpointUrl } from '@/lib/api-client';

export interface RegisterExportButtonProps {
  /** Which register — the two are separate documents, never merged. */
  register: 'actions' | 'consultations';
}

/** The three formats, in the order a reader thinks about them. */
const FORMATS = [
  { format: 'markdown', labelKey: 'effects.export.markdown' },
  { format: 'csv', labelKey: 'effects.export.csv' },
  { format: 'technical', labelKey: 'effects.export.technical' },
] as const;

export function RegisterExportButton({ register }: RegisterExportButtonProps) {
  const { t } = useTranslation();

  return (
    <div
      role="group"
      aria-label={t('effects.export.group_label')}
      className="flex flex-wrap items-center gap-2"
    >
      {FORMATS.map(({ format, labelKey }) => {
        // What the file HOLDS is not obvious from a one-word label, and the
        // difference decides whether it is safe to send to someone. The
        // description is associated programmatically rather than left to a
        // `title` alone: a tooltip reaches neither a screen reader nor a
        // finger. `title` stays for the pointer, and `aria-describedby` wins
        // over it wherever both are read, so nobody hears it twice.
        const hintId = `register-export-${register}-${format}-hint`;
        return (
          <Button key={format} variant="outline" size="sm" asChild>
            <a
              href={apiEndpointUrl(`/effects/export?register=${register}&format=${format}`)}
              download
              aria-describedby={hintId}
              title={t(`${labelKey}_hint`)}
            >
              <Download className="h-4 w-4" aria-hidden="true" />
              {t(labelKey)}
              <span id={hintId} className="sr-only">
                {t(`${labelKey}_hint`)}
              </span>
            </a>
          </Button>
        );
      })}
    </div>
  );
}
