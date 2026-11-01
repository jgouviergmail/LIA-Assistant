'use client';

/**
 * MailboxSettingsPanel — Gmail's vacation responder and filters (ADR-369,
 * spec §6.3: Gmail only, the descriptor's `vacation` and `filters`).
 *
 * The responder is set in the account's own days, the last one included, and
 * reads back as the same days. The filters are listed as what they match and
 * what they do, and created once per submission; nothing deletes one here —
 * Gmail's client has no such act, and the panel says where it is done.
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
import type { MailFolder, MailVacation, WorkbenchToolAvailability } from '@/lib/workbench/types';

import { MailFilters } from './MailFilters';

export interface MailboxSettingsPanelProps {
  lng: Language;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  tool: WorkbenchToolAvailability;
  labels: readonly MailFolder[];
  /** Says a refusal; rethrows nothing (the panel keeps what was typed). */
  onRefused: (error: unknown) => void;
  onSaved: (key: string) => void;
}

export function MailboxSettingsPanel({
  lng,
  open,
  onOpenChange,
  tool,
  labels,
  onRefused,
  onSaved,
}: MailboxSettingsPanelProps) {
  const { t } = useTranslation(lng);
  const vacationOffered = tool.features.includes('vacation');
  const filtersOffered = tool.features.includes('filters');
  const settings = useWorkbenchMailSettings(open && vacationOffered, open && filtersOffered);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-sm:inset-0 max-sm:left-0 max-sm:top-0 max-sm:h-dvh max-sm:max-h-none max-sm:w-screen max-sm:max-w-none max-sm:translate-x-0 max-sm:translate-y-0 max-sm:rounded-none max-sm:border-0 sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{t('workbench.mail.settings_title')}</DialogTitle>
          <DialogDescription>{t('workbench.mail.settings.description')}</DialogDescription>
        </DialogHeader>
        <Tabs defaultValue={vacationOffered ? 'vacation' : 'filters'}>
          <TabsList>
            {vacationOffered && (
              <TabsTrigger value="vacation">{t('workbench.mail.settings.vacation')}</TabsTrigger>
            )}
            {filtersOffered && (
              <TabsTrigger value="filters">{t('workbench.mail.settings.filters')}</TabsTrigger>
            )}
          </TabsList>
          {vacationOffered && (
            <TabsContent value="vacation" className="pt-3">
              {settings.vacation ? (
                <VacationForm
                  lng={lng}
                  vacation={settings.vacation}
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
                <EmptyState description={t('workbench.mail.settings.failed')} />
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
                failed={Boolean(settings.filtersError)}
                labels={labels}
                criterionMax={tool.bounds.search_max_chars}
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
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}

interface VacationFormProps {
  lng: Language;
  vacation: MailVacation;
  onSave: (change: MailVacationBody) => Promise<void>;
}

/** The responder as it stands, edited in place and saved as a whole. */
function VacationForm({ lng, vacation, onSave }: VacationFormProps) {
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

  const save = async (event: FormEvent) => {
    event.preventDefault();
    if (saving || reversed) return;
    setSaving(true);
    try {
      await onSave(
        enabled
          ? { enabled, subject, body, start_date: start || null, end_date: end || null }
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
                error={reversed ? t('workbench.mail.period.reversed') : undefined}
              />
            </div>
          </div>
          <Input
            label={t('workbench.mail.compose.subject')}
            value={subject}
            onChange={event => setSubject(event.target.value)}
          />
          <Textarea
            label={t('workbench.mail.settings.vacation_text')}
            value={body}
            rows={6}
            onChange={event => setBody(event.target.value)}
          />
        </>
      )}
      <div className="flex justify-end">
        <Button type="submit" isLoading={saving} aria-disabled={reversed || undefined}>
          {t('workbench.mail.settings.save')}
        </Button>
      </div>
    </form>
  );
}
