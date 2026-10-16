'use client';

import { ScanFace } from 'lucide-react';
import Link from 'next/link';
import Image from 'next/image';
import { useEffect, useRef, useState, type RefObject } from 'react';
import { useTranslation } from 'react-i18next';

import { SettingsSection } from './SettingsSection';
import { Button } from '@/components/ui/button';
import { FormSection } from '@/components/ui/form-section';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { useApiQuery } from '@/hooks/useApiQuery';
import { useAppConfig } from '@/hooks/useAppConfig';
import { useAuth } from '@/hooks/useAuth';
import { useAvatarPreferenceSave } from '@/components/avatars/AvatarPreferenceSaveProvider';
import type { AvatarConfig, AvatarFace } from '@/lib/avatars/types';
import { settingsSectionHref } from '@/lib/settings-sections';
import { useResourceRevision } from '@/stores/revisionStore';
import type { Language } from '@/i18n/settings';

function avatarFormState(
  confirmed: AvatarConfig | null,
  incoming: AvatarConfig | undefined,
  desired: Pick<AvatarConfig, 'enabled' | 'face_id'> | null,
  editedFace: string | null
) {
  // Live availability comes from the read; confirmed preferences survive navigation.
  const config = confirmed
    ? { ...confirmed, ...incoming, enabled: confirmed.enabled, face_id: confirmed.face_id }
    : incoming;
  const preference = desired ?? config;
  return {
    config,
    preference,
    face: editedFace ?? preference?.face_id ?? '',
    enabled: preference?.enabled ?? false,
  };
}

export function AvatarSettings({ lng }: { lng: Language }) {
  const { user } = useAuth();
  const { config } = useAppConfig();
  if (!user || !config?.features.avatar_enabled) return null;
  return <AvatarAccountSettings key={user.id} lng={lng} />;
}

function AvatarAccountSettings({ lng }: { lng: Language }) {
  const { t } = useTranslation();
  const persistence = useAvatarPreferenceSave();
  const revision = useResourceRevision('avatar');
  const query = useApiQuery<AvatarConfig>('/avatars/config', {
    componentName: 'AvatarSettings',
    deps: [revision],
  });
  const faces = useApiQuery<AvatarFace[]>('/avatars/faces', {
    componentName: 'AvatarFaces',
    enabled: !!query.data?.connected,
    deps: [revision],
  });
  const [editedFace, setEditedFace] = useState<string | null>(null);
  const [invalid, setInvalid] = useState(false);
  const { config, preference, face, enabled } = avatarFormState(
    persistence.confirmed,
    query.data,
    persistence.desired,
    editedFace
  );
  useEffect(() => {
    if (query.data) persistence.initialize(query.data);
  }, [query.data, persistence]);
  const saving = persistence.saving;
  function saveFace(identity: string) {
    const value = identity.trim().toLowerCase();
    if (
      (value && !/^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(value)) ||
      (enabled && !value)
    ) {
      setInvalid(true);
      return;
    }
    setInvalid(false);
    setEditedFace(null);
    if (value !== (preference?.face_id ?? ''))
      persistence.change({ enabled, face_id: value || null });
  }

  return (
    <SettingsSection
      value="avatar"
      title={t('settings.avatar.title')}
      description={t('settings.avatar.description')}
      icon={ScanFace}
    >
      {query.loading && !config ? <p role="status">{t('common.loading')}</p> : null}
      {query.error || persistence.failed || invalid ? (
        <p role="alert" className="text-sm text-destructive">
          {t('settings.avatar.error')}
        </p>
      ) : null}
      {config ? (
        <AvatarPreferencesForm
          config={config}
          lng={lng}
          face={face}
          enabled={enabled}
          faces={faces.data ?? []}
          facesError={!!faces.error}
          saving={saving}
          onFaceChange={setEditedFace}
          onFaceCommit={saveFace}
          onEnabledChange={next => {
            if (next && !preference?.face_id) {
              setInvalid(true);
              return;
            }
            setInvalid(false);
            persistence.change({ enabled: next, face_id: preference?.face_id ?? null });
          }}
          onRetry={persistence.retry}
          failed={persistence.failed}
          saved={persistence.saved}
        />
      ) : null}
    </SettingsSection>
  );
}

