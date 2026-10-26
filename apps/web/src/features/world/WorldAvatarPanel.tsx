'use client';
import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { useWorldAvatar } from './useWorldAvatar';
import { WorldAvatarEditor } from './WorldAvatarEditor';

export function WorldAvatarPanel({
  lng,
  ownerId,
  onDone,
}: {
  lng: Language;
  ownerId: string;
  onDone(): void;
}) {
  const { t } = useTranslation(lng);
  const profile = useWorldAvatar(ownerId, true);
  const [editor, setEditor] = useState(0);
  if (profile.failed)
    return (
      <div role="alert" className="space-y-3 p-6">
        <p>{t('world.avatar.failed')}</p>
        <Button onClick={() => void profile.refresh()}>{t('world.retry')}</Button>
      </div>
    );
  if (!profile.avatar) return <Skeleton className="m-4 h-80" />;
  return (
    <div className="h-full space-y-4 overflow-y-auto p-4 sm:p-6" data-world-avatar-editor>
      <p className="text-sm text-muted-foreground">{t('world.avatar.description')}</p>
      <WorldAvatarEditor
        key={editor}
        lng={lng}
        initial={profile.avatar}
        saving={profile.saving}
        save={profile.save}
        refresh={async () => {
          if (await profile.reload()) setEditor(current => current + 1);
        }}
        onSaved={onDone}
        onCancel={onDone}
      />
    </div>
  );
}
