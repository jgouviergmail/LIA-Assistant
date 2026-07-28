'use client';

import { useState, useMemo, useCallback } from 'react';
import Image from 'next/image';
import { useRouter } from 'next/navigation';
import { useTranslation } from '@/i18n/client';
import { type Language } from '@/i18n/settings';
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion';
import { normalizeSearchText } from '@/lib/utils';
import { highlightText, stripHtml } from '@/lib/faq-search';
import { chatDraftHref } from '@/lib/briefing-utils';
import { FaqAnswer } from './FaqAnswer';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { FAQ_SECTION_ICONS } from './faq-sections';
import {
  Zap,
  HelpCircle,
  Search,
  X,
  Network,
  Brain,
  Lock,
  Cpu,
  Languages,
  Activity,
  Volume2,
  ListChecks,
  ChevronDown,
  ChevronUp,
  DollarSign,
  Sparkles,
  Boxes,
  ShieldCheck,
  Compass,
  CalendarClock,
  Plug,
  Smartphone,
  Palette,
  Radio,
  HeartPulse,
  Globe2,
  Newspaper,
  RefreshCw,
  Layers,
  FolderOpen,
  BadgeCheck,
  Paperclip,
  Blocks,
  Library,
  BookOpen,
  Bot,
  Monitor,
  ImageIcon,
  UserCheck,
  Filter,
  HeartHandshake,
  History,
  Sunrise,
  PhoneCall,
} from 'lucide-react';

interface FAQContentProps {
  lng: Language;
  /** Callback to show the welcome tutorial. If provided and user has completed onboarding, button is shown. */
  onShowWelcome?: () => void;
  /** Whether to show the "Show welcome" button */
  showWelcomeButton?: boolean;
}

interface FAQQuestion {
  section: string;
  questionKey: string;
  question: string;
  answer: string;
}

const sections = [
  'getting_started',
  'chat',
  'settings',
  'connectors',
  'telephony',
  'tool_examples_services',
  'tool_examples_external',
  'rappels',
  'interests',
  'heartbeat',
  'scheduled_actions',
  'mcp_servers',
  'skills',
  'sub_agents',
  'rag_spaces',
  'voice_mode',
  'image_generation',
  'journals',
  'health_metrics',
  'usage_limits',
  'privacy',
  'other',
];

/**
 * Versions rendered by the changelog accordion, newest first.
 *
 * This list is the ONLY thing that makes an entry visible: a `faq.changelog.versions.vX_Y_Z`
 * block can exist in all 6 locales, pass i18n parity, and still never render if its key is
 * missing here. That is not hypothetical — `v1_21_8` and `v1_21_9` shipped invisible for two
 * releases. `__tests__/changelog-wiring.test.ts` now fails on any drift in either direction.
 */
