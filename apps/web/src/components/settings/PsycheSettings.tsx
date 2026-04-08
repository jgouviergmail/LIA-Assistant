/**
 * PsycheSettings — redesigned settings section for the Psyche Engine.
 *
 * 4 collapsible sections:
 * 1. LLM Summary (natural language state description)
 * 2. Education (interactive concept documentation)
 * 3. History (chronological evolution)
 * 4. Settings (toggles, sliders, reset)
 *
 * Phase: evolution — Psyche Engine (Iteration 2)
 * Created: 2026-04-01
 */

'use client';

import { useCallback, useEffect, useState } from 'react';
import { Activity, BookOpen, Brain, ChartLine, RefreshCw, Settings } from 'lucide-react';
import { toast } from 'sonner';

import { usePsyche } from '@/hooks/usePsyche';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { PsycheLLMSummary } from '@/components/psyche/PsycheLLMSummary';
import { PsycheStateSummary } from '@/components/psyche/PsycheStateSummary';
import { PsycheEducation } from '@/components/psyche/PsycheEducation';
import { PsycheHistory } from '@/components/psyche/PsycheHistory';
import { SettingsSection } from '@/components/settings/SettingsSection';
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion';
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
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Slider } from '@/components/ui/slider';
import { Switch } from '@/components/ui/switch';

interface PsycheSettingsProps {
  lng: Language;
}

