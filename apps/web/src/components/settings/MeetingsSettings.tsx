'use client';

/**
 * Meeting minutes settings (ADR-258, library ADR-259): engine and retention
 * preferences, the default minutes format, a door to the template library,
 * and the recent meetings.
 *
 * Self-gated on the instance flag `features.meetings_enabled` (the
 * OpenLoopsSection precedent): off, it renders nothing and the settings shell
 * says the section is absent. First load shows skeletons; every later refetch
 * keeps the content mounted (`aria-busy`), so a typed value survives.
 */

import { useMemo, useState } from 'react';
import { ClipboardList, ExternalLink, LibraryBig, Save, Wand2 } from 'lucide-react';
import { toast } from 'sonner';

import { SettingsSection } from '@/components/settings/SettingsSection';
import { MeetingStatusBadge } from '@/components/meetings/MeetingStatusBadge';
import { TemplateSelect } from '@/components/meetings/TemplateSelect';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { Switch } from '@/components/ui/switch';
import { useAppConfig } from '@/hooks/useAppConfig';
import { useLocalizedRouter } from '@/hooks/useLocalizedRouter';
import { useMeetingList } from '@/hooks/useMeetings';
import { useMeetingPreferences } from '@/hooks/useMeetingPreferences';
import { useMeetingTemplates } from '@/hooks/useMeetingTemplates';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { formatElapsed } from '@/lib/meetings/format';
import { userTemplateCount } from '@/lib/meetings/templates';
import type { BaseSettingsProps } from '@/types/settings';
import type {
  MeetingPreferences,
  MeetingPreferencesUpdate,
  MeetingSttEnginePreference,
  MeetingTemplateSummary,
} from '@/types/meetings';

/** ISO-639-1 hints the engines accept, offered next to auto-detection. */
const LANGUAGE_HINTS: readonly string[] = ['en', 'fr', 'de', 'es', 'it', 'zh', 'pt', 'nl'];
const ENGINES: readonly MeetingSttEnginePreference[] = ['auto', 'remote', 'local'];
const RECENT_LIMIT = 5;
function preferencesDraft(preferences: MeetingPreferences): MeetingPreferencesUpdate {
  return {
    stt_engine: preferences.stt_engine,
    language: preferences.language,
    auto_email: preferences.auto_email,
    keep_audio_hours: preferences.keep_audio_hours,
    default_template_ref: preferences.default_template_ref,
  };
}

function samePreferences(a: MeetingPreferencesUpdate, b: MeetingPreferencesUpdate): boolean {
  return (
    a.stt_engine === b.stt_engine &&
    a.language === b.language &&
    a.auto_email === b.auto_email &&
    a.keep_audio_hours === b.keep_audio_hours &&
    a.default_template_ref === b.default_template_ref
  );
}

/**
 * « Default minutes format »: automatic first, then every template grouped by
 * category in library order (ADR-259). The API stores null for automatic.
 */
function DefaultTemplateSelect({
  lng,
  templates,
  value,
  onChange,
}: {
  lng: Language;
  templates: MeetingTemplateSummary[];
  value: string | null;
  onChange: (ref: string | null) => void;
}) {
  const { t } = useTranslation(lng);
  return (
    <TemplateSelect
      lng={lng}
      id="meeting-default-template"
      label={t('meetings.settings.default_template_label')}
      templates={templates}
      value={value}
      onChange={onChange}
      autoLabel={t('meetings.settings.default_template_auto')}
      hint={t('meetings.settings.default_template_hint')}
    />
  );
}

