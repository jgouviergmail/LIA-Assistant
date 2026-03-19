'use client';

import { useEffect, useState } from 'react';
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
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    if (open && space) {
      setName(space.name);
      setDescription(space.description || '');
      setError('');
    }
  }, [space, open]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    const trimmedName = name.trim();
    if (!trimmedName || trimmedName.length < 2) {
      setError(t('spaces.name_too_short'));
      return;
    }

    const newName = trimmedName !== space?.name ? trimmedName : undefined;
    const newDesc =
      description.trim() !== (space?.description || '') ? description.trim() : undefined;

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
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('spaces.edit_title')}</DialogTitle>
          <DialogDescription>{t('spaces.edit_description')}</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
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
          <div className="space-y-2">
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
      </DialogContent>
    </Dialog>
  );
}
