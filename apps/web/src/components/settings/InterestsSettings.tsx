'use client';

import { useState, useMemo } from 'react';
import { Sparkles, Trash2, Plus, Ban, Clock, Pencil, Download } from 'lucide-react';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { InfoBox } from '@/components/ui/info-box';
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
import {
  useInterests,
  INTEREST_CATEGORY_ICONS,
  getWeightBadgeVariant,
  type InterestCategory,
  type Interest,
  type InterestFeedback,
  type InterestUpdate,
} from '@/hooks/useInterests';
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

/**
 * Format a date for display using the user's locale.
 */
function formatInterestDate(dateString: string | null | undefined, lng: Language): string {
  if (!dateString) return '-';
  try {
    const date = new Date(dateString);
    return new Intl.DateTimeFormat(getIntlLocale(lng), {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    }).format(date);
  } catch {
    return dateString;
  }
}

/**
 * Sort interests by weight descending.
 */
function sortInterestsByWeight(interests: Interest[]): Interest[] {
  return [...interests].sort((a, b) => b.weight - a.weight);
}

/**
 * Generate hour options for select.
 */
function generateHourOptions() {
  return Array.from({ length: 24 }, (_, i) => ({
    value: i.toString(),
    label: `${i.toString().padStart(2, '0')}:00`,
  }));
}

