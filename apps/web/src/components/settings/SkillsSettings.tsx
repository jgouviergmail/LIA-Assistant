'use client';

/**
 * SkillsSettings — thin section shell for the skills gallery (UXR Lot 10).
 *
 * Owns the data hook, the section toolbar, the two scope folds (`Disclosure`),
 * the selected-skill modal, the URL-import dialog, the skill library (ADR-327) and
 * the delete confirmation; rendering lives in SkillGallery / SkillDetailModal /
 * ImportFromUrlDialog / SkillLibraryDialog (CC budgets — keep this file
 * orchestration-only).
 */

import { useMemo, useRef, useState } from 'react';
import {
  Blocks,
  BookOpen,
  Library,
  Link2,
  ShieldCheck,
  Upload,
  UserRound,
  type LucideIcon,
} from 'lucide-react';
import { LoadingSpinner } from '@/components/ui/loading-spinner';

import { Disclosure } from '@/components/ui/disclosure';
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
import { SectionToolbar, type ToolbarAction } from '@/components/settings/SectionToolbar';
import { SettingsSection } from '@/components/settings/SettingsSection';
import { SkillGuideModal } from '@/components/settings/SkillGuideModal';
import { SkillGallery } from '@/components/settings/SkillGallery';
import { SkillDetailModal } from '@/components/settings/SkillDetailModal';
import { ImportFromUrlDialog } from '@/components/settings/ImportFromUrlDialog';
import { SkillLibraryDialog } from '@/components/settings/skill-library/SkillLibraryDialog';
import { useAppConfig } from '@/hooks/useAppConfig';
import { useSkills, type Skill } from '@/hooks/useSkills';
import { skillLibraryAvailable } from '@/lib/skill-library/availability';
import type { LibraryTab } from '@/lib/skill-library/dialog-state';
import { usePlugins } from '@/hooks/usePlugins';
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

/**
 * The section's actions: import a file (primary), the library, a URL, the guide.
 *
 * They sit ABOVE the two folds rather than inside the user one: a `Disclosure`
 * unmounts its content while folded, and importing is what the reader does
 * when the list is still closed (or empty). `SectionToolbar` keeps the primary
 * labelled at every size and folds the rest into « ⋯ » on a phone.
 */
function SkillsToolbar(props: {
  t: Translator;
  importing: boolean;
  fileInputRef: React.RefObject<HTMLInputElement | null>;
  onImportFile: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onShowGuide: () => void;
  onShowUrlImport: () => void;
  /** Opens the skill library — absent when this instance does not offer it. */
  onShowLibrary?: () => void;
}) {
  const { t, importing, fileInputRef, onImportFile, onShowGuide, onShowUrlImport } = props;
  const { onShowLibrary } = props;
  const secondary: ToolbarAction[] = [
    ...(onShowLibrary
      ? [
          {
            key: 'library',
            label: t('settings.skills.library.button'),
            icon: Library,
            onSelect: onShowLibrary,
          },
        ]
      : []),
    {
      key: 'url',
      label: t('settings.skills.url_import.button'),
      icon: Link2,
      onSelect: onShowUrlImport,
    },
    {
      key: 'guide',
      label: t('settings.skills.guide_button'),
      icon: BookOpen,
      onSelect: onShowGuide,
    },
  ];
  return (
    <>
      <input
        ref={fileInputRef}
        type="file"
        accept=".md,.zip"
        className="hidden"
        onChange={onImportFile}
        aria-label={t('settings.skills.import_button')}
      />
      <SectionToolbar
        primary={{
          key: 'import',
          label: t('settings.skills.import_button'),
          icon: Upload,
          onSelect: () => fileInputRef.current?.click(),
          loading: importing,
        }}
        secondary={secondary}
        menuLabel={t('common.more_actions')}
      />
    </>
  );
}

