'use client';

/**
 * DocumentSettings — how LIA illustrates and animates the documents it creates.
 *
 * Two choices on the account, read by the document tool at every generation
 * (`core/document_preferences.py`): whether a document is illustrated (LIA's
 * judgement, only on request, never) and whether a deck is animated (only a
 * deck to be presented, always, never). An illustration is an image generation:
 * while the instance offers none (the operator's switch), or the person's own
 * image generation is off, the page says that no document is illustrated,
 * whatever the choice — the instance first, since the person cannot reopen it.
 *
 * Native radios give each group its semantics and arrow-key navigation. A
 * choice being saved never disables the control the focus is on: the group is
 * `aria-disabled` and the hook's guard refuses a second save (apps/web/CLAUDE.md).
 */

import { toast } from 'sonner';

import { SettingsSection } from '@/components/settings/SettingsSection';
import { useAppConfig } from '@/hooks/useAppConfig';
import { useAuth } from '@/hooks/useAuth';
import { useDocumentPreferences } from '@/hooks/useDocumentPreferences';
import { useTranslation } from '@/i18n/client';
import { capabilityAvailable } from '@/lib/capability-availability';
import {
  Ban,
  Clapperboard,
  FileText,
  Hand,
  ImageIcon,
  Presentation,
  Sparkles,
  type LucideIcon,
} from '@/lib/icons';
import {
  DOCUMENT_ANIMATIONS,
  DOCUMENT_ILLUSTRATIONS,
  type DocumentPreferenceField,
} from '@/lib/document-preferences';
import { cn } from '@/lib/utils';
import type { BaseSettingsProps } from '@/types/settings';

const PREFIX = 'settings.documents';

const ICONS: Readonly<Record<string, LucideIcon>> = {
  auto: Sparkles,
  on_request: Hand,
  presented: Presentation,
  always: Clapperboard,
  never: Ban,
};

interface ChoiceGroupProps {
  lng: BaseSettingsProps['lng'];
  field: DocumentPreferenceField;
  group: 'illustrations' | 'animations';
  choices: readonly string[];
  current: string | undefined;
  icon: LucideIcon;
  busy: boolean;
  note?: string;
  onChoose: (field: DocumentPreferenceField, value: string) => void;
}

/** One question, its options as cards over native radios. */
function ChoiceGroup({
  lng,
  field,
  group,
  choices,
  current,
  icon: Icon,
  busy,
  note,
  onChoose,
}: ChoiceGroupProps) {
  const { t } = useTranslation(lng);
  const name = `document-${group}`;
  return (
    <fieldset aria-describedby={`${name}-hint`} aria-disabled={busy || undefined}>
      <legend className="mb-1 flex items-center gap-2 text-sm font-medium text-foreground">
        <Icon className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
        {t(`${PREFIX}.${group}.label`)}
      </legend>
      <p id={`${name}-hint`} className="mb-3 text-xs text-muted-foreground">
        {t(`${PREFIX}.${group}.hint`)}
      </p>
      {note ? (
        <p role="note" className="mb-3 rounded-lg border bg-muted/40 p-3 text-xs text-foreground">
          {note}
        </p>
      ) : null}
      <div className="grid gap-2 sm:grid-cols-3">
        {choices.map(choice => (
          <ChoiceCard
            key={choice}
            lng={lng}
            name={name}
            group={group}
            choice={choice}
            selected={current === choice}
            onSelect={() => onChoose(field, choice)}
          />
        ))}
      </div>
    </fieldset>
  );
}

interface ChoiceCardProps {
  lng: BaseSettingsProps['lng'];
  name: string;
  group: 'illustrations' | 'animations';
  choice: string;
  selected: boolean;
  onSelect: () => void;
}

function ChoiceCard({ lng, name, group, choice, selected, onSelect }: ChoiceCardProps) {
  const { t } = useTranslation(lng);
  const Icon = ICONS[choice] ?? Sparkles;
  const id = `${name}-${choice}`;
  return (
    <label
      className={cn(
        'flex cursor-pointer flex-col gap-1.5 rounded-lg border-2 p-3 transition-all hover:bg-accent',
        'has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ring has-[:focus-visible]:ring-offset-2 has-[:focus-visible]:ring-offset-background',
        selected ? 'border-primary bg-primary/5' : 'border-border bg-background'
      )}
    >
      <input
        type="radio"
        name={name}
        value={choice}
        checked={selected}
        onChange={onSelect}
        aria-labelledby={`${id}-label`}
        aria-describedby={`${id}-description`}
        className="sr-only"
      />
      <span className="flex items-center gap-2">
        <Icon
          className={cn('h-4 w-4', selected ? 'text-primary' : 'text-muted-foreground')}
          aria-hidden="true"
        />
        <span
          id={`${id}-label`}
          className={cn('text-sm font-medium', selected ? 'text-primary' : 'text-foreground')}
        >
          {t(`${PREFIX}.${group}.options.${choice}.label`)}
        </span>
      </span>
      <span id={`${id}-description`} className="text-xs text-muted-foreground">
        {t(`${PREFIX}.${group}.options.${choice}.description`)}
      </span>
    </label>
  );
}

export function DocumentSettings({ lng }: BaseSettingsProps) {
  const { t } = useTranslation(lng);
  const { user, refreshUser } = useAuth();
  const { config } = useAppConfig();
  const { saving, save } = useDocumentPreferences(user, refreshUser);

  const choose = async (field: DocumentPreferenceField, value: string) => {
    if (!user || saving !== null || user[field] === value) return;
    const saved = await save(field, value);
    if (saved) toast.success(t(`${PREFIX}.updated`));
    else toast.error(t('common.error'));
  };

  // A configuration not loaded yet says nothing: doubt states no absence.
  const instanceWithoutImages = config !== null && !capabilityAvailable(config, 'image_generation');
  const personWithoutImages = user ? !user.image_generation_enabled : false;
  const imagesNote = instanceWithoutImages
    ? t(`${PREFIX}.illustrations.instance_without_images`)
    : personWithoutImages
      ? t(`${PREFIX}.illustrations.needs_images`)
      : undefined;

  return (
    <SettingsSection
      value="documents"
      icon={FileText}
      title={t('settings.documents.title')}
      description={t('settings.documents.description')}
    >
      <div className="space-y-6" aria-busy={saving !== null || undefined}>
        <ChoiceGroup
          lng={lng}
          field="document_illustrations"
          group="illustrations"
          choices={DOCUMENT_ILLUSTRATIONS}
          current={user?.document_illustrations}
          icon={ImageIcon}
          busy={saving !== null}
          note={imagesNote}
          onChoose={(field, value) => void choose(field, value)}
        />
        <ChoiceGroup
          lng={lng}
          field="document_animations"
          group="animations"
          choices={DOCUMENT_ANIMATIONS}
          current={user?.document_animations}
          icon={Presentation}
          busy={saving !== null}
          onChoose={(field, value) => void choose(field, value)}
        />
      </div>
    </SettingsSection>
  );
}
