import fs from 'fs';
import path from 'path';
import {
  Sparkles,
  Compass,
  ClipboardCheck,
  Scale,
  Activity,
  BadgeCheck,
  Lightbulb,
} from 'lucide-react';
import { initI18next } from '@/i18n';
import { GuideMarkdown } from './GuideMarkdown';
import { GuideToc } from './GuideLayout';

interface StoryContentProps {
  lng: string;
}

const TOC_SECTIONS = [
  { id: 'essentials', icon: Sparkles },
  { id: 'approach', icon: Compass },
  { id: 'method', icon: ClipboardCheck },
  { id: 'tradeoffs', icon: Scale },
  { id: 'operations', icon: Activity },
  { id: 'proof', icon: BadgeCheck },
  { id: 'convictions', icon: Lightbulb },
] as const;

function loadGuideContent(lng: string): string {
  const guidesDir = path.join(process.cwd(), 'src', 'data', 'guides');
  const localizedPath = path.join(guidesDir, `story.${lng}.md`);
  const fallbackPath = path.join(guidesDir, 'story.fr.md');

  try {
    return fs.readFileSync(fs.existsSync(localizedPath) ? localizedPath : fallbackPath, 'utf-8');
  } catch {
    return '';
  }
}

export async function StoryContent({ lng }: StoryContentProps) {
  const { t } = await initI18next(lng);

  const tocItems = TOC_SECTIONS.map(({ id, icon }) => ({
    id,
    label: t(`story.toc.${id}`),
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
