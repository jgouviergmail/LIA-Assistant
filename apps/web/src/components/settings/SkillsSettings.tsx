'use client';

/**
 * SkillsSettings — thin section shell for the skills gallery (UXR Lot 10).
 *
 * Owns the data hook, the collapse state of the two scope sections, the
 * selected-skill modal, the URL-import dialog and the delete confirmation;
 * rendering lives in SkillGallery / SkillDetailModal / ImportFromUrlDialog
 * (CC budgets — keep this file orchestration-only).
 */

import { useRef, useState } from 'react';
import { Blocks, BookOpen, ChevronDown, Link2, ShieldCheck, Upload } from 'lucide-react';
import { LoadingSpinner } from '@/components/ui/loading-spinner';

import { Button } from '@/components/ui/button';
import { EmptyState } from '@/components/ui/empty-state';
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
import { SkillGallery } from '@/components/settings/SkillGallery';
import { SkillDetailModal } from '@/components/settings/SkillDetailModal';
import { ImportFromUrlDialog } from '@/components/settings/ImportFromUrlDialog';
import { useSkills, type Skill } from '@/hooks/useSkills';
import { toast } from 'sonner';
import type { Language } from '@/i18n/settings';

interface SkillsSettingsProps {
  lng: Language;
}

type Translator = (key: string, options?: Record<string, string>) => string;
type SkillsHook = ReturnType<typeof useSkills>;

