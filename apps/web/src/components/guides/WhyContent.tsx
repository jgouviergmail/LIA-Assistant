import fs from 'fs';
import path from 'path';
import { initI18next } from '@/i18n';
import { GuideMarkdown } from './GuideMarkdown';
import { GuideToc } from './GuideLayout';
import { WHY_TOC_SECTIONS } from './guides-toc';

interface WhyContentProps {
  lng: string;
}

function loadGuideContent(lng: string): string {
  const guidesDir = path.join(process.cwd(), 'src', 'data', 'guides');
  const localizedPath = path.join(guidesDir, `why.${lng}.md`);
  const fallbackPath = path.join(guidesDir, 'why.fr.md');

  try {
    return fs.readFileSync(fs.existsSync(localizedPath) ? localizedPath : fallbackPath, 'utf-8');
  } catch {
    return '';
  }
}

export async function WhyContent({ lng }: WhyContentProps) {
  const { t } = await initI18next(lng);

  const tocItems = WHY_TOC_SECTIONS.map(({ id, icon }) => ({
    id,
    label: t(`why.toc.${id}`),
    icon,
  }));

  const sectionIds = WHY_TOC_SECTIONS.map(s => s.id);
  const sectionIcons = WHY_TOC_SECTIONS.map(s => s.icon);
  const content = loadGuideContent(lng);

  return (
    <article className="max-w-3xl mx-auto">
      <GuideToc items={tocItems} />
      <GuideMarkdown content={content} sectionIds={sectionIds} sectionIcons={sectionIcons} />
    </article>
  );
}
