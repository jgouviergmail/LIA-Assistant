'use client';

import { useState, useMemo } from 'react';
import { Brain, Trash2, Download, AlertTriangle, Pencil, Save, X, Clock, Pin, PinOff, RefreshCw, Plus } from 'lucide-react';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { InfoBox } from '@/components/ui/info-box';
import { Label } from '@/components/ui/label';
import { Slider } from '@/components/ui/slider';
import { Switch } from '@/components/ui/switch';
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
import { useTranslation } from '@/i18n/client';
import { type Language, getIntlLocale } from '@/i18n/settings';
import { SettingsSection } from '@/components/settings/SettingsSection';
import { useMemories, getEmotionalEmoji, type MemoryCategory, type Memory } from '@/hooks/useMemories';
import { useAuth } from '@/hooks/useAuth';
import apiClient from '@/lib/api-client';
import { toast } from 'sonner';
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
import type { BaseSettingsProps } from '@/types/settings';

const CATEGORY_ICONS: Record<MemoryCategory, string> = {
  preference: '💡',
  personal: '📋',
  relationship: '👥',
  event: '📅',
  pattern: '🔄',
  sensitivity: '⚠️',
};

interface EditFormData {
  content: string;
  category: MemoryCategory;
  usage_nuance: string;
  emotional_weight: number;
  importance: number;
  trigger_topic: string;
}

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

