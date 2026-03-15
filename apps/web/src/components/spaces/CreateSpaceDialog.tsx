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

interface CreateSpaceDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (name: string, description?: string) => Promise<void>;
  isLoading?: boolean;
}

export function CreateSpaceDialog({ open, onOpenChange, onSubmit, isLoading }: CreateSpaceDialogProps) {
  const { t } = useTranslation();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [error, setError] = useState('');

  // Reset form state when dialog opens
  useEffect(() => {
    if (open) {
      setName('');
      setDescription('');
      setError('');
    }
  }, [open]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    const trimmedName = name.trim();
    if (!trimmedName || trimmedName.length < 2) {
      setError(t('spaces.name_too_short'));
      return;
    }
    if (trimmedName.length > 200) {
      setError(t('spaces.name_too_long'));
      return;
    }

    try {
      await onSubmit(trimmedName, description.trim() || undefined);
      setName('');
      setDescription('');
      onOpenChange(false);
    } catch {
      setError(t('spaces.create_error'));
    }
  };

  const handleClose = (value: boolean) => {
    if (!value) {
      setName('');
      setDescription('');
      setError('');
    }
    onOpenChange(value);
  };

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('spaces.create_title')}</DialogTitle>
          <DialogDescription>{t('spaces.create_description')}</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="space-name">{t('spaces.name_label')}</Label>
            <Input
              id="space-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t('spaces.name_placeholder')}
              maxLength={200}
              autoFocus
            />
            {error && <p className="text-sm text-destructive">{error}</p>}
          </div>
          <div className="space-y-2">
            <Label htmlFor="space-description">
              {t('spaces.description_label')}{' '}
              <span className="text-muted-foreground">({t('common.optional')})</span>
            </Label>
            <Textarea
              id="space-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder={t('spaces.description_placeholder')}
              rows={3}
            />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => handleClose(false)}>
              {t('common.cancel')}
            </Button>
            <Button type="submit" isLoading={isLoading}>
              {t('spaces.create_button')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
