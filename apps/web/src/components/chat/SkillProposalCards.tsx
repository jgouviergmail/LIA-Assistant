'use client';

/**
 * A skill the chat wrote, waiting for the person's click (ADR-327).
 *
 * The model only PROPOSES a skill: the package was validated like any import,
 * and this card is where the person reads what it is — its files, what a
 * replacement adds, changes and removes — and installs it. Nothing else can
 * install it. The skill's words (its name, description, file names and
 * contents) are drawn as React children only.
 *
 * The card reads the proposal once mounted: its status after a reload, and
 * the files' contents while it may still be installed.
 */
import { type RefObject, useEffect, useId, useRef, useState } from 'react';
import Link from 'next/link';
import { useTranslation } from 'react-i18next';
import { Blocks, CheckCircle2, Download, FileCode, Loader2, ShieldAlert } from 'lucide-react';
import type { TFunction } from 'i18next';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Disclosure } from '@/components/ui/disclosure';
import { useSkillProposal, useSkillProposalActions } from '@/hooks/useSkillProposal';
import { formatFileSize } from '@/lib/format';
import { settingsSectionHref } from '@/lib/settings-sections';
import { isProposalGone, proposalRefusalKey } from '@/lib/skill-proposals/errors';
import type {
  SkillProposal,
  SkillProposalCard,
  SkillProposalChanges,
} from '@/lib/skill-proposals/types';
import { bumpRevision } from '@/stores/revisionStore';
import { getIntlLocale, type Language } from '@/i18n/settings';

const PREFIX = 'chat.skill_proposal';

/** The chat's cards of skill proposals — nothing without proposals (hotspot CC rule). */
export function SkillProposalCards({ proposals }: { proposals?: SkillProposalCard[] }) {
  if (!proposals || proposals.length === 0) return null;
  return (
    <div className="mt-3 space-y-2">
      {proposals.map(card => (
        <ProposalCard key={card.id} card={card} />
      ))}
    </div>
  );
}

function ChangeLists({ changes, t }: { changes: SkillProposalChanges; t: TFunction }) {
  const groups = [
    ['added', changes.added],
    ['modified', changes.modified],
    ['removed', changes.removed],
  ] as const;
  return (
    <div className="space-y-1 text-xs" aria-label={t(`${PREFIX}.changes.title`)}>
      {groups.map(([kind, paths]) =>
        paths.length > 0 ? (
          <p key={kind} className={kind === 'removed' ? 'break-all text-destructive' : 'break-all'}>
            <span className="font-medium">{t(`${PREFIX}.changes.${kind}`)}</span>{' '}
            <span className="font-mono">{paths.join(', ')}</span>
          </p>
        ) : null
      )}
    </div>
  );
}

function FileList({
  card,
  read,
  t,
}: {
  card: SkillProposalCard;
  read?: SkillProposal;
  t: TFunction;
}) {
  const [open, setOpen] = useState<string | null>(null);
  const baseId = useId();
  const contents = new Map((read?.files ?? []).map(file => [file.path, file.content]));
  const total = card.files.reduce((sum, file) => sum + file.size, 0);
  return (
    <Disclosure
      icon={FileCode}
      title={t(`${PREFIX}.files_title`)}
      badge={card.files.length}
      description={t(`${PREFIX}.files_summary`, {
        count: card.files.length,
        size: formatFileSize(total),
      })}
    >
      <ul className="space-y-1 text-xs">
        {card.files.map((file, index) => {
          const content = contents.get(file.path);
          const panelId = `${baseId}-${index}`;
          const expanded = open === file.path && typeof content === 'string';
          return (
            <li key={file.path} className="space-y-1">
              <div className="flex justify-between gap-3">
                {typeof content === 'string' ? (
                  <button
                    type="button"
                    className="min-w-0 break-all text-left font-mono underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-sm"
                    aria-expanded={expanded}
                    aria-controls={panelId}
                    aria-label={t(expanded ? `${PREFIX}.hide_file` : `${PREFIX}.show_file`, {
                      path: file.path,
                    })}
                    onClick={() => setOpen(expanded ? null : file.path)}
                  >
                    {file.path}
                  </button>
                ) : (
                  <span className="min-w-0 break-all font-mono">{file.path}</span>
                )}
                <span className="shrink-0 tabular-nums text-muted-foreground">
                  {formatFileSize(file.size)}
                </span>
              </div>
              {expanded && (
                <pre
                  id={panelId}
                  className="max-h-64 overflow-auto whitespace-pre-wrap break-words rounded-md border bg-muted/40 p-2 font-mono text-[11px]"
                >
                  {content}
                </pre>
              )}
            </li>
          );
        })}
      </ul>
    </Disclosure>
  );
}

/** The sentence under the card while the proposal may be installed. */
function expiryLine(expiresAt: string, lng: string, t: TFunction): string | null {
  const instant = new Date(expiresAt);
  if (Number.isNaN(instant.getTime())) return null;
  const when = new Intl.DateTimeFormat(getIntlLocale(lng as Language), {
    dateStyle: 'short',
    timeStyle: 'short',
  }).format(instant);
  return t(`${PREFIX}.expires`, { time: when });
}

/** Whether the proposal's deadline has passed — an unreadable one reads as past (ADR-279). */
function isPast(expiresAt: string): boolean {
  const instant = new Date(expiresAt).getTime();
  return Number.isNaN(instant) || instant <= Date.now();
}

/** What the card's foot shows, decided once from the read and the click. */
type FootState = 'installed' | 'gone' | 'failed' | 'pending';

