'use client';

import { useState, useEffect, useCallback, useTransition } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Switch } from '@/components/ui/switch';
import { TableSkeleton } from '@/components/ui/skeleton';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  fetchPersonalitiesAdmin,
  createPersonality,
  updatePersonality,
  deletePersonality,
  translatePersonality,
} from '@/lib/api/personality';
import { PersonalityResponse, PersonalityCreate, PersonalityUpdate } from '@/types/personality';
import { Plus, Pencil, Trash2, Languages, GripVertical, Star, Sparkles } from 'lucide-react';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { logger } from '@/lib/logger';
import { useTranslation } from '@/i18n/client';
import { fallbackLng, languages } from '@/i18n/settings';
import { SettingsSection } from '@/components/settings/SettingsSection';
import type { BaseSettingsProps } from '@/types/settings';

export default function AdminPersonalitiesSection({ lng, collapsible = true }: BaseSettingsProps) {
  const { t } = useTranslation(lng, 'translation');
  const [personalities, setPersonalities] = useState<PersonalityResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [isPending, startTransition] = useTransition();

  // Dialog state
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingPersonality, setEditingPersonality] = useState<PersonalityResponse | null>(null);

  // Original values for change detection (to avoid unnecessary updates and propagation)
  const [originalValues, setOriginalValues] = useState<{
    code: string;
    emoji: string;
    prompt_instruction: string;
    is_default: boolean;
    sort_order: number;
    title: string;
    description: string;
  } | null>(null);

  // Form state
  const [formData, setFormData] = useState<PersonalityCreate>({
    code: '',
    emoji: '',
    prompt_instruction: '',
    title: '',
    description: '',
    source_language: fallbackLng,
    is_default: false,
    sort_order: 0,
  });

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchPersonalitiesAdmin();
      setPersonalities(data.sort((a, b) => a.sort_order - b.sort_order));
    } catch (error) {
      logger.error('personalities_fetch_failed', error instanceof Error ? error : undefined, { component: 'AdminPersonalitiesSection' });
      toast.error(t('settings.admin.personalities.errors.loading'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const openCreateDialog = () => {
    setEditingPersonality(null);
    setOriginalValues(null);
    setFormData({
      code: '',
      emoji: '',
      prompt_instruction: '',
      title: '',
      description: '',
      source_language: fallbackLng,
      is_default: false,
      sort_order: personalities.length,
    });
    setDialogOpen(true);
  };

  const openEditDialog = (personality: PersonalityResponse) => {
    setEditingPersonality(personality);
    // Find French translation for title/description
    const frTranslation = personality.translations.find(t => t.language_code === fallbackLng);
    // Store ALL original values for change detection
    setOriginalValues({
      code: personality.code,
      emoji: personality.emoji,
      prompt_instruction: personality.prompt_instruction,
      is_default: personality.is_default,
      sort_order: personality.sort_order,
      title: frTranslation?.title || '',
      description: frTranslation?.description || '',
    });
    setFormData({
      code: personality.code,
      emoji: personality.emoji,
      prompt_instruction: personality.prompt_instruction,
      title: frTranslation?.title || '',
      description: frTranslation?.description || '',
      source_language: fallbackLng,
      is_default: personality.is_default,
      sort_order: personality.sort_order,
    });
    setDialogOpen(true);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    startTransition(async () => {
      try {
        if (editingPersonality && originalValues) {
          // Detect what changed to send only modified fields (prevents concurrent edit issues)
          const codeChanged = formData.code !== originalValues.code;
          const emojiChanged = formData.emoji !== originalValues.emoji;
          const promptChanged = formData.prompt_instruction !== originalValues.prompt_instruction;
          const defaultChanged = formData.is_default !== originalValues.is_default;
          const orderChanged = formData.sort_order !== originalValues.sort_order;
          const titleChanged = formData.title !== originalValues.title;
          const descChanged = formData.description !== originalValues.description;

          // Build update data with ONLY changed fields
          const updateData: PersonalityUpdate = {
            ...(codeChanged ? { code: formData.code } : {}),
            ...(emojiChanged ? { emoji: formData.emoji } : {}),
            ...(promptChanged ? { prompt_instruction: formData.prompt_instruction } : {}),
            ...(defaultChanged ? { is_default: formData.is_default } : {}),
            ...(orderChanged ? { sort_order: formData.sort_order } : {}),
            // Include title/description only if changed (triggers propagation)
            ...(titleChanged ? { title: formData.title } : {}),
            ...(descChanged ? { description: formData.description } : {}),
            // Include source_language if title or description changed
            ...(titleChanged || descChanged ? { source_language: fallbackLng } : {}),
          };

          // Only call API if something changed
          if (Object.keys(updateData).length > 0) {
            await updatePersonality(editingPersonality.id, updateData);
            toast.success(t('settings.admin.personalities.success.updated'));
          }
        } else {
          // Create new personality
          await createPersonality(formData);
          toast.success(t('settings.admin.personalities.success.created'));
        }
        setDialogOpen(false);
        fetchData();
      } catch (error) {
        logger.error('personality_save_failed', error instanceof Error ? error : undefined, { component: 'AdminPersonalitiesSection', action: 'save' });
        toast.error(error instanceof Error ? error.message : t('settings.admin.personalities.errors.save'));
      }
    });
  };

  const handleDelete = (personality: PersonalityResponse) => {
    if (personality.is_default) {
      toast.error(t('settings.admin.personalities.errors.delete_default'));
      return;
    }

    const confirmed = confirm(
      `${t('settings.admin.personalities.confirm.delete_title', { code: personality.code })}\n\n${t('settings.admin.personalities.confirm.delete_message')}`
    );

    if (!confirmed) return;

    startTransition(async () => {
      try {
        await deletePersonality(personality.id);
        toast.success(t('settings.admin.personalities.success.deleted'));
        fetchData();
      } catch (error) {
        logger.error('personality_delete_failed', error instanceof Error ? error : undefined, { component: 'AdminPersonalitiesSection', action: 'delete', personalityId: personality.id });
        toast.error(error instanceof Error ? error.message : t('settings.admin.personalities.errors.delete'));
      }
    });
  };

  const handleToggleActive = (personality: PersonalityResponse) => {
    startTransition(async () => {
      try {
        await updatePersonality(personality.id, { is_active: !personality.is_active });
        toast.success(personality.is_active ? t('settings.admin.personalities.success.deactivated') : t('settings.admin.personalities.success.activated'));
        fetchData();
      } catch (error) {
        logger.error('personality_toggle_failed', error instanceof Error ? error : undefined, { component: 'AdminPersonalitiesSection', action: 'toggle', personalityId: personality.id });
        toast.error(t('settings.admin.personalities.errors.toggle'));
      }
    });
  };

  const handleTranslate = (personality: PersonalityResponse) => {
    startTransition(async () => {
      try {
        await translatePersonality(personality.id);
        toast.success(t('settings.admin.personalities.success.translated'));
        fetchData();
      } catch (error) {
        logger.error('personality_translate_failed', error instanceof Error ? error : undefined, { component: 'AdminPersonalitiesSection', action: 'translate', personalityId: personality.id });
        toast.error(error instanceof Error ? error.message : t('settings.admin.personalities.errors.translate'));
      }
    });
  };

  const handleSetDefault = (personality: PersonalityResponse) => {
    if (personality.is_default) return;

    startTransition(async () => {
      try {
        await updatePersonality(personality.id, { is_default: true });
        toast.success(t('settings.admin.personalities.success.set_default'));
        fetchData();
      } catch (error) {
        logger.error('personality_set_default_failed', error instanceof Error ? error : undefined, { component: 'AdminPersonalitiesSection', action: 'setDefault', personalityId: personality.id });
        toast.error(t('settings.admin.personalities.errors.toggle'));
      }
    });
  };

  // Loading state
  if (loading && personalities.length === 0) {
    return (
      <SettingsSection
        value="admin-personalities"
        title={t('settings.admin.personalities.title')}
        description={t('settings.admin.personalities.description')}
        icon={Sparkles}
        collapsible={collapsible}
      >
        <TableSkeleton rows={5} />
      </SettingsSection>
    );
  }

  // Main content
  const content = (
    <>
      <div className="flex items-center justify-between mb-4">
        <Button onClick={openCreateDialog} size="sm" className="gap-2">
          <Plus className="h-4 w-4" />
          {t('settings.admin.personalities.new_personality')}
        </Button>
      </div>

      {/* Personalities Table */}
      {loading ? (
        <TableSkeleton rows={5} />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="min-w-full divide-y divide-border" role="table">
            <thead className="bg-muted/50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider w-12">
                  {t('settings.admin.personalities.table.order')}
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                  {t('settings.admin.personalities.table.personality')}
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                  {t('settings.admin.personalities.table.code')}
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                  {t('settings.admin.personalities.table.translations')}
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                  {t('settings.admin.personalities.table.status')}
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                  {t('settings.admin.personalities.table.actions')}
                </th>
              </tr>
            </thead>
            <tbody className="bg-card divide-y divide-border">
              {personalities.map(personality => {
                const frTranslation = personality.translations.find(t => t.language_code === fallbackLng);
                const translationCount = personality.translations.length;

                return (
                  <tr
                    key={personality.id}
                    className={`transition-colors hover:bg-muted/30 ${isPending ? 'opacity-60' : ''}`}
                  >
                    <td className="px-4 py-4 whitespace-nowrap text-sm text-muted-foreground">
                      <div className="flex items-center gap-1">
                        <GripVertical className="h-4 w-4" />
                        {personality.sort_order}
                      </div>
                    </td>
                    <td className="px-4 py-4 whitespace-nowrap">
                      <div className="flex items-center gap-3">
                        <span className="text-2xl">{personality.emoji}</span>
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-medium">
                              {frTranslation?.title || personality.code}
                            </span>
                            {personality.is_default && (
                              <Star className="h-4 w-4 text-yellow-500 fill-yellow-500" />
                            )}
                          </div>
                          <p className="text-xs text-muted-foreground line-clamp-1 max-w-xs">
                            {frTranslation?.description}
                          </p>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-4 whitespace-nowrap text-sm font-mono text-muted-foreground">
                      {personality.code}
                    </td>
                    <td className="px-4 py-4 whitespace-nowrap">
                      <div className="flex items-center gap-2">
                        <span className="text-sm">{translationCount}/{languages.length}</span>
                        {translationCount < languages.length && (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleTranslate(personality)}
                            disabled={isPending}
                            className="h-7 px-2"
                            title={t('settings.admin.personalities.tooltips.generate_translations')}
                          >
                            <Languages className="h-4 w-4" />
                          </Button>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-4 whitespace-nowrap">
                      <span
                        className={`px-2 inline-flex text-xs leading-5 font-semibold rounded-full ${
                          personality.is_active
                            ? 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200 border border-green-200 dark:border-green-800'
                            : 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200 border border-red-200 dark:border-red-800'
                        }`}
                      >
                        {personality.is_active ? t('settings.admin.personalities.status.active') : t('settings.admin.personalities.status.inactive')}
                      </span>
                    </td>
                    <td className="px-4 py-4 whitespace-nowrap">
                      <div className="flex items-center gap-1">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => openEditDialog(personality)}
                          disabled={isPending}
                          className="h-8 w-8 p-0"
                          title={t('settings.admin.personalities.tooltips.edit')}
                        >
                          <Pencil className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleToggleActive(personality)}
                          disabled={isPending}
                          className="h-8 px-2"
                          title={personality.is_active ? t('settings.admin.personalities.tooltips.deactivate') : t('settings.admin.personalities.tooltips.activate')}
                        >
                          <Switch checked={personality.is_active} className="pointer-events-none" />
                        </Button>
                        {!personality.is_default && (
                          <>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleSetDefault(personality)}
                              disabled={isPending}
                              className="h-8 w-8 p-0"
                              title={t('settings.admin.personalities.tooltips.set_default')}
                            >
                              <Star className="h-4 w-4" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleDelete(personality)}
                              disabled={isPending}
                              className="h-8 w-8 p-0 text-destructive hover:text-destructive"
                              title={t('settings.admin.personalities.tooltips.delete')}
                            >
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Create/Edit Dialog */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>
              {editingPersonality ? t('settings.admin.personalities.dialog.title_edit') : t('settings.admin.personalities.dialog.title_create')}
            </DialogTitle>
            <DialogDescription>
              {editingPersonality
                ? t('settings.admin.personalities.dialog.description_edit')
                : t('settings.admin.personalities.dialog.description_create')}
            </DialogDescription>
          </DialogHeader>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="code">{t('settings.admin.personalities.dialog.code_label')}</Label>
                <Input
                  id="code"
                  value={formData.code}
                  onChange={e => setFormData({ ...formData, code: e.target.value })}
                  placeholder={t('settings.admin.personalities.dialog.code_placeholder')}
                  required
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="emoji">{t('settings.admin.personalities.dialog.emoji_label')}</Label>
                <Input
                  id="emoji"
                  value={formData.emoji}
                  onChange={e => setFormData({ ...formData, emoji: e.target.value })}
                  placeholder={t('settings.admin.personalities.dialog.emoji_placeholder')}
                  required
                  className="text-xl"
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="title">{t('settings.admin.personalities.dialog.title_label')}</Label>
                <Input
                  id="title"
                  value={formData.title}
                  onChange={e => setFormData({ ...formData, title: e.target.value })}
                  placeholder={t('settings.admin.personalities.dialog.title_placeholder')}
                  required
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="sort_order">{t('settings.admin.personalities.dialog.sort_order_label')}</Label>
                <Input
                  id="sort_order"
                  type="number"
                  value={formData.sort_order}
                  onChange={e =>
                    setFormData({ ...formData, sort_order: parseInt(e.target.value) || 0 })
                  }
                  min={0}
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="description">{t('settings.admin.personalities.dialog.description_label')}</Label>
              <Textarea
                id="description"
                value={formData.description}
                onChange={e => setFormData({ ...formData, description: e.target.value })}
                placeholder={t('settings.admin.personalities.dialog.description_placeholder')}
                required
                rows={2}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="prompt_instruction">{t('settings.admin.personalities.dialog.prompt_label')}</Label>
              <Textarea
                id="prompt_instruction"
                value={formData.prompt_instruction}
                onChange={e => setFormData({ ...formData, prompt_instruction: e.target.value })}
                placeholder={t('settings.admin.personalities.dialog.prompt_placeholder')}
                required
                rows={4}
              />
              <p className="text-xs text-muted-foreground">
                {t('settings.admin.personalities.dialog.prompt_hint')}
              </p>
            </div>

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setDialogOpen(false)}>
                {t('settings.admin.personalities.dialog.cancel')}
              </Button>
              <Button type="submit" disabled={isPending}>
                {isPending && <LoadingSpinner size="default" className="mr-2" />}
                {editingPersonality ? t('settings.admin.personalities.dialog.save') : t('settings.admin.personalities.dialog.create')}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );

  return (
    <SettingsSection
      value="admin-personalities"
      title={t('settings.admin.personalities.title')}
      description={t('settings.admin.personalities.description')}
      icon={Sparkles}
      collapsible={collapsible}
    >
      {content}
    </SettingsSection>
  );
}