function PreferencesForm({
  lng,
  templates,
}: {
  lng: Language;
  templates: MeetingTemplateSummary[];
}) {
  const { t } = useTranslation(lng);
  const { preferences, isLoading, isSaving, save } = useMeetingPreferences();
  // The draft is DERIVED during render: null means "what the server holds";
  // an edit materialises it, a save clears it (no setState inside an effect).
  const [draft, setDraft] = useState<MeetingPreferencesUpdate | null>(null);

  if (isLoading || preferences === null) {
    return <Skeleton className="h-40 w-full" />;
  }
  const saved = preferencesDraft(preferences);
  const value = draft ?? saved;
  const dirty = draft !== null && !samePreferences(draft, saved);
  const max = preferences.keep_audio_hours_max;
  const edit = (patch: Partial<MeetingPreferencesUpdate>) => setDraft({ ...value, ...patch });

  const submit = async () => {
    if (isSaving || !dirty) return;
    const result = await save(value);
    if (result) {
      setDraft(null);
      toast.success(t('meetings.settings.saved'));
    } else {
      toast.error(t('common.error'));
    }
  };

  return (
    <div className="space-y-4" aria-busy={isSaving}>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-3">
          <Label htmlFor="meeting-engine">{t('meetings.settings.engine_label')}</Label>
          <Select
            value={value.stt_engine}
            onValueChange={next => edit({ stt_engine: next as MeetingSttEnginePreference })}
          >
            <SelectTrigger id="meeting-engine">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {ENGINES.map(engine => (
                <SelectItem key={engine} value={engine}>
                  {t(`meetings.settings.engine_${engine}`)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <p className="text-xs text-muted-foreground">{t('meetings.settings.engine_hint')}</p>
        </div>
        <div className="space-y-3">
          <Label htmlFor="meeting-language">{t('meetings.settings.language_label')}</Label>
          <Select value={value.language} onValueChange={next => edit({ language: next })}>
            <SelectTrigger id="meeting-language">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="auto">{t('meetings.settings.language_auto')}</SelectItem>
              {LANGUAGE_HINTS.map(code => (
                <SelectItem key={code} value={code}>
                  {t(`meetings.settings.language_codes.${code}`)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>
      <DefaultTemplateSelect
        lng={lng}
        templates={templates}
        value={value.default_template_ref}
        onChange={ref => edit({ default_template_ref: ref })}
      />
      <div className="flex items-center justify-between gap-3 rounded-md border border-border/60 p-3">
        <div>
          <Label htmlFor="meeting-auto-email">{t('meetings.settings.auto_email_label')}</Label>
          <p className="text-xs text-muted-foreground">{t('meetings.settings.auto_email_hint')}</p>
        </div>
        <Switch
          id="meeting-auto-email"
          checked={value.auto_email}
          onCheckedChange={checked => edit({ auto_email: checked })}
        />
      </div>
      <div className="space-y-3">
        <Label htmlFor="meeting-keep-audio">{t('meetings.settings.keep_audio_label')}</Label>
        <div className="flex flex-wrap items-center gap-3">
          <Input
            id="meeting-keep-audio"
            type="number"
            inputMode="numeric"
            min={0}
            max={max}
            className="w-28"
            value={value.keep_audio_hours}
            onChange={e =>
              edit({ keep_audio_hours: Math.max(0, Math.min(max, Number(e.target.value) || 0)) })
            }
          />
          <span className="text-xs text-muted-foreground">
            {value.keep_audio_hours === 0
              ? t('meetings.settings.keep_audio_none')
              : t('meetings.settings.keep_audio_hours', { count: value.keep_audio_hours })}
            {' · '}
            {t('meetings.settings.keep_audio_max', { count: max })}
          </span>
        </div>
      </div>
      <Button
        type="button"
        size="sm"
        onClick={() => void submit()}
        aria-disabled={!dirty || isSaving}
        isLoading={isSaving}
      >
        <Save className="mr-1 h-4 w-4" aria-hidden="true" />
        {t('common.save')}
      </Button>
    </div>
  );
}

/** The library in one line: how many templates the user keeps, and the door to it. */
function TemplatesBlock({
  lng,
  templates,
  isLoading,
}: {
  lng: Language;
  templates: MeetingTemplateSummary[];
  isLoading: boolean;
}) {
  const { t } = useTranslation(lng);
  const router = useLocalizedRouter();
  if (isLoading) return <Skeleton className="h-16 w-full" />;
  return (
    <div className="flex flex-wrap items-center gap-3">
      <p className="text-sm text-muted-foreground">
        {t('meetings.settings.templates_count', { count: userTemplateCount(templates) })}
      </p>
      <Button
        type="button"
        size="sm"
        variant="outline"
        onClick={() => router.push('/dashboard/meetings/templates')}
      >
        <LibraryBig className="mr-1 h-4 w-4" aria-hidden="true" />
        {t('meetings.settings.manage_templates')}
      </Button>
    </div>
  );
}

function RecentMeetings({ lng }: { lng: Language }) {
  const { t } = useTranslation(lng);
  const router = useLocalizedRouter();
  const { meetings, total, isLoading } = useMeetingList(RECENT_LIMIT);
  if (isLoading) return <Skeleton className="h-24 w-full" />;
  return (
    <div className="space-y-3">
      {meetings.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t('meetings.settings.no_meetings')}</p>
      ) : (
        <ul className="divide-y divide-border/60 rounded-md border border-border/60">
          {meetings.map(meeting => (
            <li key={meeting.id} className="flex flex-wrap items-center gap-2 px-3 py-2">
              <button
                type="button"
                className="min-w-0 flex-1 truncate text-left text-sm font-medium hover:underline"
                onClick={() => router.push(`/dashboard/meetings/${meeting.id}`)}
              >
                {meeting.title ?? t('meetings.list.untitled')}
              </button>
              <span className="text-xs text-muted-foreground">
                {new Date(meeting.started_at).toLocaleDateString(lng)}
                {meeting.audio_duration_seconds
                  ? ` · ${formatElapsed(meeting.audio_duration_seconds)}`
                  : ''}
              </span>
              <MeetingStatusBadge lng={lng} status={meeting.status} stage={meeting.stage} />
            </li>
          ))}
        </ul>
      )}
      <Button
        type="button"
        size="sm"
        variant="outline"
        onClick={() => router.push('/dashboard/meetings')}
      >
        <ExternalLink className="mr-1 h-4 w-4" aria-hidden="true" />
        {t('meetings.settings.view_all', { count: total })}
      </Button>
    </div>
  );
}

export function MeetingsSettings({ lng }: BaseSettingsProps) {
  const { t } = useTranslation(lng);
  const { config, loading } = useAppConfig();
  const enabled = useMemo(() => config?.features?.meetings_enabled ?? false, [config]);
  // One library read for the section: the default-format select and the block share it.
  const { templates, isLoading: templatesLoading } = useMeetingTemplates(enabled);
  if (loading || !enabled) return null;

  return (
    <SettingsSection
      value="meetings"
      title={t('settings.meetings.title')}
      description={t('settings.meetings.description')}
      icon={ClipboardList}
    >
      <div className="space-y-8">
        <section className="space-y-3">
          <h4 className="flex items-center gap-2 text-sm font-semibold">
            <Wand2 className="h-4 w-4 text-primary" aria-hidden="true" />
            {t('meetings.settings.preferences_title')}
          </h4>
          <PreferencesForm lng={lng} templates={templates} />
        </section>
        <section className="space-y-3">
          <h4 className="flex items-center gap-2 text-sm font-semibold">
            <LibraryBig className="h-4 w-4 text-primary" aria-hidden="true" />
            {t('meetings.settings.templates_title')}
          </h4>
          <p className="text-xs text-muted-foreground">
            {t('meetings.settings.templates_description')}
          </p>
          <TemplatesBlock lng={lng} templates={templates} isLoading={templatesLoading} />
        </section>
        <section className="space-y-3">
          <h4 className="flex items-center gap-2 text-sm font-semibold">
            <ClipboardList className="h-4 w-4 text-primary" aria-hidden="true" />
            {t('meetings.settings.recent_title')}
          </h4>
          <RecentMeetings lng={lng} />
        </section>
      </div>
    </SettingsSection>
  );
}
