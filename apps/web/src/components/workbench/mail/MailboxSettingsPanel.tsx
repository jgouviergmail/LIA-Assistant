'use client';

/**
 * MailboxSettingsPanel — what a mailbox signs with, on every provider, and the
 * vacation responder and filters of Gmail and Outlook (ADR-369, spec §6.3: the
 * descriptor's `vacation` and `filters`).
 *
 * The signature closes the messages the person writes and those the assistant
 * prepares. The responder is set in the account's own days, the last one included,
 * and reads back as the same days; only what the mailbox holds is asked: an Outlook
 * reply has no subject, and its schedule has an end. The filters are listed as what
 * they match and what they do, created once per submission, and deleted after a
 * question. A connection made before Outlook's right was asked says to renew it.
 */
import { useId, useState, type FormEvent } from 'react';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { EmptyState } from '@/components/ui/empty-state';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { Switch } from '@/components/ui/switch';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Textarea } from '@/components/ui/textarea';
import { useWorkbenchMailSettings, type MailVacationBody } from '@/hooks/useWorkbenchMailSettings';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { workbenchRefusal } from '@/lib/workbench/errors';
import type { MailFolder, MailVacation, WorkbenchToolAvailability } from '@/lib/workbench/types';

import { MailFilters } from './MailFilters';

export interface MailboxSettingsPanelProps {
  lng: Language;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  tool: WorkbenchToolAvailability;
  labels: readonly MailFolder[];
  /** What the mailbox signs with. */
  signature: string;
  onSaveSignature: (text: string) => Promise<void>;
  /** Says a refusal; rethrows nothing (the panel keeps what was typed). */
  onRefused: (error: unknown) => void;
  onSaved: (key: string) => void;
}

export function MailboxSettingsPanel({
  lng,
  open,
  onOpenChange,
  tool,
  signature,
  onSaveSignature,
  labels,
  onRefused,
  onSaved,
}: MailboxSettingsPanelProps) {
  const { t } = useTranslation(lng);
  const vacationOffered = tool.features.includes('vacation');
  const filtersOffered = tool.features.includes('filters');
  const settings = useWorkbenchMailSettings(open && vacationOffered, open && filtersOffered);
  const unread = (error: unknown): string => {
    const refusal = workbenchRefusal(error);
    return refusal ? t(refusal.key, refusal.values) : t('workbench.mail.settings.failed');
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-sm:inset-0 max-sm:left-0 max-sm:top-0 max-sm:h-dvh max-sm:max-h-none max-sm:w-screen max-sm:max-w-none max-sm:translate-x-0 max-sm:translate-y-0 max-sm:rounded-none max-sm:border-0 sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{t('workbench.mail.settings_title')}</DialogTitle>
          <DialogDescription>{t('workbench.mail.settings.description')}</DialogDescription>
        </DialogHeader>
        <Tabs defaultValue={firstTab(vacationOffered, filtersOffered)}>
          <TabsList>
            {vacationOffered && (
              <TabsTrigger value="vacation">{t('workbench.mail.settings.vacation')}</TabsTrigger>
            )}
            {filtersOffered && (
              <TabsTrigger value="filters">{t('workbench.mail.settings.filters')}</TabsTrigger>
            )}
            <TabsTrigger value="signature">{t('workbench.mail.settings.signature')}</TabsTrigger>
          </TabsList>
          {vacationOffered && (
            <TabsContent value="vacation" className="pt-3">
              {settings.vacation ? (
                <VacationForm
                  lng={lng}
                  vacation={settings.vacation}
                  subjectOffered={tool.features.includes('vacation_subject')}
                  openEnd={tool.features.includes('vacation_open_end')}
                  onSave={async change => {
                    try {
                      await settings.setVacation(change);
                      onSaved('workbench.mail.settings.vacation_saved');
                    } catch (error: unknown) {
                      onRefused(error);
                    }
                  }}
                />
              ) : settings.vacationError ? (
                <EmptyState description={unread(settings.vacationError)} />
              ) : (
                <Skeleton className="h-48 w-full" />
              )}
            </TabsContent>
          )}
          {filtersOffered && (
            <TabsContent value="filters" className="pt-3">
              <MailFilters
                lng={lng}
                filters={settings.filters}
                failure={settings.filtersError ? unread(settings.filtersError) : null}
                labels={labels}
                wordsOffered={tool.features.includes('filter_words')}
                folders={!tool.features.includes('labels')}
                criterionMax={tool.bounds.search_max_chars}
                onDelete={async filter => {
                  try {
                    await settings.deleteFilter(filter.id);
                    onSaved('workbench.mail.settings.filter_deleted');
                  } catch (error: unknown) {
                    onRefused(error);
                  }
                }}
                onCreate={async body => {
                  try {
                    await settings.createFilter(body);
                    onSaved('workbench.mail.settings.filter_created');
                    return true;
                  } catch (error: unknown) {
                    onRefused(error);
                    return false;
                  }
                }}
              />
            </TabsContent>
          )}
          <TabsContent value="signature" className="pt-3">
            <SignatureForm
              key={signature}
              lng={lng}
              signature={signature}
              maxLength={tool.bounds.signature_max_chars}
              onSave={async text => {
                try {
                  await onSaveSignature(text);
                  onSaved('workbench.mail.settings.signature_saved');
                } catch (error: unknown) {
                  onRefused(error);
                }
              }}
            />
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}

/** The first tab a mailbox offers: the signature is there on every provider. */
function firstTab(vacation: boolean, filters: boolean): string {
  if (vacation) return 'vacation';
  return filters ? 'filters' : 'signature';
}

/** The lines at the foot of the person's messages; an empty text takes them away. */
function SignatureForm({
  lng,
  signature,
  maxLength,
  onSave,
}: {
  lng: Language;
  signature: string;
  maxLength: number | undefined;
  onSave: (text: string) => Promise<void>;
}) {
  const { t } = useTranslation(lng);
  const [text, setText] = useState(signature);
  const [saving, setSaving] = useState(false);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (saving) return;
    setSaving(true);
    await onSave(text);
    setSaving(false);
  };
  return (
    <form className="space-y-4" onSubmit={event => void submit(event)}>
      <Textarea
        label={t('workbench.mail.settings.signature_label')}
        value={text}
        maxLength={maxLength}
        rows={6}
        onChange={event => setText(event.target.value)}
      />
      <p className="text-sm text-muted-foreground">{t('workbench.mail.settings.signature_help')}</p>
      <div className="flex justify-end">
        <Button type="submit" isLoading={saving}>
          {t('workbench.mail.settings.save')}
        </Button>
      </div>
    </form>
  );
}

