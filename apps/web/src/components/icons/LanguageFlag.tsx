import Image from 'next/image';

import type { Language } from '@/i18n/settings';

const FLAG_ASSETS: Record<Language, string> = {
  fr: '/flags/fr.svg',
  en: '/flags/gb.svg',
  es: '/flags/es.svg',
  de: '/flags/de.svg',
  it: '/flags/it.svg',
  zh: '/flags/cn.svg',
};

/** Decorative local SVG: flag emojis can render as country letters on Windows. */
export function LanguageFlag({ language }: { language: Language }) {
  return (
    <Image
      src={FLAG_ASSETS[language]}
      width={24}
      height={18}
      alt=""
      aria-hidden="true"
      className="h-[18px] w-6 shrink-0 rounded-[2px]"
    />
  );
}
