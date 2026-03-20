'use client';

import { useState, useEffect } from 'react';
import {
  BookOpen,
  Trash2,
  Plus,
  Pencil,
  Download,
  AlertTriangle,
  Settings2,
} from 'lucide-react';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion';
import { useTranslation } from '@/i18n/client';
import { type Language } from '@/i18n/settings';
import { SettingsSection } from '@/components/settings/SettingsSection';
import {
  useJournals,
  type JournalEntry,
  type JournalEntryCreate,
  type JournalEntryUpdate,
  type JournalTheme,
  type JournalEntryMood,
} from '@/hooks/useJournals';
import { toast } from 'sonner';

/** Mood emoji mapping */
const MOOD_EMOJI: Record<string, string> = {
  reflective: '\u{1F60C}',
  curious: '\u{1F50D}',
  satisfied: '\u2705',
  concerned: '\u26A0\uFE0F',
  inspired: '\u{1F4A1}',
};

/** Source emoji mapping */
const SOURCE_EMOJI: Record<string, string> = {
  conversation: '\u{1F4AC}',
  consolidation: '\u{1F504}',
  manual: '\u270F\uFE0F',
};

/** Theme display info */
const THEME_INFO: Record<JournalTheme, { icon: string; color: string }> = {
  self_reflection: { icon: '\u{1F6AA}', color: 'blue' },
  user_observations: { icon: '\u{1F441}\uFE0F', color: 'green' },
  ideas_analyses: { icon: '\u{1F4A1}', color: 'yellow' },
  learnings: { icon: '\u{1F4DA}', color: 'purple' },
};

interface JournalsSettingsProps {
  lng: Language;
}

