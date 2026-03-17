'use client';

import { useRef, useState } from 'react';
import { Blocks, BookOpen, Download, Upload, Trash2, ShieldCheck } from 'lucide-react';
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
import { useTranslation } from '@/i18n/client';
import { SettingsSection } from '@/components/settings/SettingsSection';
import { SkillGuideModal } from '@/components/settings/SkillGuideModal';
import { useSkills, type Skill } from '@/hooks/useSkills';
import { toast } from 'sonner';
import type { Language } from '@/i18n/settings';

interface SkillsSettingsProps {
  lng: Language;
}

export function SkillsSettings({ lng }: SkillsSettingsProps) {
  const { t } = useTranslation(lng);
  const { skills, loading, error, refetch, importSkill, deleteSkill, deleting, toggleSkill, toggling, downloadSkill } =
    useSkills();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [importing, setImporting] = useState(false);
  const [deletingName, setDeletingName] = useState<string | null>(null);
  const [downloadingName, setDownloadingName] = useState<string | null>(null);
  const [showGuide, setShowGuide] = useState(false);

  const adminSkills = skills.filter((s) => s.scope === 'admin');
  const userSkills = skills.filter((s) => s.scope === 'user');

  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setImporting(true);
    try {
      const result = await importSkill(file);
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

  const handleDownload = async (skill: Skill) => {
    setDownloadingName(skill.name);
    try {
      await downloadSkill(skill.name, skill.scope === 'admin');
    } catch {
      toast.error(t('settings.skills.download_error'));
    } finally {
      setDownloadingName(null);
    }
  };

  const handleDelete = async () => {
    if (!deletingName) return;
    try {
      await deleteSkill(deletingName);
      toast.success(t('settings.skills.delete_success'));
    } catch {
      toast.error(t('settings.skills.delete_error'));
    }
    setDeletingName(null);
  };

  const handleToggle = async (skill: Skill) => {
    try {
      const result = await toggleSkill(skill.name);
      if (result) {
        toast.success(
          result.enabled_for_user
            ? t('settings.skills.enabled_toast', { name: skill.name })
            : t('settings.skills.disabled_toast', { name: skill.name })
        );
      }
    } catch {
      toast.error(t('settings.skills.toggle_error'));
    }
  };

  return (
    <SettingsSection
      value="skills"
      title={t('settings.skills.title')}
      description={t('settings.skills.description')}
      icon={Blocks}
    >
      {/* Loading */}
      {loading && (
        <div className="flex justify-center py-8">
          <LoadingSpinner className="h-6 w-6" />
        </div>
      )}

      {/* Error */}
      {!loading && error && (
        <div className="flex items-center gap-3 py-4">
          <p className="text-sm text-muted-foreground">
            {t('settings.skills.load_error')}
          </p>
          <button
            type="button"
            onClick={() => refetch()}
            className="text-sm text-primary hover:underline"
          >
            {t('common.retry')}
          </button>
        </div>
      )}

      {!loading && !error && (
        <div className="space-y-6">
          {/* Admin skills section */}
          {adminSkills.length > 0 && (
            <div>
              <div className="flex items-center gap-2 mb-3">
                <ShieldCheck className="h-4 w-4 text-muted-foreground" />
                <h4 className="text-sm font-medium text-muted-foreground">
                  {t('settings.skills.admin_section_title')}
                </h4>
                <span className="text-xs text-muted-foreground">
                  ({adminSkills.length})
                </span>
              </div>
              <div className="space-y-2">
                {adminSkills.map((skill) => (
                  <SkillCard
                    key={skill.name}
                    skill={skill}
                    t={t}
                    lng={lng}
                    onToggle={() => handleToggle(skill)}
                    onDownload={() => handleDownload(skill)}
                    downloading={downloadingName === skill.name}
                    toggling={toggling}
                  />
                ))}
              </div>
            </div>
          )}

          {/* Separator */}
          {adminSkills.length > 0 && <div className="border-t" />}

          {/* User skills section */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <h4 className="text-sm font-medium text-muted-foreground">
                  {t('settings.skills.user_section_title')}
                </h4>
                {userSkills.length > 0 && (
                  <span className="text-xs text-muted-foreground">
                    ({userSkills.length})
                  </span>
                )}
                <button
                  type="button"
                  onClick={() => setShowGuide(true)}
                  className="inline-flex items-center gap-1 text-xs text-muted-foreground/60 hover:text-primary transition-colors border border-border/50 rounded px-1.5 py-0.5 hover:border-primary/40"
                  title={t('settings.skills.guide_toggle')}
                >
                  <BookOpen className="h-3 w-3" />
                  {t('settings.skills.guide_button')}
                </button>
              </div>
              <div>
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
                  disabled={importing}
                >
                  {importing ? (
                    <LoadingSpinner className="mr-2 h-4 w-4" />
                  ) : (
                    <Upload className="h-4 w-4 mr-1" />
                  )}
                  {t('settings.skills.import_button')}
                </Button>
              </div>
            </div>

            {/* Guide modal */}
            <SkillGuideModal lng={lng} open={showGuide} onOpenChange={setShowGuide} />

            {userSkills.length === 0 && (
              <div className="text-center py-6 text-muted-foreground">
                <p className="text-sm">{t('settings.skills.empty')}</p>
              </div>
            )}

            {userSkills.length > 0 && (
              <div className="space-y-2">
                {userSkills.map((skill) => (
                  <SkillCard
                    key={skill.name}
                    skill={skill}
                    t={t}
                    lng={lng}
                    onToggle={() => handleToggle(skill)}
                    onDownload={() => handleDownload(skill)}
                    downloading={downloadingName === skill.name}
                    onDelete={() => setDeletingName(skill.name)}
                    toggling={toggling}
                  />
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Delete confirmation */}
      <AlertDialog
        open={deletingName !== null}
        onOpenChange={(open) => !open && setDeletingName(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('settings.skills.delete_confirm_title')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('settings.skills.delete_confirm_description', { name: deletingName ?? '' })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              disabled={deleting}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {t('common.delete')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </SettingsSection>
  );
}

/** Unified skill card with toggle switch — used for both admin and user skills. */
function SkillCard({
  skill,
  t,
  lng,
  onToggle,
  onDownload,
  downloading,
  onDelete,
  toggling,
}: {
  skill: Skill;
  t: (key: string, options?: Record<string, string>) => string;
  lng: string;
  onToggle: () => void;
  onDownload: () => void;
  downloading: boolean;
  onDelete?: () => void;
  toggling: boolean;
}) {
  const isAdmin = skill.scope === 'admin';
  return (
    <div
      className={`rounded-lg border p-3 space-y-1 group ${isAdmin ? 'bg-card/50' : 'bg-card'}`}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0 flex-1 flex-wrap">
          <span className="font-medium text-sm truncate">{skill.name}</span>
          {skill.category && (
            <Badge variant="secondary" className="text-xs">
              {skill.category}
            </Badge>
          )}
          <SkillBadges skill={skill} t={t} />
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <Button
            variant="ghost"
            size="icon"
            onClick={onDownload}
            disabled={downloading}
            className="opacity-0 group-hover:opacity-100 h-7 w-7"
            aria-label={t('settings.skills.download_button')}
          >
            {downloading ? (
              <LoadingSpinner className="h-3.5 w-3.5" />
            ) : (
              <Download className="h-3.5 w-3.5" />
            )}
          </Button>
          {onDelete && (
            <Button
              variant="ghost"
              size="icon"
              onClick={onDelete}
              className="opacity-0 group-hover:opacity-100 h-7 w-7"
              aria-label={t('settings.skills.delete_button')}
            >
              <Trash2 className="h-3.5 w-3.5 text-destructive" />
            </Button>
          )}
          <Switch
            checked={skill.enabled_for_user}
            onCheckedChange={onToggle}
            disabled={toggling}
            aria-label={t('settings.skills.toggle_skill', { name: skill.name })}
          />
        </div>
      </div>
      <p className="text-xs text-muted-foreground line-clamp-2">
        {skill.descriptions?.[lng] ??
          (isAdmin
            ? t(`settings.skills.desc_${skill.name}`, { defaultValue: skill.description })
            : skill.description)}
      </p>
    </div>
  );
}

function SkillBadges({
  skill,
  t,
}: {
  skill: Skill;
  t: (key: string) => string;
}) {
  return (
    <>
      {skill.always_loaded && (
        <Badge variant="secondary" className="shrink-0 text-xs">
          {t('settings.skills.always_loaded')}
        </Badge>
      )}
      {skill.has_scripts && (
        <Badge variant="outline" className="shrink-0 text-xs">
          {t('settings.skills.has_scripts')}
        </Badge>
      )}
      {skill.has_plan_template && (
        <Badge variant="outline" className="shrink-0 text-xs">
          {t('settings.skills.has_plan_template')}
        </Badge>
      )}
    </>
  );
}