export const changelogVersionKeys = [
  'v1_25_30',
  'v1_25_29',
  'v1_25_28',
  'v1_25_27',
  'v1_25_26',
  'v1_25_25',
  'v1_25_24',
  'v1_25_23',
  'v1_25_22',
  'v1_25_21',
  'v1_25_20',
  'v1_25_19',
  'v1_25_18',
  'v1_25_17',
  'v1_25_16',
  'v1_25_15',
  'v1_25_14',
  'v1_25_13',
  'v1_25_12',
  'v1_25_11',
  'v1_25_10',
  'v1_25_9',
  'v1_25_8',
  'v1_25_7',
  'v1_25_6',
  'v1_25_5',
  'v1_25_4',
  'v1_25_3',
  'v1_25_2',
  'v1_25_1',
  'v1_25_0',
  'v1_24_0',
  'v1_23_13',
  'v1_23_12',
  'v1_23_11',
  'v1_23_10',
  'v1_23_9',
  'v1_23_8',
  'v1_23_7',
  'v1_23_6',
  'v1_23_5',
  'v1_23_4',
  'v1_23_3',
  'v1_23_2',
  'v1_23_1',
  'v1_23_0',
  'v1_22_0',
  'v1_21_26',
  'v1_21_25',
  'v1_21_24',
  'v1_21_23',
  'v1_21_22',
  'v1_21_21',
  'v1_21_20',
  'v1_21_19',
  'v1_21_18',
  'v1_21_17',
  'v1_21_16',
  'v1_21_15',
  'v1_21_14',
  'v1_21_13',
  'v1_21_12',
  'v1_21_11',
  'v1_21_10',
  'v1_21_9',
  'v1_21_8',
  'v1_21_7',
  'v1_21_6',
  'v1_21_5',
  'v1_21_4',
  'v1_21_3',
  'v1_21_2',
  'v1_21_1',
  'v1_21_0',
  // v1_20_17..22 shipped complete in the 6 locales but were never listed here,
  // so six releases of history stayed invisible. Found by changelog-wiring.test.ts.
  'v1_20_22',
  'v1_20_21',
  'v1_20_20',
  'v1_20_19',
  'v1_20_18',
  'v1_20_17',
  'v1_20_16',
  'v1_20_15',
  'v1_20_14',
  'v1_20_13',
  'v1_20_12',
  'v1_20_11',
  'v1_20_10',
  'v1_20_9',
  'v1_20_8',
  'v1_20_7',
  'v1_20_6',
  'v1_20_5',
  'v1_20_4',
  'v1_20_3',
  'v1_20_2',
  'v1_20_1',
  'v1_20_0',
  'v1_18_1',
  'v1_18_0',
  'v1_17_2',
  'v1_17_1',
  'v1_17_0',
  'v1_16_10',
  'v1_16_9',
  'v1_16_8',
  'v1_16_7',
  'v1_16_6',
  'v1_16_5',
  'v1_16_4',
  'v1_16_3',
  'v1_16_2',
  'v1_16_1',
  'v1_16_0',
  'v1_15_3',
  'v1_15_2',
  'v1_15_1',
  'v1_15',
  'v1_14',
  'v1_13',
  'v1_12',
  'v1_11',
  'v1_10',
  'v1_9',
  'v1_8',
  'v1_7',
  'v1_6',
  'v1_5',
  'v1_4',
  'v1_3',
  'v1_1',
];

/**
 * Exported for `__tests__/feature-cards-wiring.test.ts`: a key listed in
 * `featureKeys` without an entry here resolves to `undefined`, and rendering
 * `<undefined />` crashes the whole FAQ page — a failure tsc cannot see through
 * the `as keyof` cast below.
 */
export const featureIcons = {
  architecture: Network,
  queryAnalyzer: Compass,
  planning: ListChecks,
  semanticTypes: Boxes,
  semanticValidation: ShieldCheck,
  memory: Brain,
  interests: Sparkles,
  security: Lock,
  hitl: UserCheck,
  semanticLeakDefense: Filter,
  healthMetrics: HeartHandshake,
  llm: Cpu,
  i18n: Languages,
  observability: Activity,
  voice: Volume2,
  costTransparency: DollarSign,
  scheduledActions: CalendarClock,
  mcp: Plug,
  mcpApps: Smartphone,
  excalidraw: Palette,
  multichannel: Radio,
  heartbeatAutonome: HeartPulse,
  webFetch: Globe2,
  knowledgeEnrichment: Newspaper,
  adaptiveReplanner: RefreshCw,
  parallelExecution: Layers,
  dataRegistry: FolderOpen,
  qualityAssurance: BadgeCheck,
  attachments: Paperclip,
  skills: Blocks,
  ragSpaces: Library,
  subAgents: Bot,
  browserControl: Monitor,
  psycheEngine: Brain,
  personalJournals: BookOpen,
  imageGeneration: ImageIcon,
  reactMode: Zap,
  proactiveInitiative: Compass,
  todayBriefing: Sunrise,
  telephony: PhoneCall,
};

/**
 * The "How LIA works" cards actually rendered, in display order. A card written
 * and translated into the six locales but absent from this array renders
 * nowhere — see `__tests__/feature-cards-wiring.test.ts`.
 */
