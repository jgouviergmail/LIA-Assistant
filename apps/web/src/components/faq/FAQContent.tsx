'use client';

import { useState, useMemo } from 'react';
import Image from 'next/image';
import { useTranslation } from '@/i18n/client';
import { type Language } from '@/i18n/settings';
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion';
import { normalizeSearchText } from '@/lib/utils';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import {
  MessageSquare,
  Settings,
  Shield,
  Zap,
  HelpCircle,
  Globe,
  Mail,
  Cloud,
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
  Bell,
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
  Bot,
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

const sectionIcons = {
  getting_started: Zap,
  chat: MessageSquare,
  settings: Settings,
  connectors: Globe,
  tool_examples_services: Mail,
  tool_examples_external: Cloud,
  rappels: Bell,
  interests: Sparkles,
  heartbeat: Activity,
  scheduled_actions: CalendarClock,
  mcp_servers: Plug,
  skills: Blocks,
  sub_agents: Bot,
  rag_spaces: Library,
  privacy: Shield,
  other: HelpCircle,
};

const sections = [
  'getting_started',
  'chat',
  'settings',
  'connectors',
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
  'privacy',
  'other',
];

function stripHtml(html: string): string {
  return html
    .replace(/<[^>]*>/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

/**
 * Highlight search query matches in text content (accent-insensitive).
 * XSS Protection: User query is escaped before being used in the highlight regex.
 * The text content (from translations) contains safe HTML and is NOT escaped.
 *
 * This function finds matches using normalized (accent-stripped) text but
 * highlights the original characters in the source text.
 */
function highlightText(text: string, query: string): string {
  if (!query.trim()) return text;

  const normalizedQuery = normalizeSearchText(query.trim());
  if (!normalizedQuery) return text;

  // For text with HTML, we need to only highlight text nodes, not tags
  // Split by HTML tags, highlight text parts, then rejoin
  const parts = text.split(/(<[^>]*>)/);

  return parts
    .map(part => {
      // Skip HTML tags
      if (part.startsWith('<') && part.endsWith('>')) {
        return part;
      }
      // Highlight text content
      return highlightTextContent(part, normalizedQuery);
    })
    .join('');
}

/**
 * Highlight matches in plain text (no HTML tags).
 * Maps normalized positions back to original text positions.
 */
function highlightTextContent(text: string, normalizedQuery: string): string {
  if (!text) return text;

  const normalizedText = normalizeSearchText(text);

  // Find all match positions in normalized text
  const escapedQuery = normalizedQuery.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const regex = new RegExp(escapedQuery, 'gi');

  const matches: Array<{ start: number; end: number }> = [];
  let match;
  while ((match = regex.exec(normalizedText)) !== null) {
    matches.push({ start: match.index, end: match.index + match[0].length });
  }

  if (matches.length === 0) return text;

  // Build mapping from original char index to normalized char index
  // NFD normalization: é (1 char) → e + ́ (2 chars), then we remove diacritics
  const originalToNormalized: number[] = [];
  let normalizedPos = 0;

  for (let i = 0; i < text.length; i++) {
    originalToNormalized.push(normalizedPos);
    const char = text[i].toLowerCase();
    const nfdChar = char.normalize('NFD');
    // Count base characters (non-combining marks) after NFD
    const baseChars = nfdChar.replace(/[\u0300-\u036f]/g, '').length;
    normalizedPos += baseChars;
  }
  originalToNormalized.push(normalizedPos); // End sentinel

  // Map normalized match positions to original positions
  const originalMatches: Array<{ start: number; end: number }> = [];

  for (const m of matches) {
    let origStart = 0;
    let origEnd = text.length;

    // Find original start: first i where normalizedPos[i] <= m.start < normalizedPos[i+1]
    for (let i = 0; i < text.length; i++) {
      if (originalToNormalized[i] <= m.start && originalToNormalized[i + 1] > m.start) {
        origStart = i;
        break;
      }
    }

    // Find original end: first i where normalizedPos[i] >= m.end
    for (let i = origStart; i <= text.length; i++) {
      if (originalToNormalized[i] >= m.end) {
        origEnd = i;
        break;
      }
    }

    originalMatches.push({ start: origStart, end: origEnd });
  }

  // Build highlighted string (don't escape - content is from safe translations)
  let result = '';
  let lastEnd = 0;

  for (const m of originalMatches) {
    result += text.slice(lastEnd, m.start);
    result += `<mark class="bg-yellow-200 dark:bg-yellow-800 rounded px-0.5">${text.slice(m.start, m.end)}</mark>`;
    lastEnd = m.end;
  }
  result += text.slice(lastEnd);

  return result;
}

const featureIcons = {
  architecture: Network,
  queryAnalyzer: Compass,
  planning: ListChecks,
  semanticTypes: Boxes,
  semanticValidation: ShieldCheck,
  memory: Brain,
  interests: Sparkles,
  security: Lock,
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
};

const featureKeys = ['architecture', 'queryAnalyzer', 'planning', 'semanticTypes', 'semanticValidation', 'memory', 'interests', 'security', 'llm', 'i18n', 'observability', 'voice', 'costTransparency', 'scheduledActions', 'mcp', 'mcpApps', 'excalidraw', 'multichannel', 'heartbeatAutonome', 'webFetch', 'knowledgeEnrichment', 'adaptiveReplanner', 'parallelExecution', 'dataRegistry', 'qualityAssurance', 'attachments', 'skills', 'ragSpaces', 'subAgents'];

export function FAQContent({ lng, onShowWelcome, showWelcomeButton = false }: FAQContentProps) {
  const { t } = useTranslation(lng);
  const [searchQuery, setSearchQuery] = useState('');
  const [showIntro, setShowIntro] = useState(false);

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
        <div className={`flex gap-3 ${showWelcomeButton && onShowWelcome ? 'flex-col sm:flex-row' : ''}`}>
          {/* Show Welcome Button - only if user has dismissed onboarding */}
          {showWelcomeButton && onShowWelcome && (
            <Button
              variant="outline"
              onClick={onShowWelcome}
              className="h-10 shrink-0 gap-2"
            >
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

      {/* No Results Message */}
      {isSearching && resultsCount === 0 && (
        <Card className="p-8 text-center">
          <Search className="h-12 w-12 mx-auto text-muted-foreground/50 mb-4" />
          <p className="text-lg font-medium text-muted-foreground">
            {t('faq.search.no_results', { query: searchQuery })}
          </p>
          <p className="text-sm text-muted-foreground mt-1">{t('faq.search.no_results_hint')}</p>
        </Card>
      )}

      {/* FAQ Sections */}
      {sections.map(section => {
        const Icon = sectionIcons[section as keyof typeof sectionIcons];
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
                      <div
                        dangerouslySetInnerHTML={{
                          __html: isSearching ? highlightText(answer, searchQuery) : answer,
                        }}
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
