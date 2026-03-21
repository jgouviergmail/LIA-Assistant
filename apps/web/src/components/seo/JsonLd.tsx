import type { Language } from '@/i18n/settings';
import { languages, fallbackLng, LOCALE_MAP } from '@/i18n/settings';
import { LANDING_STATS } from '@/components/landing/constants';

const BASE_URL = process.env.NEXT_PUBLIC_APP_URL || 'https://lia.jeyswork.com';

/**
 * Build the full URL for a given language.
 */
function buildLangUrl(lng: Language): string {
  return lng === fallbackLng ? BASE_URL : `${BASE_URL}/${lng}`;
}

/**
 * WebSite schema — site-level identity for search engines and AI systems.
 * Placed in root layout.
 */
export function WebSiteJsonLd() {
  const schema = {
    '@context': 'https://schema.org',
    '@type': 'WebSite',
    name: 'LIA',
    alternateName: 'LIA — Intelligent Personal AI Assistant',
    url: BASE_URL,
    description:
      'LIA orchestrates 15 specialized AI agents to manage your emails, calendar, contacts, and more. Human validation at every step, privacy by design.',
    inLanguage: languages.map(lng => LOCALE_MAP[lng]),
    potentialAction: {
      '@type': 'ReadAction',
      target: BASE_URL,
    },
  };

  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(schema) }}
    />
  );
}

/**
 * Organization schema — brand authority signal.
 * Placed in root layout.
 */
export function OrganizationJsonLd() {
  const schema = {
    '@context': 'https://schema.org',
    '@type': 'Organization',
    name: 'LIA',
    url: BASE_URL,
    logo: `${BASE_URL}/icon.svg`,
    description:
      'Open-source multi-agent conversational AI assistant with human-in-the-loop approval workflows.',
    sameAs: ['https://github.com/JeysWork/LIA'],
    knowsAbout: [
      'Conversational AI',
      'Multi-Agent Systems',
      'LangGraph Orchestration',
      'Human-in-the-Loop Approval',
      'Natural Language Processing',
    ],
  };

  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(schema) }}
    />
  );
}

interface SoftwareApplicationJsonLdProps {
  lng: Language;
  title: string;
  description: string;
}

/**
 * SoftwareApplication schema — rich snippet for the landing page.
 * Provides structured product information to search engines and AI systems.
 */
export function SoftwareApplicationJsonLd({
  lng,
  title,
  description,
}: SoftwareApplicationJsonLdProps) {
  const schema = {
    '@context': 'https://schema.org',
    '@type': 'SoftwareApplication',
    name: 'LIA',
    alternateName: title,
    description,
    url: buildLangUrl(lng),
    applicationCategory: 'ProductivityApplication',
    operatingSystem: 'Web',
    offers: {
      '@type': 'Offer',
      price: '0',
      priceCurrency: 'EUR',
      availability: 'https://schema.org/InStock',
    },
    featureList: [
      `${LANDING_STATS.agents}+ specialized AI agents`,
      `${LANDING_STATS.providers} LLM providers (OpenAI, Anthropic, Google, DeepSeek, Qwen, Ollama)`,
      'Human-in-the-Loop approval (6 levels)',
      'Google, Apple iCloud & Microsoft 365 connectors',
      `${LANDING_STATS.uiLanguages} UI languages, ${LANDING_STATS.voiceLanguages}+ voice languages`,
      `${LANDING_STATS.tools}+ integrated tools`,
      'Voice mode with speech synthesis',
      'Browser automation (Playwright)',
      'Knowledge Spaces (RAG)',
      'Extensible via MCP protocol',
    ],
    screenshot: `${BASE_URL}/Title.png`,
    softwareVersion: '1.8.1',
    inLanguage: LOCALE_MAP[lng],
    image: `${BASE_URL}/Title.png`,
  };

  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(schema) }}
    />
  );
}

interface FAQPageJsonLdProps {
  questions: Array<{ question: string; answer: string }>;
}

/**
 * FAQPage schema — structured FAQ data for rich snippets and AI extraction.
 */
export function FAQPageJsonLd({ questions }: FAQPageJsonLdProps) {
  const schema = {
    '@context': 'https://schema.org',
    '@type': 'FAQPage',
    mainEntity: questions.map(({ question, answer }) => ({
      '@type': 'Question',
      name: question,
      acceptedAnswer: {
        '@type': 'Answer',
        // Strip HTML tags from answers for clean schema.org output
        text: answer
          .replace(/<[^>]*>/g, ' ')
          .replace(/\s+/g, ' ')
          .trim(),
      },
    })),
  };

  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(schema) }}
    />
  );
}

interface BreadcrumbJsonLdProps {
  items: Array<{ name: string; url: string }>;
}

/**
 * BreadcrumbList schema — navigation breadcrumb for rich snippets.
 * Helps search engines understand page hierarchy.
 */
export function BreadcrumbJsonLd({ items }: BreadcrumbJsonLdProps) {
  const schema = {
    '@context': 'https://schema.org',
    '@type': 'BreadcrumbList',
    itemListElement: items.map((item, index) => ({
      '@type': 'ListItem',
      position: index + 1,
      name: item.name,
      item: item.url,
    })),
  };

  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(schema) }}
    />
  );
}

interface HowToJsonLdProps {
  name: string;
  description: string;
  steps: Array<{ name: string; text: string }>;
}

/**
 * HowTo schema — structured how-to data for rich snippets.
 * Used on the landing page "How it works" section.
 */
export function HowToJsonLd({ name, description, steps }: HowToJsonLdProps) {
  const schema = {
    '@context': 'https://schema.org',
    '@type': 'HowTo',
    name,
    description,
    step: steps.map((step, index) => ({
      '@type': 'HowToStep',
      position: index + 1,
      name: step.name,
      text: step.text,
    })),
  };

  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(schema) }}
    />
  );
}

interface BlogListJsonLdProps {
  lng: Language;
  title: string;
  description: string;
  articles: Array<{ title: string; url: string; date: string; excerpt: string }>;
}

/**
 * Blog schema — structured data for blog listing page.
 */
export function BlogListJsonLd({ lng, title, description, articles }: BlogListJsonLdProps) {
  const schema = {
    '@context': 'https://schema.org',
    '@type': 'Blog',
    name: title,
    description,
    url: `${buildLangUrl(lng)}/blog`,
    inLanguage: LOCALE_MAP[lng],
    blogPost: articles.map(article => ({
      '@type': 'BlogPosting',
      headline: article.title,
      description: article.excerpt,
      datePublished: article.date,
      url: article.url,
      author: {
        '@type': 'Organization',
        name: 'LIA',
      },
    })),
  };

  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(schema) }}
    />
  );
}