export const featureKeys = [
  'architecture',
  'queryAnalyzer',
  'planning',
  'semanticTypes',
  'semanticValidation',
  'memory',
  'interests',
  'security',
  // Three cards shipped complete in the six locales and were never listed here,
  // so they rendered nowhere: `hitl` (rewritten at v1.25.7 for a surface nobody
  // could see), `semanticLeakDefense` (v1.20.6) and `healthMetrics` (v1.17.1).
  // Same never-wired class as the FAQ sections repaired on 2026-07-13.
  'hitl',
  'semanticLeakDefense',
  'healthMetrics',
  'llm',
  'i18n',
  'observability',
  'voice',
  'costTransparency',
  'scheduledActions',
  'mcp',
  'mcpApps',
  'excalidraw',
  'multichannel',
  'heartbeatAutonome',
  'webFetch',
  'knowledgeEnrichment',
  'adaptiveReplanner',
  'parallelExecution',
  'dataRegistry',
  'qualityAssurance',
  'attachments',
  'skills',
  'ragSpaces',
  'subAgents',
  'browserControl',
  'psycheEngine',
  'personalJournals',
  'imageGeneration',
  'reactMode',
  'proactiveInitiative',
  'todayBriefing',
  'telephony',
];

export function FAQContent({ lng, onShowWelcome, showWelcomeButton = false }: FAQContentProps) {
  const { t } = useTranslation(lng);
  const router = useRouter();
  const [searchQuery, setSearchQuery] = useState('');
  const [showIntro, setShowIntro] = useState(false);
  const [showChangelog, setShowChangelog] = useState(false);

  // W1: a written example becomes a real intent. The phrase is handed to the
  // chat composer through the shared `?draft=` rail — prefilled, NEVER sent, so
  // the user reads it, edits it and decides.
  const handleExampleClick = useCallback(
    (example: string) => {
      router.push(chatDraftHref(lng, example));
    },
    [router, lng]
  );

  // Build searchable FAQ data
  const faqData = useMemo(() => {
    const data: FAQQuestion[] = [];
    sections.forEach(section => {
      const questionCount = parseInt(t(`faq.sections.${section}.count`));
      for (let i = 1; i <= questionCount; i++) {
        data.push({
          section,
          questionKey: `q${i}`,
          question: t(`faq.sections.${section}.questions.q${i}.question`),
          answer: t(`faq.sections.${section}.questions.q${i}.answer`),
        });
      }
    });
    return data;
  }, [t]);

  // Filter FAQ based on search query (case-insensitive and accent-insensitive)
  const filteredData = useMemo(() => {
    if (!searchQuery.trim()) return null;

    const normalizedQuery = normalizeSearchText(searchQuery.trim());
    return faqData.filter(item => {
      const questionMatch = normalizeSearchText(item.question).includes(normalizedQuery);
      const answerMatch = normalizeSearchText(stripHtml(item.answer)).includes(normalizedQuery);
      return questionMatch || answerMatch;
    });
  }, [faqData, searchQuery]);

  const isSearching = searchQuery.trim().length > 0;
  const resultsCount = filteredData?.length ?? 0;

  // Get sections that have matching questions
  const matchingSections = useMemo(() => {
    if (!filteredData) return new Set<string>();
    return new Set(filteredData.map(item => item.section));
  }, [filteredData]);

  // Get matching question keys by section
  const matchingQuestionsBySection = useMemo(() => {
    if (!filteredData) return new Map<string, Set<string>>();
    const map = new Map<string, Set<string>>();
    filteredData.forEach(item => {
      if (!map.has(item.section)) {
        map.set(item.section, new Set());
      }
      map.get(item.section)!.add(item.questionKey);
    });
    return map;
  }, [filteredData]);

  return (
    <div className="space-y-6">
      {/* Search Bar with optional Welcome Button */}
      <Card className="p-4">
        <div
          className={`flex gap-3 ${showWelcomeButton && onShowWelcome ? 'flex-col sm:flex-row' : ''}`}
        >
          {/* Show Welcome Button - only if user has dismissed onboarding */}
          {showWelcomeButton && onShowWelcome && (
            <Button variant="outline" onClick={onShowWelcome} className="h-10 shrink-0 gap-2">
              <Sparkles className="h-4 w-4" />
              <span>{t('faq.show_welcome')}</span>
            </Button>
          )}

          {/* Search Input */}
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <input
              type="text"
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              placeholder={t('faq.search.placeholder')}
              aria-label={t('faq.search.placeholder')}
              className="flex h-10 w-full rounded-lg border border-input bg-background pl-10 pr-10 py-2 text-base shadow-sm transition-all duration-200 placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 focus-visible:border-primary hover:border-primary/50 md:text-sm"
            />
            {searchQuery && (
              <button
                onClick={() => setSearchQuery('')}
                className="absolute right-3 top-1/2 -translate-y-1/2 h-5 w-5 rounded-full bg-muted hover:bg-muted-foreground/20 flex items-center justify-center transition-colors"
                title={t('faq.search.clear')}
              >
                <X className="h-3 w-3 text-muted-foreground" />
              </button>
            )}
          </div>
        </div>
        {isSearching && (
          <p className="mt-2 text-sm text-muted-foreground">
            {resultsCount > 0
              ? t('faq.search.results_count', { count: resultsCount })
              : t('faq.search.no_results', { query: searchQuery })}
          </p>
        )}
      </Card>

      {/* How it Works Section - Collapsible */}
      {!isSearching && (
        <Card className="overflow-hidden">
          <button
            onClick={() => setShowIntro(!showIntro)}
            className="w-full p-6 flex items-center justify-between hover:bg-muted/50 transition-colors"
          >
            <div className="flex items-center gap-3">
              <div className="rounded-lg bg-gradient-to-br from-primary/20 to-primary/10 p-2">
                <Cpu className="h-5 w-5 text-primary" />
              </div>
              <div className="text-left">
                <h2 className="text-xl font-semibold">{t('faq.intro.title')}</h2>
                <p className="text-sm text-muted-foreground">{t('faq.intro.description')}</p>
              </div>
            </div>
            {showIntro ? (
              <ChevronUp className="h-5 w-5 text-muted-foreground" />
            ) : (
              <ChevronDown className="h-5 w-5 text-muted-foreground" />
            )}
          </button>

          {showIntro && (
            <div className="px-6 pb-6 pt-2 border-t">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {featureKeys.map(featureKey => {
                  const Icon = featureIcons[featureKey as keyof typeof featureIcons];
                  return (
                    <div
                      key={featureKey}
                      className="flex gap-3 p-4 rounded-lg bg-muted/30 hover:bg-muted/50 transition-colors"
                    >
                      <div className="rounded-md bg-primary/10 p-2 h-fit">
                        <Icon className="h-4 w-4 text-primary" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <h3 className="font-medium text-sm mb-1">
                          {t(`faq.intro.features.${featureKey}.title`)}
                        </h3>
                        <p className="text-xs text-muted-foreground leading-relaxed">
                          {t(`faq.intro.features.${featureKey}.description`)}
                        </p>
                      </div>
                    </div>
                  );
                })}
              </div>
              {/* Architecture diagram */}
              <div className="mt-6 rounded-lg overflow-hidden border bg-background relative">
                <Image
                  src="/schema2.png"
                  alt={t('faq.intro.diagram_alt')}
                  width={1200}
                  height={800}
                  className="w-full h-auto"
                  priority={false}
                />
              </div>
            </div>
          )}
        </Card>
      )}

      {/* Changelog Section - Collapsible */}
      {!isSearching && (
        <Card className="overflow-hidden">
          <button
            onClick={() => setShowChangelog(!showChangelog)}
            className="w-full p-6 flex items-center justify-between hover:bg-muted/50 transition-colors"
          >
            <div className="flex items-center gap-3">
              <div className="rounded-lg bg-gradient-to-br from-primary/20 to-primary/10 p-2">
                <History className="h-5 w-5 text-primary" />
              </div>
              <div className="text-left">
                <h2 className="text-xl font-semibold">{t('faq.changelog.title')}</h2>
                <p className="text-sm text-muted-foreground">{t('faq.changelog.description')}</p>
              </div>
            </div>
            {showChangelog ? (
              <ChevronUp className="h-5 w-5 text-muted-foreground" />
            ) : (
              <ChevronDown className="h-5 w-5 text-muted-foreground" />
            )}
          </button>

          {showChangelog && (
            <div className="px-6 pb-6 pt-2 border-t">
              <Accordion type="multiple" className="w-full">
                {changelogVersionKeys.map(versionKey => {
                  const itemCount = parseInt(t(`faq.changelog.versions.${versionKey}.count`));
                  return (
                    <AccordionItem key={versionKey} value={`changelog-${versionKey}`}>
                      <AccordionTrigger className="text-left">
                        <div className="flex items-center gap-3">
                          <span className="font-semibold">
                            {t(`faq.changelog.versions.${versionKey}.title`)}
                          </span>
                          <span className="text-xs text-muted-foreground font-normal">
                            {t(`faq.changelog.versions.${versionKey}.date`)}
                          </span>
                        </div>
                      </AccordionTrigger>
                      <AccordionContent>
                        <ul className="space-y-2 text-sm text-muted-foreground">
                          {Array.from({ length: itemCount }, (_, i) => (
                            <li key={i} className="flex gap-2">
                              <span className="text-primary mt-0.5">•</span>
                              <span
                                dangerouslySetInnerHTML={{
                                  __html: t(`faq.changelog.versions.${versionKey}.items.i${i + 1}`),
                                }}
                              />
                            </li>
                          ))}
                        </ul>
                      </AccordionContent>
                    </AccordionItem>
                  );
                })}
              </Accordion>
            </div>
          )}
        </Card>
      )}

      {/* No Results Message */}
      {isSearching && resultsCount === 0 && (
        <Card className="p-8 text-center">
          <Search className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
          <p className="text-lg font-medium text-muted-foreground">
            {t('faq.search.no_results', { query: searchQuery })}
          </p>
          <p className="text-sm text-muted-foreground mt-1">{t('faq.search.no_results_hint')}</p>
        </Card>
      )}

      {/* FAQ Sections */}
      {sections.map(section => {
        const Icon = FAQ_SECTION_ICONS[section];
        const questionCount = parseInt(t(`faq.sections.${section}.count`));

        // If searching, only show sections with matches
        if (isSearching && !matchingSections.has(section)) {
          return null;
        }

        const matchingKeys = matchingQuestionsBySection.get(section);

        return (
          <Card key={section} className="p-6">
            <div className="mb-4 flex items-center gap-3">
              <div className="rounded-lg bg-primary/10 p-2">
                <Icon className="h-5 w-5 text-primary" />
              </div>
              <div>
                <h2 className="text-xl font-semibold">{t(`faq.sections.${section}.title`)}</h2>
                <p className="text-sm text-muted-foreground">
                  {t(`faq.sections.${section}.description`)}
                </p>
              </div>
            </div>

            <Accordion
              type="multiple"
              className="w-full"
              defaultValue={
                isSearching && matchingKeys
                  ? Array.from(matchingKeys).map(k => `${section}-${k}`)
                  : []
              }
            >
              {Array.from({ length: questionCount }, (_, i) => i + 1).map(num => {
                const questionKey = `q${num}`;

                // If searching, only show matching questions
                if (isSearching && matchingKeys && !matchingKeys.has(questionKey)) {
                  return null;
                }

                const question = t(`faq.sections.${section}.questions.${questionKey}.question`);
                const answer = t(`faq.sections.${section}.questions.${questionKey}.answer`);

                return (
                  <AccordionItem key={num} value={`${section}-${questionKey}`}>
                    <AccordionTrigger className="text-left">
                      {isSearching ? (
                        <span
                          dangerouslySetInnerHTML={{
                            __html: highlightText(question, searchQuery),
                          }}
                        />
                      ) : (
                        question
                      )}
                    </AccordionTrigger>
                    <AccordionContent className="text-muted-foreground">
                      <FaqAnswer
                        lng={lng}
                        html={isSearching ? highlightText(answer, searchQuery) : answer}
                        onExampleClick={handleExampleClick}
                      />
                    </AccordionContent>
                  </AccordionItem>
                );
              })}
            </Accordion>
          </Card>
        );
      })}

      {/* Contact Support Section - Always visible */}
      {!isSearching && (
        <Card className="bg-primary/5 border-primary/20 p-6">
          <div className="flex items-start gap-4">
            <div className="rounded-lg bg-primary/10 p-3">
              <HelpCircle className="h-6 w-6 text-primary" />
            </div>
            <div className="flex-1">
              <h3 className="text-lg font-semibold mb-2">{t('faq.contact.title')}</h3>
              <p className="text-muted-foreground mb-4">{t('faq.contact.description')}</p>
              <p className="text-sm text-muted-foreground">{t('faq.contact.info')}</p>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}
