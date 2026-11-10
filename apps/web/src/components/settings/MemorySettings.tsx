'use client';

import { useState, useMemo } from 'react';
import {
  AlertTriangle,
  BookUser,
  Brain,
  Clock,
  Download,
  Pencil,
  Pin,
  PinOff,
  Plus,
  RefreshCw,
  Save,
  Trash2,
  X,
} from '@/lib/icons';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { InfoBox } from '@/components/ui/info-box';
import { RowActions } from '@/components/ui/row-actions';
import { Switch } from '@/components/ui/switch';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { apiEndpointUrl } from '@/lib/api-client';
import { useTranslation } from '@/i18n/client';
import { type Language, getIntlLocale } from '@/i18n/settings';
import { SettingsSection } from '@/components/settings/SettingsSection';
import { SectionToolbar } from '@/components/settings/SectionToolbar';
import {
  CATEGORY_ICONS,
  EMPTY_MEMORY_FORM,
  MemoryFormFields,
  type MemoryFormData,
} from '@/components/settings/MemoryFormFields';
import {
  useMemories,
  getEmotionalEmoji,
  type MemoryCategory,
  type Memory,
} from '@/hooks/useMemories';
import { useAuth } from '@/hooks/useAuth';
import { useApplicationAccountToast } from '@/hooks/useApplicationAccountToast';
import { useMemoryCreateForm } from './useMemoryCreateForm';
import apiClient from '@/lib/api-client';
import { isMemoryTextSavable, isRefusedInput } from '@/lib/memories/text-bounds';
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
import type { BaseSettingsProps } from '@/types/settings';

/**
 * Format a date for display using the user's locale.
 */
function formatMemoryDate(dateString: string | undefined, lng: Language): string {
  if (!dateString) return '';
  try {
    const date = new Date(dateString);
    return new Intl.DateTimeFormat(getIntlLocale(lng), {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    }).format(date);
  } catch {
    return dateString;
  }
}

/**
 * Sort memories by date descending (most recent first).
 */
function sortMemoriesByDate(memories: Memory[]): Memory[] {
  return [...memories].sort((a, b) => {
    const dateA = a.created_at ? new Date(a.created_at).getTime() : 0;
    const dateB = b.created_at ? new Date(b.created_at).getTime() : 0;
    return dateB - dateA; // Descending order
  });
}

/**
 * Whether a memory should show a purge-risk warning.
 */
function isAtPurgeRisk(memory: Memory): boolean {
  return memory.purge_risk === 'at_risk' || memory.purge_risk === 'imminent';
}

function memoryDetailTone(pinned: boolean | undefined): string {
  return pinned ? 'text-foreground' : 'text-muted-foreground';
}

export function MemorySettings({ lng }: BaseSettingsProps) {
  const { user } = useAuth();
  return <AccountMemorySettings key={user?.id ?? 'signed-out'} lng={lng} />;
}

