'use client';

/**
 * A library skill read at one commit, before it is installed or updated (ADR-327).
 *
 * Everything the reader decides on is on this panel: where it comes from and
 * at which commit, what it ships (every file, with what was never read), what
 * the audits said, whether this instance refuses it, and — always — what a
 * skill written elsewhere may and may not do here. The skill's own words (its
 * name, its description, its file names) are a stranger's text, drawn as
 * React children only.
 */
import type { TFunction } from 'i18next';
import { ArrowLeft, Download, FileCode, FolderGit2, ShieldAlert, ShieldCheck } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Disclosure } from '@/components/ui/disclosure';
import { formatFileSize } from '@/lib/format';
import type { LibraryChanges, LibraryPreview } from '@/lib/skill-library/types';
import { shortSha } from '@/lib/skill-library/types';
import { auditRiskTone } from '@/lib/status-tone';

function Audits({ preview, t }: { preview: LibraryPreview; t: TFunction }) {
  return (
    <section className="space-y-2" aria-labelledby="library-audits-title">
      <h4 id="library-audits-title" className="flex items-center gap-2 text-sm font-medium">
        <ShieldCheck className="h-4 w-4 text-primary" aria-hidden />
        {t('settings.skills.library.preview.audits_title')}
      </h4>
      {preview.audits === null && (
        <p className="text-xs text-muted-foreground">
          {t('settings.skills.library.preview.audits_unavailable')}
        </p>
      )}
      {preview.audits?.length === 0 && (
        <p className="text-xs text-muted-foreground">
          {t('settings.skills.library.preview.audits_none')}
        </p>
      )}
      {!!preview.audits?.length && (
        <ul className="flex flex-wrap gap-2">
          {preview.audits.map(audit => (
            <li key={audit.provider}>
              <Badge variant={auditRiskTone(audit.risk)} className="text-xs">
                {audit.provider} · {t(`settings.skills.library.risk.${audit.risk}`)}
                {audit.alerts > 0 &&
                  ` · ${t('settings.skills.library.preview.alerts', { count: audit.alerts })}`}
              </Badge>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function Files({ preview, t }: { preview: LibraryPreview; t: TFunction }) {
  const total = preview.files.reduce((sum, file) => sum + file.size, 0);
  return (
    <Disclosure
      icon={FileCode}
      title={t('settings.skills.library.preview.files_title')}
      badge={preview.files.length}
      description={t('settings.skills.library.preview.files_summary', {
        count: preview.files.length,
        size: formatFileSize(total),
      })}
    >
      <ul className="space-y-1 text-xs">
        {preview.files.map(file => (
          <li key={file.path} className="flex justify-between gap-3">
            <span className="min-w-0 break-all font-mono">{file.path}</span>
            <span className="shrink-0 tabular-nums text-muted-foreground">
              {formatFileSize(file.size)}
            </span>
          </li>
        ))}
      </ul>
      {preview.skipped.length > 0 && (
        <p className="mt-2 text-xs text-muted-foreground">
          {t('settings.skills.library.preview.skipped', { list: preview.skipped.join(', ') })}
        </p>
      )}
    </Disclosure>
  );
}

function Changes({ changes, t }: { changes: LibraryChanges; t: TFunction }) {
  const groups = [
    ['added', changes.added],
    ['modified', changes.modified],
    ['removed', changes.removed],
  ] as const;
  const any = groups.some(([, paths]) => paths.length > 0);
  return (
    <section className="space-y-1 text-xs" aria-label={t('settings.skills.library.update.changes')}>
      {!any && <p className="text-muted-foreground">{t('settings.skills.library.update.none')}</p>}
      {groups.map(([kind, paths]) =>
        paths.length > 0 ? (
          <p key={kind} className="break-all">
            <span className="font-medium">{t(`settings.skills.library.update.${kind}`)}</span>{' '}
            <span className="font-mono">{paths.join(', ')}</span>
          </p>
        ) : null
      )}
    </section>
  );
}

/** Why the act cannot run, as the sentence shown under the panel — or null. */
function blockerOf(preview: LibraryPreview, mode: 'install' | 'update', t: TFunction) {
  if (preview.blocked_by) {
    return t('settings.skills.library.preview.blocked', {
      risk: t(`settings.skills.library.risk.${preview.blocked_by}`),
    });
  }
  if (mode === 'install' && preview.conflict === 'installed') {
    return t('settings.skills.library.preview.conflict_installed');
  }
  if (mode === 'install' && preview.conflict === 'name_taken') {
    return t('settings.skills.library.preview.conflict_name_taken', { name: preview.name });
  }
  return null;
}

export function LibraryPreviewPanel({
  preview,
  mode,
  changes,
  busy,
  t,
  onConfirm,
  onBack,
}: {
  preview: LibraryPreview;
  mode: 'install' | 'update';
  changes?: LibraryChanges;
  busy: boolean;
  t: TFunction;
  onConfirm: () => void;
  onBack: () => void;
}) {
  const blocker = blockerOf(preview, mode, t);
  const location = preview.path ? `${preview.repository}/${preview.path}` : preview.repository;
  return (
    <div className="space-y-4" aria-busy={busy}>
      <div className="space-y-1">
        <h3 className="flex items-center gap-2 text-base font-semibold">
          <FolderGit2 className="h-4 w-4 shrink-0 text-primary" aria-hidden />
          <span className="min-w-0 break-words">{preview.name}</span>
        </h3>
        <p className="text-sm text-muted-foreground">{preview.description}</p>
        <p className="break-all text-xs text-muted-foreground">
          {t('settings.skills.library.preview.source', {
            location,
            sha: shortSha(preview.commit_sha),
          })}
        </p>
      </div>

      <div className="flex items-start gap-2 rounded-md border border-warning/40 bg-warning/10 p-3 text-xs">
        <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-warning" aria-hidden />
        <p>{t('settings.skills.library.preview.third_party')}</p>
      </div>

      {changes && <Changes changes={changes} t={t} />}
      <Audits preview={preview} t={t} />
      <Files preview={preview} t={t} />
      {preview.has_scripts && (
        <p className="text-xs text-muted-foreground">
          {t('settings.skills.library.preview.scripts')}
        </p>
      )}
      {blocker && (
        <p role="alert" className="text-sm text-destructive">
          {blocker}
        </p>
      )}

      <div className="flex flex-col-reverse gap-2 border-t pt-4 sm:flex-row sm:justify-between">
        <Button variant="outline" onClick={onBack} className="gap-1.5">
          <ArrowLeft className="h-4 w-4" aria-hidden />
          {t('settings.skills.library.preview.back')}
        </Button>
        <Button
          onClick={() => {
            // The guard, not the attribute, prevents the act: `aria-disabled`
            // keeps the focus where the reader is (frontend rule).
            if (!blocker && !busy) onConfirm();
          }}
          aria-disabled={Boolean(blocker) || busy}
          isLoading={busy}
          className="gap-1.5"
        >
          <Download className="h-4 w-4" aria-hidden />
          {t(
            mode === 'install'
              ? 'settings.skills.library.preview.install'
              : 'settings.skills.library.update.confirm'
          )}
        </Button>
      </div>
    </div>
  );
}