export function PsycheSettings({ lng }: PsycheSettingsProps) {
  const { t } = useTranslation(lng, 'translation');
  const { settings, isUpdatingSettings, isResetting, updateSettings, resetPsyche } = usePsyche();

  // Track which accordion sections are open (for conditional data fetching)
  const [openSections, setOpenSections] = useState<string[]>([]);

  // Refresh key — incremented to trigger refetch of LLM summary + state
  const [refreshKey, setRefreshKey] = useState(0);

  // Controlled local state for sliders (initial 0, synced from server via useEffect)
  const [localSensitivity, setLocalSensitivity] = useState(0);
  const [localStability, setLocalStability] = useState(0);

  // Sync from server
  useEffect(() => {
    if (settings) {
      setLocalSensitivity(settings.psyche_sensitivity);
      setLocalStability(settings.psyche_stability);
    }
  }, [settings]);

  const handleToggle = useCallback(
    async (field: 'psyche_enabled' | 'psyche_display_avatar', value: boolean) => {
      try {
        await updateSettings({ [field]: value });
        toast.success(t('psyche.settingsUpdated', 'Settings updated'));
      } catch {
        toast.error(t('psyche.settingsError', 'Failed to update settings'));
      }
    },
    [updateSettings, t]
  );

  const handleSliderCommit = useCallback(
    async (field: 'psyche_sensitivity' | 'psyche_stability', value: number) => {
      try {
        await updateSettings({ [field]: value });
        toast.success(t('psyche.settingsUpdated', 'Settings updated'));
      } catch {
        toast.error(t('psyche.settingsError', 'Failed to update settings'));
      }
    },
    [updateSettings, t]
  );

  const handleReset = useCallback(
    async (level: 'soft' | 'full') => {
      try {
        await resetPsyche(level);
        toast.success(t('psyche.resetSuccess', 'Psyche state reset successfully'));
      } catch {
        toast.error(t('psyche.resetError', 'Failed to reset psyche state'));
      }
    },
    [resetPsyche, t]
  );

  return (
    <SettingsSection
      value="psyche"
      title={t('psyche.title', 'Psyche Engine')}
      description={t('psyche.description', 'Dynamic emotional intelligence system')}
      icon={Brain}
    >
      <div className="space-y-6">
        {/* Master toggle */}
        <div className="flex items-center justify-between">
          <div className="space-y-0.5">
            <Label>{t('psyche.enable', 'Enable Psyche Engine')}</Label>
            <p className="text-xs text-muted-foreground">
              {t(
                'psyche.enableDescription',
                'LIA develops emotional states that influence conversation style'
              )}
            </p>
          </div>
          <Switch
            checked={settings?.psyche_enabled ?? false}
            onCheckedChange={v => handleToggle('psyche_enabled', v)}
            disabled={isUpdatingSettings}
          />
        </div>

        {/* Conditional content when enabled */}
        {settings?.psyche_enabled && (
          <Accordion
            type="multiple"
            value={openSections}
            onValueChange={setOpenSections}
            className="w-full space-y-2"
          >
            {/* 1. Education */}
            <AccordionItem value="education" className="border rounded-lg px-3">
              <AccordionTrigger className="py-3 text-sm font-medium hover:no-underline">
                <span className="flex items-center gap-2">
                  <BookOpen className="h-4 w-4 text-muted-foreground" />
                  {t('psyche.education.title', 'Understanding the Psyche')}
                </span>
              </AccordionTrigger>
              <AccordionContent>
                <PsycheEducation lng={lng} />
              </AccordionContent>
            </AccordionItem>

            {/* 2. LLM Summary + State Details */}
            <AccordionItem value="summary" className="border rounded-lg px-3">
              <AccordionTrigger className="py-3 text-sm font-medium hover:no-underline">
                <span className="flex items-center gap-2">
                  <Activity className="h-4 w-4 text-muted-foreground" />
                  {t('psyche.summary.title', 'Psyche State')}
                </span>
              </AccordionTrigger>
              <AccordionContent>
                <div className="space-y-4 pb-2">
                  <div className="flex justify-end">
                    <button
                      onClick={() => setRefreshKey(k => k + 1)}
                      className="flex items-center gap-1 text-[10px] text-muted-foreground hover:text-foreground transition-colors"
                      title={t('psyche.summary.refresh', 'Refresh')}
                    >
                      <RefreshCw className="h-3 w-3" />
                      {t('psyche.summary.refresh', 'Refresh')}
                    </button>
                  </div>
                  <PsycheLLMSummary
                    lng={lng}
                    isOpen={openSections.includes('summary')}
                    refreshKey={refreshKey}
                  />
                  <PsycheStateSummary lng={lng} refreshKey={refreshKey} />
                </div>
              </AccordionContent>
            </AccordionItem>

            {/* 3. History */}
            <AccordionItem value="history" className="border rounded-lg px-3">
              <AccordionTrigger className="py-3 text-sm font-medium hover:no-underline">
                <span className="flex items-center gap-2">
                  <ChartLine className="h-4 w-4 text-muted-foreground" />
                  {t('psyche.history.title', 'History')}
                </span>
              </AccordionTrigger>
              <AccordionContent>
                <PsycheHistory lng={lng} isOpen={openSections.includes('history')} />
              </AccordionContent>
            </AccordionItem>

            {/* 4. Settings (toggles, sliders, reset) */}
            <AccordionItem value="settings" className="border rounded-lg px-3">
              <AccordionTrigger className="py-3 text-sm font-medium hover:no-underline">
                <span className="flex items-center gap-2">
                  <Settings className="h-4 w-4 text-muted-foreground" />
                  {t('psyche.settingsSection.title', 'Settings')}
                </span>
              </AccordionTrigger>
              <AccordionContent>
                <div className="space-y-4 pb-2">
                  {/* Display avatar toggle */}
                  <div className="flex items-center justify-between">
                    <div className="space-y-0.5">
                      <Label>{t('psyche.displayAvatar', 'Show emotional avatar')}</Label>
                      <p className="text-xs text-muted-foreground">
                        {t(
                          'psyche.displayAvatarDescription',
                          'Display the double avatar (personality + mood) in the chat'
                        )}
                      </p>
                    </div>
                    <Switch
                      checked={settings?.psyche_display_avatar ?? true}
                      onCheckedChange={v => handleToggle('psyche_display_avatar', v)}
                      disabled={isUpdatingSettings}
                    />
                  </div>

                  {/* Sensitivity slider */}
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <Label className="text-sm">{t('psyche.sensitivity', 'Expressiveness')}</Label>
                      <span className="text-xs text-muted-foreground">{localSensitivity}%</span>
                    </div>
                    <Slider
                      value={[localSensitivity]}
                      min={0}
                      max={100}
                      step={5}
                      onValueChange={([v]) => setLocalSensitivity(v)}
                      onValueCommit={([v]) => handleSliderCommit('psyche_sensitivity', v)}
                      disabled={isUpdatingSettings}
                      aria-label={t('psyche.sensitivity', 'Expressiveness')}
                    />
                    <p className="text-xs text-muted-foreground">
                      {t(
                        'psyche.sensitivityDescription',
                        'How strongly emotions influence responses (0 = stoic, 100 = highly expressive)'
                      )}
                    </p>
                  </div>

                  {/* Stability slider */}
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <Label className="text-sm">{t('psyche.stability', 'Mood Stability')}</Label>
                      <span className="text-xs text-muted-foreground">{localStability}%</span>
                    </div>
                    <Slider
                      value={[localStability]}
                      min={0}
                      max={100}
                      step={5}
                      onValueChange={([v]) => setLocalStability(v)}
                      onValueCommit={([v]) => handleSliderCommit('psyche_stability', v)}
                      disabled={isUpdatingSettings}
                      aria-label={t('psyche.stability', 'Mood Stability')}
                    />
                    <p className="text-xs text-muted-foreground">
                      {t(
                        'psyche.stabilityDescription',
                        'How quickly mood returns to baseline (0 = volatile, 100 = very stable)'
                      )}
                    </p>
                  </div>

                  {/* Reset section */}
                  <div className="space-y-3 pt-4 border-t">
                    {/* Soft reset */}
                    <div className="flex items-start gap-3">
                      <AlertDialog>
                        <AlertDialogTrigger asChild>
                          <Button
                            variant="outline"
                            size="sm"
                            disabled={isResetting}
                            className="shrink-0 w-44 justify-center"
                          >
                            {t('psyche.softReset', 'Refresh mood')}
                          </Button>
                        </AlertDialogTrigger>
                        <AlertDialogContent>
                          <AlertDialogHeader>
                            <AlertDialogTitle>
                              {t('psyche.softResetTitle', 'Refresh mood?')}
                            </AlertDialogTitle>
                            <AlertDialogDescription>
                              {t(
                                'psyche.softResetConfirm',
                                "LIA's mood will return to neutral and active emotions will be cleared. The relationship and acquired personality will be preserved."
                              )}
                            </AlertDialogDescription>
                          </AlertDialogHeader>
                          <AlertDialogFooter>
                            <AlertDialogCancel>{t('common.cancel', 'Cancel')}</AlertDialogCancel>
                            <AlertDialogAction onClick={() => handleReset('soft')}>
                              {t('psyche.softReset', 'Refresh mood')}
                            </AlertDialogAction>
                          </AlertDialogFooter>
                        </AlertDialogContent>
                      </AlertDialog>
                      <p className="text-xs text-muted-foreground pt-1">
                        {t(
                          'psyche.softResetDescription',
                          "Like a good night's sleep — mood resets but relationship and personality are preserved."
                        )}
                      </p>
                    </div>

                    {/* Full reset */}
                    <div className="flex items-start gap-3">
                      <AlertDialog>
                        <AlertDialogTrigger asChild>
                          <Button
                            variant="destructive"
                            size="sm"
                            disabled={isResetting}
                            className="shrink-0 w-44 justify-center"
                          >
                            {t('psyche.fullReset', 'Reset everything')}
                          </Button>
                        </AlertDialogTrigger>
                        <AlertDialogContent>
                          <AlertDialogHeader>
                            <AlertDialogTitle>
                              {t('psyche.fullResetTitle', 'Reset everything?')}
                            </AlertDialogTitle>
                            <AlertDialogDescription>
                              {t(
                                'psyche.fullResetConfirm',
                                'Emotional state, relationship progress, and domain confidence will be completely reset. Memories and journals are not affected. This action cannot be undone.'
                              )}
                            </AlertDialogDescription>
                          </AlertDialogHeader>
                          <AlertDialogFooter>
                            <AlertDialogCancel>{t('common.cancel', 'Cancel')}</AlertDialogCancel>
                            <AlertDialogAction
                              onClick={() => handleReset('full')}
                              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                            >
                              {t('psyche.fullReset', 'Reset everything')}
                            </AlertDialogAction>
                          </AlertDialogFooter>
                        </AlertDialogContent>
                      </AlertDialog>
                      <p className="text-xs text-muted-foreground pt-1">
                        {t(
                          'psyche.fullResetDescription',
                          'Relational amnesia — LIA starts over emotionally and relationally, like a first meeting.'
                        )}
                      </p>
                    </div>
                  </div>
                </div>
              </AccordionContent>
            </AccordionItem>
          </Accordion>
        )}
      </div>
    </SettingsSection>
  );
}
