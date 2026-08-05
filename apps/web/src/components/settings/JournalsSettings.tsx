'use client';

import { useState, useEffect, useRef } from 'react';
import {
  BookOpen,
  Trash2,
  Plus,
  Pencil,
  Download,
  AlertTriangle,
  Info,
  Settings2,
  RefreshCw,
  Flag,
  UserSquare2,
} from 'lucide-react';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { RowActions } from '@/components/ui/row-actions';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ProvenanceDisclosure } from '@/components/provenance/ProvenanceDisclosure';
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
import { SectionToolbar } from '@/components/settings/SectionToolbar';
import { SettingsDisclosure } from '@/components/settings/SettingsDisclosure';
import {
  useJournals,
  type JournalEntry,
  type JournalEntryCreate,
  type JournalEntryUpdate,
  type JournalEntryConfidence,
  type JournalEntryLevel,
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
/**
 * Above this many characters the clamped entry very likely hides text, so the
 * "show more" toggle appears. A character count, not a layout measurement:
 * `line-clamp` truncation cannot be read back without a resize observer, and
 * an occasionally superfluous toggle is harmless.
 */
const CONTENT_CLAMP_THRESHOLD = 240;

const SOURCE_EMOJI: Record<string, string> = {
  conversation: '\u{1F4AC}',
  consolidation: '\u{1F504}',
  manual: '\u270F\uFE0F',
  user_correction: '\u{1F6A9}', // \uD83D\uDEA9
};

/**
 * Confidence visual style \u2014 distinguishes hypothesis from validated directive.
 * Theme tokens, not raw palette: low is a caution, high a confirmation, and
 * medium takes the house "info" ground (primary tint, like Badge `info`).
 */
const CONFIDENCE_DOT: Record<JournalEntryConfidence, string> = {
  low: 'bg-warning',
  medium: 'bg-primary',
  high: 'bg-success',
};

/**
 * Level visual style \u2014 cognitive stratification (L0 raw \u2192 L3 portrait).
 * Still raw palette: four ORDINAL hues have no semantic tokens to map to;
 * this table belongs to the deferred raw-colour ratchet, not this lot.
 */
const LEVEL_BADGE: Record<JournalEntryLevel, string> = {
  L0: 'bg-slate-100 text-slate-700 border-slate-300',
  L1: 'bg-indigo-50 text-indigo-700 border-indigo-300',
  L2: 'bg-violet-50 text-violet-700 border-violet-300',
  L3: 'bg-amber-50 text-amber-700 border-amber-300',
};

const ALL_LEVELS: JournalEntryLevel[] = ['L0', 'L1', 'L2', 'L3'];

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
    portrait,
    createEntry,
    updateEntry,
    deleteEntry,
    deleteAllEntries,
    updateSettings,
    consolidateNow,
    submitPortraitFeedback,
    isCreating,
    isUpdating,
    isUpdatingSettings,
    isConsolidating,
    isSubmittingFeedback,
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
  const [deletingEntryId, setDeletingEntryId] = useState<string | null>(null);
  // Controlled confirm for the mass deletion (opened from the toolbar).
  const [confirmDeleteAllOpen, setConfirmDeleteAllOpen] = useState(false);
  // Entries the reader unclamped ("show more").
  const [expandedEntries, setExpandedEntries] = useState<Set<string>>(new Set());

  const toggleEntryExpanded = (id: string) => {
    setExpandedEntries(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };
  // Focus anchor for the post-deletion return (rows vanish under the reader).
  const entriesRegionRef = useRef<HTMLDivElement>(null);
  const [editingEntry, setEditingEntry] = useState<JournalEntry | null>(null);
  const [createForm, setCreateForm] = useState<JournalEntryCreate>({
    theme: 'self_reflection',
    title: '',
    content: '',
    mood: 'reflective',
  });
  const [editForm, setEditForm] = useState<JournalEntryUpdate>({});
  const [groupBy, setGroupBy] = useState<'theme' | 'level'>('theme');
  const [portraitFormat, setPortraitFormat] = useState<'full' | 'brief'>('full');
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const [feedbackComment, setFeedbackComment] = useState('');
  const [feedbackHighlight, setFeedbackHighlight] = useState('');

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
  // The API paginates (50 by default); `total` counts every active entry. When
  // they differ the list is a partial view and must say so — a group badge over
  // a silently truncated list reads as an exhaustive count.
  const totalEntries = entries?.total ?? entryList.length;
  const isTruncated = totalEntries > entryList.length;

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
    previousValue: number
  ) => {
    try {
      await updateSettings({ [field]: value });
      toast.success(t('journals.settingsUpdated', 'Settings updated'));
    } catch (err) {
      // Restore previous value on error
      restoreFn(previousValue);
      const message =
        err instanceof Error
          ? err.message
          : t('journals.settingsError', 'Failed to update settings');
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

  const handleSubmitFeedback = async () => {
    const trimmed = feedbackComment.trim();
    if (!trimmed) return;
    try {
      const result = await submitPortraitFeedback({
        comment: trimmed,
        highlighted_section: feedbackHighlight.trim() || undefined,
      });
      if (result) {
        const seconds = Math.max(1, Math.round(result.duration_ms / 1000));
        toast.success(
          t(
            'journals.portraitFeedbackSuccess',
            'Feedback applied — portrait recompiled in {{s}}s',
            {
              s: seconds,
            }
          )
        );
        setFeedbackOpen(false);
        setFeedbackComment('');
        setFeedbackHighlight('');
      }
    } catch (err) {
      const status = (err as { status?: number } | undefined)?.status;
      if (status === 429) {
        toast.error(t('journals.consolidatedQuota', 'LLM quota exceeded — try again later.'));
      } else {
        toast.error(
          t('journals.portraitFeedbackError', 'Failed to submit feedback on the portrait.')
        );
      }
    }
  };

  const handleConsolidateNow = async () => {
    try {
      const result = await consolidateNow();
      if (result) {
        const seconds = Math.max(1, Math.round(result.duration_ms / 1000));
        if (result.actions_applied === 0) {
          toast.success(
            t(
              'journals.consolidatedNoop',
              'Nothing to change — your journal is already well organized ({{s}}s).',
              { s: seconds }
            )
          );
        } else {
          toast.success(
            t(
              'journals.consolidatedSuccess',
              '{{n}} change(s) applied in {{s}}s — refresh the list to see the effect.',
              { n: result.actions_applied, s: seconds }
            )
          );
        }
      }
    } catch (err) {
      const status = (err as { status?: number } | undefined)?.status;
      if (status === 429) {
        toast.error(t('journals.consolidatedQuota', 'LLM quota exceeded — try again later.'));
      } else {
        toast.error(t('journals.consolidatedError', 'Manual consolidation failed.'));
      }
    }
  };

  const openEdit = (entry: JournalEntry) => {
    setEditingEntry(entry);
    setEditForm({
      title: entry.title,
      content: entry.content,
      mood: entry.mood,
      search_hints: entry.search_hints ?? [],
      confidence: entry.confidence,
      level: entry.level,
    });
  };

  const formatRelativeDate = (iso: string | null): string => {
    if (!iso) return t('journals.never', 'never');
    const date = new Date(iso);
    const now = new Date();
    const diffDays = Math.floor((now.getTime() - date.getTime()) / (1000 * 60 * 60 * 24));
    if (diffDays === 0) return t('journals.today', 'today');
    if (diffDays === 1) return t('journals.yesterday', 'yesterday');
    if (diffDays < 7) return t('journals.daysAgo', '{{n}}d ago', { n: diffDays });
    return date.toLocaleDateString();
  };

  return (
    <SettingsSection
      value="journals"
      title={t('journals.title', 'Personal Journals')}
      description={t(
        'journals.description',
        "Assistant's personal logbooks — reflections, observations, and learnings"
      )}
      icon={BookOpen}
    >
      <div ref={entriesRegionRef} tabIndex={-1} className="space-y-6 focus:outline-none">
        {/* Master toggle */}
        <div className="flex items-center justify-between">
          <div className="space-y-0.5">
            <Label htmlFor="journals-enabled" className="text-sm font-medium">
              {t('journals.enable', 'Enable personal journals')}
            </Label>
            <p className="text-xs text-muted-foreground">
              {t(
                'journals.enableDescription',
                'The assistant will write reflections after conversations'
              )}
            </p>
          </div>
          <Switch
            id="journals-enabled"
            checked={journalSettings?.journals_enabled ?? false}
            onCheckedChange={v => handleToggle('journals_enabled', v)}
            disabled={isUpdatingSettings}
          />
        </div>

        {/* Conditional settings — only shown when enabled */}
        {journalSettings?.journals_enabled && (
          <div className="space-y-5 pl-1">
            {/* Portrait section (read-only — three levers for correction) */}
            {(portrait?.full || portrait?.brief) && (
              <div className="rounded-lg border bg-card p-3 space-y-2">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <UserSquare2 className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
                    <div className="min-w-0">
                      <div className="text-sm font-medium">
                        {t('journals.portraitTitle', 'How LIA sees you')}
                      </div>
                      <div className="text-[11px] text-muted-foreground">
                        {portrait?.compiled_at
                          ? t('journals.portraitCompiledAt', 'Compiled {{when}}', {
                              when: formatRelativeDate(portrait.compiled_at),
                            })
                          : t('journals.portraitNeverCompiled', 'Not compiled yet')}
                      </div>
                    </div>
                  </div>
                  <div className="flex gap-1 shrink-0">
                    <Button
                      size="sm"
                      variant={portraitFormat === 'full' ? 'default' : 'outline'}
                      className="h-7 text-xs"
                      onClick={() => setPortraitFormat('full')}
                      disabled={!portrait?.full}
                    >
                      {t('journals.portraitFormatFull', 'Full')}
                    </Button>
                    <Button
                      size="sm"
                      variant={portraitFormat === 'brief' ? 'default' : 'outline'}
                      className="h-7 text-xs"
                      onClick={() => setPortraitFormat('brief')}
                      disabled={!portrait?.brief}
                    >
                      {t('journals.portraitFormatBrief', 'Brief')}
                    </Button>
                  </div>
                </div>

                <p className="text-xs text-muted-foreground whitespace-pre-wrap leading-relaxed">
                  {portraitFormat === 'full' ? (portrait?.full ?? '') : (portrait?.brief ?? '')}
                </p>

                <p className="text-[10px] text-muted-foreground italic">
                  {t(
                    'journals.portraitTip',
                    'The portrait is a living synthesis. To correct it: signal a problem, edit the L3 entries, or trigger a consolidation.'
                  )}
                </p>

                <div className="flex flex-wrap gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-8 text-xs"
                    onClick={() => setFeedbackOpen(true)}
                    disabled={isSubmittingFeedback}
                  >
                    <Flag className="h-3.5 w-3.5 mr-1" />
                    {t('journals.portraitFeedbackButton', 'Signal a problem')}
                  </Button>
                </div>
              </div>
            )}

            {/* Configuration, folded (owner arbitration 2026-08-05): two
                toggles, a gauge and four numeric dials are TUNING, not
                reading — the reader came for the portrait and the entries. */}
            <div className="border-t pt-4">
              <SettingsDisclosure
                icon={Settings2}
                title={t('journals.configuration', 'Configuration')}
              >
                <div className="space-y-5 pt-1">
                  {/* Consolidation Toggle — the cost warning lives IN the row it
                warns about (it used to float as an orphan badge between two
                toggles, glued back with a -mt-3 hack). */}
                  <div className="flex items-center justify-between">
                    <div className="space-y-0.5">
                      <Label htmlFor="consolidation-enabled" className="text-sm">
                        {t('journals.consolidation', 'Periodic consolidation')}
                      </Label>
                      <p className="text-xs text-muted-foreground">
                        {t(
                          'journals.consolidationDescription',
                          'Assistant periodically reviews and organizes its notes'
                        )}
                      </p>
                      <p className="flex items-center gap-1 text-xs text-warning">
                        <AlertTriangle className="h-3 w-3" aria-hidden="true" />
                        {t('journals.higherCost', 'Higher cost')}
                      </p>
                    </div>
                    <Switch
                      id="consolidation-enabled"
                      checked={journalSettings?.journal_consolidation_enabled ?? true}
                      onCheckedChange={v => handleToggle('journal_consolidation_enabled', v)}
                      disabled={isUpdatingSettings}
                    />
                  </div>

                  {/* History Analysis Toggle */}
                  <div className="flex items-center justify-between">
                    <div className="space-y-0.5">
                      <Label htmlFor="history-enabled" className="text-sm">
                        {t('journals.historyAnalysis', 'Analyze conversation history')}
                      </Label>
                      <p className="text-xs text-muted-foreground">
                        {t(
                          'journals.historyDescription',
                          'Consolidation also reviews recent conversations'
                        )}
                      </p>
                    </div>
                    <Switch
                      id="history-enabled"
                      checked={journalSettings?.journal_consolidation_with_history ?? false}
                      onCheckedChange={v => handleToggle('journal_consolidation_with_history', v)}
                      disabled={isUpdatingSettings}
                    />
                  </div>

                  {/* Size Gauge */}
                  {sizeInfo && (
                    <div className="space-y-2 rounded-lg border p-3">
                      <div className="flex flex-col sm:flex-row sm:justify-between text-sm gap-0.5">
                        <span className="text-muted-foreground">
                          {t('journals.sizeUsage', 'Size usage')}
                        </span>
                        <span className="font-mono text-xs">
                          {sizeInfo.total_chars.toLocaleString()} /{' '}
                          {sizeInfo.max_total_chars.toLocaleString()}
                          <span className="text-muted-foreground ml-1">
                            ({sizeInfo.usage_pct}%)
                          </span>
                        </span>
                      </div>
                      <div className="h-1.5 w-full rounded-full bg-secondary overflow-hidden">
                        <div
                          className={`h-full rounded-full transition-all ${
                            sizeInfo.usage_pct > 80 ? 'bg-warning' : 'bg-primary'
                          }`}
                          style={{ width: `${Math.min(sizeInfo.usage_pct, 100)}%` }}
                        />
                      </div>
                    </div>
                  )}

                  {/* Numeric Settings — every cell is the ExportCard shape (ADR-207:
                a grid aligns its actions): label and hint at the top, the
                input pushed to the cell's bottom with `mt-auto`, so the four
                boxes sit on the same line whatever the hint's length. The old
                cells mixed space-y-3 and space-y-1.5 and let the longest hint
                push its input out of line with its neighbour. */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    {/* Max Total Chars */}
                    <div className="flex flex-col gap-3">
                      <Label className="text-sm" htmlFor="journal-max-total-chars">
                        {t('journals.maxTotalChars', 'Max journal size')}
                      </Label>
                      <p
                        id="journal-max-total-chars-hint"
                        className="text-[11px] text-muted-foreground"
                      >
                        {t(
                          'journals.maxTotalCharsDescription',
                          'Cannot be set below current usage.'
                        )}
                      </p>
                      <Input
                        id="journal-max-total-chars"
                        aria-describedby="journal-max-total-chars-hint"
                        type="number"
                        min={sizeInfo?.total_chars ?? 5000}
                        max={200000}
                        step={5000}
                        value={localMaxTotalChars}
                        onChange={e => setLocalMaxTotalChars(parseInt(e.target.value) || 0)}
                        onBlur={() =>
                          handleNumericSave(
                            'journal_max_total_chars',
                            localMaxTotalChars,
                            setLocalMaxTotalChars,
                            journalSettings!.journal_max_total_chars
                          )
                        }
                        className="mt-auto w-full font-mono text-sm"
                        disabled={isUpdatingSettings}
                      />
                    </div>

                    {/* Context Max Chars */}
                    <div className="flex flex-col gap-3">
                      <Label className="text-sm" htmlFor="journal-context-max-chars">
                        {t('journals.contextMaxChars', 'Prompt injection budget')}
                      </Label>
                      <p
                        id="journal-context-max-chars-hint"
                        className="text-[11px] text-muted-foreground"
                      >
                        {t(
                          'journals.contextMaxCharsDescription',
                          'Max characters injected into prompts'
                        )}
                      </p>
                      <Input
                        id="journal-context-max-chars"
                        aria-describedby="journal-context-max-chars-hint"
                        type="number"
                        min={200}
                        max={10000}
                        step={100}
                        value={localContextMaxChars}
                        onChange={e => setLocalContextMaxChars(parseInt(e.target.value) || 0)}
                        onBlur={() =>
                          handleNumericSave(
                            'journal_context_max_chars',
                            localContextMaxChars,
                            setLocalContextMaxChars,
                            journalSettings!.journal_context_max_chars
                          )
                        }
                        className="mt-auto w-full font-mono text-sm"
                        disabled={isUpdatingSettings}
                      />
                    </div>

                    {/* Max Entry Chars */}
                    <div className="flex flex-col gap-3">
                      <Label className="text-sm" htmlFor="journal-max-entry-chars">
                        {t('journals.maxEntryChars', 'Max entry size')}
                      </Label>
                      <p
                        id="journal-max-entry-chars-hint"
                        className="text-[11px] text-muted-foreground"
                      >
                        {t(
                          'journals.maxEntryCharsDescription',
                          'Max characters per individual entry.'
                        )}
                      </p>
                      <Input
                        id="journal-max-entry-chars"
                        aria-describedby="journal-max-entry-chars-hint"
                        type="number"
                        min={100}
                        max={5000}
                        step={100}
                        value={localMaxEntryChars}
                        onChange={e => setLocalMaxEntryChars(parseInt(e.target.value) || 0)}
                        onBlur={() =>
                          handleNumericSave(
                            'journal_max_entry_chars',
                            localMaxEntryChars,
                            setLocalMaxEntryChars,
                            journalSettings!.journal_max_entry_chars
                          )
                        }
                        className="mt-auto w-full font-mono text-sm"
                        disabled={isUpdatingSettings}
                      />
                    </div>

                    {/* Context Max Results */}
                    <div className="flex flex-col gap-3">
                      <Label className="text-sm" htmlFor="journal-context-max-results">
                        {t('journals.contextMaxResults', 'Max search results')}
                      </Label>
                      <p
                        id="journal-context-max-results-hint"
                        className="text-[11px] text-muted-foreground"
                      >
                        {t(
                          'journals.contextMaxResultsDescription',
                          'Max entries for context injection'
                        )}
                      </p>
                      <Input
                        id="journal-context-max-results"
                        aria-describedby="journal-context-max-results-hint"
                        type="number"
                        min={1}
                        max={30}
                        step={1}
                        value={localContextMaxResults}
                        onChange={e => setLocalContextMaxResults(parseInt(e.target.value) || 0)}
                        onBlur={() =>
                          handleNumericSave(
                            'journal_context_max_results',
                            localContextMaxResults,
                            setLocalContextMaxResults,
                            journalSettings!.journal_context_max_results
                          )
                        }
                        className="mt-auto w-full font-mono text-sm"
                        disabled={isUpdatingSettings}
                      />
                    </div>
                  </div>
                </div>
              </SettingsDisclosure>
            </div>

            {/* Last Cost Info */}
            {lastCost?.timestamp && (
              <div className="rounded-lg border p-3 text-xs text-muted-foreground">
                {/* Desktop: single row */}
                <div className="hidden sm:flex items-center gap-1.5">
                  <Settings2 className="h-3.5 w-3.5 shrink-0" />
                  <span>{t('journals.lastCost', 'Last intervention')}:</span>
                  <span>
                    {lastCost.source === 'extraction'
                      ? SOURCE_EMOJI.conversation
                      : SOURCE_EMOJI.consolidation}
                  </span>
                  <span className="font-mono">
                    {lastCost.tokens_in ?? 0} in / {lastCost.tokens_out ?? 0} out
                  </span>
                  {lastCost.cost_eur != null && (
                    <span className="font-mono">{Number(lastCost.cost_eur).toFixed(4)} EUR</span>
                  )}
                  <span className="ml-auto">
                    {new Date(lastCost.timestamp).toLocaleDateString()}
                  </span>
                </div>
                {/* Mobile: each element on its own line */}
                <div className="flex sm:hidden flex-col gap-1">
                  <div className="flex items-center gap-1.5">
                    <Settings2 className="h-3.5 w-3.5 shrink-0" />
                    <span>{t('journals.lastCost', 'Last intervention')}</span>
                  </div>
                  <div className="pl-5 flex items-center gap-1.5">
                    <span>{t('journals.lastCostSource', 'Source')}:</span>
                    <span>
                      {lastCost.source === 'extraction'
                        ? SOURCE_EMOJI.conversation
                        : SOURCE_EMOJI.consolidation}{' '}
                      {lastCost.source}
                    </span>
                  </div>
                  <div className="pl-5">
                    <span className="font-mono">
                      {lastCost.tokens_in ?? 0} in / {lastCost.tokens_out ?? 0} out
                    </span>
                  </div>
                  {lastCost.cost_eur != null && (
                    <div className="pl-5">
                      <span className="font-mono">{Number(lastCost.cost_eur).toFixed(4)} EUR</span>
                    </div>
                  )}
                  <div className="pl-5">
                    <span>{new Date(lastCost.timestamp).toLocaleDateString()}</span>
                  </div>
                </div>
              </div>
            )}

            {/* Group toggle (the never-used filter was removed on owner
                arbitration 2026-08-05: a maintenance view, not a reading one) */}
            {entryList.length > 0 && (
              <div className="flex flex-col gap-2">
                <div className="flex items-center justify-between">
                  <Label className="text-xs text-muted-foreground">
                    {t('journals.groupBy.label', 'Group by')}
                  </Label>
                  <div className="flex gap-1">
                    <Button
                      size="sm"
                      variant={groupBy === 'theme' ? 'default' : 'outline'}
                      className="h-7 text-xs"
                      onClick={() => setGroupBy('theme')}
                    >
                      {t('journals.groupBy.theme', 'Theme')}
                    </Button>
                    <Button
                      size="sm"
                      variant={groupBy === 'level' ? 'default' : 'outline'}
                      className="h-7 text-xs"
                      onClick={() => setGroupBy('level')}
                    >
                      {t('journals.groupBy.level', 'Level')}
                    </Button>
                  </div>
                </div>
              </div>
            )}

            {/* Entries Accordion (by Theme or by Level) */}
            {entryList.length > 0 ? (
              (() => {
                const themeKeys: JournalTheme[] = [
                  'self_reflection',
                  'user_observations',
                  'ideas_analyses',
                  'learnings',
                ];
                type Group = {
                  key: string;
                  label: string;
                  icon: string;
                  filter: (e: JournalEntry) => boolean;
                };
                // No `count` on the group: it is derived from the rows actually
                // rendered, below. Theme badges used to carry the server-side
                // total while the list was paginated, so a badge could claim
                // 12 over three rows.
                const groups: Group[] =
                  groupBy === 'theme'
                    ? themeKeys.map(theme => ({
                        key: theme,
                        label: t(`journals.themes.${theme}`, theme.replaceAll('_', ' ')),
                        icon: THEME_INFO[theme].icon,
                        filter: (e: JournalEntry) => e.theme === theme,
                      }))
                    : ALL_LEVELS.map(level => ({
                        key: level,
                        label: t(`journals.levels.${level}.label`, level),
                        icon: level,
                        filter: (e: JournalEntry) => e.level === level,
                      }));
                return (
                  <>
                    {isTruncated && (
                      <p
                        role="status"
                        className="text-xs text-muted-foreground mb-2"
                        data-testid="journals-truncated-notice"
                      >
                        {t('journals.listTruncated', {
                          shown: entryList.length,
                          total: totalEntries,
                          defaultValue: 'Showing the {{shown}} most recent of {{total}} entries.',
                        })}
                      </p>
                    )}
                    <Accordion type="multiple" className="w-full">
                      {groups.map(g => {
                        const groupEntries = entryList.filter(g.filter);
                        return (
                          <AccordionItem key={g.key} value={g.key}>
                            <AccordionTrigger className="text-sm">
                              <span className="flex items-center gap-2">
                                {groupBy === 'level' ? (
                                  <Badge
                                    variant="outline"
                                    className={`text-[10px] px-1.5 py-0 font-mono ${
                                      LEVEL_BADGE[g.key as JournalEntryLevel]
                                    }`}
                                  >
                                    {g.icon}
                                  </Badge>
                                ) : (
                                  <span>{g.icon}</span>
                                )}
                                <span>{g.label}</span>
                                <Badge variant="secondary" className="ml-1">
                                  {groupEntries.length}
                                </Badge>
                              </span>
                            </AccordionTrigger>
                            <AccordionContent>
                              {groupEntries.length === 0 ? (
                                <p className="text-sm text-muted-foreground py-2">
                                  {t('journals.noEntries', 'No entries in this group')}
                                </p>
                              ) : (
                                <div className="space-y-2">
                                  {groupEntries.map(entry => (
                                    <div
                                      key={entry.id}
                                      className="flex items-start justify-between p-3 rounded-lg border bg-card"
                                    >
                                      <div className="flex-1 min-w-0">
                                        <div className="flex flex-col sm:flex-row sm:items-center gap-0.5 sm:gap-2 mb-1">
                                          <div className="flex items-center gap-2 min-w-0">
                                            <span className="text-xs">
                                              {MOOD_EMOJI[entry.mood] ?? ''}
                                            </span>
                                            <span className="font-medium text-sm truncate">
                                              {entry.title}
                                            </span>
                                          </div>
                                          <div className="flex items-center gap-1.5">
                                            <Badge variant="outline" className="text-xs w-fit">
                                              {SOURCE_EMOJI[entry.source] ?? ''} {entry.source}
                                            </Badge>
                                            {/* The level stays VISIBLE: grouped
                                                by theme it is the only thing
                                                telling an L1 note from an L3
                                                synthesis. */}
                                            <Badge
                                              variant="outline"
                                              className={`text-[10px] px-1.5 py-0 font-mono ${LEVEL_BADGE[entry.level]}`}
                                              title={t(
                                                `journals.levels.${entry.level}.description`,
                                                entry.level
                                              )}
                                            >
                                              {entry.level}
                                            </Badge>
                                          </div>
                                        </div>
                                        {/* Clamped: a long reflection used to
                                            render in FULL inside the list,
                                            turning ten entries into a wall.
                                            The toggle appears only when there
                                            is actually more to read. */}
                                        <p
                                          className={`text-xs text-muted-foreground whitespace-pre-wrap ${
                                            expandedEntries.has(entry.id) ? '' : 'line-clamp-3'
                                          }`}
                                        >
                                          {entry.content}
                                        </p>
                                        {entry.content.length > CONTENT_CLAMP_THRESHOLD && (
                                          <Button
                                            type="button"
                                            variant="ghost"
                                            size="sm"
                                            className="h-6 px-1 text-xs text-muted-foreground"
                                            aria-expanded={expandedEntries.has(entry.id)}
                                            onClick={() => toggleEntryExpanded(entry.id)}
                                          >
                                            {expandedEntries.has(entry.id)
                                              ? t('common.show_less', 'Show less')
                                              : t('common.show_more', 'Show more')}
                                          </Button>
                                        )}
                                        {/* Epistemic metrics + search hints,
                                            FOLDED: five 10px chips under every
                                            entry answered questions nobody was
                                            asking while scanning (owner
                                            arbitration 2026-08-05). */}
                                        <SettingsDisclosure
                                          icon={Info}
                                          title={t('common.details', 'Details')}
                                          className="mt-1"
                                        >
                                          <div className="space-y-1.5">
                                            {entry.search_hints &&
                                              entry.search_hints.length > 0 && (
                                                <div className="flex flex-wrap gap-1">
                                                  {entry.search_hints.map((hint, idx) => (
                                                    <Badge
                                                      key={idx}
                                                      variant="outline"
                                                      className="text-[10px] px-1.5 py-0 font-normal text-muted-foreground"
                                                    >
                                                      {hint}
                                                    </Badge>
                                                  ))}
                                                </div>
                                              )}
                                            <div className="flex flex-wrap items-center gap-2 text-[10px] text-muted-foreground">
                                              <span
                                                className="flex items-center gap-1"
                                                title={t(
                                                  `journals.confidence.${entry.confidence}`,
                                                  entry.confidence
                                                )}
                                              >
                                                <span
                                                  className={`inline-block h-2 w-2 rounded-full ${CONFIDENCE_DOT[entry.confidence]}`}
                                                />
                                                {t(
                                                  `journals.confidence.${entry.confidence}`,
                                                  entry.confidence
                                                )}
                                              </span>
                                              <span
                                                title={t('journals.injectionCount', 'Times used')}
                                              >
                                                ✨ {entry.injection_count}
                                              </span>
                                              <span title={t('journals.lastInjected', 'Last used')}>
                                                {t('journals.lastUsed', 'last')}:{' '}
                                                {formatRelativeDate(entry.last_injected_at)}
                                              </span>
                                              {(entry.evidence_count > 0 ||
                                                entry.contradiction_count > 0) && (
                                                <span
                                                  title={t(
                                                    'journals.evidenceTooltip',
                                                    'Confirmations / contradictions'
                                                  )}
                                                >
                                                  ✓{entry.evidence_count} / ✗
                                                  {entry.contradiction_count}
                                                </span>
                                              )}
                                              <span>
                                                · {new Date(entry.created_at).toLocaleDateString()}
                                              </span>
                                            </div>
                                          </div>
                                        </SettingsDisclosure>
                                        {/* The counters above answer HOW MANY
                                            signals; this answers WHICH. A
                                            conclusion nobody can examine is one
                                            nobody can argue with — and the
                                            correction is offered right where
                                            the reason is read. */}
                                        <ProvenanceDisclosure
                                          endpoint={`/journals/${entry.id}/provenance`}
                                          locale={lng}
                                          onCorrect={() => openEdit(entry)}
                                        />
                                      </div>
                                      <RowActions
                                        className="ml-2"
                                        menuLabel={t('common.actions_for', {
                                          name: entry.title,
                                        })}
                                        actions={[
                                          {
                                            key: 'edit',
                                            label: t('common.edit', 'Edit'),
                                            icon: Pencil,
                                            onSelect: () => openEdit(entry),
                                          },
                                          {
                                            key: 'delete',
                                            label: t('common.delete', 'Delete'),
                                            icon: Trash2,
                                            tone: 'destructive',
                                            onSelect: () => setDeletingEntryId(entry.id),
                                          },
                                        ]}
                                      />
                                    </div>
                                  ))}
                                </div>
                              )}
                            </AccordionContent>
                          </AccordionItem>
                        );
                      })}
                    </Accordion>
                  </>
                );
              })()
            ) : (
              <p className="text-sm text-muted-foreground text-center py-4">
                {t(
                  'journals.empty',
                  'No journal entries yet. The assistant will start writing after conversations.'
                )}
              </p>
            )}

            {/* Action Buttons — BELOW the categories (owner arbitration
                2026-08-05): the reader scans first, acts after. Unified
                section toolbar: no four stacked full-width buttons on a
                phone. */}
            <SectionToolbar
              menuLabel={t('common.more_actions', 'More actions')}
              primary={{
                key: 'create',
                label: t('journals.create', 'Add'),
                icon: Plus,
                onSelect: () => setIsCreateOpen(true),
              }}
              secondary={[
                {
                  key: 'export',
                  label: t('journals.export', 'Export'),
                  icon: Download,
                  onSelect: () => void handleExport('json'),
                  // Visible on phones too (owner request 2026-08-05); the
                  // consolidation below stays foldable — it is occasional.
                  pinned: true,
                },
                {
                  key: 'consolidate',
                  label: isConsolidating
                    ? t('journals.consolidating', 'Consolidating…')
                    : t('journals.consolidateNow', 'Consolidate now'),
                  icon: RefreshCw,
                  loading: isConsolidating,
                  onSelect: () => void handleConsolidateNow(),
                },
              ]}
              destructive={{
                key: 'delete-all',
                label: t('journals.deleteAll', 'Delete all'),
                icon: Trash2,
                disabled: entryList.length === 0,
                onSelect: () => setConfirmDeleteAllOpen(true),
              }}
            />
            <AlertDialog open={confirmDeleteAllOpen} onOpenChange={setConfirmDeleteAllOpen}>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>
                    {t('journals.deleteAllTitle', 'Delete all entries?')}
                  </AlertDialogTitle>
                  <AlertDialogDescription>
                    {t(
                      'journals.deleteAllDescription',
                      'This will permanently delete all journal entries. This action cannot be undone.'
                    )}
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>{t('common.cancel', 'Cancel')}</AlertDialogCancel>
                  <AlertDialogAction variant="destructive" onClick={handleDeleteAll}>
                    {t('common.delete', 'Delete')}
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </div>
        )}
      </div>

      {/* Entry delete confirmation — ONE controlled dialog for the whole list
          (the old per-row inline AlertDialog rendered a dialog per entry and
          returned focus into the row it had just removed). */}
      <AlertDialog
        open={deletingEntryId !== null}
        onOpenChange={open => !open && setDeletingEntryId(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('journals.deleteTitle', 'Delete entry?')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('journals.deleteDescription', 'This entry will be permanently deleted.')}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel', 'Cancel')}</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              onClick={() => {
                if (deletingEntryId) void handleDelete(deletingEntryId);
                setDeletingEntryId(null);
                // The trigger row is gone with the deletion: park focus on the
                // surviving container instead of letting it fall to <body>
                // (ScheduledActionsSettings precedent).
                entriesRegionRef.current?.focus();
              }}
            >
              {t('common.delete', 'Delete')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Portrait feedback dialog (lever 2 of ADR-079) */}
      <Dialog open={feedbackOpen} onOpenChange={setFeedbackOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {t('journals.portraitFeedbackTitle', 'Signal a problem on the portrait')}
            </DialogTitle>
            <DialogDescription>
              {t(
                'journals.portraitFeedbackDescription',
                'Describe what is wrong, inaccurate, or outdated. LIA will treat this as a strong correction signal and recompile the portrait accordingly.'
              )}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-3">
              <Label htmlFor="journal-feedback-highlight">
                {t('journals.portraitFeedbackHighlightLabel', 'Highlighted passage (optional)')}
              </Label>
              <Input
                id="journal-feedback-highlight"
                value={feedbackHighlight}
                onChange={e => setFeedbackHighlight(e.target.value)}
                placeholder={t(
                  'journals.portraitFeedbackHighlightPlaceholder',
                  'Paste the passage that bothers you'
                )}
                maxLength={500}
              />
            </div>
            <div className="space-y-3">
              <Label htmlFor="journal-feedback-comment">
                {t('journals.portraitFeedbackCommentLabel', 'Your correction')}
              </Label>
              <Textarea
                id="journal-feedback-comment"
                value={feedbackComment}
                onChange={e => setFeedbackComment(e.target.value)}
                placeholder={t(
                  'journals.portraitFeedbackCommentPlaceholder',
                  'Why is this wrong? What should it say instead?'
                )}
                maxLength={2000}
                rows={5}
              />
            </div>
            <p className="text-[11px] text-muted-foreground">
              {t(
                'journals.portraitFeedbackHelp',
                'Submitting will trigger a synchronous re-consolidation (~10-15s).'
              )}
            </p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setFeedbackOpen(false)}>
              {t('common.cancel', 'Cancel')}
            </Button>
            <Button
              onClick={handleSubmitFeedback}
              disabled={isSubmittingFeedback || !feedbackComment.trim()}
            >
              {isSubmittingFeedback ? (
                <LoadingSpinner />
              ) : (
                <>
                  <Flag className="h-3.5 w-3.5 mr-1" />
                  {t('journals.portraitFeedbackSubmit', 'Submit feedback')}
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

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
            <div className="space-y-3">
              <Label>{t('journals.theme', 'Theme')}</Label>
              <Select
                value={createForm.theme}
                onValueChange={v => setCreateForm({ ...createForm, theme: v as JournalTheme })}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {(
                    [
                      'self_reflection',
                      'user_observations',
                      'ideas_analyses',
                      'learnings',
                    ] as JournalTheme[]
                  ).map(theme => (
                    <SelectItem key={theme} value={theme}>
                      {THEME_INFO[theme].icon}{' '}
                      {t(`journals.themes.${theme}`, theme.replace('_', ' '))}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-3">
              <Label htmlFor="journal-create-title">{t('journals.entryTitle', 'Title')}</Label>
              <Input
                id="journal-create-title"
                value={createForm.title}
                onChange={e => setCreateForm({ ...createForm, title: e.target.value })}
                maxLength={200}
              />
            </div>
            <div className="space-y-3">
              <Label htmlFor="journal-create-content">{t('journals.content', 'Content')}</Label>
              <Textarea
                id="journal-create-content"
                value={createForm.content}
                onChange={e => setCreateForm({ ...createForm, content: e.target.value })}
                maxLength={2000}
                rows={5}
              />
            </div>
            <div className="space-y-3">
              <Label>{t('journals.mood', 'Mood')}</Label>
              <Select
                value={createForm.mood}
                onValueChange={v => setCreateForm({ ...createForm, mood: v as JournalEntryMood })}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {(
                    [
                      'reflective',
                      'curious',
                      'satisfied',
                      'concerned',
                      'inspired',
                    ] as JournalEntryMood[]
                  ).map(mood => (
                    <SelectItem key={mood} value={mood}>
                      {MOOD_EMOJI[mood]} {t(`journals.moods.${mood}`, mood)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsCreateOpen(false)}>
              {t('common.cancel', 'Cancel')}
            </Button>
            <Button
              onClick={handleCreate}
              disabled={isCreating || !createForm.title || !createForm.content}
            >
              {isCreating ? <LoadingSpinner /> : t('journals.create', 'Add')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit Dialog */}
      <Dialog open={!!editingEntry} onOpenChange={open => !open && setEditingEntry(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('journals.editTitle', 'Edit journal entry')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-3">
              <Label htmlFor="journal-edit-title">{t('journals.entryTitle', 'Title')}</Label>
              <Input
                id="journal-edit-title"
                value={editForm.title ?? ''}
                onChange={e => setEditForm({ ...editForm, title: e.target.value })}
                maxLength={200}
              />
            </div>
            <div className="space-y-3">
              <Label htmlFor="journal-edit-content">{t('journals.content', 'Content')}</Label>
              <Textarea
                id="journal-edit-content"
                value={editForm.content ?? ''}
                onChange={e => setEditForm({ ...editForm, content: e.target.value })}
                maxLength={2000}
                rows={5}
              />
            </div>
            <div className="space-y-3">
              <Label>{t('journals.mood', 'Mood')}</Label>
              <Select
                value={editForm.mood}
                onValueChange={v => setEditForm({ ...editForm, mood: v as JournalEntryMood })}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {(
                    [
                      'reflective',
                      'curious',
                      'satisfied',
                      'concerned',
                      'inspired',
                    ] as JournalEntryMood[]
                  ).map(mood => (
                    <SelectItem key={mood} value={mood}>
                      {MOOD_EMOJI[mood]} {t(`journals.moods.${mood}`, mood)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-3">
              <Label htmlFor="journal-edit-search-hints">
                {t('journals.searchHints', 'Search hints')}
              </Label>
              <p
                id="journal-edit-search-hints-hint"
                className="text-[11px] text-muted-foreground mb-1"
              >
                {t(
                  'journals.searchHintsDescription',
                  'Keywords for semantic search (comma-separated)'
                )}
              </p>
              <Input
                id="journal-edit-search-hints"
                aria-describedby="journal-edit-search-hints-hint"
                value={(editForm.search_hints ?? []).join(', ')}
                onChange={e =>
                  setEditForm({
                    ...editForm,
                    search_hints: e.target.value
                      .split(',')
                      .map(s => s.trim())
                      .filter(Boolean),
                  })
                }
                placeholder="keyword1, keyword2, keyword3"
                maxLength={500}
              />
            </div>
            <div className="space-y-3">
              <Label>{t('journals.confidenceLabel', 'Confidence')}</Label>
              <p className="text-[11px] text-muted-foreground mb-1">
                {t(
                  'journals.confidenceDescription',
                  'Epistemic status — override only when you know the assistant misclassified.'
                )}
              </p>
              <Select
                value={editForm.confidence}
                onValueChange={v =>
                  setEditForm({ ...editForm, confidence: v as JournalEntryConfidence })
                }
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {(['low', 'medium', 'high'] as JournalEntryConfidence[]).map(c => (
                    <SelectItem key={c} value={c}>
                      <span className="flex items-center gap-2">
                        <span
                          className={`inline-block h-2 w-2 rounded-full ${CONFIDENCE_DOT[c]}`}
                        />
                        {t(`journals.confidence.${c}`, c)}
                      </span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-3">
              <Label>{t('journals.levelLabel', 'Level')}</Label>
              <p className="text-[11px] text-muted-foreground mb-1">
                {t(
                  'journals.levelDescription',
                  'Cognitive abstraction level — L0 raw observations, L1 directives, L2 patterns, L3 portrait facets.'
                )}
              </p>
              <Select
                value={editForm.level}
                onValueChange={v => setEditForm({ ...editForm, level: v as JournalEntryLevel })}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {ALL_LEVELS.map(l => (
                    <SelectItem key={l} value={l}>
                      <span className="flex items-center gap-2">
                        <Badge
                          variant="outline"
                          className={`text-[10px] px-1.5 py-0 font-mono ${LEVEL_BADGE[l]}`}
                        >
                          {l}
                        </Badge>
                        {t(`journals.levels.${l}.label`, l)}
                      </span>
                    </SelectItem>
                  ))}
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