export function InterestsSettings({ lng, collapsible = true }: BaseSettingsProps) {
  const { t } = useTranslation(lng);
  const {
    interests,
    total,
    blockedCount,
    categories,
    settings,
    loading,
    settingsLoading,
    creating,
    deleting,
    deletingAll,
    submittingFeedback,
    updatingSettings,
    updating,
    createInterest,
    deleteInterest,
    deleteAllInterests,
    submitFeedback,
    updateSettings,
    updateInterest,
  } = useInterests();

  // State for create dialog
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [createForm, setCreateForm] = useState({
    topic: '',
    category: 'technology' as InterestCategory,
  });

  // State for edit dialog
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [editingInterest, setEditingInterest] = useState<Interest | null>(null);
  const [editForm, setEditForm] = useState({
    topic: '',
    category: 'technology' as InterestCategory,
    positive_signals: 1,
    negative_signals: 0,
  });

  // State for delete confirmation
  const [pendingDelete, setPendingDelete] = useState<Interest | null>(null);

  // State for mobile action popup
  const [mobileActionInterest, setMobileActionInterest] = useState<Interest | null>(null);

  // Hour options
  const hourOptions = useMemo(() => generateHourOptions(), []);

  // Sort interests by weight
  const sortedInterests = useMemo(() => sortInterestsByWeight(interests), [interests]);

  // Group active interests by category
  const groupedByCategory = useMemo(() => {
    const activeInterests = sortedInterests.filter(i => i.status === 'active');
    return activeInterests.reduce(
      (acc, interest) => {
        const cat = interest.category;
        if (!acc[cat]) acc[cat] = [];
        acc[cat].push(interest);
        return acc;
      },
      {} as Record<InterestCategory, Interest[]>
    );
  }, [sortedInterests]);

  // Blocked interests (separate section)
  const blockedInterests = useMemo(
    () => sortedInterests.filter(i => i.status === 'blocked'),
    [sortedInterests]
  );

  // Get localized category label
  const getCategoryLabel = (category: InterestCategory): string => {
    return t(`interests.categories.${category}`) || category;
  };

  // Handlers
  const handleOpenCreate = () => {
    setCreateForm({ topic: '', category: 'technology' });
    setCreateDialogOpen(true);
  };

  const handleCloseCreate = () => {
    setCreateDialogOpen(false);
    setCreateForm({ topic: '', category: 'technology' });
  };

  const handleSaveCreate = async () => {
    if (!createForm.topic.trim()) return;
    try {
      await createInterest(createForm);
      toast.success(t('interests.create_success'));
      handleCloseCreate();
    } catch {
      toast.error(t('interests.create_error'));
    }
  };

  const handleDelete = async (interest: Interest) => {
    try {
      await deleteInterest(interest.id);
      toast.success(t('interests.delete_success'));
    } catch {
      toast.error(t('interests.delete_error'));
    }
  };

  const handleFeedback = async (interest: Interest, feedback: InterestFeedback) => {
    try {
      await submitFeedback(interest.id, feedback);
      if (feedback === 'block') {
        toast.success(t('interests.blocked_success'));
      } else {
        toast.success(t('interests.feedback_success'));
      }
    } catch {
      toast.error(t('interests.feedback_error'));
    }
  };

  const handleOpenEdit = (interest: Interest) => {
    setEditingInterest(interest);
    setEditForm({
      topic: interest.topic,
      category: interest.category,
      positive_signals: interest.positive_signals,
      negative_signals: interest.negative_signals,
    });
    setEditDialogOpen(true);
  };

  const handleCloseEdit = () => {
    setEditDialogOpen(false);
    setEditingInterest(null);
  };

  const handleSaveEdit = async () => {
    if (!editingInterest || !editForm.topic.trim()) return;

    // Build update payload with only changed fields
    const updates: InterestUpdate = {};
    if (editForm.topic !== editingInterest.topic) updates.topic = editForm.topic;
    if (editForm.category !== editingInterest.category) updates.category = editForm.category;
    if (editForm.positive_signals !== editingInterest.positive_signals)
      updates.positive_signals = editForm.positive_signals;
    if (editForm.negative_signals !== editingInterest.negative_signals)
      updates.negative_signals = editForm.negative_signals;

    // Skip API call if nothing changed
    if (Object.keys(updates).length === 0) {
      handleCloseEdit();
      return;
    }

    try {
      await updateInterest(editingInterest.id, updates);
      toast.success(t('interests.update_success'));
      handleCloseEdit();
    } catch {
      toast.error(t('interests.update_error'));
    }
  };

  const handleToggleEnabled = async (enabled: boolean) => {
    try {
      await updateSettings({ interests_enabled: enabled });
      toast.success(enabled ? t('interests.enabled_success') : t('interests.disabled_success'));
    } catch {
      toast.error(t('interests.settings_error'));
    }
  };

  const handleUpdateHours = async (field: 'start' | 'end', value: number) => {
    try {
      if (field === 'start') {
        await updateSettings({ interests_notify_start_hour: value });
      } else {
        await updateSettings({ interests_notify_end_hour: value });
      }
      toast.success(t('interests.settings_updated'));
    } catch {
      toast.error(t('interests.settings_error'));
    }
  };

  const handleUpdateFrequency = async (field: 'min' | 'max', value: number) => {
    try {
      if (field === 'min') {
        await updateSettings({ interests_notify_min_per_day: value });
      } else {
        await updateSettings({ interests_notify_max_per_day: value });
      }
      toast.success(t('interests.settings_updated'));
    } catch {
      toast.error(t('interests.settings_error'));
    }
  };

  const handleDeleteAll = async () => {
    try {
      await deleteAllInterests();
      toast.success(t('interests.delete_all_success'));
    } catch {
      toast.error(t('interests.delete_all_error'));
    }
  };

  const content = (
    <div className="space-y-4">
      {loading || settingsLoading ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <LoadingSpinner size="default" />
          {t('common.loading')}
        </div>
      ) : (
        <>
          {/* Global Toggle */}
          <div className="flex items-center justify-between p-3 rounded-lg border bg-card">
            <div className="flex-1">
              <p className="text-sm font-medium">{t('interests.enable_proactive')}</p>
              <p className="text-xs text-muted-foreground">{t('interests.enable_description')}</p>
            </div>
            <Switch
              checked={settings?.interests_enabled ?? false}
              onCheckedChange={handleToggleEnabled}
              disabled={updatingSettings}
            />
          </div>

          {/* Settings Panel */}
          {settings && (
            <div className="space-y-4 p-4 rounded-lg border bg-muted/30">
              {/* Time Window */}
              <div className="space-y-2">
                <Label className="flex items-center gap-2">
                  <Clock className="h-4 w-4" />
                  {t('interests.notification_hours')}
                </Label>
                <div className="flex items-center gap-2">
                  <Select
                    value={settings.interests_notify_start_hour.toString()}
                    onValueChange={v => handleUpdateHours('start', parseInt(v))}
                  >
                    <SelectTrigger className="w-24">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {hourOptions.map(opt => (
                        <SelectItem key={opt.value} value={opt.value}>
                          {opt.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <span className="text-muted-foreground">-</span>
                  <Select
                    value={settings.interests_notify_end_hour.toString()}
                    onValueChange={v => handleUpdateHours('end', parseInt(v))}
                  >
                    <SelectTrigger className="w-24">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {hourOptions.map(opt => (
                        <SelectItem key={opt.value} value={opt.value}>
                          {opt.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <p className="text-xs text-muted-foreground">{t('interests.hours_description')}</p>
              </div>

              {/* Frequency */}
              <div className="space-y-2">
                <Label>{t('interests.notification_frequency')}</Label>
                <div className="flex items-center gap-2">
                  <Select
                    value={settings.interests_notify_min_per_day.toString()}
                    onValueChange={v => handleUpdateFrequency('min', parseInt(v))}
                  >
                    <SelectTrigger className="w-20">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {Array.from({ length: 10 }, (_, i) => i + 1).map(n => (
                        <SelectItem key={n} value={n.toString()}>
                          {n}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <span className="text-muted-foreground">-</span>
                  <Select
                    value={settings.interests_notify_max_per_day.toString()}
                    onValueChange={v => handleUpdateFrequency('max', parseInt(v))}
                  >
                    <SelectTrigger className="w-20">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {Array.from({ length: 10 }, (_, i) => i + 1).map(n => (
                        <SelectItem key={n} value={n.toString()}>
                          {n}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <span className="text-sm text-muted-foreground">{t('interests.per_day')}</span>
                </div>
              </div>
            </div>
          )}

          {/* Stats and Actions */}
          <div className="flex items-center justify-between">
            <div className="text-sm text-muted-foreground">
              {total} {t('interests.count', { count: total })}
              {blockedCount > 0 && (
                <span className="ml-2 text-xs">
                  ({blockedCount} {t('interests.blocked')})
                </span>
              )}
            </div>
            <div className="flex gap-2">
              {/* Create button */}
              <Button variant="outline" size="sm" onClick={handleOpenCreate}>
                <Plus className="h-4 w-4 mr-1" />
                <span className="hidden sm:inline">{t('interests.create')}</span>
              </Button>
              {/* Export button - hidden on mobile */}
              <Button
                variant="outline"
                size="sm"
                onClick={() => window.open('/api/v1/interests/export', '_blank')}
                disabled={total === 0}
                className="hidden lg:flex"
              >
                <Download className="h-4 w-4 mr-1" />
                {t('interests.export')}
              </Button>
              {/* Delete all button */}
              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button variant="destructive" size="sm" disabled={total === 0 || deletingAll}>
                    {deletingAll ? (
                      <LoadingSpinner size="default" className="mr-1" />
                    ) : (
                      <Trash2 className="h-4 w-4 mr-1" />
                    )}
                    {t('interests.delete_all')}
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>{t('interests.confirm_delete_all_title')}</AlertDialogTitle>
                    <AlertDialogDescription>
                      {t('interests.confirm_delete_all_description')}
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
                    <AlertDialogAction
                      onClick={handleDeleteAll}
                      className="bg-destructive hover:bg-destructive/90"
                    >
                      <Trash2 className="h-4 w-4 mr-1" />
                      {t('interests.delete_all_confirm')}
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            </div>
          </div>

          {/* Interests List */}
          {total === 0 ? (
            <div className="rounded-lg border border-dashed p-6 text-center text-muted-foreground">
              <Sparkles className="h-8 w-8 mx-auto mb-2 opacity-50" />
              <p>{t('interests.empty')}</p>
              <p className="text-xs mt-1">{t('interests.empty_hint')}</p>
            </div>
          ) : (
            <Accordion type="multiple" defaultValue={[]} className="space-y-2">
              {/* Active Interests by Category */}
              {Object.entries(groupedByCategory).map(([category, categoryInterests]) => (
                <AccordionItem key={category} value={category} className="border rounded-lg px-3">
                  <AccordionTrigger className="py-3 hover:no-underline">
                    <div className="flex items-center gap-2">
                      <span>{INTEREST_CATEGORY_ICONS[category as InterestCategory]}</span>
                      <span className="font-medium">
                        {getCategoryLabel(category as InterestCategory)}
                      </span>
                      <span className="text-muted-foreground text-sm">
                        ({categoryInterests.length})
                      </span>
                    </div>
                  </AccordionTrigger>
                  <AccordionContent>
                    <div className="space-y-2">
                      {categoryInterests.map(interest => (
                        <div
                          key={interest.id}
                          className="group flex items-center gap-3 rounded-lg border p-3 bg-card hover:bg-accent/50 transition-colors cursor-pointer lg:cursor-default"
                          onClick={() => {
                            if (window.innerWidth < 1024) {
                              setMobileActionInterest(interest);
                            }
                          }}
                        >
                          {/* Content */}
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium truncate">{interest.topic}</p>
                            <div className="flex items-center gap-2 mt-1">
                              <Badge
                                variant={getWeightBadgeVariant(interest.weight)}
                                className="text-xs"
                              >
                                {(interest.weight * 100).toFixed(0)}%
                              </Badge>
                              {interest.last_mentioned_at && (
                                <span className="text-xs text-muted-foreground hidden sm:inline">
                                  {formatInterestDate(interest.last_mentioned_at, lng)}
                                </span>
                              )}
                            </div>
                          </div>

                          {/* Action buttons - hidden on mobile */}
                          <div className="hidden lg:flex gap-1 shrink-0 opacity-0 group-hover:opacity-100">
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={e => {
                                e.stopPropagation();
                                handleOpenEdit(interest);
                              }}
                              disabled={updating}
                              title={t('interests.edit')}
                            >
                              <Pencil className="h-4 w-4" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={e => {
                                e.stopPropagation();
                                handleFeedback(interest, 'block');
                              }}
                              disabled={submittingFeedback}
                              title={t('interests.block')}
                            >
                              <Ban className="h-4 w-4 text-red-500" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={e => {
                                e.stopPropagation();
                                setPendingDelete(interest);
                              }}
                              disabled={deleting}
                              title={t('interests.delete')}
                            >
                              <Trash2 className="h-4 w-4 text-destructive" />
                            </Button>
                          </div>
                        </div>
                      ))}
                    </div>
                  </AccordionContent>
                </AccordionItem>
              ))}

              {/* Blocked Interests */}
              {blockedInterests.length > 0 && (
                <AccordionItem value="blocked" className="border rounded-lg px-3">
                  <AccordionTrigger className="py-3 hover:no-underline">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-muted-foreground">
                        {t('interests.blocked_section')}
                      </span>
                      <span className="text-muted-foreground text-sm">
                        ({blockedInterests.length})
                      </span>
                    </div>
                  </AccordionTrigger>
                  <AccordionContent>
                    <div className="space-y-2 opacity-60">
                      {blockedInterests.map(interest => (
                        <div
                          key={interest.id}
                          className="group flex items-center gap-3 rounded-lg border p-3 bg-muted/30"
                        >
                          <span className="text-lg shrink-0">
                            {INTEREST_CATEGORY_ICONS[interest.category]}
                          </span>
                          <div className="flex-1 min-w-0">
                            <p className="text-sm line-through">{interest.topic}</p>
                          </div>
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => setPendingDelete(interest)}
                            disabled={deleting}
                          >
                            <Trash2 className="h-4 w-4 text-destructive" />
                          </Button>
                        </div>
                      ))}
                    </div>
                  </AccordionContent>
                </AccordionItem>
              )}
            </Accordion>
          )}

          {/* Info box */}
          <InfoBox>
            <div className="text-xs text-muted-foreground space-y-1">
              <p>{t('interests.info_extraction')}</p>
              <p>{t('interests.info_gdpr')}</p>
            </div>
          </InfoBox>

          {/* Create Dialog */}
          <Dialog open={createDialogOpen} onOpenChange={setCreateDialogOpen}>
            <DialogContent className="sm:max-w-[400px]">
              <DialogHeader>
                <DialogTitle>{t('interests.create_title')}</DialogTitle>
                <DialogDescription>{t('interests.create_description')}</DialogDescription>
              </DialogHeader>
              <div className="grid gap-4 py-4">
                <div className="grid gap-2">
                  <Label htmlFor="create-topic">{t('interests.field_topic')} *</Label>
                  <Input
                    id="create-topic"
                    value={createForm.topic}
                    onChange={e => setCreateForm({ ...createForm, topic: e.target.value })}
                    placeholder={t('interests.topic_placeholder')}
                    autoFocus
                  />
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="create-category">{t('interests.field_category')}</Label>
                  <Select
                    value={createForm.category}
                    onValueChange={value =>
                      setCreateForm({ ...createForm, category: value as InterestCategory })
                    }
                  >
                    <SelectTrigger id="create-category">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {categories.map(cat => (
                        <SelectItem key={cat.value} value={cat.value}>
                          {INTEREST_CATEGORY_ICONS[cat.value]} {getCategoryLabel(cat.value)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={handleCloseCreate} disabled={creating}>
                  {t('common.cancel')}
                </Button>
                <Button onClick={handleSaveCreate} disabled={creating || !createForm.topic.trim()}>
                  {creating ? <LoadingSpinner size="default" className="mr-1" /> : null}
                  {t('interests.create_button')}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>

          {/* Edit Dialog */}
          <Dialog open={editDialogOpen} onOpenChange={setEditDialogOpen}>
            <DialogContent className="sm:max-w-[400px]">
              <DialogHeader>
                <DialogTitle>{t('interests.edit_title')}</DialogTitle>
                <DialogDescription>{t('interests.edit_description')}</DialogDescription>
              </DialogHeader>
              <div className="grid gap-4 py-4">
                <div className="grid gap-2">
                  <Label htmlFor="edit-topic">{t('interests.field_topic')} *</Label>
                  <Input
                    id="edit-topic"
                    value={editForm.topic}
                    onChange={e => setEditForm({ ...editForm, topic: e.target.value })}
                    placeholder={t('interests.topic_placeholder')}
                    autoFocus
                  />
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="edit-category">{t('interests.field_category')}</Label>
                  <Select
                    value={editForm.category}
                    onValueChange={value =>
                      setEditForm({ ...editForm, category: value as InterestCategory })
                    }
                  >
                    <SelectTrigger id="edit-category">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {categories.map(cat => (
                        <SelectItem key={cat.value} value={cat.value}>
                          {INTEREST_CATEGORY_ICONS[cat.value]} {getCategoryLabel(cat.value)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div className="grid gap-2">
                    <Label htmlFor="edit-positive">{t('interests.field_positive_signals')}</Label>
                    <Input
                      id="edit-positive"
                      type="number"
                      min={1}
                      value={editForm.positive_signals}
                      onChange={e =>
                        setEditForm({
                          ...editForm,
                          positive_signals: Math.max(1, parseInt(e.target.value) || 1),
                        })
                      }
                    />
                  </div>
                  <div className="grid gap-2">
                    <Label htmlFor="edit-negative">{t('interests.field_negative_signals')}</Label>
                    <Input
                      id="edit-negative"
                      type="number"
                      min={0}
                      value={editForm.negative_signals}
                      onChange={e =>
                        setEditForm({
                          ...editForm,
                          negative_signals: Math.max(0, parseInt(e.target.value) || 0),
                        })
                      }
                    />
                  </div>
                </div>
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={handleCloseEdit} disabled={updating}>
                  {t('common.cancel')}
                </Button>
                <Button onClick={handleSaveEdit} disabled={updating || !editForm.topic.trim()}>
                  {updating ? <LoadingSpinner size="default" className="mr-1" /> : null}
                  {t('interests.edit_button')}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>

          {/* Mobile Action Popup */}
          <Dialog
            open={mobileActionInterest !== null}
            onOpenChange={open => !open && setMobileActionInterest(null)}
          >
            <DialogContent className="lg:hidden max-w-[90vw] rounded-lg">
              <DialogHeader>
                <DialogTitle className="text-base flex items-center gap-2">
                  {mobileActionInterest && INTEREST_CATEGORY_ICONS[mobileActionInterest.category]}
                  {mobileActionInterest?.topic}
                </DialogTitle>
              </DialogHeader>
              {/* Note: Feedback (thumbs up/down) only appears on notification cards in chat */}
              <div className="flex flex-col gap-2 py-2">
                <Button
                  variant="outline"
                  className="w-full justify-start gap-3"
                  onClick={() => {
                    if (mobileActionInterest) {
                      handleOpenEdit(mobileActionInterest);
                      setMobileActionInterest(null);
                    }
                  }}
                  disabled={updating}
                >
                  <Pencil className="h-4 w-4" />
                  {t('interests.edit')}
                </Button>
                <Button
                  variant="outline"
                  className="w-full justify-start gap-3"
                  onClick={() => {
                    if (mobileActionInterest) {
                      handleFeedback(mobileActionInterest, 'block');
                      setMobileActionInterest(null);
                    }
                  }}
                  disabled={submittingFeedback}
                >
                  <Ban className="h-4 w-4 text-red-500" />
                  {t('interests.block')}
                </Button>
                <Button
                  variant="outline"
                  className="w-full justify-start gap-3 text-destructive"
                  onClick={() => {
                    if (mobileActionInterest) {
                      setPendingDelete(mobileActionInterest);
                      setMobileActionInterest(null);
                    }
                  }}
                  disabled={deleting}
                >
                  <Trash2 className="h-4 w-4" />
                  {t('interests.delete')}
                </Button>
              </div>
            </DialogContent>
          </Dialog>

          {/* Delete Confirmation */}
          <AlertDialog
            open={pendingDelete !== null}
            onOpenChange={open => !open && setPendingDelete(null)}
          >
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>{t('interests.confirm_delete_title')}</AlertDialogTitle>
                <AlertDialogDescription>
                  {t('interests.confirm_delete_description')}
                  {pendingDelete && (
                    <span className="block mt-2 p-2 bg-muted rounded text-foreground text-sm">
                      {pendingDelete.topic}
                    </span>
                  )}
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel disabled={deleting}>{t('common.cancel')}</AlertDialogCancel>
                <AlertDialogAction
                  onClick={() => {
                    if (pendingDelete) {
                      handleDelete(pendingDelete);
                      setPendingDelete(null);
                    }
                  }}
                  disabled={deleting}
                  className="bg-destructive hover:bg-destructive/90"
                >
                  {deleting ? <LoadingSpinner size="default" className="mr-1" /> : null}
                  {t('interests.delete')}
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
      value="interests"
      title={t('interests.settings.title')}
      description={t('interests.settings.description')}
      icon={Sparkles}
    >
      {content}
    </SettingsSection>
  );
}
