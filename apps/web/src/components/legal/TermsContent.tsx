import fs from 'fs';
import path from 'path';
import {
  FileText, CheckCircle, UserPlus, Layers, Shield, GitBranch,
  Database, Cloud, Scale, XCircle, Gavel,
} from 'lucide-react';
import { initI18next } from '@/i18n';
import { GuideMarkdown } from '../guides/GuideMarkdown';
import { GuideToc } from '../guides/GuideLayout';

interface TermsContentProps {
  lng: string;
}

const TOC_SECTIONS = [
  { id: 'purpose', icon: FileText },
  { id: 'acceptance', icon: CheckCircle },
  { id: 'registration', icon: UserPlus },
  { id: 'service', icon: Layers },
  { id: 'usage', icon: Shield },
  { id: 'opensource', icon: GitBranch },
  { id: 'personal_data', icon: Database },
  { id: 'availability', icon: Cloud },
  { id: 'liability', icon: Scale },
  { id: 'termination', icon: XCircle },
  { id: 'applicable_law', icon: Gavel },
] as const;

/**
 * Load terms of service markdown content.
 * Falls back to English (not French) for non-FR/EN languages,
 * as English is more universally readable for legal documents.
 */
function loadGuideContent(lng: string): string {
  const guidesDir = path.join(process.cwd(), 'src', 'data', 'guides');
  const localizedPath = path.join(guidesDir, `terms.${lng}.md`);
  const fallbackPath = path.join(guidesDir, 'terms.en.md');

  try {
    return fs.readFileSync(fs.existsSync(localizedPath) ? localizedPath : fallbackPath, 'utf-8');
  } catch {
    return '';
  }
}

export async function TermsContent({ lng }: TermsContentProps) {
  const { t } = await initI18next(lng);

  const tocItems = TOC_SECTIONS.map(({ id, icon }) => ({
    id,
    label: t(`terms.toc.${id}`),
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