function AvatarPreferencesForm({
  config,
  lng,
  face,
  enabled,
  faces,
  facesError,
  saving,
  onFaceChange,
  onEnabledChange,
  onRetry,
  failed,
  saved,
  onFaceCommit,
}: {
  config: AvatarConfig;
  lng: Language;
  face: string;
  enabled: boolean;
  faces: readonly AvatarFace[];
  facesError: boolean;
  saving: boolean;
  onFaceChange: (face: string) => void;
  onEnabledChange: (enabled: boolean) => void;
  onRetry: () => Promise<boolean>;
  failed: boolean;
  saved: boolean;
  onFaceCommit: (face: string) => void;
}) {
  const { t } = useTranslation();
  const formRef = useRef<HTMLDivElement>(null);
  return (
    <FormSection icon={ScanFace} title={t('settings.avatar.title')}>
      <div ref={formRef} className="space-y-4" aria-busy={saving}>
        <div className="flex items-center justify-between gap-4">
          <Label htmlFor="avatar-enabled">{t('settings.avatar.enabled')}</Label>
          <Switch
            id="avatar-enabled"
            checked={enabled}
            onCheckedChange={onEnabledChange}
            disabled={!enabled && (!config.connected || !config.available)}
          />
        </div>
        {!config.available ? (
          <p className="text-sm text-muted-foreground">
            {t('settings.avatar.disabled_by_instance')}
          </p>
        ) : null}
        {!config.connected ? (
          <Button asChild variant="outline">
            <Link href={settingsSectionHref(lng, 'connectors')}>
              {t('settings.avatar.connect')}
            </Link>
          </Button>
        ) : (
          <AvatarFaceFields
            face={face}
            faces={faces}
            onChange={onFaceChange}
            onCommit={onFaceCommit}
          />
        )}
        {facesError ? (
          <p role="alert" className="text-sm text-destructive">
            {t('settings.avatar.error')}
          </p>
        ) : null}
        <p role="note" className="text-xs text-muted-foreground">
          {t('settings.avatar.cost_note')}
        </p>
        {saving || saved ? (
          <p role="status" className="text-xs text-muted-foreground">
            {t(saving ? 'settings.avatar.saving' : 'settings.avatar.saved')}
          </p>
        ) : null}
        <AvatarRetryAction failed={failed} saving={saving} onRetry={onRetry} formRef={formRef} />
      </div>
    </FormSection>
  );
}

/** Keep the event's target alive until retry settles, including navigation-safe focus return. */
function AvatarRetryAction({
  failed,
  saving,
  onRetry,
  formRef,
}: {
  failed: boolean;
  saving: boolean;
  onRetry: () => Promise<boolean>;
  formRef: RefObject<HTMLDivElement | null>;
}) {
  const { t } = useTranslation();
  const buttonRef = useRef<HTMLButtonElement>(null);
  const pending = useRef(false);
  const [retrying, setRetrying] = useState(false);
  async function retry() {
    if (pending.current || saving) return;
    pending.current = true;
    setRetrying(true);
    const button = buttonRef.current;
    const confirmed = await onRetry();
    // The provider outlives route content. A departed form owns no focus and
    // must not publish local UI state when its outstanding save completes.
    if (!button?.isConnected) return;
    if (confirmed && document.activeElement === button) {
      formRef.current
        ?.querySelector<HTMLElement>(
          '[role="switch"]:not(:disabled),#avatar-face,#avatar-face-custom,a[href]'
        )
        ?.focus();
    }
    pending.current = false;
    setRetrying(false);
  }
  if (!failed && !retrying) return null;
  return (
    <Button ref={buttonRef} onClick={() => void retry()} isLoading={retrying}>
      {t('common.retry')}
    </Button>
  );
}

function AvatarFaceFields({
  face,
  faces,
  onChange,
  onCommit,
}: {
  face: string;
  faces: readonly AvatarFace[];
  onChange: (face: string) => void;
  onCommit: (face: string) => void;
}) {
  const { t } = useTranslation();
  const selected = faces.find(item => item.id === face.trim().toLowerCase());
  return (
    <div className="space-y-3">
      {faces.length > 0 ? (
        <div className="space-y-2">
          <Label htmlFor="avatar-face">{t('settings.avatar.face')}</Label>
          <Select value={face} onValueChange={onCommit}>
            <SelectTrigger id="avatar-face">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {faces.map(item => (
                <SelectItem key={item.id} value={item.id}>
                  {item.name}
                </SelectItem>
              ))}
              {face && !faces.some(item => item.id === face) ? (
                <SelectItem value={face}>{face}</SelectItem>
              ) : null}
            </SelectContent>
          </Select>
        </div>
      ) : null}
      <AvatarFacePreview
        key={`${face.trim().toLowerCase()}:${selected?.preview_image_url ?? ''}`}
        selected={selected}
      />
      <div className="space-y-2">
        <Label htmlFor="avatar-face-custom">{t('settings.avatar.face_custom')}</Label>
        <Input
          id="avatar-face-custom"
          value={face}
          onChange={event => onChange(event.target.value)}
          onBlur={event => onCommit(event.target.value)}
          onKeyDown={event => {
            if (event.key === 'Enter') {
              event.preventDefault();
              onCommit(event.currentTarget.value);
            }
          }}
          maxLength={36}
          autoComplete="off"
          spellCheck={false}
        />
      </div>
    </div>
  );
}

function AvatarFacePreview({ selected }: { selected: AvatarFace | undefined }) {
  const { t } = useTranslation();
  const [failed, setFailed] = useState(false);
  return (
    <figure className="flex flex-col items-center gap-2 rounded-lg border bg-background p-3">
      {selected?.preview_image_url && !failed ? (
        <Image
          src={selected.preview_image_url}
          alt={selected.name}
          width={176}
          height={176}
          unoptimized
          referrerPolicy="no-referrer"
          className="h-44 w-44 max-w-full rounded-md object-contain"
          onError={() => setFailed(true)}
        />
      ) : (
        <div className="flex min-h-32 flex-col items-center justify-center gap-2 text-sm text-muted-foreground">
          <ScanFace aria-hidden="true" className="size-8" />
          <span>{t('settings.avatar.preview_unavailable')}</span>
        </div>
      )}
      {selected ? (
        <figcaption className="max-w-full break-words text-center text-sm">
          {selected.name}
        </figcaption>
      ) : null}
    </figure>
  );
}
