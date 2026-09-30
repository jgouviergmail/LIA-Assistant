'use client';

/**
 * Reading a skill from a GitHub address (ADR-327): ``owner/repo`` or a
 * github.com URL, a folder included (``/tree/<branch>/<path>``). A repository
 * holding several skills answers with the folders to choose from.
 */
import { useState } from 'react';
import type { TFunction } from 'i18next';
import { BookOpenText } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

export function LibraryAddressTab({
  t,
  busy,
  onRead,
}: {
  t: TFunction;
  busy: boolean;
  onRead: (address: string) => void;
}) {
  const [address, setAddress] = useState('');
  const ready = address.trim().length > 0;
  const submit = () => {
    if (ready && !busy) onRead(address.trim());
  };

  return (
    <form
      className="space-y-3"
      onSubmit={event => {
        event.preventDefault();
        submit();
      }}
    >
      <Input
        label={t('settings.skills.library.address.label')}
        value={address}
        onChange={event => setAddress(event.target.value)}
        placeholder={t('settings.skills.library.address.placeholder')}
        autoComplete="off"
        spellCheck={false}
      />
      <p className="text-xs text-muted-foreground">{t('settings.skills.library.address.hint')}</p>
      <div className="flex justify-end">
        <Button type="submit" aria-disabled={!ready || busy} isLoading={busy} className="gap-1.5">
          <BookOpenText className="h-4 w-4" aria-hidden />
          {t('settings.skills.library.address.read')}
        </Button>
      </div>
    </form>
  );
}
