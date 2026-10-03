import Link from 'next/link';
import {
  Activity,
  BadgeCheck,
  Database,
  Landmark,
  Lock,
  PackageCheck,
  ShieldCheck,
} from 'lucide-react';
import { buildLocalizedPath } from '@/utils/i18n-path-utils';
import type { Language } from '@/i18n/settings';
import type { Translate } from './FeatureCatalog';

/**
 * The former "Security & Privacy" section, presented inside chapter
 * 04's catalog (reusing the localized `landing.security.*` copy ×6). Chapter
 * 04 carries the trust narrative; this block keeps every detail one click
 * away — and crawlable, since the disclosure keeps its content in the DOM.
 *
 * The blocks run from design to operation: what the account controls, how the
 * architecture and the encryption protect it, what privacy rules hold, how a
 * version is built and verified, and how production is watched. An even count,
 * so the two-column grid closes on a full row.
 */

const SECURITY_BLOCKS = [
  { key: 'data_control', icon: Database },
  { key: 'bff', icon: Landmark },
  { key: 'encryption', icon: Lock },
  { key: 'gdpr', icon: ShieldCheck },
  { key: 'supply_chain', icon: PackageCheck },
  { key: 'operations', icon: Activity },
] as const;

/**
 * Open standards and regulatory reference points relevant to the product.
 *
 * Proper nouns, so they are identical in the six locales and live here rather
 * than in six translation files that could drift apart. A visitor deciding
 * whether to trust an assistant reads « GDPR » and « AI Act » faster than any
 * paragraph — and an open standard is what makes a promise checkable against a
 * text somebody else wrote.
 */
const STANDARDS = [
  'RGPD / GDPR',
  'EU AI Act',
  'MCP 2026-07-28',
  'Agent Plugins 1.0',
  'agentskills.io',
  'OWASP Top 10',
  'WebAuthn / FIDO2',
  'OAuth 2.1 + PKCE',
  'OpenTelemetry',
  'Prometheus / OpenMetrics',
  'CycloneDX SBOM',
  'ISO/IEC 25010',
  'Keep a Changelog',
  'SemVer 2.0',
  'Conventional Commits',
  'WCAG 2.2 AA',
] as const;

export function SecurityDetail({ t, lng }: { t: Translate; lng: string }) {
  return (
    <div className="mt-6 border-t border-dashed border-border pt-5">
      <h4 className="text-sm font-semibold">{t('landing.security.title')}</h4>
      <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
        {t('landing.security.intro')}
      </p>
      <ul className="mt-4 grid list-none grid-cols-1 gap-4 md:grid-cols-2">
        {SECURITY_BLOCKS.map(({ key, icon: Icon }) => (
          <li key={key} className="rounded-xl border border-border bg-background p-5">
            <h5 className="flex items-center gap-2 text-px-13 font-semibold">
              <Icon aria-hidden="true" className="h-4 w-4 shrink-0 text-primary" />
              {t(`landing.security.${key}.title`)}
            </h5>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">
              {t(`landing.security.${key}.description`)}
            </p>
          </li>
        ))}
      </ul>
      <div className="mt-5 rounded-xl border border-dashed border-border bg-muted/30 p-4">
        <h5 className="flex items-center gap-2 text-px-13 font-semibold">
          <BadgeCheck aria-hidden="true" className="h-4 w-4 shrink-0 text-primary" />
          {t('landing.security.standards.title')}
        </h5>
        <ul className="mt-3 flex list-none flex-wrap gap-2">
          {STANDARDS.map(name => (
            <li
              key={name}
              className="rounded-full border border-border bg-background px-2.5 py-1 text-px-11 font-medium"
            >
              {name}
            </li>
          ))}
        </ul>
        <p className="mt-3 text-xs leading-relaxed text-muted-foreground">
          {t('landing.security.standards.note')}
        </p>
      </div>
      <Link
        href={buildLocalizedPath('/privacy', lng as Language)}
        className="mt-4 inline-block text-xs font-medium text-primary hover:underline"
      >
        {t('landing.security.privacy_link')} →
      </Link>
    </div>
  );
}
