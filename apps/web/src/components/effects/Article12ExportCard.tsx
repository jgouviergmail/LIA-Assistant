'use client';

/**
 * Article12ExportCard — the five records about you, in one file (ADR-263).
 *
 * Placed BELOW the tabs and outside all three, because it is not one register's
 * export: it crosses the two journals, the turns, the model calls and the gaps
 * in the record itself. Putting it inside a tab would imply it belonged to that
 * tab's register — the same reason the seal card sits above them.
 *
 * It is the administrator's own contract, narrowed to one account: no content,
 * every identifier pseudonymised, the caller's included. That is what makes the
 * file safe to attach to a complaint, a portability request or a bug report
 * without editing it first — and the route it calls declares no account
 * parameter at all, so the scope is the session rather than a default.
 *
 * An ANCHOR, never a button: a download is a navigation, and a top-level
 * same-site GET carries the session cookie on its own. Fetching it into a blob
 * would work today and break the day the file outgrows what a tab wants to hold.
 */

import { FileJson } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { apiEndpointUrl } from '@/lib/api-client';

export function Article12ExportCard() {
  const { t } = useTranslation();

  return (
    <Card className="min-w-0">
      <CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0 space-y-1 sm:flex-1">
          <h2 className="flex items-center gap-2 text-sm font-medium">
            <FileJson className="h-4 w-4 text-primary" aria-hidden="true" />
            {t('registers.article12.title')}
          </h2>
          <p className="text-xs leading-relaxed text-muted-foreground">
            {t('registers.article12.description')}
          </p>
        </div>
        <Button variant="outline" size="sm" asChild className="sm:shrink-0">
          <a
            href={apiEndpointUrl('/effects/export/article12')}
            download
            aria-describedby="article12-export-hint"
            title={t('registers.article12.hint')}
          >
            <FileJson className="h-4 w-4" aria-hidden="true" />
            {t('registers.article12.action')}
            <span id="article12-export-hint" className="sr-only">
              {t('registers.article12.hint')}
            </span>
          </a>
        </Button>
      </CardContent>
    </Card>
  );
}
