'use client';

import { Blocks, Server } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import type { PluginComponentReport, PluginImportReport } from '@/hooks/usePlugins';

type Translator = (key: string, options?: Record<string, unknown>) => string;
const statusVariant: Record<
  PluginComponentReport['status'],
  'default' | 'secondary' | 'outline' | 'destructive'
> = {
  installed: 'default',
  updated: 'secondary',
  skipped: 'outline',
  removed: 'destructive',
};

function ComponentLine({ component, t }: { component: PluginComponentReport; t: Translator }) {
  const issue = component.issues[0];
  const KindIcon = component.kind === 'skill' ? Blocks : Server;
  return (
    <li className="flex flex-wrap items-center gap-2 text-sm">
      <KindIcon className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
      <span className="min-w-0 truncate font-medium">{component.key}</span>
      <Badge variant={statusVariant[component.status]}>
        {t(`settings.plugins.status.${component.status}`)}
      </Badge>
      {issue && (
        <span className="w-full pl-6 text-xs text-muted-foreground">
          {t(`settings.plugins.reasons.${issue.code}`)}
        </span>
      )}
    </li>
  );
}

/** Settings and native upload show the same translated outcomes, never raw debug details. */
export function PluginImportReportDetails({
  report,
  t,
}: {
  report: PluginImportReport | null;
  t: Translator;
}) {
  return (
    <>
      {report?.file_cleanup_pending && (
        <p role="status" className="text-sm text-muted-foreground">
          {t('settings.plugins.file_cleanup_pending')}
        </p>
      )}
      <ul className="space-y-2">
        {report?.components.map(component => (
          <ComponentLine key={`${component.kind}:${component.key}`} component={component} t={t} />
        ))}
        {report && report.components.length === 0 && (
          <li className="text-sm text-muted-foreground">{t('settings.plugins.report_empty')}</li>
        )}
      </ul>
    </>
  );
}