/** File-import handler factory (CC discipline: one top-level unit per flow). */
function makeImportHandler(deps: {
  t: Translator;
  hook: SkillsHook;
  fileInputRef: React.RefObject<HTMLInputElement | null>;
  setImporting: (value: boolean) => void;
}) {
  const { t, hook, fileInputRef, setImporting } = deps;
  return async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setImporting(true);
    try {
      const result = await hook.importSkill(file);
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
}

/** Zip-download handler factory. */
function makeDownloadHandler(deps: {
  t: Translator;
  hook: SkillsHook;
  setDownloadingName: (value: string | null) => void;
}) {
  const { t, hook, setDownloadingName } = deps;
  return async (skill: Skill) => {
    setDownloadingName(skill.name);
    try {
      await hook.downloadSkill(skill.name, skill.scope === 'admin');
    } catch {
      toast.error(t('settings.skills.download_error'));
    } finally {
      setDownloadingName(null);
    }
  };
}

/** Confirmed-delete handler factory. */
function makeDeleteHandler(deps: {
  t: Translator;
  hook: SkillsHook;
  deletingName: string | null;
  setDeletingName: (value: string | null) => void;
  onDeleted: () => void;
}) {
  const { t, hook, deletingName, setDeletingName, onDeleted } = deps;
  return async () => {
    if (!deletingName) return;
    try {
      await hook.deleteSkill(deletingName);
      toast.success(t('settings.skills.delete_success'));
      onDeleted();
    } catch {
      toast.error(t('settings.skills.delete_error'));
    }
    setDeletingName(null);
  };
}

/** Per-user toggle handler factory. */
function makeToggleHandler(deps: { t: Translator; hook: SkillsHook }) {
  const { t, hook } = deps;
  return async (skill: Skill) => {
    try {
      const result = await hook.toggleSkill(skill.name);
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
}

/** Toast-wrapped skill actions — composition only (branches live above). */
function useSkillsActions(args: {
  t: Translator;
  hook: SkillsHook;
  fileInputRef: React.RefObject<HTMLInputElement | null>;
  onDeleted: () => void;
}) {
  const { t, hook, fileInputRef, onDeleted } = args;
  const [importing, setImporting] = useState(false);
  const [deletingName, setDeletingName] = useState<string | null>(null);
  const [downloadingName, setDownloadingName] = useState<string | null>(null);

  return {
    importing,
    deletingName,
    setDeletingName,
    downloadingName,
    handleImport: makeImportHandler({ t, hook, fileInputRef, setImporting }),
    handleDownload: makeDownloadHandler({ t, hook, setDownloadingName }),
    handleDelete: makeDeleteHandler({ t, hook, deletingName, setDeletingName, onDeleted }),
    handleToggle: makeToggleHandler({ t, hook }),
  };
}

/** Collapsible admin-scope gallery section. */
function AdminScopeSection(props: {
  skills: Skill[];
  lng: string;
  t: Translator;
  open: boolean;
  onToggleOpen: () => void;
  onOpenSkill: (skill: Skill) => void;
  onToggle: (skill: Skill) => void;
  toggling: boolean;
}) {
  const { skills, lng, t, open, onToggleOpen, onOpenSkill, onToggle, toggling } = props;
  return (
    <div>
      <button
        type="button"
        onClick={onToggleOpen}
        aria-expanded={open}
        className="flex items-center gap-2 mb-3 w-full text-left hover:opacity-80 transition-opacity"
      >
        <ChevronDown
          className={`h-4 w-4 text-muted-foreground transition-transform duration-200 ${
            open ? '' : '-rotate-90'
          }`}
        />
        <ShieldCheck className="h-4 w-4 text-muted-foreground" />
        <h4 className="text-sm font-medium text-muted-foreground">
          {t('settings.skills.admin_section_title')}
        </h4>
        <span className="text-xs text-muted-foreground">({skills.length})</span>
      </button>
      {open && (
        <SkillGallery
          skills={skills}
          lng={lng}
          t={t}
          onOpen={onOpenSkill}
          onToggle={onToggle}
          toggling={toggling}
        />
      )}
    </div>
  );
}

/** Collapsible user-scope gallery section with the import actions. */
function UserScopeSection(props: {
  skills: Skill[];
  lng: string;
  t: Translator;
  open: boolean;
  onToggleOpen: () => void;
  onOpenSkill: (skill: Skill) => void;
  onToggle: (skill: Skill) => void;
  toggling: boolean;
  importing: boolean;
  fileInputRef: React.RefObject<HTMLInputElement | null>;
  onImportFile: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onShowGuide: () => void;
  onShowUrlImport: () => void;
}) {
  const { skills, lng, t, open, onToggleOpen, onOpenSkill, onToggle, toggling } = props;
  const { importing, fileInputRef, onImportFile, onShowGuide, onShowUrlImport } = props;
  return (
    <div>
      {/* No bottom margin here: it stacked UNDER the button row on top of the
          card's own `pb-4/sm:pb-6`, so the band below the separator was ~48 px
          against 12 px above and the buttons hugged the line. The spacing that
          balances them now lives on the row and on the list below it. */}
      <div className="flex flex-col gap-3">
        <button
          type="button"
          onClick={onToggleOpen}
          aria-expanded={open}
          className="flex items-center gap-2 flex-wrap text-left hover:opacity-80 transition-opacity"
        >
          <ChevronDown
            className={`h-4 w-4 text-muted-foreground transition-transform duration-200 ${
              open ? '' : '-rotate-90'
            }`}
          />
          <h4 className="text-sm font-medium text-muted-foreground">
            {t('settings.skills.user_section_title')}
          </h4>
          {skills.length > 0 && (
            <span className="text-xs text-muted-foreground">({skills.length})</span>
          )}
        </button>
        {/* Import actions on their own row, visually detached by a separator
            line (owner request 2026-07-30). `pt-4 sm:pt-6` MIRRORS the card's
            own `pb-4 sm:pb-6`: what sits under these buttons is the card's
            bottom padding, so matching it at the top is what actually centres
            them between the line and the edge, at both breakpoints. */}
        {/* Right-aligned (owner arbitration 2026-08-05), like the section
            toolbars everywhere else: count/summary left, actions right. */}
        <div className="flex items-center justify-end gap-2 flex-wrap border-t pt-4 sm:pt-6">
          <Button
            size="sm"
            onClick={onShowGuide}
            className="gap-1.5"
            title={t('settings.skills.guide_toggle')}
          >
            <BookOpen className="h-3.5 w-3.5" />
            {t('settings.skills.guide_button')}
          </Button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".md,.zip"
            className="hidden"
            onChange={onImportFile}
            aria-label={t('settings.skills.import_button')}
          />
          <Button size="sm" onClick={onShowUrlImport}>
            <Link2 className="h-3.5 w-3.5" />
            {t('settings.skills.url_import.button')}
          </Button>
          <Button size="sm" onClick={() => fileInputRef.current?.click()} disabled={importing}>
            {importing ? (
              <LoadingSpinner className="mr-2 h-4 w-4" />
            ) : (
              <Upload className="h-4 w-4 mr-1" />
            )}
            {t('settings.skills.import_button')}
          </Button>
        </div>
      </div>

      {/* When the list is EXPANDED it becomes what sits under the buttons, so
          it carries the same gap the card's padding provides when collapsed —
          the row keeps one balanced band in both states. */}
      {open && skills.length === 0 && (
        <EmptyState className="mt-4 sm:mt-6" description={t('settings.skills.empty')} />
      )}
      {open && skills.length > 0 && (
        <div className="mt-4 sm:mt-6">
          <SkillGallery
            skills={skills}
            lng={lng}
            t={t}
            onOpen={onOpenSkill}
            onToggle={onToggle}
            toggling={toggling}
          />
        </div>
      )}
    </div>
  );
}

export function SkillsSettings({ lng }: SkillsSettingsProps) {
  const { t } = useTranslation(lng);
  const hook = useSkills();
  const { skills, loading, error, refetch, importFromUrl, importingFromUrl, deleting, toggling } =
    hook;
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [showGuide, setShowGuide] = useState(false);
  const [showUrlImport, setShowUrlImport] = useState(false);
  const [selected, setSelected] = useState<Skill | null>(null);
  // Collapse state per scope section — compact panel at first glance.
  const [adminOpen, setAdminOpen] = useState(false);
  const [userOpen, setUserOpen] = useState(false);

  const {
    importing,
    deletingName,
    setDeletingName,
    downloadingName,
    handleImport,
    handleDownload,
    handleDelete,
    handleToggle,
  } = useSkillsActions({ t, hook, fileInputRef, onDeleted: () => setSelected(null) });

  const adminSkills = skills.filter(s => s.scope === 'admin');
  const userSkills = skills.filter(s => s.scope === 'user');
  // The modal mirrors live hook data (a toggle updates the open sheet).
  const selectedLive = selected ? (skills.find(s => s.name === selected.name) ?? null) : null;

  return (
    <SettingsSection
      value="skills"
      title={t('settings.skills.title')}
      description={t('settings.skills.description')}
      icon={Blocks}
    >
      {loading && (
        <div className="flex justify-center py-8">
          <LoadingSpinner className="h-6 w-6" />
        </div>
      )}

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

      {!loading && !error && (
        <div className="space-y-6">
          {adminSkills.length > 0 && (
            <>
              <AdminScopeSection
                skills={adminSkills}
                lng={lng}
                t={t}
                open={adminOpen}
                onToggleOpen={() => setAdminOpen(v => !v)}
                onOpenSkill={setSelected}
                onToggle={handleToggle}
                toggling={toggling}
              />
              <div className="border-t" />
            </>
          )}
          <UserScopeSection
            skills={userSkills}
            lng={lng}
            t={t}
            open={userOpen}
            onToggleOpen={() => setUserOpen(v => !v)}
            onOpenSkill={setSelected}
            onToggle={handleToggle}
            toggling={toggling}
            importing={importing}
            fileInputRef={fileInputRef}
            onImportFile={handleImport}
            onShowGuide={() => setShowGuide(true)}
            onShowUrlImport={() => setShowUrlImport(true)}
          />
        </div>
      )}

      <SkillGuideModal lng={lng} open={showGuide} onOpenChange={setShowGuide} />
      <ImportFromUrlDialog
        open={showUrlImport}
        t={t}
        onOpenChange={setShowUrlImport}
        onImport={importFromUrl}
        importing={importingFromUrl}
      />

      <SkillDetailModal
        skill={selectedLive}
        lng={lng}
        t={t}
        onOpenChange={open => !open && setSelected(null)}
        onToggle={handleToggle}
        onDownload={handleDownload}
        onDelete={skill => setDeletingName(skill.name)}
        downloading={downloadingName === selectedLive?.name}
        toggling={toggling}
      />

      <AlertDialog
        open={deletingName !== null}
        onOpenChange={open => !open && setDeletingName(null)}
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
            <AlertDialogAction onClick={handleDelete} disabled={deleting} variant="destructive">
              {t('common.delete')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </SettingsSection>
  );
}
