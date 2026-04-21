/**
 * HealthMetricsSettings — single top-level settings section for the
 * Health Metrics feature, mirroring the PsycheSettings pattern.
 *
 * Structure:
 *   SettingsSection "Données santé"
 *     ├─ period selector (shared — drives charts + stats)
 *     └─ Accordion (multiple)
 *          1. Ingestion API (URL + token generation/revocation)
 *          2. Charts (HR line + steps bar, with period average overlays)
 *          3. Statistics (period-wide averages/min/max)
 *          4. Management (selective + full deletion)
 *
 * Phase: evolution — Health Metrics (iPhone Shortcuts integration)
 * Created: 2026-04-20
 */

'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  Activity,
  BarChart3,
  Copy,
  Eye,
  EyeOff,
  HeartPulse,
  Key,
  Plus,
  ShieldAlert,
  Trash2,
} from 'lucide-react';
import { toast } from 'sonner';

import { useHealthMetrics, type HealthMetricsPeriod } from '@/hooks/useHealthMetrics';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { SettingsSection } from '@/components/settings/SettingsSection';
import { HealthMetricsCharts } from '@/components/health_metrics/HealthMetricsCharts';
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
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

interface HealthMetricsSettingsProps {
  lng: Language;
}

const PERIOD_VALUES: HealthMetricsPeriod[] = ['hour', 'day', 'week', 'month', 'year'];
const INGEST_PATH = '/api/v1/ingest/health';

