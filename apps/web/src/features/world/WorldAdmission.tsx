'use client';
import { useState } from 'react';
import { Map as MapIcon, UsersRound } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { useWorldAvatar } from './useWorldAvatar';
import { WorldAvatarEditor } from './WorldAvatarEditor';
import { WorldAvatarPreview } from './WorldAvatarPreview';
import type { AvatarView } from './avatar-protocol';

interface Props {
  lng: Language;
  ownerId: string;
  onEnter(name: string): void;
}
export function WorldAdmission({ lng, ownerId, onEnter }: Props) {
  const { t } = useTranslation(lng);
  const profile = useWorldAvatar(ownerId, true);
  return (
    <section
      className="world-gateway border border-border bg-background"
      aria-label={t('world.title')}
    >
      <div className="world-gateway-art" aria-hidden="true">
        <MapIcon className="size-20" />
      </div>
      <div className="world-admission">
        <p className="flex items-center gap-2 text-sm font-medium text-primary">
          <UsersRound className="size-4" aria-hidden="true" />
          {t('world.session.shared')}
        </p>
        <h1 className="text-3xl font-semibold tracking-tight">{t('world.title')}</h1>
        <p className="text-sm leading-relaxed text-muted-foreground">{t('world.avatar.welcome')}</p>
        {profile.failed ? (
          <div role="alert" className="space-y-3">
            <p>{t('world.avatar.failed')}</p>
            <Button onClick={() => void profile.refresh()}>{t('world.retry')}</Button>
          </div>
        ) : profile.avatar ? (
          <AdmissionReady
            key={ownerId}
            lng={lng}
            value={profile.avatar}
            profile={profile}
            onEnter={onEnter}
          />
        ) : (
          <Skeleton className="h-80 w-full" />
        )}
      </div>
    </section>
  );
}
function AdmissionReady({
  lng,
  value,
  profile,
  onEnter,
}: {
  lng: Language;
  value: AvatarView;
  profile: ReturnType<typeof useWorldAvatar>;
  onEnter(name: string): void;
}) {
  const { t } = useTranslation(lng);
  const [editing, setEditing] = useState(value.needs_setup);
  const [editor, setEditor] = useState(0);
  if (editing)
    return (
      <WorldAvatarEditor
        key={editor}
        lng={lng}
        initial={value}
        onboarding
        saving={profile.saving}
        save={profile.save}
        refresh={async () => {
          if (await profile.reload()) setEditor(current => current + 1);
        }}
        onSaved={saved => onEnter(saved.public_name)}
        onCancel={value.needs_setup ? undefined : () => setEditing(false)}
      />
    );
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-center gap-3 rounded-2xl border bg-muted/20 p-3">
        <WorldAvatarPreview lng={lng} appearance={value.preferences.appearance} />
        <div className="min-w-0">
          <p data-world-public-name className="break-words text-lg font-semibold">
            {value.public_name}
          </p>
          <Button variant="ghost" className="min-h-11" onClick={() => setEditing(true)}>
            {t('world.avatar.change')}
          </Button>
        </div>
      </div>
      <p className="text-xs leading-relaxed text-muted-foreground">{t('world.avatar.consent')}</p>
      <Button className="min-h-11 w-full" onClick={() => onEnter(value.public_name)}>
        {t('world.session.enter')}
      </Button>
    </div>
  );
}
