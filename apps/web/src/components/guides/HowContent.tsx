import fs from 'fs';
import path from 'path';
import { initI18next } from '@/i18n';
import { GuideMarkdown } from './GuideMarkdown';
import { GuideToc } from './GuideLayout';
import { HOW_TOC_SECTIONS } from './guides-toc';

interface HowContentProps {
  lng: string;
}

function loadGuideContent(lng: string): string {
  const guidesDir = path.join(process.cwd(), 'src', 'data', 'guides');
  const localizedPath = path.join(guidesDir, `how.${lng}.md`);
  const fallbackPath = path.join(guidesDir, 'how.fr.md');

  try {
    return fs.readFileSync(fs.existsSync(localizedPath) ? localizedPath : fallbackPath, 'utf-8');
  } catch {
    return '';
  }
}

export async function HowContent({ lng }: HowContentProps) {
  const { t } = await initI18next(lng);

  const tocItems = HOW_TOC_SECTIONS.map(({ id, icon }) => ({
    id,
    label: t(`how.toc.${id}`),
    icon,
  }));

  const sectionIds = HOW_TOC_SECTIONS.map(s => s.id);
  const sectionIcons = HOW_TOC_SECTIONS.map(s => s.icon);
  const content = loadGuideContent(lng);

  return (
    <article className="max-w-3xl mx-auto">
      <GuideToc items={tocItems} />
      <GuideMarkdown content={content} sectionIds={sectionIds} sectionIcons={sectionIcons} />
    </article>
  );
}