export function HealthMetricsSettings({ lng }: HealthMetricsSettingsProps) {
  const { t } = useTranslation(lng, 'translation');
  const [openSections, setOpenSections] = useState<string[]>([]);
  const [period, setPeriod] = useState<HealthMetricsPeriod>('day');
  const [newTokenLabel, setNewTokenLabel] = useState('');
  const [justCreatedToken, setJustCreatedToken] = useState<string | null>(null);
  const [showJustCreated, setShowJustCreated] = useState(true);

  const {
    aggregate,
    tokens,
    isLoading,
    isCreatingToken,
    isDeleting,
    createToken,
    revokeToken,
    deleteField,
    deleteAll,
  } = useHealthMetrics(period);

  const [ingestUrl, setIngestUrl] = useState<string>(INGEST_PATH);
  useEffect(() => {
    if (typeof window !== 'undefined') {
      setIngestUrl(`${window.location.origin}${INGEST_PATH}`);
    }
  }, []);

  const handleCopy = useCallback(
    async (value: string, messageKey: string, defaultMessage: string) => {
      try {
        await navigator.clipboard.writeText(value);
        toast.success(t(messageKey, defaultMessage));
      } catch {
        toast.error(t('common.copyFailed', 'Impossible de copier.'));
      }
    },
    [t]
  );

  const handleCreateToken = useCallback(async () => {
    const result = await createToken(newTokenLabel.trim() || undefined);
    if (result) {
      setJustCreatedToken(result.token);
      setShowJustCreated(true);
      setNewTokenLabel('');
      toast.success(t('healthMetrics.tokens.created', 'Jeton créé. Copiez-le maintenant.'));
    } else {
      toast.error(t('healthMetrics.tokens.createError', 'Impossible de créer le jeton.'));
    }
  }, [createToken, newTokenLabel, t]);

  const handleRevokeToken = useCallback(
    async (tokenId: string) => {
      await revokeToken(tokenId);
      toast.success(t('healthMetrics.tokens.revoked', 'Jeton révoqué.'));
    },
    [revokeToken, t]
  );

  const handleDeleteField = useCallback(
    async (field: 'heart_rate' | 'steps') => {
      await deleteField(field);
      toast.success(t('healthMetrics.management.deleted', 'Données supprimées.'));
    },
    [deleteField, t]
  );

  const handleDeleteAll = useCallback(async () => {
    await deleteAll();
    toast.success(t('healthMetrics.management.deletedAll', 'Toutes les données supprimées.'));
  }, [deleteAll, t]);

  const avgHr = aggregate?.averages.heart_rate_avg ?? null;
  const avgStepsPerDay = aggregate?.averages.steps_per_day_avg ?? null;

  const hrPoints = aggregate?.points.filter(p => p.heart_rate_avg !== null) ?? [];
  const hrMin = hrPoints.length
    ? Math.min(...hrPoints.map(p => p.heart_rate_min ?? Number.POSITIVE_INFINITY))
    : null;
  const hrMax = hrPoints.length
    ? Math.max(...hrPoints.map(p => p.heart_rate_max ?? Number.NEGATIVE_INFINITY))
    : null;

  const stepsTotal = (aggregate?.points ?? []).reduce(
    (sum, p) => sum + (p.steps_total ?? 0),
    0
  );

  return (
    <SettingsSection
      value="health_metrics"
      title={t('healthMetrics.title', 'Données santé')}
      description={t(
        'healthMetrics.description',
        'Ingestion iPhone + visualisation des fréquences cardiaques et pas'
      )}
      icon={HeartPulse}
    >
      <div className="space-y-4">
        {/* Shared period selector */}
        <div className="flex items-center gap-3">
          <Label htmlFor="hm-period" className="text-sm">
            {t('healthMetrics.charts.periodLabel', 'Période')}
          </Label>
          <Select
            value={period}
            onValueChange={value => setPeriod(value as HealthMetricsPeriod)}
          >
            <SelectTrigger id="hm-period" className="w-40">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {PERIOD_VALUES.map(value => (
                <SelectItem key={value} value={value}>
                  {t(`healthMetrics.charts.period.${value}`, value)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {isLoading && (
            <span className="text-xs text-muted-foreground">
              {t('common.loading', 'Chargement…')}
            </span>
          )}
        </div>

        <Accordion
          type="multiple"
          value={openSections}
          onValueChange={setOpenSections}
          className="w-full space-y-2"
        >
          {/* =================================================================== */}
          {/* 1. Ingestion API */}
          {/* =================================================================== */}
          <AccordionItem value="ingestion" className="border rounded-lg px-3">
            <AccordionTrigger className="py-3 text-sm font-medium hover:no-underline">
              <span className="flex items-center gap-2">
                <Key className="h-4 w-4 text-muted-foreground" />
                {t('healthMetrics.ingestion.title', "API d'ingestion")}
              </span>
            </AccordionTrigger>
            <AccordionContent>
              <div className="space-y-6 pb-2">
                {/* URL */}
                <div className="space-y-2">
                  <Label className="text-xs uppercase tracking-wide text-muted-foreground">
                    {t('healthMetrics.ingestion.urlLabel', 'URL à appeler (POST)')}
                  </Label>
                  <div className="flex gap-2">
                    <Input value={ingestUrl} readOnly className="font-mono text-xs" />
                    <Button
                      type="button"
                      variant="outline"
                      size="icon"
                      onClick={() =>
                        handleCopy(
                          ingestUrl,
                          'healthMetrics.ingestion.urlCopied',
                          'URL copiée.'
                        )
                      }
                    >
                      <Copy className="h-4 w-4" />
                    </Button>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {t(
                      'healthMetrics.ingestion.payloadHint',
                      'Corps JSON attendu : {"data": {"c": 72, "p": 4521, "o": "iphone"}}. En-tête Authorization: Bearer <votre_jeton>.'
                    )}
                  </p>
                </div>

                {/* Just-created token banner */}
                {justCreatedToken && (
                  <div className="rounded-lg border border-amber-500/50 bg-amber-50 dark:bg-amber-950/20 p-4 space-y-2">
                    <div className="flex items-center gap-2">
                      <ShieldAlert className="h-4 w-4 text-amber-600" />
                      <span className="font-medium text-sm">
                        {t(
                          'healthMetrics.tokens.justCreated',
                          'Copiez ce jeton — il ne sera plus affiché.'
                        )}
                      </span>
                    </div>
                    <div className="flex gap-2 items-center">
                      <Input
                        type={showJustCreated ? 'text' : 'password'}
                        value={justCreatedToken}
                        readOnly
                        className="font-mono text-xs"
                      />
                      <Button
                        type="button"
                        variant="outline"
                        size="icon"
                        onClick={() => setShowJustCreated(v => !v)}
                        aria-label={
                          showJustCreated
                            ? t('common.hide', 'Masquer')
                            : t('common.show', 'Afficher')
                        }
                      >
                        {showJustCreated ? (
                          <EyeOff className="h-4 w-4" />
                        ) : (
                          <Eye className="h-4 w-4" />
                        )}
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        size="icon"
                        onClick={() =>
                          handleCopy(
                            justCreatedToken,
                            'healthMetrics.tokens.copied',
                            'Jeton copié.'
                          )
                        }
                      >
                        <Copy className="h-4 w-4" />
                      </Button>
                    </div>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => setJustCreatedToken(null)}
                    >
                      {t('common.close', 'Fermer')}
                    </Button>
                  </div>
                )}

                {/* Token creation */}
                <div className="space-y-2">
                  <Label className="text-xs uppercase tracking-wide text-muted-foreground">
                    {t('healthMetrics.tokens.newLabel', 'Nouveau jeton (libellé optionnel)')}
                  </Label>
                  <div className="flex gap-2">
                    <Input
                      value={newTokenLabel}
                      onChange={e => setNewTokenLabel(e.target.value)}
                      placeholder={t(
                        'healthMetrics.tokens.labelPlaceholder',
                        'iPhone perso'
                      )}
                      maxLength={64}
                    />
                    <Button
                      type="button"
                      onClick={handleCreateToken}
                      disabled={isCreatingToken}
                    >
                      <Plus className="h-4 w-4 mr-2" />
                      {t('healthMetrics.tokens.generate', 'Générer')}
                    </Button>
                  </div>
                </div>

                {/* Token list */}
                <div className="space-y-2">
                  <Label className="text-xs uppercase tracking-wide text-muted-foreground">
                    {t('healthMetrics.tokens.existing', 'Jetons existants')}
                  </Label>
                  {tokens.length === 0 ? (
                    <p className="text-sm text-muted-foreground italic">
                      {t('healthMetrics.tokens.none', 'Aucun jeton pour le moment.')}
                    </p>
                  ) : (
                    <ul className="space-y-2">
                      {tokens.map(token => (
                        <li
                          key={token.id}
                          className="flex items-center justify-between gap-3 rounded-md border px-3 py-2"
                        >
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-2">
                              <code className="font-mono text-xs">
                                {token.token_prefix}…
                              </code>
                              {token.label && (
                                <span className="text-xs text-muted-foreground truncate">
                                  · {token.label}
                                </span>
                              )}
                              {token.revoked_at && (
                                <span className="text-xs font-medium text-red-500">
                                  ({t('healthMetrics.tokens.revokedBadge', 'révoqué')})
                                </span>
                              )}
                            </div>
                            <p className="text-[11px] text-muted-foreground mt-0.5">
                              {t('healthMetrics.tokens.createdOn', 'Créé le')}{' '}
                              {new Date(token.created_at).toLocaleString(lng)}
                              {token.last_used_at && (
                                <>
                                  {' · '}
                                  {t(
                                    'healthMetrics.tokens.lastUsed',
                                    'Dernière utilisation'
                                  )}{' '}
                                  {new Date(token.last_used_at).toLocaleString(lng)}
                                </>
                              )}
                            </p>
                          </div>
                          {!token.revoked_at && (
                            <Button
                              type="button"
                              variant="ghost"
                              size="sm"
                              onClick={() => handleRevokeToken(token.id)}
                            >
                              {t('healthMetrics.tokens.revoke', 'Révoquer')}
                            </Button>
                          )}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>
            </AccordionContent>
          </AccordionItem>

          {/* =================================================================== */}
          {/* 2. Charts */}
          {/* =================================================================== */}
          <AccordionItem value="charts" className="border rounded-lg px-3">
            <AccordionTrigger className="py-3 text-sm font-medium hover:no-underline">
              <span className="flex items-center gap-2">
                <BarChart3 className="h-4 w-4 text-muted-foreground" />
                {t('healthMetrics.charts.title', 'Graphiques')}
              </span>
            </AccordionTrigger>
            <AccordionContent>
              <div className="pb-2">
                <HealthMetricsCharts lng={lng} aggregate={aggregate} period={period} />
              </div>
            </AccordionContent>
          </AccordionItem>

          {/* =================================================================== */}
          {/* 3. Statistics */}
          {/* =================================================================== */}
          <AccordionItem value="stats" className="border rounded-lg px-3">
            <AccordionTrigger className="py-3 text-sm font-medium hover:no-underline">
              <span className="flex items-center gap-2">
                <Activity className="h-4 w-4 text-muted-foreground" />
                {t('healthMetrics.stats.title', 'Statistiques')}
              </span>
            </AccordionTrigger>
            <AccordionContent>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 pb-2">
                <StatTile
                  label={t('healthMetrics.stats.hrAvg', 'FC moyenne')}
                  value={avgHr !== null ? `${Math.round(avgHr)} bpm` : '—'}
                />
                <StatTile
                  label={t('healthMetrics.stats.hrMin', 'FC min')}
                  value={
                    hrMin !== null && Number.isFinite(hrMin) ? `${hrMin} bpm` : '—'
                  }
                />
                <StatTile
                  label={t('healthMetrics.stats.hrMax', 'FC max')}
                  value={
                    hrMax !== null && Number.isFinite(hrMax) ? `${hrMax} bpm` : '—'
                  }
                />
                <StatTile
                  label={t('healthMetrics.stats.stepsAvg', 'Pas moyens / jour')}
                  value={avgStepsPerDay !== null ? `${Math.round(avgStepsPerDay)}` : '—'}
                />
                <StatTile
                  label={t('healthMetrics.stats.stepsTotal', 'Pas totaux (période)')}
                  value={`${Math.round(stepsTotal)}`}
                />
              </div>
            </AccordionContent>
          </AccordionItem>

          {/* =================================================================== */}
          {/* 4. Management */}
          {/* =================================================================== */}
          <AccordionItem value="management" className="border rounded-lg px-3">
            <AccordionTrigger className="py-3 text-sm font-medium hover:no-underline">
              <span className="flex items-center gap-2">
                <Trash2 className="h-4 w-4 text-muted-foreground" />
                {t('healthMetrics.management.title', 'Gestion des données')}
              </span>
            </AccordionTrigger>
            <AccordionContent>
              <div className="space-y-3 pb-2">
                <DeleteTile
                  lng={lng}
                  disabled={isDeleting}
                  triggerLabel={t('healthMetrics.management.deleteHr', 'Supprimer les FC')}
                  alertTitle={t(
                    'healthMetrics.management.deleteHrTitle',
                    'Supprimer toutes les fréquences cardiaques ?'
                  )}
                  alertDescription={t(
                    'healthMetrics.management.deleteHrDescription',
                    'Les valeurs FC seront mises à NULL pour toutes les lignes. Les pas et autres données seront conservés.'
                  )}
                  onConfirm={() => handleDeleteField('heart_rate')}
                />
                <DeleteTile
                  lng={lng}
                  disabled={isDeleting}
                  triggerLabel={t('healthMetrics.management.deleteSteps', 'Supprimer les pas')}
                  alertTitle={t(
                    'healthMetrics.management.deleteStepsTitle',
                    'Supprimer tous les compteurs de pas ?'
                  )}
                  alertDescription={t(
                    'healthMetrics.management.deleteStepsDescription',
                    'Les valeurs de pas seront mises à NULL pour toutes les lignes. Les FC et autres données seront conservées.'
                  )}
                  onConfirm={() => handleDeleteField('steps')}
                />
                <DeleteTile
                  lng={lng}
                  disabled={isDeleting}
                  destructive
                  triggerLabel={t('healthMetrics.management.deleteAll', 'Tout supprimer')}
                  alertTitle={t(
                    'healthMetrics.management.deleteAllTitle',
                    'Effacer toutes les données santé ?'
                  )}
                  alertDescription={t(
                    'healthMetrics.management.deleteAllDescription',
                    "Toutes les lignes seront supprimées définitivement. Vos jetons d'ingestion restent actifs."
                  )}
                  onConfirm={handleDeleteAll}
                />
              </div>
            </AccordionContent>
          </AccordionItem>
        </Accordion>
      </div>
    </SettingsSection>
  );
}

// ============================================================================
// Helper tiles
// ============================================================================

function StatTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border px-3 py-2">
      <p className="text-xs uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="mt-1 text-lg font-semibold tabular-nums">{value}</p>
    </div>
  );
}

interface DeleteTileProps {
  lng: Language;
  disabled: boolean;
  destructive?: boolean;
  triggerLabel: string;
  alertTitle: string;
  alertDescription: string;
  onConfirm: () => Promise<unknown>;
}

function DeleteTile({
  lng,
  disabled,
  destructive,
  triggerLabel,
  alertTitle,
  alertDescription,
  onConfirm,
}: DeleteTileProps) {
  const { t } = useTranslation(lng, 'translation');
  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button
          type="button"
          variant={destructive ? 'destructive' : 'outline'}
          disabled={disabled}
          className="w-full justify-start"
        >
          <Trash2 className="h-4 w-4 mr-2" />
          {triggerLabel}
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{alertTitle}</AlertDialogTitle>
          <AlertDialogDescription>{alertDescription}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>{t('common.cancel', 'Annuler')}</AlertDialogCancel>
          <AlertDialogAction onClick={() => void onConfirm()}>
            {t('common.confirm', 'Confirmer')}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