export function MemorySettings({ lng, collapsible = true }: BaseSettingsProps) {
  const { t } = useTranslation(lng);
  const { user, refreshUser } = useAuth();
  const {
    memories,
    total,
    loading,
    creating,
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

  // State for mobile action popup
  const [mobileActionMemory, setMobileActionMemory] = useState<Memory | null>(null);

  // State for pinned memory delete confirmation
  const [memoryPendingDelete, setMemoryPendingDelete] = useState<Memory | null>(null);

  const handleTogglePin = async (memory: Memory) => {
    setTogglingPin(memory.id);
    try {
      await togglePin(memory.id, !memory.pinned);
      toast.success(
        memory.pinned
          ? t('memories.unpin_success')
          : t('memories.pin_success')
      );
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
      toast.success(
        enabled
          ? t('memories.enabled_success')
          : t('memories.disabled_success')
      );
    } catch {
      toast.error(t('common.error'));
    } finally {
      setUpdatingMemoryEnabled(false);
    }
  };

  // Create dialog state
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [createForm, setCreateForm] = useState<EditFormData>({
    content: '',
    category: 'personal',
    usage_nuance: '',
    emotional_weight: 0,
    importance: 0.7,
    trigger_topic: '',
  });

  // Edit dialog state
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [editingMemoryId, setEditingMemoryId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<EditFormData>({
    content: '',
    category: 'personal',
    usage_nuance: '',
    emotional_weight: 0,
    importance: 0.7,
    trigger_topic: '',
  });

  // Create dialog handlers
  const handleOpenCreate = () => {
    setCreateForm({
      content: '',
      category: 'personal',
      usage_nuance: '',
      emotional_weight: 0,
      importance: 0.7,
      trigger_topic: '',
    });
    setCreateDialogOpen(true);
  };

  const handleCloseCreate = () => {
    setCreateDialogOpen(false);
    setCreateForm({
      content: '',
      category: 'personal',
      usage_nuance: '',
      emotional_weight: 0,
      importance: 0.7,
      trigger_topic: '',
    });
  };

  const handleSaveCreate = async () => {
    if (!createForm.content.trim()) return;
    try {
      await createMemory({
        content: createForm.content,
        category: createForm.category,
        usage_nuance: createForm.usage_nuance || undefined,
        emotional_weight: createForm.emotional_weight,
        importance: createForm.importance,
        trigger_topic: createForm.trigger_topic || undefined,
      });
      toast.success(t('memories.create_success'));
      handleCloseCreate();
    } catch {
      toast.error(t('memories.create_error'));
    }
  };

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
    setEditForm({
      content: '',
      category: 'personal',
      usage_nuance: '',
      emotional_weight: 0,
      importance: 0.7,
      trigger_topic: '',
    });
  };

  const handleSaveEdit = async () => {
    if (!editingMemoryId) return;
    try {
      await updateMemory(editingMemoryId, {
        content: editForm.content,
        category: editForm.category,
        usage_nuance: editForm.usage_nuance || undefined,
        emotional_weight: editForm.emotional_weight,
        importance: editForm.importance,
        trigger_topic: editForm.trigger_topic || undefined,
      });
      toast.success(t('memories.update_success'));
      handleCloseEdit();
    } catch {
      toast.error(t('memories.update_error'));
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
    window.open('/api/v1/memories/export', '_blank');
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
          <div className="flex items-center justify-between p-3 rounded-lg border bg-card">
            <div className="flex-1">
              <p className="text-sm font-medium">{t('memories.enable_memory')}</p>
              <p className="text-xs text-muted-foreground">{t('memories.enable_description')}</p>
            </div>
            <Switch
              checked={user?.memory_enabled ?? true}
              onCheckedChange={handleToggleMemoryEnabled}
              disabled={updatingMemoryEnabled}
            />
          </div>

          {/* Stats and Actions */}
          <div className="flex items-center justify-between">
            <div className="text-sm text-muted-foreground">
              {total} {total === 1 ? 'mémoire' : 'mémoires'}
            </div>
            <div className="flex gap-2">
              {/* Create button */}
              <Button variant="outline" size="sm" onClick={handleOpenCreate}>
                <Plus className="h-4 w-4 mr-1" />
                <span className="hidden sm:inline">{t('memories.create')}</span>
              </Button>
              {/* Export button - hidden on mobile */}
              <Button variant="outline" size="sm" onClick={handleExport} disabled={total === 0} className="hidden lg:flex">
                <Download className="h-4 w-4 mr-1" />
                {t('memories.export')}
              </Button>
              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button variant="destructive" size="sm" disabled={total === 0 || deletingAll}>
                    {deletingAll ? (
                      <LoadingSpinner size="default" className="mr-1" />
                    ) : (
                      <Trash2 className="h-4 w-4 mr-1" />
                    )}
                    {t('memories.delete_all')}
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>
                      {t('memories.confirm_delete_all_title')}
                    </AlertDialogTitle>
                    <AlertDialogDescription>
                      {pinnedCount > 0 ? (
                        <>
                          {t('memories.confirm_delete_all_with_pinned', { count: pinnedCount })}
                        </>
                      ) : (
                        <>
                          {t('memories.confirm_delete_all_description')}
                        </>
                      )}
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
                    {pinnedCount > 0 ? (
                      <div className="flex flex-col-reverse sm:flex-row gap-2">
                        <AlertDialogAction
                          onClick={() => handleDeleteAll(true)}
                          className="bg-orange-600 hover:bg-orange-700"
                        >
                          <Pin className="h-4 w-4 mr-1" />
                          {t('memories.delete_all_keep_pinned')}
                        </AlertDialogAction>
                        <AlertDialogAction
                          onClick={() => handleDeleteAll(false)}
                          className="bg-destructive hover:bg-destructive/90"
                        >
                          <Trash2 className="h-4 w-4 mr-1" />
                          {t('memories.delete_all_including_pinned')}
                        </AlertDialogAction>
                      </div>
                    ) : (
                      <AlertDialogAction
                        onClick={() => handleDeleteAll(false)}
                        className="bg-destructive hover:bg-destructive/90"
                      >
                        <Trash2 className="h-4 w-4 mr-1" />
                        {t('memories.delete_all_including_pinned')}
                      </AlertDialogAction>
                    )}
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            </div>
          </div>

          {/* Memories List */}
          {total === 0 ? (
            <div className="rounded-lg border border-dashed p-6 text-center text-muted-foreground">
              <Brain className="h-8 w-8 mx-auto mb-2 opacity-50" />
              <p>{t('memories.empty')}</p>
              <p className="text-xs mt-1">
                {t('memories.empty_hint')}
              </p>
            </div>
          ) : (
            <Accordion type="multiple" defaultValue={[]} className="space-y-2">
              {Object.entries(groupedMemories).map(([category, categoryMemories]) => (
                <AccordionItem key={category} value={category} className="border rounded-lg px-3">
                  <AccordionTrigger className="py-3 hover:no-underline">
                    <div className="flex items-center gap-2">
                      <span>{CATEGORY_ICONS[category as MemoryCategory]}</span>
                      <span className="font-medium">{getCategoryLabel(category as MemoryCategory)}</span>
                      <span className="text-muted-foreground text-sm">({categoryMemories.length})</span>
                    </div>
                  </AccordionTrigger>
                  <AccordionContent>
                  <div className="space-y-2">
                    {categoryMemories.map(memory => (
                      <div
                        key={memory.id}
                        className="group flex items-start gap-3 rounded-lg border p-3 bg-card hover:bg-accent/50 transition-colors cursor-pointer lg:cursor-default"
                        onClick={() => {
                          // On mobile/tablet, open action popup
                          if (window.innerWidth < 1024) {
                            setMobileActionMemory(memory);
                          }
                        }}
                      >
                        {/* Emotional indicator + Pinned icon (mobile/tablet) */}
                        {/* FIX 2025-12-29: self-center on mobile for vertical centering */}
                        <div className="flex flex-col items-center shrink-0 gap-0.5 self-center lg:self-start">
                          <span
                            className="text-lg"
                            title={`${t('memories.field_emotional_weight')}: ${memory.emotional_weight}`}
                          >
                            {getEmotionalEmoji(memory.emotional_weight)}
                          </span>
                          {/* Pinned indicator - visible on mobile/tablet only */}
                          {memory.pinned && (
                            <Pin className="h-3 w-3 text-primary lg:hidden" />
                          )}
                        </div>

                        {/* Content */}
                        <div className="flex-1 min-w-0">
                          <p className="text-sm">{memory.content}</p>
                          {memory.usage_nuance && (
                            <p className="text-xs text-muted-foreground mt-1 italic">
                              {memory.usage_nuance}
                            </p>
                          )}
                          {/* Trigger topic badge */}
                          {memory.trigger_topic && (
                            <div className="mt-1">
                              <Badge variant="secondary" className="text-xs">
                                {memory.trigger_topic}
                              </Badge>
                            </div>
                          )}
                          {/* Metadata: dates, usage count, importance */}
                          <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 mt-1">
                            {memory.created_at && (
                              <span
                                className="text-xs text-muted-foreground flex items-center gap-1"
                                title={t('memories.created_at')}
                              >
                                <Clock className="h-3 w-3" />
                                {formatMemoryDate(memory.created_at, lng)}
                              </span>
                            )}
                            {memory.updated_at && memory.updated_at !== memory.created_at && (
                              <span
                                className="text-xs text-muted-foreground flex items-center gap-1"
                                title={t('memories.updated_at')}
                              >
                                ✏️ {formatMemoryDate(memory.updated_at, lng)}
                              </span>
                            )}
                            {memory.last_accessed_at && (
                              <span
                                className="text-xs text-muted-foreground flex items-center gap-1"
                                title={t('memories.last_accessed')}
                              >
                                👁️ {formatMemoryDate(memory.last_accessed_at, lng)}
                              </span>
                            )}
                            {typeof memory.usage_count === 'number' && memory.usage_count > 0 && (
                              <span
                                className="text-xs text-muted-foreground flex items-center gap-1"
                                title={t('memories.usage_count')}
                              >
                                <RefreshCw className="h-3 w-3" />
                                {memory.usage_count}×
                              </span>
                            )}
                            {typeof memory.importance === 'number' && (
                              <span
                                className="text-xs text-muted-foreground"
                                title={t('memories.field_importance')}
                              >
                                ★ {(memory.importance * 100).toFixed(0)}%
                              </span>
                            )}
                          </div>
                        </div>

                        {/* Action buttons - hidden on mobile/tablet (use popup instead) */}
                        <div className="hidden lg:flex gap-1 shrink-0">
                          {/* Pin button - always visible when pinned */}
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => handleTogglePin(memory)}
                            disabled={togglingPin === memory.id}
                            title={memory.pinned
                              ? t('memories.unpin')
                              : t('memories.pin')
                            }
                            className={memory.pinned ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'}
                          >
                            {togglingPin === memory.id ? (
                              <LoadingSpinner size="default" />
                            ) : memory.pinned ? (
                              <Pin className="h-4 w-4 text-primary" />
                            ) : (
                              <PinOff className="h-4 w-4 text-muted-foreground hover:text-foreground" />
                            )}
                          </Button>
                          {/* Edit button */}
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => handleOpenEdit(memory)}
                            disabled={updating}
                            title={t('memories.edit')}
                            className="opacity-0 group-hover:opacity-100"
                          >
                            <Pencil className="h-4 w-4 text-muted-foreground hover:text-foreground" />
                          </Button>
                          {/* Delete button */}
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => handleDeleteClick(memory)}
                            disabled={deleting}
                            title={t('memories.delete')}
                            className="opacity-0 group-hover:opacity-100"
                          >
                            {deleting ? (
                              <LoadingSpinner size="default" />
                            ) : (
                              <Trash2 className="h-4 w-4 text-destructive" />
                            )}
                          </Button>
                        </div>
                      </div>
                    ))}
                  </div>
                  </AccordionContent>
                </AccordionItem>
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
            <DialogContent className="sm:max-w-[500px] max-h-[90vh] overflow-y-auto">
              <DialogHeader>
                <DialogTitle>{t('memories.edit_title')}</DialogTitle>
                <DialogDescription>
                  {t('memories.edit_description')}
                </DialogDescription>
              </DialogHeader>
              <div className="grid gap-4 py-4">
                {/* Content */}
                <div className="grid gap-2">
                  <Label htmlFor="edit-content">{t('memories.field_content')}</Label>
                  <Textarea
                    id="edit-content"
                    value={editForm.content}
                    onChange={(e) => setEditForm({ ...editForm, content: e.target.value })}
                    placeholder={t('memories.content_placeholder')}
                    rows={3}
                  />
                </div>
                {/* Category */}
                <div className="grid gap-2">
                  <Label htmlFor="edit-category">{t('memories.field_category')}</Label>
                  <Select
                    value={editForm.category}
                    onValueChange={(value) => setEditForm({ ...editForm, category: value as MemoryCategory })}
                  >
                    <SelectTrigger id="edit-category">
                      <SelectValue placeholder={t('memories.select_category')} />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="preference">
                        {CATEGORY_ICONS.preference} {getCategoryLabel('preference')}
                      </SelectItem>
                      <SelectItem value="personal">
                        {CATEGORY_ICONS.personal} {getCategoryLabel('personal')}
                      </SelectItem>
                      <SelectItem value="relationship">
                        {CATEGORY_ICONS.relationship} {getCategoryLabel('relationship')}
                      </SelectItem>
                      <SelectItem value="event">
                        {CATEGORY_ICONS.event} {getCategoryLabel('event')}
                      </SelectItem>
                      <SelectItem value="pattern">
                        {CATEGORY_ICONS.pattern} {getCategoryLabel('pattern')}
                      </SelectItem>
                      <SelectItem value="sensitivity">
                        {CATEGORY_ICONS.sensitivity} {getCategoryLabel('sensitivity')}
                      </SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                {/* Usage Nuance */}
                <div className="grid gap-2">
                  <Label htmlFor="edit-nuance">{t('memories.field_usage_nuance')}</Label>
                  <Input
                    id="edit-nuance"
                    value={editForm.usage_nuance}
                    onChange={(e) => setEditForm({ ...editForm, usage_nuance: e.target.value })}
                    placeholder={t('memories.nuance_placeholder')}
                  />
                  <p className="text-xs text-muted-foreground">
                    {t('memories.nuance_help')}
                  </p>
                </div>
                {/* Trigger Topic */}
                <div className="grid gap-2">
                  <Label htmlFor="edit-trigger">{t('memories.field_trigger_topic')}</Label>
                  <Input
                    id="edit-trigger"
                    value={editForm.trigger_topic}
                    onChange={(e) => setEditForm({ ...editForm, trigger_topic: e.target.value })}
                    placeholder={t('memories.trigger_placeholder')}
                  />
                  <p className="text-xs text-muted-foreground">
                    {t('memories.trigger_help')}
                  </p>
                </div>
                {/* Emotional Weight */}
                <div className="grid gap-2">
                  <div className="flex items-center justify-between">
                    <Label htmlFor="edit-emotional">{t('memories.field_emotional_weight')}</Label>
                    <span className="text-sm flex items-center gap-1">
                      {getEmotionalEmoji(editForm.emotional_weight)} {editForm.emotional_weight}
                    </span>
                  </div>
                  <Slider
                    id="edit-emotional"
                    min={-10}
                    max={10}
                    step={1}
                    value={[editForm.emotional_weight]}
                    onValueChange={(value: number[]) => setEditForm({ ...editForm, emotional_weight: value[0] })}
                    className="w-full"
                  />
                  <div className="flex justify-between text-xs text-muted-foreground">
                    <span>-10 ({t('memories.emotional_negative')})</span>
                    <span>+10 ({t('memories.emotional_positive')})</span>
                  </div>
                </div>
                {/* Importance */}
                <div className="grid gap-2">
                  <div className="flex items-center justify-between">
                    <Label htmlFor="edit-importance">{t('memories.field_importance')}</Label>
                    <span className="text-sm">★ {(editForm.importance * 100).toFixed(0)}%</span>
                  </div>
                  <Slider
                    id="edit-importance"
                    min={0}
                    max={1}
                    step={0.1}
                    value={[editForm.importance]}
                    onValueChange={(value: number[]) => setEditForm({ ...editForm, importance: value[0] })}
                    className="w-full"
                  />
                  <div className="flex justify-between text-xs text-muted-foreground">
                    <span>0% ({t('memories.importance_low')})</span>
                    <span>100% ({t('memories.importance_high')})</span>
                  </div>
                </div>
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={handleCloseEdit} disabled={updating}>
                  <X className="h-4 w-4 mr-1" />
                  {t('common.cancel')}
                </Button>
                <Button onClick={handleSaveEdit} disabled={updating || !editForm.content.trim()}>
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
            <DialogContent className="sm:max-w-[500px] max-h-[90vh] overflow-y-auto">
              <DialogHeader>
                <DialogTitle>{t('memories.create_title')}</DialogTitle>
                <DialogDescription>
                  {t('memories.create_description')}
                </DialogDescription>
              </DialogHeader>
              <div className="grid gap-4 py-4">
                {/* Content */}
                <div className="grid gap-2">
                  <Label htmlFor="create-content">{t('memories.field_content')} *</Label>
                  <Textarea
                    id="create-content"
                    value={createForm.content}
                    onChange={(e) => setCreateForm({ ...createForm, content: e.target.value })}
                    placeholder={t('memories.content_placeholder')}
                    rows={3}
                    autoFocus
                  />
                </div>
                {/* Category */}
                <div className="grid gap-2">
                  <Label htmlFor="create-category">{t('memories.field_category')}</Label>
                  <Select
                    value={createForm.category}
                    onValueChange={(value) => setCreateForm({ ...createForm, category: value as MemoryCategory })}
                  >
                    <SelectTrigger id="create-category">
                      <SelectValue placeholder={t('memories.select_category')} />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="preference">
                        {CATEGORY_ICONS.preference} {getCategoryLabel('preference')}
                      </SelectItem>
                      <SelectItem value="personal">
                        {CATEGORY_ICONS.personal} {getCategoryLabel('personal')}
                      </SelectItem>
                      <SelectItem value="relationship">
                        {CATEGORY_ICONS.relationship} {getCategoryLabel('relationship')}
                      </SelectItem>
                      <SelectItem value="event">
                        {CATEGORY_ICONS.event} {getCategoryLabel('event')}
                      </SelectItem>
                      <SelectItem value="pattern">
                        {CATEGORY_ICONS.pattern} {getCategoryLabel('pattern')}
                      </SelectItem>
                      <SelectItem value="sensitivity">
                        {CATEGORY_ICONS.sensitivity} {getCategoryLabel('sensitivity')}
                      </SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                {/* Usage Nuance */}
                <div className="grid gap-2">
                  <Label htmlFor="create-nuance">{t('memories.field_usage_nuance')}</Label>
                  <Input
                    id="create-nuance"
                    value={createForm.usage_nuance}
                    onChange={(e) => setCreateForm({ ...createForm, usage_nuance: e.target.value })}
                    placeholder={t('memories.nuance_placeholder')}
                  />
                  <p className="text-xs text-muted-foreground">
                    {t('memories.nuance_help')}
                  </p>
                </div>
                {/* Trigger Topic */}
                <div className="grid gap-2">
                  <Label htmlFor="create-trigger">{t('memories.field_trigger_topic')}</Label>
                  <Input
                    id="create-trigger"
                    value={createForm.trigger_topic}
                    onChange={(e) => setCreateForm({ ...createForm, trigger_topic: e.target.value })}
                    placeholder={t('memories.trigger_placeholder')}
                  />
                  <p className="text-xs text-muted-foreground">
                    {t('memories.trigger_help')}
                  </p>
                </div>
                {/* Emotional Weight */}
                <div className="grid gap-2">
                  <div className="flex items-center justify-between">
                    <Label htmlFor="create-emotional">{t('memories.field_emotional_weight')}</Label>
                    <span className="text-sm flex items-center gap-1">
                      {getEmotionalEmoji(createForm.emotional_weight)} {createForm.emotional_weight}
                    </span>
                  </div>
                  <Slider
                    id="create-emotional"
                    min={-10}
                    max={10}
                    step={1}
                    value={[createForm.emotional_weight]}
                    onValueChange={(value: number[]) => setCreateForm({ ...createForm, emotional_weight: value[0] })}
                    className="w-full"
                  />
                  <div className="flex justify-between text-xs text-muted-foreground">
                    <span>-10 ({t('memories.emotional_negative')})</span>
                    <span>+10 ({t('memories.emotional_positive')})</span>
                  </div>
                </div>
                {/* Importance */}
                <div className="grid gap-2">
                  <div className="flex items-center justify-between">
                    <Label htmlFor="create-importance">{t('memories.field_importance')}</Label>
                    <span className="text-sm">★ {(createForm.importance * 100).toFixed(0)}%</span>
                  </div>
                  <Slider
                    id="create-importance"
                    min={0}
                    max={1}
                    step={0.1}
                    value={[createForm.importance]}
                    onValueChange={(value: number[]) => setCreateForm({ ...createForm, importance: value[0] })}
                    className="w-full"
                  />
                  <div className="flex justify-between text-xs text-muted-foreground">
                    <span>0% ({t('memories.importance_low')})</span>
                    <span>100% ({t('memories.importance_high')})</span>
                  </div>
                </div>
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={handleCloseCreate} disabled={creating}>
                  <X className="h-4 w-4 mr-1" />
                  {t('common.cancel')}
                </Button>
                <Button onClick={handleSaveCreate} disabled={creating || !createForm.content.trim()}>
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

          {/* Mobile/Tablet Action Popup */}
          <Dialog open={mobileActionMemory !== null} onOpenChange={(open) => !open && setMobileActionMemory(null)}>
            <DialogContent className="lg:hidden max-w-[90vw] rounded-lg">
              <DialogHeader>
                <DialogTitle className="text-base flex items-center gap-2">
                  {mobileActionMemory && getEmotionalEmoji(mobileActionMemory.emotional_weight)}
                  {t('memories.actions_title')}
                </DialogTitle>
                <DialogDescription className="text-sm line-clamp-2">
                  {mobileActionMemory?.content}
                </DialogDescription>
              </DialogHeader>
              <div className="flex flex-col gap-2 py-2">
                {/* Pin/Unpin button */}
                <Button
                  variant="outline"
                  className="w-full justify-start gap-3"
                  onClick={() => {
                    if (mobileActionMemory) {
                      handleTogglePin(mobileActionMemory);
                      setMobileActionMemory(null);
                    }
                  }}
                  disabled={togglingPin === mobileActionMemory?.id}
                >
                  {togglingPin === mobileActionMemory?.id ? (
                    <LoadingSpinner size="default" />
                  ) : mobileActionMemory?.pinned ? (
                    <PinOff className="h-4 w-4" />
                  ) : (
                    <Pin className="h-4 w-4" />
                  )}
                  {mobileActionMemory?.pinned
                    ? t('memories.unpin')
                    : t('memories.pin')
                  }
                </Button>

                {/* Edit button */}
                <Button
                  variant="outline"
                  className="w-full justify-start gap-3"
                  onClick={() => {
                    if (mobileActionMemory) {
                      handleOpenEdit(mobileActionMemory);
                      setMobileActionMemory(null);
                    }
                  }}
                >
                  <Pencil className="h-4 w-4" />
                  {t('memories.edit')}
                </Button>

                {/* Delete button */}
                <Button
                  variant="outline"
                  className="w-full justify-start gap-3 text-destructive hover:text-destructive"
                  onClick={() => {
                    if (mobileActionMemory) {
                      handleDeleteClick(mobileActionMemory);
                      setMobileActionMemory(null);
                    }
                  }}
                  disabled={deleting}
                >
                  {deleting ? (
                    <LoadingSpinner size="default" />
                  ) : (
                    <Trash2 className="h-4 w-4" />
                  )}
                  {t('memories.delete')}
                </Button>
              </div>
            </DialogContent>
          </Dialog>

          {/* Pinned Memory Delete Confirmation */}
          <AlertDialog
            open={memoryPendingDelete !== null}
            onOpenChange={(open) => {
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
                    <span className="block mt-2 p-2 bg-muted rounded text-foreground text-sm">
                      {memoryPendingDelete.content}
                    </span>
                  )}
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel disabled={deleting}>
                  {t('common.cancel')}
                </AlertDialogCancel>
                <AlertDialogAction
                  onClick={handleConfirmDeletePinned}
                  disabled={deleting}
                  className="bg-destructive hover:bg-destructive/90"
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

  if (!collapsible) {
    return content;
  }

  return (
    <SettingsSection
      value="memories"
      title={t('memories.settings.title')}
      description={t('memories.settings.description')}
      icon={Brain}
    >
      {content}
    </SettingsSection>
  );
}