function AccountMemorySettings({ lng }: BaseSettingsProps) {
  const { t } = useTranslation(lng);
  const { user, refreshUser } = useAuth();
  const toast = useApplicationAccountToast(user?.id);
  const {
    memories,
    total,
    limits,
    loading,
    deleting,
    updating,
    deletingAll,
    createMemory,
    deleteMemory,
    updateMemory,
    deleteAllMemories,
    togglePin,
  } = useMemories();

  // State for memory enabled toggle
  const [updatingMemoryEnabled, setUpdatingMemoryEnabled] = useState(false);

  // State for pin toggle loading
  const [togglingPin, setTogglingPin] = useState<string | null>(null);

  // Controlled confirm for the mass deletion (opened from the toolbar).
  const [confirmDeleteAllOpen, setConfirmDeleteAllOpen] = useState(false);

  // State for pinned memory delete confirmation
  const [memoryPendingDelete, setMemoryPendingDelete] = useState<Memory | null>(null);

  const handleTogglePin = async (memory: Memory) => {
    setTogglingPin(memory.id);
    try {
      await togglePin(memory.id, !memory.pinned);
      toast.success(memory.pinned ? t('memories.unpin_success') : t('memories.pin_success'));
    } catch {
      toast.error(t('memories.pin_error'));
    } finally {
      setTogglingPin(null);
    }
  };

  const handleToggleMemoryEnabled = async (enabled: boolean) => {
    if (!user || updatingMemoryEnabled) return;

    setUpdatingMemoryEnabled(true);
    try {
      await apiClient.patch('/auth/me/memory-preference', {
        memory_enabled: enabled,
      });
      await refreshUser();
      toast.success(enabled ? t('memories.enabled_success') : t('memories.disabled_success'));
    } catch {
      toast.error(t('common.error'));
    } finally {
      setUpdatingMemoryEnabled(false);
    }
  };

  // Edit dialog state
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [editingMemoryId, setEditingMemoryId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<MemoryFormData>(EMPTY_MEMORY_FORM);

  const {
    open: createDialogOpen,
    form: createForm,
    setForm: setCreateForm,
    start: handleOpenCreate,
    close: handleCloseCreate,
    save: handleSaveCreate,
    saving: creating,
    onOpenChange: setCreateDialogOpen,
  } = useMemoryCreateForm(lng, createMemory, loading, editDialogOpen, limits);

  const handleOpenEdit = (memory: Memory) => {
    setEditingMemoryId(memory.id);
    setEditForm({
      content: memory.content,
      category: memory.category,
      usage_nuance: memory.usage_nuance || '',
      emotional_weight: memory.emotional_weight ?? 0,
      importance: memory.importance ?? 0.7,
      trigger_topic: memory.trigger_topic || '',
    });
    setEditDialogOpen(true);
  };

  const handleCloseEdit = () => {
    setEditDialogOpen(false);
    setEditingMemoryId(null);
    setEditForm(EMPTY_MEMORY_FORM);
  };

  const handleSaveEdit = async () => {
    if (!editingMemoryId) return;
    try {
      await updateMemory(editingMemoryId, editForm);
      toast.success(t('memories.update_success'));
      handleCloseEdit();
    } catch (error) {
      toast.error(t(isRefusedInput(error) ? 'memories.text_refused' : 'memories.update_error'));
    }
  };

  const handleDeleteMemory = async (memoryId: string) => {
    try {
      await deleteMemory(memoryId);
      toast.success(t('memories.delete_success'));
    } catch {
      toast.error(t('memories.delete_error'));
    }
  };

  // Handler for delete button click - shows confirmation for pinned memories
  const handleDeleteClick = (memory: Memory) => {
    if (memory.pinned) {
      setMemoryPendingDelete(memory);
    } else {
      handleDeleteMemory(memory.id);
    }
  };

  // Confirm deletion of pinned memory
  const handleConfirmDeletePinned = async () => {
    if (memoryPendingDelete) {
      await handleDeleteMemory(memoryPendingDelete.id);
      setMemoryPendingDelete(null);
    }
  };

  const handleDeleteAll = async (preservePinned: boolean = false) => {
    try {
      await deleteAllMemories(preservePinned);
      if (preservePinned) {
        toast.success(t('memories.delete_all_keep_pinned_success'));
      } else {
        toast.success(t('memories.delete_all_success'));
      }
    } catch {
      toast.error(t('memories.delete_all_error'));
    }
  };

  // Count pinned memories
  const pinnedCount = useMemo(() => {
    return memories.filter(m => m.pinned).length;
  }, [memories]);

  const handleExport = () => {
    window.open(apiEndpointUrl('/memories/export'), '_blank');
  };

  // Group memories by category for display, sorted by date DESC within each category
  const groupedMemories = useMemo(() => {
    const groups: Record<string, Memory[]> = {};
    for (const memory of memories) {
      if (!groups[memory.category]) {
        groups[memory.category] = [];
      }
      groups[memory.category].push(memory);
    }
    // Sort each category's memories by date descending
    for (const category of Object.keys(groups)) {
      groups[category] = sortMemoriesByDate(groups[category]);
    }
    return groups;
  }, [memories]);

  // Get localized category label
  const getCategoryLabel = (category: MemoryCategory): string => {
    return t(`memories.categories.${category}`) || category;
  };

  const content = (
    <div className="space-y-4">
      {loading ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <LoadingSpinner size="default" />
          {t('common.loading')}
        </div>
      ) : (
        <>
          {/* Global Toggle */}
          <Card surface="nested" variant="flat" className="flex items-center justify-between p-3">
            <div className="flex-1">
              <p className="text-sm font-medium">{t('memories.enable_memory')}</p>
              <p className="text-xs text-muted-foreground">{t('memories.enable_description')}</p>
            </div>
            <Switch
              checked={user?.memory_enabled ?? true}
              onCheckedChange={handleToggleMemoryEnabled}
              disabled={updatingMemoryEnabled}
              aria-label={t('memories.enable_memory')}
            />
          </Card>

          {/* Stats and Actions — the unified section toolbar: labelled CTA at
              every size, export present on phones too (it was `hidden lg:flex`
              — amputated on mobile AND tablet). */}
          <SectionToolbar
            count={t('memories.count', { count: total })}
            menuLabel={t('common.more_actions')}
            primary={{
              key: 'create',
              label: t('memories.create'),
              icon: Plus,
              onSelect: handleOpenCreate,
            }}
            secondary={[
              {
                key: 'export',
                label: t('memories.export'),
                icon: Download,
                disabled: total === 0,
                onSelect: handleExport,
                // Visible on phones too (owner request 2026-08-05): folded
                // into "⋯" it read as absent.
                pinned: true,
              },
            ]}
            destructive={{
              key: 'delete-all',
              label: t('memories.delete_all'),
              icon: Trash2,
              disabled: total === 0 || deletingAll,
              loading: deletingAll,
              onSelect: () => setConfirmDeleteAllOpen(true),
            }}
          />
          <AlertDialog open={confirmDeleteAllOpen} onOpenChange={setConfirmDeleteAllOpen}>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>{t('memories.confirm_delete_all_title')}</AlertDialogTitle>
                <AlertDialogDescription>
                  {pinnedCount > 0 ? (
                    <>{t('memories.confirm_delete_all_with_pinned', { count: pinnedCount })}</>
                  ) : (
                    <>{t('memories.confirm_delete_all_description')}</>
                  )}
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
                {pinnedCount > 0 ? (
                  <div className="flex flex-col-reverse sm:flex-row gap-2">
                    <AlertDialogAction onClick={() => handleDeleteAll(true)} variant="warning">
                      <Pin className="h-4 w-4 mr-1" />
                      {t('memories.delete_all_keep_pinned')}
                    </AlertDialogAction>
                    <AlertDialogAction onClick={() => handleDeleteAll(false)} variant="destructive">
                      <Trash2 className="h-4 w-4 mr-1" />
                      {t('memories.delete_all_including_pinned')}
                    </AlertDialogAction>
                  </div>
                ) : (
                  <AlertDialogAction onClick={() => handleDeleteAll(false)} variant="destructive">
                    <Trash2 className="h-4 w-4 mr-1" />
                    {t('memories.delete_all_including_pinned')}
                  </AlertDialogAction>
                )}
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>

          {/* Memories List */}
          {total === 0 ? (
            <div className="rounded-lg border border-dashed bg-background p-6 text-center text-muted-foreground">
              <Brain className="h-8 w-8 mx-auto mb-2 opacity-50" />
              <p>{t('memories.empty')}</p>
              <p className="text-xs mt-1">{t('memories.empty_hint')}</p>
            </div>
          ) : (
            <Accordion type="multiple" defaultValue={[]} className="space-y-2">
              {Object.entries(groupedMemories).map(([category, categoryMemories]) => (
                <Card key={category} surface="nested" variant="flat" className="px-3">
                  <AccordionItem value={category} className="border-0">
                    <AccordionTrigger className="py-3 hover:no-underline">
                      <div className="flex items-center gap-2">
                        <span>{CATEGORY_ICONS[category as MemoryCategory]}</span>
                        <span className="font-medium">
                          {getCategoryLabel(category as MemoryCategory)}
                        </span>
                        <span className="text-muted-foreground text-sm">
                          ({categoryMemories.length})
                        </span>
                      </div>
                    </AccordionTrigger>
                    <AccordionContent>
                      <div className="space-y-2">
                        {/* A directive was DICTATED, not inferred: nothing
                          automated takes it back (owner, 2026-09-10). Said
                          here because the guarantee is invisible otherwise —
                          the reader would have to notice an absence. */}
                        {category === 'procedural' && (
                          <p className="text-xs text-muted-foreground">
                            {t('memories.procedural_never_deleted')}
                          </p>
                        )}
                        {categoryMemories.map(memory => (
                          <div
                            key={memory.id}
                            // A pinned memory wears the theme tint (owner request
                            // 2026-08-05) — the peer-bubble pair, solid enough
                            // against the plain bg-card of its neighbours.
                            className={
                              memory.pinned
                                ? 'flex items-start gap-3 rounded-lg border p-3 bg-primary/10 border-primary/25'
                                : 'flex items-start gap-3 rounded-lg border p-3 bg-card'
                            }
                          >
                            <div className="flex shrink-0 items-center self-center sm:self-start">
                              <span
                                className="text-lg"
                                title={`${t('memories.field_emotional_weight')}: ${memory.emotional_weight}`}
                              >
                                {getEmotionalEmoji(memory.emotional_weight)}
                              </span>
                            </div>

                            {/* Content */}
                            <div className="flex-1 min-w-0">
                              {/* The pin sits IN FRONT of the content, on the
                                emoji's line (owner request 2026-08-05) —
                                inline, so wrapped text flows under it instead
                                of opening a gutter. Every size: the ⋮ menu
                                hides the pin BUTTON on phones, and on sm+ the
                                tinted action alone was a state easy to miss. */}
                              <p className="text-sm">
                                {memory.pinned && (
                                  <Pin
                                    className="mr-1 inline-block h-3.5 w-3.5 align-text-bottom text-primary"
                                    aria-hidden="true"
                                  />
                                )}
                                {memory.content}
                              </p>
                              {memory.usage_nuance && (
                                <p
                                  className={
                                    'text-xs mt-1 italic ' + memoryDetailTone(memory.pinned)
                                  }
                                >
                                  {memory.usage_nuance}
                                </p>
                              )}
                              {/* Trigger topic badge */}
                              {memory.trigger_topic && (
                                <div className="mt-1">
                                  {/* Theme-coloured, not grey: an active trigger
                                    topic is not an inactive element (owner
                                    rule 2026-08-05). */}
                                  <Badge variant="default" className="text-xs">
                                    {memory.trigger_topic}
                                  </Badge>
                                </div>
                              )}
                              {/* Metadata, ONE line worth reading: created date,
                                usage, importance, purge risk. The update and
                                last-access dates (two more full timestamps,
                                glyph-prefixed) said little and doubled the
                                row's footprint — a 390px screen wrapped this
                                into three lines of fragments. */}
                              <div
                                className={
                                  'flex flex-wrap items-center gap-x-2 gap-y-0.5 mt-1 ' +
                                  memoryDetailTone(memory.pinned)
                                }
                              >
                                {memory.created_at && (
                                  <span
                                    className="text-xs flex items-center gap-1"
                                    title={t('memories.created_at')}
                                  >
                                    <Clock className="h-3 w-3" aria-hidden="true" />
                                    {formatMemoryDate(memory.created_at, lng)}
                                  </span>
                                )}
                                {typeof memory.usage_count === 'number' &&
                                  memory.usage_count > 0 && (
                                    <span
                                      className="text-xs flex items-center gap-1"
                                      title={t('memories.usage_count')}
                                    >
                                      <RefreshCw className="h-3 w-3" aria-hidden="true" />
                                      {memory.usage_count}×
                                    </span>
                                  )}
                                {typeof memory.importance === 'number' && (
                                  <span className="text-xs" title={t('memories.field_importance')}>
                                    ★ {(memory.importance * 100).toFixed(0)}%
                                  </span>
                                )}
                                {isAtPurgeRisk(memory) && !memory.pinned && (
                                  <span
                                    className={
                                      'text-xs flex items-center gap-1 ' +
                                      (memory.purge_risk === 'imminent'
                                        ? 'text-destructive'
                                        : 'text-warning')
                                    }
                                    title={t('memories.purge_risk_tooltip')}
                                  >
                                    <AlertTriangle className="h-3 w-3" aria-hidden="true" />
                                    {memory.purge_risk === 'imminent'
                                      ? t('memories.purge_risk_badge_imminent')
                                      : t('memories.purge_risk_badge_at_risk')}
                                  </span>
                                )}
                              </div>
                            </div>

                            <RowActions
                              // Truncated: a memory's content is a paragraph, and
                              // an accessible name is an utterance, not a document.
                              menuLabel={t('common.actions_for', {
                                name:
                                  memory.content.length > 60
                                    ? `${memory.content.slice(0, 60)}…`
                                    : memory.content,
                              })}
                              actions={[
                                {
                                  key: 'pin',
                                  label: memory.pinned ? t('memories.unpin') : t('memories.pin'),
                                  icon: memory.pinned ? Pin : PinOff,
                                  loading: togglingPin === memory.id,
                                  iconClassName: memory.pinned
                                    ? 'text-primary hover:text-primary'
                                    : undefined,
                                  onSelect: () => void handleTogglePin(memory),
                                },
                                {
                                  key: 'edit',
                                  label: t('memories.edit'),
                                  icon: Pencil,
                                  disabled: updating,
                                  onSelect: () => handleOpenEdit(memory),
                                },
                                {
                                  key: 'delete',
                                  label: t('memories.delete'),
                                  icon: Trash2,
                                  tone: 'destructive',
                                  loading: deleting,
                                  onSelect: () => handleDeleteClick(memory),
                                },
                              ]}
                            />
                          </div>
                        ))}
                      </div>
                    </AccordionContent>
                  </AccordionItem>
                </Card>
              ))}
            </Accordion>
          )}

          {/* Info box */}
          <InfoBox>
            <div className="flex items-start gap-2">
              <AlertTriangle className="h-4 w-4 text-muted-foreground mt-0.5 shrink-0" />
              <div className="text-xs text-muted-foreground space-y-1">
                <p>{t('memories.privacy_note')}</p>
                <p>{t('memories.gdpr_note')}</p>
              </div>
            </div>
          </InfoBox>

          {/* Edit Dialog */}
          <Dialog open={editDialogOpen} onOpenChange={setEditDialogOpen}>
            <DialogContent className="sm:max-w-[500px] max-h-[90dvh] overflow-y-auto">
              <DialogHeader>
                <DialogTitle>{t('memories.edit_title')}</DialogTitle>
                <DialogDescription>{t('memories.edit_description')}</DialogDescription>
              </DialogHeader>
              <MemoryFormFields
                lng={lng}
                idPrefix="edit"
                form={editForm}
                onChange={setEditForm}
                limits={limits}
                contentLabel={t('memories.field_content')}
                categoryLabel={getCategoryLabel}
              />
              <DialogFooter>
                <Button variant="outline" onClick={handleCloseEdit} disabled={updating}>
                  <X className="h-4 w-4 mr-1" />
                  {t('common.cancel')}
                </Button>
                <Button
                  onClick={handleSaveEdit}
                  disabled={updating || !isMemoryTextSavable(editForm, limits)}
                >
                  {updating ? (
                    <LoadingSpinner size="default" className="mr-1" />
                  ) : (
                    <Save className="h-4 w-4 mr-1" />
                  )}
                  {t('common.save')}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>

          {/* Create Dialog */}
          <Dialog open={createDialogOpen} onOpenChange={setCreateDialogOpen}>
            <DialogContent className="sm:max-w-[500px] max-h-[90dvh] overflow-y-auto">
              <DialogHeader>
                <DialogTitle>{t('memories.create_title')}</DialogTitle>
                <DialogDescription>{t('memories.create_description')}</DialogDescription>
              </DialogHeader>
              <MemoryFormFields
                lng={lng}
                idPrefix="create"
                form={createForm}
                onChange={setCreateForm}
                limits={limits}
                contentLabel={`${t('memories.field_content')} *`}
                categoryLabel={getCategoryLabel}
                autoFocusContent
              />
              <DialogFooter>
                <Button variant="outline" onClick={handleCloseCreate} disabled={creating}>
                  <X className="h-4 w-4 mr-1" />
                  {t('common.cancel')}
                </Button>
                <Button
                  onClick={handleSaveCreate}
                  disabled={creating || !isMemoryTextSavable(createForm, limits)}
                >
                  {creating ? (
                    <LoadingSpinner size="default" className="mr-1" />
                  ) : (
                    <Plus className="h-4 w-4 mr-1" />
                  )}
                  {t('memories.create_button')}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>

          {/* Pinned Memory Delete Confirmation */}
          <AlertDialog
            open={memoryPendingDelete !== null}
            onOpenChange={open => {
              // Prevent closing while deletion is in progress
              if (!open && !deleting) {
                setMemoryPendingDelete(null);
              }
            }}
          >
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle className="flex items-center gap-2">
                  <Pin className="h-4 w-4 text-primary" />
                  {t('memories.confirm_delete_pinned_title')}
                </AlertDialogTitle>
                <AlertDialogDescription>
                  {t('memories.confirm_delete_pinned_description')}
                  {memoryPendingDelete && (
                    <span className="block mt-2 p-2 bg-card rounded text-foreground text-sm">
                      {memoryPendingDelete.content}
                    </span>
                  )}
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel disabled={deleting}>{t('common.cancel')}</AlertDialogCancel>
                <AlertDialogAction
                  onClick={handleConfirmDeletePinned}
                  disabled={deleting}
                  variant="destructive"
                >
                  {deleting ? (
                    <LoadingSpinner size="default" className="mr-1" />
                  ) : (
                    <Trash2 className="h-4 w-4 mr-1" />
                  )}
                  {t('memories.delete')}
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </>
      )}
    </div>
  );

  return (
    <SettingsSection
      value="memories"
      title={t('memories.settings.title')}
      description={t('memories.settings.description')}
      icon={BookUser}
    >
      {content}
    </SettingsSection>
  );
}
