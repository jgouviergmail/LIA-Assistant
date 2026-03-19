'use client';

import { useRef, useState } from 'react';
import { Blocks, Download, Languages, Pencil, RotateCcw, Trash2, Upload } from 'lucide-react';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { useTranslation } from '@/i18n/client';
import { SettingsSection } from '@/components/settings/SettingsSection';
import { useSkills, type Skill } from '@/hooks/useSkills';
import { toast } from 'sonner';
import type { Language } from '@/i18n/settings';

interface AdminSkillsSectionProps {
  lng: Language;
}

export function AdminSkillsSection({ lng }: AdminSkillsSectionProps) {
  const { t } = useTranslation(lng);
  const {
    skills: allSkills,
    loading,
    error,
    refetch,
    reloadSkills,
    reloading,
    importAdminSkill,
    deleteAdminSkill,
    adminSystemToggleSkill,
    togglingSystem,
    translateSkillDescription,
    translating,
    updateAdminSkillDescription,
    updatingDescription,
    downloadSkill,
  } = useSkills(true);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const [importing, setImporting] = useState(false);
  const [translatingName, setTranslatingName] = useState<string | null>(null);
  const [deletingName, setDeletingName] = useState<string | null>(null);
  const [downloadingName, setDownloadingName] = useState<string | null>(null);

  // Edit description state
  const [editingSkill, setEditingSkill] = useState<Skill | null>(null);
  const [editDescription, setEditDescription] = useState('');

  const adminSkills = allSkills.filter(s => s.scope === 'admin');

  const handleReload = async () => {
    try {
      const result = await reloadSkills();
      if (result) {
        toast.success(t('settings.skills.reload_success', { count: result.count }));
      }
    } catch {
      toast.error(t('settings.skills.reload_error'));
    }
  };

  const handleToggle = async (skill: Skill) => {
    try {
      const result = await adminSystemToggleSkill(skill.name);
      if (result) {
        toast.success(
          result.admin_enabled
            ? t('settings.skills.enabled_toast', { name: skill.name })
            : t('settings.skills.disabled_toast', { name: skill.name })
        );
      }
    } catch {
      toast.error(t('settings.skills.toggle_error'));
    }
  };

  const handleTranslate = async (skill: Skill) => {
    setTranslatingName(skill.name);
    try {
      const result = await translateSkillDescription(skill.name);
      if (result) {
        toast.success(t('settings.skills.translate_success', { name: skill.name }));
      }
    } catch {
      toast.error(t('settings.skills.translate_error'));
    } finally {
      setTranslatingName(null);
    }
  };

  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setImporting(true);
    try {
      const result = await importAdminSkill(file);
      if (result) {
        toast.success(t('settings.skills.import_success', { name: result.name }));
      }
    } catch (err) {
      const detail = err instanceof Error ? err.message : null;
      toast.error(detail || t('settings.skills.import_error'));
    } finally {
      setImporting(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const handleDelete = async () => {
    if (!deletingName) return;
    try {
      await deleteAdminSkill(deletingName);
      toast.success(t('settings.skills.delete_admin_success'));
    } catch {
      toast.error(t('settings.skills.delete_admin_error'));
    }
    setDeletingName(null);
  };

  const handleDownload = async (skill: Skill) => {
    setDownloadingName(skill.name);
    try {
      await downloadSkill(skill.name, true);
    } catch {
      toast.error(t('settings.skills.download_error'));
    } finally {
      setDownloadingName(null);
    }
  };

  const openEditDescription = (skill: Skill) => {
    setEditingSkill(skill);
    // Prefill with current description in admin's language, fallback to English
    setEditDescription(skill.descriptions?.[lng] ?? skill.description);
  };

  const handleEditDescriptionSubmit = async () => {
    if (!editingSkill) return;
    try {
      const result = await updateAdminSkillDescription(editingSkill.name, editDescription, lng);
      if (result) {
        toast.success(t('settings.skills.edit_description_success', { name: editingSkill.name }));
      }
    } catch {
      toast.error(t('settings.skills.edit_description_error'));
    } finally {
      setEditingSkill(null);
    }
  };

  return (
    <SettingsSection
      value="admin-skills"
      title={t('settings.skills.admin_title')}
      description={t('settings.skills.admin_description')}
      icon={Blocks}
    >
      {/* Header with import + reload buttons */}
      <div className="flex items-center justify-between mb-4">
        <p className="text-sm text-muted-foreground">
          {adminSkills.length > 0
            ? t('settings.skills.admin_count', { count: adminSkills.length })
            : ''}
        </p>
        <div className="flex items-center gap-2">
          <input
            ref={fileInputRef}
            type="file"
            accept=".md,.zip"
            className="hidden"
            onChange={handleImport}
            aria-label={t('settings.skills.import_button')}
          />
          <Button
            size="sm"
            onClick={() => fileInputRef.current?.click()}
            disabled={importing || loading}
          >
            {importing ? (
              <LoadingSpinner className="mr-2 h-4 w-4" />
            ) : (
              <Upload className="h-4 w-4 mr-1" />
            )}
            {t('settings.skills.import_button')}
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={handleReload}
            disabled={reloading || loading}
          >
            {reloading ? (
              <LoadingSpinner className="mr-2 h-4 w-4" />
            ) : (
              <RotateCcw className="h-4 w-4 mr-1" />
            )}
            {t('settings.skills.reload_button')}
          </Button>
        </div>
      </div>

      {/* Loading */}
      {loading && (
        <div className="flex justify-center py-8">
          <LoadingSpinner className="h-6 w-6" />
        </div>
      )}

      {/* Error */}
      {!loading && error && (
        <div className="flex items-center gap-3 py-4">
          <p className="text-sm text-muted-foreground">{t('settings.skills.load_error')}</p>
          <button
            type="button"
            onClick={() => refetch()}
            className="text-sm text-primary hover:underline"
          >
            {t('common.retry')}
          </button>
        </div>
      )}

      {/* Empty state */}
      {!loading && !error && adminSkills.length === 0 && (
        <div className="text-center py-8 text-muted-foreground">
          <Blocks className="h-12 w-12 mx-auto mb-3 opacity-30" />
          <p className="text-sm">{t('settings.skills.empty')}</p>
        </div>
      )}

      {/* Skill cards */}
      {!loading && !error && adminSkills.length > 0 && (
        <div className="space-y-3">
          {adminSkills.map(skill => (
            <div key={skill.name} className="rounded-lg border bg-card p-4 space-y-2 group">
              <div className="flex items-center justify-between gap-2">
                {/* Name + badges */}
                <div className="flex items-center gap-2 min-w-0 flex-1 flex-wrap">
                  <span className="font-medium">{skill.name}</span>
                  <Badge variant="default" className="text-xs">
                    {t('settings.skills.scope_admin')}
                  </Badge>
                  {skill.category && (
                    <Badge variant="secondary" className="text-xs">
                      {skill.category}
                    </Badge>
                  )}
                  {skill.always_loaded && (
                    <Badge variant="secondary" className="text-xs">
                      {t('settings.skills.always_loaded')}
                    </Badge>
                  )}
                  {skill.has_scripts && (
                    <Badge variant="outline" className="text-xs">
                      {t('settings.skills.has_scripts')}
                    </Badge>
                  )}
                  {skill.has_plan_template && (
                    <Badge variant="outline" className="text-xs">
                      {t('settings.skills.has_plan_template')}
                    </Badge>
                  )}
                </div>

                {/* Action buttons */}
                <div className="flex items-center gap-1 shrink-0">
                  {/* Edit description */}
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => openEditDescription(skill)}
                    disabled={updatingDescription}
                    title={t('settings.skills.edit_description_button')}
                    className="h-8 w-8 p-0 opacity-0 group-hover:opacity-100 transition-opacity"
                  >
                    <Pencil className="h-3.5 w-3.5" />
                  </Button>

                  {/* Translate */}
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => handleTranslate(skill)}
                    disabled={translating || translatingName === skill.name}
                    title={t('settings.skills.translate_button')}
                    aria-label={t('settings.skills.translate_button_label', { name: skill.name })}
                    className="h-8 w-8 p-0 opacity-0 group-hover:opacity-100 transition-opacity"
                  >
                    {translatingName === skill.name ? (
                      <LoadingSpinner className="h-3.5 w-3.5" />
                    ) : (
                      <Languages className="h-3.5 w-3.5" />
                    )}
                  </Button>

                  {/* Download */}
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => handleDownload(skill)}
                    disabled={downloadingName === skill.name}
                    title={t('settings.skills.download_button')}
                    className="h-8 w-8 p-0 opacity-0 group-hover:opacity-100 transition-opacity"
                  >
                    {downloadingName === skill.name ? (
                      <LoadingSpinner className="h-3.5 w-3.5" />
                    ) : (
                      <Download className="h-3.5 w-3.5" />
                    )}
                  </Button>

                  {/* Delete */}
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => setDeletingName(skill.name)}
                    title={t('settings.skills.delete_admin_button')}
                    className="h-8 w-8 p-0 opacity-0 group-hover:opacity-100 transition-opacity text-destructive hover:text-destructive"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>

                  {/* System-level toggle on/off */}
                  <Switch
                    checked={skill.admin_enabled ?? true}
                    onCheckedChange={() => handleToggle(skill)}
                    disabled={togglingSystem}
                    aria-label={t('settings.skills.toggle_skill', { name: skill.name })}
                  />
                </div>
              </div>

              {/* Description */}
              <p className="text-sm text-muted-foreground line-clamp-2">
                {skill.descriptions?.[lng] ??
                  t(`settings.skills.desc_${skill.name}`, { defaultValue: skill.description })}
              </p>
            </div>
          ))}
        </div>
      )}

      {/* Delete admin skill confirmation */}
      <AlertDialog
        open={deletingName !== null}
        onOpenChange={open => !open && setDeletingName(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('settings.skills.delete_admin_confirm_title')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('settings.skills.delete_admin_confirm_description', { name: deletingName ?? '' })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {t('common.delete')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Edit description dialog */}
      <Dialog open={editingSkill !== null} onOpenChange={open => !open && setEditingSkill(null)}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>
              {t('settings.skills.edit_description_title')} — {editingSkill?.name}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <Label htmlFor="skill-desc-edit" className="text-sm text-muted-foreground">
              {t('settings.skills.edit_description_hint')}
            </Label>
            <Textarea
              id="skill-desc-edit"
              value={editDescription}
              onChange={e => setEditDescription(e.target.value)}
              rows={5}
              placeholder={t('settings.skills.edit_description_label')}
              className="resize-none text-sm"
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditingSkill(null)}>
              {t('common.cancel')}
            </Button>
            <Button
              onClick={handleEditDescriptionSubmit}
              disabled={updatingDescription || editDescription.trim().length < 10}
            >
              {updatingDescription ? (
                <LoadingSpinner className="mr-2 h-4 w-4" />
              ) : (
                <Languages className="h-4 w-4 mr-1" />
              )}
              {updatingDescription
                ? t('settings.skills.edit_description_saving')
                : t('settings.skills.edit_description_submit')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </SettingsSection>
  );
}
