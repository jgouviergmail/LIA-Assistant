'use client';

/**
 * FileShareDialog — who a file is shared with (ADR-369, lot 6).
 *
 * Who reaches it and what they may do; a person added, whom the drive tells; a link
 * anyone can follow, opened or closed. An access is taken back from here, an owner's
 * never. A refusal is said in its own words and keeps what was typed, its key too, so
 * a lost answer pressed again is told what became of the first.
 */
import { Link2, Trash2, UserPlus } from '@/lib/icons';
import { useState, type FormEvent } from 'react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog';
import { EmptyState } from '@/components/ui/empty-state';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { useWorkbenchItem } from '@/hooks/useWorkbenchItem';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import apiClient from '@/lib/api-client';
import { copyText } from '@/lib/workbench/copy';
import { workbenchRefusal } from '@/lib/workbench/errors';
import type {
  WorkbenchFileDetail,
  WorkbenchFileSharing,
  WorkbenchSharedPerson,
} from '@/lib/workbench/types';
import { generateUUID } from '@/lib/utils';
import { ToolDialogHeader } from '../ToolForm';
import { NativeSelect } from '@/components/ui/native-select';

const SHARING_PATH = '/workbench/files/sharing';
const ROLES = ['reader', 'writer'] as const;
type ShareRole = (typeof ROLES)[number];

export interface FileShareDialogProps {
  lng: Language;
  file: Pick<WorkbenchFileDetail, 'id' | 'name'>;
  onClose: () => void;
}

export function FileShareDialog({ lng, file, onClose }: FileShareDialogProps) {
  const { t } = useTranslation(lng);
  const sharing = useWorkbenchItem<WorkbenchFileSharing>(SHARING_PATH, { id: file.id });
  const [email, setEmail] = useState('');
  const [role, setRole] = useState<ShareRole>('reader');
  const [key, setKey] = useState(() => generateUUID());
  const [busy, setBusy] = useState(false);

  /** Runs an act and reads the sharing again; whether it went through. */
  const act = async (run: () => Promise<unknown>): Promise<boolean> => {
    if (busy) return false;
    setBusy(true);
    try {
      await run();
      await sharing.refresh();
      return true;
    } catch (error: unknown) {
      const refusal = workbenchRefusal(error);
      toast.error(refusal ? t(refusal.key, refusal.values) : t('workbench.files.failed'));
      return false;
    } finally {
      setBusy(false);
    }
  };

  const share = async (event: FormEvent) => {
    event.preventDefault();
    const address = email.trim();
    if (!address) return;
    const done = await act(() =>
      apiClient.post(SHARING_PATH, {
        file_id: file.id,
        email: address,
        role,
        idempotency_key: key,
      })
    );
    if (!done) return;
    setEmail('');
    setKey(generateUUID());
    toast.success(t('workbench.files.shared'));
  };

  const removeAccess = (permissionId: string) =>
    void act(() =>
      apiClient.post(`${SHARING_PATH}/remove`, { file_id: file.id, permission_id: permissionId })
    );
  const link = sharing.item?.link ?? null;

  return (
    <Dialog open onOpenChange={open => !open && onClose()}>
      <DialogContent aria-describedby={undefined} className="sm:max-w-md">
        <ToolDialogHeader>
          <DialogTitle className="truncate">
            {t('workbench.files.share_title', { name: file.name })}
          </DialogTitle>
        </ToolDialogHeader>
        <form className="flex flex-wrap items-center gap-2" onSubmit={event => void share(event)}>
          <div className="min-w-0 flex-1 basis-40">
            <Input
              type="text"
              inputMode="email"
              autoComplete="email"
              value={email}
              onChange={event => setEmail(event.target.value)}
              aria-label={t('workbench.files.share_email')}
              placeholder={t('workbench.files.share_email')}
            />
          </div>
          <NativeSelect
            aria-label={t('workbench.files.share_role')}
            value={role}
            onChange={event => setRole(ROLES.find(item => item === event.target.value) ?? 'reader')}
            className="h-9 w-auto px-2"
          >
            {ROLES.map(item => (
              <option key={item} value={item}>
                {t(`workbench.files.role_${item}`)}
              </option>
            ))}
          </NativeSelect>
          <Button type="submit" size="sm" className="gap-1.5" isLoading={busy}>
            <UserPlus className="h-4 w-4" aria-hidden="true" />
            {t('workbench.files.share_send')}
          </Button>
        </form>
        <SharedPeople
          lng={lng}
          people={sharing.item?.people}
          loading={sharing.loading}
          error={sharing.error}
          onRetry={() => void sharing.refresh()}
          onRemove={removeAccess}
        />
        {sharing.item && (
          <div className="flex flex-wrap items-center gap-2 border-t pt-3 text-sm">
            <Link2 className="h-4 w-4 shrink-0" aria-hidden="true" />
            <span className="min-w-0 flex-1">
              {t(link ? 'workbench.files.link_on' : 'workbench.files.link_off')}
            </span>
            {link?.url && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  copyText(link.url ?? '').then(
                    () => toast.success(t('workbench.files.link_copied')),
                    () => toast.error(t('workbench.files.failed'))
                  );
                }}
              >
                {t('workbench.files.copy_link')}
              </Button>
            )}
            {link ? (
              <Button variant="ghost" size="sm" onClick={() => removeAccess(link.id)}>
                {t('workbench.files.link_close')}
              </Button>
            ) : (
              <Button
                variant="outline"
                size="sm"
                onClick={() =>
                  void act(() => apiClient.post(`${SHARING_PATH}/link`, { file_id: file.id }))
                }
              >
                {t('workbench.files.link_open')}
              </Button>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

function SharedPeople({
  lng,
  people,
  loading,
  error,
  onRetry,
  onRemove,
}: {
  lng: Language;
  people: readonly WorkbenchSharedPerson[] | undefined;
  loading: boolean;
  error: unknown;
  onRetry: () => void;
  onRemove: (permissionId: string) => void;
}) {
  const { t } = useTranslation(lng);
  if (people) {
    return (
      <ul className="max-h-56 space-y-1 overflow-y-auto">
        {people.map(person => (
          <li key={person.id} className="flex items-center gap-2 text-sm">
            <span className="flex min-w-0 flex-1 flex-col">
              <span className="truncate">{person.name ?? person.email}</span>
              {person.name && person.email && (
                <span className="truncate text-xs text-muted-foreground">{person.email}</span>
              )}
            </span>
            <span className="shrink-0 text-xs text-muted-foreground">
              {t(`workbench.files.role_${person.role}`)}
            </span>
            {person.role !== 'owner' && (
              <Button
                variant="ghost"
                size="icon"
                className="shrink-0"
                aria-label={t('workbench.files.share_remove')}
                onClick={() => onRemove(person.id)}
              >
                <Trash2 className="h-4 w-4" aria-hidden="true" />
              </Button>
            )}
          </li>
        ))}
      </ul>
    );
  }
  if (loading) return <Skeleton className="h-16 w-full" />;
  const refusal = workbenchRefusal(error);
  return (
    <EmptyState
      description={refusal ? t(refusal.key, refusal.values) : t('workbench.files.failed')}
      action={{ label: t('workbench.states.retry'), onClick: onRetry }}
    />
  );
}
