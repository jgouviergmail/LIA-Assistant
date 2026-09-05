'use client';

/**
 * RegistersPage — the two transparency registers, side by side (ADR-263).
 *
 * Two tabs and not one merged list, by decision (owner arbitration,
 * 2026-09-04): the registers count different things — one row per ACTION
 * against one row per CONSULTATION — and a reader able to add their totals
 * would get a number that means nothing. A busy turn consults dozens of
 * capabilities and acts on none; merging them would drown the four lines that
 * matter under four hundred that do not.
 *
 * The tab is the only state this shell owns. Each register loads its own page
 * only when its tab is shown, so opening the page costs one request, not two.
 */

import { BarChart3, ClipboardList, Eye, ShieldCheck } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Article12ExportCard } from '@/components/effects/Article12ExportCard';
import { ChainSealCard } from '@/components/effects/ChainSealCard';
import { RegisterCharts } from '@/components/effects/RegisterCharts';
import { EffectsJournal } from '@/components/effects/EffectsJournal';
import { TreatmentsJournal } from '@/components/effects/TreatmentsJournal';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

export interface RegistersPageProps {
  /** Current URL locale segment (drives date/time formatting). */
  lng: string;
}

export function RegistersPage({ lng }: RegistersPageProps) {
  const { t } = useTranslation();

  return (
    <div className="space-y-6">
      <header className="min-w-0">
        <h1 className="flex items-center gap-2 text-2xl font-bold">
          <ShieldCheck className="h-6 w-6 text-primary" aria-hidden="true" />
          {t('registers.title')}
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">{t('registers.description')}</p>
      </header>

      {/* Above both tabs, not inside either: ONE chain seals the two
          journals, and two indicators would suggest two separate proofs. */}
      <ChainSealCard />

      <Tabs defaultValue="actions" className="space-y-6">
        <TabsList>
          <TabsTrigger value="actions">
            <ClipboardList className="h-4 w-4" aria-hidden="true" />
            {t('registers.tab_actions')}
          </TabsTrigger>
          <TabsTrigger value="consultations">
            <Eye className="h-4 w-4" aria-hidden="true" />
            {t('registers.tab_consultations')}
          </TabsTrigger>
          {/* A third VIEW, not a third register: the same records, answering
              « what has been happening » where the journals answer « what
              exactly happened ». */}
          <TabsTrigger value="overview">
            <BarChart3 className="h-4 w-4" aria-hidden="true" />
            {t('registers.tab_overview')}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="actions">
          <EffectsJournal lng={lng} />
        </TabsContent>
        <TabsContent value="consultations">
          <TreatmentsJournal lng={lng} />
        </TabsContent>
        <TabsContent value="overview">
          <RegisterCharts />
        </TabsContent>
      </Tabs>

      {/* Below all three and inside none: this file crosses the two journals,
          the turns, the model calls and the gaps — the same reason the seal
          card sits above them rather than in a tab. */}
      <Article12ExportCard />
    </div>
  );
}
