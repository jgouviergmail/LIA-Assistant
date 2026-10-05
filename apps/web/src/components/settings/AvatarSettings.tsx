'use client';

import { ScanFace } from 'lucide-react';
import Link from 'next/link';
import Image from 'next/image';
import { useEffect, useRef, useState } from 'react';
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
import apiClient from '@/lib/api-client';
import type { AvatarConfig, AvatarFace } from '@/lib/avatars/types';
import { settingsSectionHref } from '@/lib/settings-sections';
import { bumpRevision, useResourceRevision } from '@/stores/revisionStore';
import type { Language } from '@/i18n/settings';

export function AvatarSettings({ lng }: { lng: Language }) {
  const { user } = useAuth();
  const { config } = useAppConfig();
  if (!user || !config?.features.avatar_enabled) return null;
  return <AvatarAccountSettings key={user.id} lng={lng} />;
}

function AvatarAccountSettings({ lng }: { lng: Language }) {
  const { t } = useTranslation();
  const { refreshUser } = useAuth();
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
  const [editedEnabled, setEditedEnabled] = useState<boolean | null>(null);
  const [saving, setSaving] = useState(false);
  const [failed, setFailed] = useState(false);
  const request = useRef<AbortController | null>(null);
  useEffect(() => () => request.current?.abort(), []);
  const config = query.data;
  const face = editedFace ?? config?.face_id ?? '';
  const enabled = editedEnabled ?? config?.enabled ?? false;

  async function save() {
    if (request.current || !config) return;
    const identity = face.trim();
    if (
      (identity && !/^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(identity)) ||
      (enabled && !identity)
    ) {
      setFailed(true);
      return;
    }
    const controller = new AbortController();
    request.current = controller;
    setSaving(true);
    setFailed(false);
    try {
      const updated = await apiClient.put<AvatarConfig>(
        '/avatars/settings',
        {
          enabled,
          face_id: identity || null,
        },
        { signal: controller.signal }
      );
      if (controller.signal.aborted) return;
      query.setData(updated);
      setEditedFace(null);
      setEditedEnabled(null);
      bumpRevision('avatar');
      await refreshUser();
    } catch {
      if (!controller.signal.aborted) setFailed(true);
    } finally {
      if (request.current === controller) request.current = null;
      if (!controller.signal.aborted) setSaving(false);
    }
  }

  return (
    <SettingsSection
      value="avatar"
      title={t('settings.avatar.title')}
      description={t('settings.avatar.description')}
      icon={ScanFace}
    >
      {query.loading && !config ? <p role="status">{t('common.loading')}</p> : null}
      {query.error || failed ? (
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
          onEnabledChange={setEditedEnabled}
          onSave={() => void save()}
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
  onSave,
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
  onSave: () => void;
}) {
  const { t } = useTranslation();
  return (
    <FormSection icon={ScanFace} title={t('settings.avatar.title')}>
      <div className="space-y-4" aria-busy={saving}>
        <div className="flex items-center justify-between gap-4">
          <Label htmlFor="avatar-enabled">{t('settings.avatar.enabled')}</Label>
          <Switch
            id="avatar-enabled"
            checked={enabled}
            onCheckedChange={onEnabledChange}
            disabled={saving || (!enabled && (!config.connected || !config.available))}
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
          <AvatarFaceFields face={face} faces={faces} disabled={saving} onChange={onFaceChange} />
        )}
        {facesError ? (
          <p role="alert" className="text-sm text-destructive">
            {t('settings.avatar.error')}
          </p>
        ) : null}
        <p role="note" className="text-xs text-muted-foreground">
          {t('settings.avatar.cost_note')}
        </p>
        <Button onClick={onSave} aria-disabled={saving}>
          {t(saving ? 'settings.avatar.saving' : 'settings.avatar.save')}
        </Button>
      </div>
    </FormSection>
  );
}

function AvatarFaceFields({
  face,
  faces,
  disabled,
  onChange,
}: {
  face: string;
  faces: readonly AvatarFace[];
  disabled: boolean;
  onChange: (face: string) => void;
}) {
  const { t } = useTranslation();
  const selected = faces.find(item => item.id === face.trim().toLowerCase());
  return (
    <div className="space-y-3">
      {faces.length > 0 ? (
        <div className="space-y-2">
          <Label htmlFor="avatar-face">{t('settings.avatar.face')}</Label>
          <Select value={face} onValueChange={onChange} disabled={disabled}>
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
          disabled={disabled}
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
    <figure className="flex flex-col items-center gap-2 rounded-lg border bg-muted/30 p-3">
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