/** What is wrong with a period, said under its last day. */
function periodProblem(
  reversed: boolean,
  endless: boolean,
  t: (key: string) => string
): string | undefined {
  if (reversed) return t('workbench.mail.period.reversed');
  return endless ? t('workbench.mail.settings.last_day_needed') : undefined;
}

interface VacationFormProps {
  lng: Language;
  vacation: MailVacation;
  /** The mailbox keeps a subject for its replies. */
  subjectOffered: boolean;
  /** A first day needs no last one. */
  openEnd: boolean;
  onSave: (change: MailVacationBody) => Promise<void>;
}

/** The responder as it stands, edited in place and saved as a whole. */
function VacationForm({ lng, vacation, subjectOffered, openEnd, onSave }: VacationFormProps) {
  const { t } = useTranslation(lng);
  const [enabled, setEnabled] = useState(vacation.enabled);
  const [subject, setSubject] = useState(vacation.subject);
  const [body, setBody] = useState(vacation.body);
  const [start, setStart] = useState(vacation.start_date ?? '');
  const [end, setEnd] = useState(vacation.end_date ?? '');
  const [saving, setSaving] = useState(false);
  const switchId = useId();
  const startId = useId();
  const endId = useId();
  const reversed = start !== '' && end !== '' && end < start;
  const endless = enabled && !openEnd && start !== '' && end === '';
  const [asked, setAsked] = useState(false);
  const words = subjectOffered ? { subject, body } : { body };

  const save = async (event: FormEvent) => {
    event.preventDefault();
    setAsked(true);
    if (saving || reversed || endless) return;
    setSaving(true);
    try {
      await onSave(
        enabled
          ? { enabled, ...words, start_date: start || null, end_date: end || null }
          : { enabled }
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={save} className="space-y-4">
      <div className="flex items-center gap-3">
        <Switch
          id={switchId}
          aria-labelledby={`${switchId}-label`}
          checked={enabled}
          onCheckedChange={setEnabled}
        />
        <Label id={`${switchId}-label`} htmlFor={switchId}>
          {t('workbench.mail.settings.vacation_on')}
        </Label>
      </div>
      {enabled && (
        <>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label id={`${startId}-label`} htmlFor={startId}>
                {t('workbench.mail.settings.first_day')}
              </Label>
              <Input
                id={startId}
                aria-labelledby={`${startId}-label`}
                type="date"
                value={start}
                onChange={event => setStart(event.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label id={`${endId}-label`} htmlFor={endId}>
                {t('workbench.mail.settings.last_day')}
              </Label>
              <Input
                id={endId}
                aria-labelledby={`${endId}-label`}
                type="date"
                value={end}
                min={start || undefined}
                onChange={event => setEnd(event.target.value)}
                error={periodProblem(reversed, endless && asked, t)}
              />
            </div>
          </div>
          {subjectOffered && (
            <Input
              label={t('workbench.mail.compose.subject')}
              value={subject}
              onChange={event => setSubject(event.target.value)}
            />
          )}
          <Textarea
            label={t('workbench.mail.settings.vacation_text')}
            value={body}
            rows={6}
            onChange={event => setBody(event.target.value)}
          />
        </>
      )}
      <div className="flex justify-end">
        <Button type="submit" isLoading={saving} aria-disabled={reversed || endless || undefined}>
          {t('workbench.mail.settings.save')}
        </Button>
      </div>
    </form>
  );
}
