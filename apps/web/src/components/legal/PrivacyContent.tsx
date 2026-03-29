import fs from 'fs';
import path from 'path';
import {
  Info, Database, Scale, Server, ShieldCheck, Cpu,
  Clock, UserCheck, Cookie, Mail,
} from 'lucide-react';
import { initI18next } from '@/i18n';
import { GuideMarkdown } from '../guides/GuideMarkdown';
import { GuideToc } from '../guides/GuideLayout';

interface PrivacyContentProps {
  lng: string;
}

const TOC_SECTIONS = [
  { id: 'introduction', icon: Info },
  { id: 'data_collected', icon: Database },
  { id: 'legal_basis', icon: Scale },
  { id: 'hosting', icon: Server },
  { id: 'security', icon: ShieldCheck },
  { id: 'llm_providers', icon: Cpu },
  { id: 'retention', icon: Clock },
  { id: 'rights', icon: UserCheck },
  { id: 'cookies', icon: Cookie },
  { id: 'contact', icon: Mail },
] as const;

/**
 * Load privacy policy markdown content.
 * Falls back to English (not French) for non-FR/EN languages,
 * as English is more universally readable for legal documents.
 */
function loadGuideContent(lng: string): string {
  const guidesDir = path.join(process.cwd(), 'src', 'data', 'guides');
  const localizedPath = path.join(guidesDir, `privacy.${lng}.md`);
  const fallbackPath = path.join(guidesDir, 'privacy.en.md');

  try {
    return fs.readFileSync(fs.existsSync(localizedPath) ? localizedPath : fallbackPath, 'utf-8');
  } catch {
    return '';
  }
}

export async function PrivacyContent({ lng }: PrivacyContentProps) {
  const { t } = await initI18next(lng);

  const tocItems = TOC_SECTIONS.map(({ id, icon }) => ({
    id,
    label: t(`privacy.toc.${id}`),
    icon,
  }));

  const sectionIds = TOC_SECTIONS.map(s => s.id);
  const sectionIcons = TOC_SECTIONS.map(s => s.icon);
  const content = loadGuideContent(lng);

  return (
    <article className="max-w-3xl mx-auto">
      <GuideToc items={tocItems} />
      <GuideMarkdown content={content} sectionIds={sectionIds} sectionIcons={sectionIcons} />
    </article>
  );
}