/** The foot's state — pure, so the card's own render stays branch-light. */
function footStateOf(read: { data?: SkillProposal; error: unknown }, expired: boolean): FootState {
  if (read.data?.status === 'installed') return 'installed';
  if (read.data) return 'pending';
  if (expired || isProposalGone(read.error)) return 'gone';
  return read.error ? 'failed' : 'pending';
}

function InstalledFoot({
  focusRef,
  t,
  lng,
}: {
  focusRef: RefObject<HTMLParagraphElement | null>;
  t: TFunction;
  lng: string;
}) {
  return (
    <p
      ref={focusRef}
      tabIndex={-1}
      className="flex flex-wrap items-center gap-2 text-sm text-success outline-none"
    >
      <CheckCircle2 className="h-4 w-4 shrink-0" aria-hidden />
      <span>{t(`${PREFIX}.installed`)}</span>
      <Link
        href={settingsSectionHref(lng, 'skills')}
        className="font-medium text-primary underline-offset-2 hover:underline"
      >
        {t(`${PREFIX}.open_settings`)}
      </Link>
    </p>
  );
}

function PendingFoot({
  card,
  ready,
  busy,
  refusal,
  onInstall,
  t,
  lng,
}: {
  card: SkillProposalCard;
  ready: boolean;
  busy: boolean;
  refusal: string | null;
  onInstall: () => void;
  t: TFunction;
  lng: string;
}) {
  const waiting = busy || !ready;
  return (
    <div className="space-y-2">
      <div className="flex items-start gap-2 rounded-md border border-warning/40 bg-warning/10 p-2 text-xs">
        <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-warning" aria-hidden />
        <p>{t(`${PREFIX}.notice`)}</p>
      </div>
      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-xs text-muted-foreground">{expiryLine(card.expires_at, lng, t)}</p>
        <Button
          onClick={onInstall}
          aria-disabled={waiting}
          aria-label={t(`${PREFIX}.install_label`, { name: card.name })}
          className="gap-1.5"
        >
          {waiting ? (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
          ) : (
            <Download className="h-4 w-4" aria-hidden />
          )}
          {t(`${PREFIX}.install`)}
        </Button>
      </div>
      {refusal && (
        <p role="alert" className="text-sm text-destructive">
          {t(refusal)}
        </p>
      )}
    </div>
  );
}

function ProposalCard({ card }: { card: SkillProposalCard }) {
  const { t, i18n } = useTranslation();
  const titleId = useId();
  // A card past its deadline asks nothing: the proposal is gone by construction.
  const expired = isPast(card.expires_at);
  const read = useSkillProposal(card.id, !expired);
  const { install } = useSkillProposalActions();
  const [busy, setBusy] = useState(false);
  const [refusal, setRefusal] = useState<string | null>(null);
  const [justInstalled, setJustInstalled] = useState(false);
  const doneRef = useRef<HTMLParagraphElement>(null);
  const foot = footStateOf(read, expired);

  // The button the person clicked disappears with the install: the focus goes
  // to the sentence that replaces it, never to <body>.
  useEffect(() => {
    if (justInstalled) doneRef.current?.focus();
  }, [justInstalled]);

  const onInstall = async () => {
    // The guard, not the attribute, prevents a second install (frontend rule).
    if (busy || foot !== 'pending' || !read.data) return;
    setBusy(true);
    setRefusal(null);
    try {
      read.setData(await install(card.id));
      setJustInstalled(true);
      // The chat's own skill shortcuts and the settings list read it again.
      bumpRevision('skills');
    } catch (error) {
      setRefusal(proposalRefusalKey(error) ?? `${PREFIX}.install_failed`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section
      aria-labelledby={titleId}
      aria-busy={busy || (read.loading && !read.data)}
      data-testid="skill-proposal-card"
      className="mx-auto w-full max-w-[512px] space-y-3 rounded-lg border bg-card p-3"
    >
      <div className="space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <h3 id={titleId} className="flex min-w-0 items-center gap-2 text-sm font-semibold">
            <Blocks className="h-4 w-4 shrink-0 text-primary" aria-hidden />
            <span className="min-w-0 break-words">{card.name}</span>
          </h3>
          <Badge variant="default" className="text-xs">
            {t(card.replaces ? `${PREFIX}.badge_update` : `${PREFIX}.badge_new`)}
          </Badge>
        </div>
        <p className="text-sm text-muted-foreground">{card.description}</p>
      </div>

      {card.changes && <ChangeLists changes={card.changes} t={t} />}
      <FileList card={card} read={read.data} t={t} />

      {foot === 'installed' && <InstalledFoot focusRef={doneRef} t={t} lng={i18n.language} />}
      {foot === 'gone' && <p className="text-sm text-muted-foreground">{t(`${PREFIX}.closed`)}</p>}
      {foot === 'failed' && (
        <div className="flex flex-wrap items-center gap-2">
          <p role="alert" className="text-sm text-destructive">
            {t(proposalRefusalKey(read.error) ?? `${PREFIX}.load_failed`)}
          </p>
          <Button variant="outline" size="sm" onClick={() => read.refetch()}>
            {t(`${PREFIX}.retry`)}
          </Button>
        </div>
      )}
      {foot === 'pending' && (
        <PendingFoot
          card={card}
          ready={Boolean(read.data)}
          busy={busy}
          refusal={refusal}
          onInstall={() => void onInstall()}
          t={t}
          lng={i18n.language}
        />
      )}
    </section>
  );
}
