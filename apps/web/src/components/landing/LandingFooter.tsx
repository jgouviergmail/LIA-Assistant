import Link from 'next/link';
import { initI18next } from '@/i18n';
import Image from 'next/image';
import { Github } from 'lucide-react';
import { APP_VERSION } from '@/lib/version';
import { buildLocalizedPath } from '@/utils/i18n-path-utils';
import type { Language } from '@/i18n/settings';

const GITHUB_REPO_URL = 'https://github.com/jgouviergmail/LIA-Assistant';

interface LandingFooterProps {
  lng: string;
}

export async function LandingFooter({ lng }: LandingFooterProps) {
  const { t } = await initI18next(lng);
  const lang = lng as Language;
  const year = new Date().getFullYear();

  const columns = [
    {
      title: t('landing.footer.product'),
      links: [
        { label: t('landing.footer.features'), href: '#features' },
        { label: t('landing.footer.how_it_works'), href: '#how-it-works' },
      ],
    },
    {
      title: t('landing.footer.resources'),
      links: [
        { label: t('landing.footer.blog'), href: buildLocalizedPath('/blog', lang) },
        { label: t('landing.footer.faq'), href: buildLocalizedPath('/faq', lang) },
        { label: t('landing.footer.technical'), href: buildLocalizedPath('/how', lang) },
        { label: t('landing.footer.philosophy'), href: buildLocalizedPath('/why', lang) },
      ],
    },
    {
      title: t('landing.footer.legal'),
      links: [
        { label: t('landing.footer.privacy'), href: buildLocalizedPath('/privacy', lang) },
        { label: t('landing.footer.terms'), href: buildLocalizedPath('/terms', lang) },
      ],
    },
    {
      title: t('landing.footer.community'),
      links: [{ label: 'GitHub', href: GITHUB_REPO_URL, external: true }],
    },
  ];

  return (
    <footer className="border-t border-border py-12">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Columns */}
        <div className="grid grid-cols-2 mobile:grid-cols-4 gap-8 mb-10">
          {columns.map(({ title, links }) => (
            <div key={title}>
              <h3 className="text-sm font-semibold text-foreground mb-3">{title}</h3>
              <ul className="space-y-2">
                {links.map(({ label, href, ...rest }) => {
                  const isExternal = 'external' in rest;
                  const isAnchor = href.startsWith('#');

                  if (isExternal) {
                    return (
                      <li key={label}>
                        <a
                          href={href}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
                        >
                          <Github className="w-3.5 h-3.5" />
                          {label}
                        </a>
                      </li>
                    );
                  }

                  if (isAnchor) {
                    return (
                      <li key={label}>
                        <a
                          href={href}
                          className="text-sm text-muted-foreground hover:text-foreground transition-colors"
                        >
                          {label}
                        </a>
                      </li>
                    );
                  }

                  return (
                    <li key={label}>
                      <Link
                        href={href}
                        className="text-sm text-muted-foreground hover:text-foreground transition-colors"
                      >
                        {label}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </div>

        {/* Bottom bar */}
        <div className="border-t border-border pt-6 flex flex-col mobile:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <Image
              src="/v4-lia-brain.svg"
              alt="LIA"
              width={24}
              height={24}
              className="rounded-md"
            />
            <span className="text-sm text-muted-foreground">
              {t('landing.footer.copyright', { year })} · v{APP_VERSION}
            </span>
          </div>
        </div>
      </div>
    </footer>
  );
}
