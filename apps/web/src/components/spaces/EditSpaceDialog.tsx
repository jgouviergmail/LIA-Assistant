'use client';

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import type { RAGSpace } from '@/types/rag-spaces';

interface EditSpaceDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  space: RAGSpace | null;
  onSubmit: (name?: string, description?: string) => Promise<void>;
  isLoading?: boolean;
}

export function EditSpaceDialog({
  open,
  onOpenChange,
  space,
  onSubmit,
  isLoading,
}: EditSpaceDialogProps) {
  const { t } = useTranslation();

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('spaces.edit_title')}</DialogTitle>
          <DialogDescription>{t('spaces.edit_description')}</DialogDescription>
        </DialogHeader>
        {open && space && (
          <EditSpaceForm
            key={space.id}
            space={space}
            onOpenChange={onOpenChange}
            onSubmit={onSubmit}
            isLoading={isLoading}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

type EditSpaceFormProps = Omit<EditSpaceDialogProps, 'open' | 'space'> & { space: RAGSpace };

/** One draft per opening: background reads never overwrite the person's edits. */
function EditSpaceForm({ space, onOpenChange, onSubmit, isLoading }: EditSpaceFormProps) {
  const { t } = useTranslation();
  const [initial] = useState(() => ({
    name: space.name,
    description: space.description || '',
  }));
  const [name, setName] = useState(initial.name);
  const [description, setDescription] = useState(initial.description);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    const trimmedName = name.trim();
    if (!trimmedName || trimmedName.length < 2) {
      setError(t('spaces.name_too_short'));
      return;
    }

    const newName = trimmedName !== initial.name ? trimmedName : undefined;
    const newDesc = description.trim() !== initial.description ? description.trim() : undefined;

    // Skip API call if nothing changed
    if (newName === undefined && newDesc === undefined) {
      onOpenChange(false);
      return;
    }

    try {
      await onSubmit(newName, newDesc);
      onOpenChange(false);
    } catch {
      setError(t('spaces.edit_error'));
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="space-y-3">
        <Label htmlFor="edit-space-name">{t('spaces.name_label')}</Label>
        <Input
          id="edit-space-name"
          value={name}
          onChange={e => setName(e.target.value)}
          placeholder={t('spaces.name_placeholder')}
          maxLength={200}
          autoFocus
        />
        {error && <p className="text-sm text-destructive">{error}</p>}
      </div>
      <div className="space-y-3">
        <Label htmlFor="edit-space-description">
          {t('spaces.description_label')}{' '}
          <span className="text-muted-foreground">({t('common.optional')})</span>
        </Label>
        <Textarea
          id="edit-space-description"
          value={description}
          onChange={e => setDescription(e.target.value)}
          placeholder={t('spaces.description_placeholder')}
          rows={3}
        />
      </div>
      <DialogFooter>
        <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
          {t('common.cancel')}
        </Button>
        <Button type="submit" isLoading={isLoading}>
          {t('common.save')}
        </Button>
      </DialogFooter>
    </form>
  );
}