/**
 * One scope of the gallery (admin or the person's own), folded by default.
 *
 * The standard `Disclosure` of every settings panel: theme-coloured icon, the
 * EXACT count in the summary, closed on arrival — the panel stays an index.
 */
function ScopeDisclosure(props: {
  icon: LucideIcon;
  title: string;
  skills: Skill[];
  lng: string;
  t: Translator;
  onOpenSkill: (skill: Skill) => void;
  onToggle: (skill: Skill) => void;
  toggling: boolean;
}) {
  const { icon, title, skills, lng, t, onOpenSkill, onToggle, toggling } = props;
  return (
    <Disclosure icon={icon} title={title} badge={skills.length}>
      {skills.length === 0 ? (
        <EmptyState description={t('settings.skills.empty')} />
      ) : (
        <SkillGallery
          skills={skills}
          lng={lng}
          t={t}
          onOpen={onOpenSkill}
          onToggle={onToggle}
          toggling={toggling}
        />
      )}
    </Disclosure>
  );
}

export function SkillsSettings({ lng }: SkillsSettingsProps) {
  const { t } = useTranslation(lng);
  const hook = useSkills();
  const { skills, loading, error, refetch, importFromUrl, importingFromUrl, deleting, toggling } =
    hook;
  // ADR-225 arbitrage F: skills installed by a plugin leave through the
  // plugin uninstall — the delete guard below needs to know which ones.
  const { plugins } = usePlugins();
  const pluginOwnedSkills = useMemo(
    () => new Set(plugins.flatMap(plugin => plugin.skill_names)),
    [plugins]
  );
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [showGuide, setShowGuide] = useState(false);
  const [showUrlImport, setShowUrlImport] = useState(false);
  // The skill library (ADR-327): open on a tab, or closed.
  const { config } = useAppConfig();
  const libraryOffered = skillLibraryAvailable(config);
  const [libraryTab, setLibraryTab] = useState<LibraryTab | null>(null);
  const [selected, setSelected] = useState<Skill | null>(null);

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
        <div className="space-y-3">
          <SkillsToolbar
            t={t}
            importing={importing}
            fileInputRef={fileInputRef}
            onImportFile={handleImport}
            onShowGuide={() => setShowGuide(true)}
            onShowUrlImport={() => setShowUrlImport(true)}
            onShowLibrary={libraryOffered ? () => setLibraryTab('search') : undefined}
          />
          {adminSkills.length > 0 && (
            <ScopeDisclosure
              icon={ShieldCheck}
              title={t('settings.skills.admin_section_title')}
              skills={adminSkills}
              lng={lng}
              t={t}
              onOpenSkill={setSelected}
              onToggle={handleToggle}
              toggling={toggling}
            />
          )}
          <ScopeDisclosure
            icon={UserRound}
            title={t('settings.skills.user_section_title')}
            skills={userSkills}
            lng={lng}
            t={t}
            onOpenSkill={setSelected}
            onToggle={handleToggle}
            toggling={toggling}
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
      {libraryTab !== null && (
        <SkillLibraryDialog
          lng={lng}
          initialTab={libraryTab}
          onOpenChange={open => !open && setLibraryTab(null)}
          onChanged={() => void refetch()}
        />
      )}

      <SkillDetailModal
        skill={selectedLive}
        lng={lng}
        t={t}
        onOpenChange={open => !open && setSelected(null)}
        onToggle={handleToggle}
        onDownload={handleDownload}
        onDelete={skill => {
          // Guard, not a disabled attribute: explains where to go and never
          // drops keyboard focus (ADR-225 arbitrage F).
          if (pluginOwnedSkills.has(skill.name)) {
            toast.info(t('settings.plugins.component_locked', { name: skill.name }));
            return;
          }
          setDeletingName(skill.name);
        }}
        downloading={downloadingName === selectedLive?.name}
        toggling={toggling}
        onOpenLibrary={
          libraryOffered
            ? () => {
                setSelected(null);
                setLibraryTab('installed');
              }
            : undefined
        }
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