export function JournalsSettings({ lng }: JournalsSettingsProps) {
  const { t } = useTranslation(lng, 'translation');

  const {
    entries,
    settings: journalSettings,
    isLoading,
    createEntry,
    updateEntry,
    deleteEntry,
    deleteAllEntries,
    updateSettings,
    isCreating,
    isUpdating,
    isUpdatingSettings,
  } = useJournals();

  // Controlled numeric inputs — initialized to 0, then synced with server settings
  const [localMaxTotalChars, setLocalMaxTotalChars] = useState(0);
  const [localContextMaxChars, setLocalContextMaxChars] = useState(0);
  const [localMaxEntryChars, setLocalMaxEntryChars] = useState(0);
  const [localContextMaxResults, setLocalContextMaxResults] = useState(0);

  // Sync local state when server settings are fetched/updated
  // (isLoading guard prevents rendering inputs before this runs)
  useEffect(() => {
    if (journalSettings) {
      setLocalMaxTotalChars(journalSettings.journal_max_total_chars);
      setLocalContextMaxChars(journalSettings.journal_context_max_chars);
      setLocalMaxEntryChars(journalSettings.journal_max_entry_chars);
      setLocalContextMaxResults(journalSettings.journal_context_max_results);
    }
  }, [journalSettings]);

  // Dialog states
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [editingEntry, setEditingEntry] = useState<JournalEntry | null>(null);
  const [createForm, setCreateForm] = useState<JournalEntryCreate>({
    theme: 'self_reflection',
    title: '',
    content: '',
    mood: 'reflective',
  });
  const [editForm, setEditForm] = useState<JournalEntryUpdate>({});

  if (isLoading) {
    return (
      <SettingsSection
        value="journals"
        title={t('journals.title', 'Personal Journals')}
        description={t('journals.description', "Assistant's personal logbooks")}
        icon={BookOpen}
      >
        <LoadingSpinner />
      </SettingsSection>
    );
  }

  const entryList = entries?.entries ?? [];
  const sizeInfo = journalSettings?.size_info;
  const lastCost = journalSettings?.last_cost;
  const themeGroups = (entries?.by_theme ?? []).reduce(
    (acc, tc) => ({ ...acc, [tc.theme]: tc.count }),
    {} as Record<string, number>
  );

  // Handlers
  const handleToggle = async (field: string, value: boolean) => {
    try {
      await updateSettings({ [field]: value });
      toast.success(t('journals.settingsUpdated', 'Settings updated'));
    } catch {
      toast.error(t('journals.settingsError', 'Failed to update settings'));
    }
  };

  const handleNumericSave = async (
    field: string,
    value: number,
    restoreFn: (v: number) => void,
    previousValue: number,
  ) => {
    try {
      await updateSettings({ [field]: value });
      toast.success(t('journals.settingsUpdated', 'Settings updated'));
    } catch (err) {
      // Restore previous value on error
      restoreFn(previousValue);
      const message = err instanceof Error ? err.message : t('journals.settingsError', 'Failed to update settings');
      toast.error(message);
    }
  };

  const handleCreate = async () => {
    if (!createForm.title || !createForm.content) return;
    try {
      await createEntry(createForm);
      setIsCreateOpen(false);
      setCreateForm({ theme: 'self_reflection', title: '', content: '', mood: 'reflective' });
      toast.success(t('journals.created', 'Entry created'));
    } catch {
      toast.error(t('journals.createError', 'Failed to create entry'));
    }
  };

  const handleUpdate = async () => {
    if (!editingEntry) return;
    try {
      await updateEntry(editingEntry.id, editForm);
      setEditingEntry(null);
      setEditForm({});
      toast.success(t('journals.updated', 'Entry updated'));
    } catch {
      toast.error(t('journals.updateError', 'Failed to update entry'));
    }
  };

  const handleDelete = async (entryId: string) => {
    try {
      await deleteEntry(entryId);
      toast.success(t('journals.deleted', 'Entry deleted'));
    } catch {
      toast.error(t('journals.deleteError', 'Failed to delete entry'));
    }
  };

  const handleDeleteAll = async () => {
    try {
      await deleteAllEntries();
      toast.success(t('journals.allDeleted', 'All entries deleted'));
    } catch {
      toast.error(t('journals.deleteAllError', 'Failed to delete all entries'));
    }
  };

  const handleExport = (format: 'json' | 'csv') => {
    window.open(`/api/v1/journals/export?format=${format}`, '_blank');
  };

  const openEdit = (entry: JournalEntry) => {
    setEditingEntry(entry);
    setEditForm({ title: entry.title, content: entry.content, mood: entry.mood });
  };

  return (
    <SettingsSection
      value="journals"
      title={t('journals.title', 'Personal Journals')}
      description={t('journals.description', "Assistant's personal logbooks — reflections, observations, and learnings")}
      icon={BookOpen}
    >
      <div className="space-y-6">
        {/* Master toggle */}
        <div className="flex items-center justify-between">
          <div className="space-y-0.5">
            <Label htmlFor="journals-enabled" className="text-sm font-medium">
              {t('journals.enable', 'Enable personal journals')}
            </Label>
            <p className="text-xs text-muted-foreground">
              {t('journals.enableDescription', 'The assistant will write reflections after conversations')}
            </p>
          </div>
          <Switch
            id="journals-enabled"
            checked={journalSettings?.journals_enabled ?? false}
            onCheckedChange={(v) => handleToggle('journals_enabled', v)}
            disabled={isUpdatingSettings}
          />
        </div>

        {/* Conditional settings — only shown when enabled */}
        {journalSettings?.journals_enabled && (
          <div className="space-y-5 pl-1">
            {/* Consolidation Toggle */}
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Label htmlFor="consolidation-enabled" className="text-sm">
                  {t('journals.consolidation', 'Periodic consolidation')}
                </Label>
                <p className="text-xs text-muted-foreground">
                  {t('journals.consolidationDescription', 'Assistant periodically reviews and organizes its notes')}
                </p>
              </div>
              <Switch
                id="consolidation-enabled"
                checked={journalSettings?.journal_consolidation_enabled ?? true}
                onCheckedChange={(v) => handleToggle('journal_consolidation_enabled', v)}
                disabled={isUpdatingSettings}
              />
            </div>

            {/* History Analysis Toggle (with cost warning) */}
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Label htmlFor="history-enabled" className="text-sm flex items-center gap-2">
                  {t('journals.historyAnalysis', 'Analyze conversation history')}
                  <Badge variant="outline" className="text-yellow-600 text-[10px] px-1.5 py-0">
                    <AlertTriangle className="h-3 w-3 mr-0.5" />
                    {t('journals.higherCost', 'Higher cost')}
                  </Badge>
                </Label>
                <p className="text-xs text-muted-foreground">
                  {t('journals.historyDescription', 'Consolidation also reviews recent conversations')}
                </p>
              </div>
              <Switch
                id="history-enabled"
                checked={journalSettings?.journal_consolidation_with_history ?? false}
                onCheckedChange={(v) => handleToggle('journal_consolidation_with_history', v)}
                disabled={isUpdatingSettings}
              />
            </div>

            {/* Size Gauge */}
            {sizeInfo && (
              <div className="space-y-2 rounded-lg border p-3">
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">{t('journals.sizeUsage', 'Size usage')}</span>
                  <span className="font-mono text-xs">
                    {sizeInfo.total_chars.toLocaleString()} / {sizeInfo.max_total_chars.toLocaleString()}
                    <span className="text-muted-foreground ml-1">({sizeInfo.usage_pct}%)</span>
                  </span>
                </div>
                <div className="h-1.5 w-full rounded-full bg-secondary overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all ${
                      sizeInfo.usage_pct > 80 ? 'bg-yellow-500' : 'bg-primary'
                    }`}
                    style={{ width: `${Math.min(sizeInfo.usage_pct, 100)}%` }}
                  />
                </div>
              </div>
            )}

            {/* Numeric Settings */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {/* Max Total Chars */}
              <div className="space-y-1.5">
                <Label className="text-sm">{t('journals.maxTotalChars', 'Max journal size')}</Label>
                <p className="text-[11px] text-muted-foreground">
                  {t('journals.maxTotalCharsDescription', 'Cannot be set below current usage.')}
                </p>
                <Input
                  type="number"
                  min={sizeInfo?.total_chars ?? 5000}
                  max={200000}
                  step={5000}
                  value={localMaxTotalChars}
                  onChange={(e) => setLocalMaxTotalChars(parseInt(e.target.value) || 0)}
                  onBlur={() => handleNumericSave(
                    'journal_max_total_chars',
                    localMaxTotalChars,
                    setLocalMaxTotalChars,
                    journalSettings?.journal_max_total_chars ?? 40000,
                  )}
                  className="w-full font-mono text-sm"
                  disabled={isUpdatingSettings}
                />
              </div>

              {/* Context Max Chars */}
              <div className="space-y-1.5">
                <Label className="text-sm">{t('journals.contextMaxChars', 'Prompt injection budget')}</Label>
                <p className="text-[11px] text-muted-foreground">
                  {t('journals.contextMaxCharsDescription', 'Max characters injected into prompts')}
                </p>
                <Input
                  type="number"
                  min={200}
                  max={10000}
                  step={100}
                  value={localContextMaxChars}
                  onChange={(e) => setLocalContextMaxChars(parseInt(e.target.value) || 0)}
                  onBlur={() => handleNumericSave(
                    'journal_context_max_chars',
                    localContextMaxChars,
                    setLocalContextMaxChars,
                    journalSettings?.journal_context_max_chars ?? 1500,
                  )}
                  className="w-full font-mono text-sm"
                  disabled={isUpdatingSettings}
                />
              </div>

              {/* Max Entry Chars */}
              <div className="space-y-1.5">
                <Label className="text-sm">{t('journals.maxEntryChars', 'Max entry size')}</Label>
                <p className="text-[11px] text-muted-foreground">
                  {t('journals.maxEntryCharsDescription', 'Max characters per individual entry.')}
                </p>
                <Input
                  type="number"
                  min={100}
                  max={5000}
                  step={100}
                  value={localMaxEntryChars}
                  onChange={(e) => setLocalMaxEntryChars(parseInt(e.target.value) || 0)}
                  onBlur={() => handleNumericSave(
                    'journal_max_entry_chars',
                    localMaxEntryChars,
                    setLocalMaxEntryChars,
                    journalSettings?.journal_max_entry_chars ?? 2000,
                  )}
                  className="w-full font-mono text-sm"
                  disabled={isUpdatingSettings}
                />
              </div>

              {/* Context Max Results */}
              <div className="space-y-1.5">
                <Label className="text-sm">{t('journals.contextMaxResults', 'Max search results')}</Label>
                <p className="text-[11px] text-muted-foreground">
                  {t('journals.contextMaxResultsDescription', 'Max entries for context injection')}
                </p>
                <Input
                  type="number"
                  min={1}
                  max={30}
                  step={1}
                  value={localContextMaxResults}
                  onChange={(e) => setLocalContextMaxResults(parseInt(e.target.value) || 0)}
                  onBlur={() => handleNumericSave(
                    'journal_context_max_results',
                    localContextMaxResults,
                    setLocalContextMaxResults,
                    journalSettings?.journal_context_max_results ?? 10,
                  )}
                  className="w-full font-mono text-sm"
                  disabled={isUpdatingSettings}
                />
              </div>
            </div>

            {/* Last Cost Info */}
            {lastCost?.timestamp && (
              <div className="rounded-lg border p-3 text-xs text-muted-foreground">
                <div className="flex items-center gap-1.5">
                  <Settings2 className="h-3.5 w-3.5 shrink-0" />
                  <span>{t('journals.lastCost', 'Last intervention')}:</span>
                  <span>
                    {lastCost.source === 'extraction' ? SOURCE_EMOJI.conversation : SOURCE_EMOJI.consolidation}
                  </span>
                  <span className="font-mono">
                    {lastCost.tokens_in ?? 0} in / {lastCost.tokens_out ?? 0} out
                  </span>
                  {lastCost.cost_eur != null && (
                    <span className="font-mono">{Number(lastCost.cost_eur).toFixed(4)} EUR</span>
                  )}
                  <span className="ml-auto">{new Date(lastCost.timestamp).toLocaleDateString()}</span>
                </div>
              </div>
            )}

            {/* Action Buttons */}
            <div className="flex flex-wrap gap-2">
              <Button size="sm" variant="outline" onClick={() => setIsCreateOpen(true)}>
                <Plus className="h-4 w-4 mr-1" />
                {t('journals.create', 'New entry')}
              </Button>
              <Button size="sm" variant="outline" onClick={() => handleExport('json')}>
                <Download className="h-4 w-4 mr-1" />
                {t('journals.export', 'Export')}
              </Button>
              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button size="sm" variant="destructive" disabled={entryList.length === 0}>
                    <Trash2 className="h-4 w-4 mr-1" />
                    {t('journals.deleteAll', 'Delete all')}
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>{t('journals.deleteAllTitle', 'Delete all entries?')}</AlertDialogTitle>
                    <AlertDialogDescription>
                      {t('journals.deleteAllDescription', 'This will permanently delete all journal entries. This action cannot be undone.')}
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>{t('common.cancel', 'Cancel')}</AlertDialogCancel>
                    <AlertDialogAction onClick={handleDeleteAll}>
                      {t('common.delete', 'Delete')}
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            </div>

            {/* Entries Accordion by Theme */}
            {entryList.length > 0 ? (
        <Accordion type="multiple" className="w-full">
          {(['self_reflection', 'user_observations', 'ideas_analyses', 'learnings'] as JournalTheme[]).map(
            (theme) => {
              const themeEntries = entryList.filter((e) => e.theme === theme);
              const info = THEME_INFO[theme];
              const count = themeGroups[theme] ?? 0;

              return (
                <AccordionItem key={theme} value={theme}>
                  <AccordionTrigger className="text-sm">
                    <span className="flex items-center gap-2">
                      <span>{info.icon}</span>
                      <span>{t(`journals.themes.${theme}`, theme.replace('_', ' '))}</span>
                      <Badge variant="secondary" className="ml-1">
                        {count}
                      </Badge>
                    </span>
                  </AccordionTrigger>
                  <AccordionContent>
                    {themeEntries.length === 0 ? (
                      <p className="text-sm text-muted-foreground py-2">
                        {t('journals.noEntries', 'No entries in this theme')}
                      </p>
                    ) : (
                      <div className="space-y-2">
                        {themeEntries.map((entry) => (
                          <div
                            key={entry.id}
                            className="flex items-start justify-between p-3 rounded-lg border bg-card"
                          >
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2 mb-1">
                                <span className="text-xs">{MOOD_EMOJI[entry.mood] ?? ''}</span>
                                <span className="font-medium text-sm truncate">{entry.title}</span>
                                <Badge variant="outline" className="text-xs">
                                  {SOURCE_EMOJI[entry.source] ?? ''} {entry.source}
                                </Badge>
                              </div>
                              <p className="text-xs text-muted-foreground line-clamp-2">
                                {entry.content}
                              </p>
                              <span className="text-xs text-muted-foreground">
                                {new Date(entry.created_at).toLocaleDateString()}
                              </span>
                            </div>
                            <div className="flex gap-1 ml-2">
                              <Button
                                size="icon"
                                variant="ghost"
                                className="h-7 w-7"
                                onClick={() => openEdit(entry)}
                              >
                                <Pencil className="h-3 w-3" />
                              </Button>
                              <AlertDialog>
                                <AlertDialogTrigger asChild>
                                  <Button size="icon" variant="ghost" className="h-7 w-7 text-destructive">
                                    <Trash2 className="h-3 w-3" />
                                  </Button>
                                </AlertDialogTrigger>
                                <AlertDialogContent>
                                  <AlertDialogHeader>
                                    <AlertDialogTitle>
                                      {t('journals.deleteTitle', 'Delete entry?')}
                                    </AlertDialogTitle>
                                    <AlertDialogDescription>
                                      {t('journals.deleteDescription', 'This entry will be permanently deleted.')}
                                    </AlertDialogDescription>
                                  </AlertDialogHeader>
                                  <AlertDialogFooter>
                                    <AlertDialogCancel>{t('common.cancel', 'Cancel')}</AlertDialogCancel>
                                    <AlertDialogAction onClick={() => handleDelete(entry.id)}>
                                      {t('common.delete', 'Delete')}
                                    </AlertDialogAction>
                                  </AlertDialogFooter>
                                </AlertDialogContent>
                              </AlertDialog>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </AccordionContent>
                </AccordionItem>
              );
            }
          )}
        </Accordion>
            ) : (
              <p className="text-sm text-muted-foreground text-center py-4">
                {t('journals.empty', 'No journal entries yet. The assistant will start writing after conversations.')}
              </p>
            )}
          </div>
        )}
      </div>

      {/* Create Dialog */}
      <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('journals.createTitle', 'New journal entry')}</DialogTitle>
            <DialogDescription>
              {t('journals.createDescription', 'Add a note to the assistant\u0027s journal')}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>{t('journals.theme', 'Theme')}</Label>
              <Select
                value={createForm.theme}
                onValueChange={(v) => setCreateForm({ ...createForm, theme: v as JournalTheme })}
              >
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {(['self_reflection', 'user_observations', 'ideas_analyses', 'learnings'] as JournalTheme[]).map(
                    (theme) => (
                      <SelectItem key={theme} value={theme}>
                        {THEME_INFO[theme].icon} {t(`journals.themes.${theme}`, theme.replace('_', ' '))}
                      </SelectItem>
                    )
                  )}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>{t('journals.entryTitle', 'Title')}</Label>
              <Input
                value={createForm.title}
                onChange={(e) => setCreateForm({ ...createForm, title: e.target.value })}
                maxLength={200}
              />
            </div>
            <div>
              <Label>{t('journals.content', 'Content')}</Label>
              <Textarea
                value={createForm.content}
                onChange={(e) => setCreateForm({ ...createForm, content: e.target.value })}
                maxLength={2000}
                rows={5}
              />
            </div>
            <div>
              <Label>{t('journals.mood', 'Mood')}</Label>
              <Select
                value={createForm.mood}
                onValueChange={(v) => setCreateForm({ ...createForm, mood: v as JournalEntryMood })}
              >
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {(['reflective', 'curious', 'satisfied', 'concerned', 'inspired'] as JournalEntryMood[]).map(
                    (mood) => (
                      <SelectItem key={mood} value={mood}>
                        {MOOD_EMOJI[mood]} {t(`journals.moods.${mood}`, mood)}
                      </SelectItem>
                    )
                  )}
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsCreateOpen(false)}>
              {t('common.cancel', 'Cancel')}
            </Button>
            <Button onClick={handleCreate} disabled={isCreating || !createForm.title || !createForm.content}>
              {isCreating ? <LoadingSpinner /> : t('journals.create', 'Create')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit Dialog */}
      <Dialog open={!!editingEntry} onOpenChange={(open) => !open && setEditingEntry(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('journals.editTitle', 'Edit journal entry')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>{t('journals.entryTitle', 'Title')}</Label>
              <Input
                value={editForm.title ?? ''}
                onChange={(e) => setEditForm({ ...editForm, title: e.target.value })}
                maxLength={200}
              />
            </div>
            <div>
              <Label>{t('journals.content', 'Content')}</Label>
              <Textarea
                value={editForm.content ?? ''}
                onChange={(e) => setEditForm({ ...editForm, content: e.target.value })}
                maxLength={2000}
                rows={5}
              />
            </div>
            <div>
              <Label>{t('journals.mood', 'Mood')}</Label>
              <Select
                value={editForm.mood}
                onValueChange={(v) => setEditForm({ ...editForm, mood: v as JournalEntryMood })}
              >
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {(['reflective', 'curious', 'satisfied', 'concerned', 'inspired'] as JournalEntryMood[]).map(
                    (mood) => (
                      <SelectItem key={mood} value={mood}>
                        {MOOD_EMOJI[mood]} {t(`journals.moods.${mood}`, mood)}
                      </SelectItem>
                    )
                  )}
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditingEntry(null)}>
              {t('common.cancel', 'Cancel')}
            </Button>
            <Button onClick={handleUpdate} disabled={isUpdating}>
              {isUpdating ? <LoadingSpinner /> : t('common.save', 'Save')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </SettingsSection>
  );
}
