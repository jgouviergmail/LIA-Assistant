import Link from 'next/link';
import Image from 'next/image';
import { Github } from 'lucide-react';
import { initI18next } from '@/i18n';
import { buildLocalizedPath } from '@/utils/i18n-path-utils';
import type { Language } from '@/i18n/settings';
import { APP_VERSION } from '@/lib/version';

const GITHUB_REPO_URL = 'https://github.com/jgouviergmail/LIA-Assistant';

interface PublicFooterProps {
  lng: string;
}

/**
 * Shared footer for all public pages (except landing which has its own LandingFooter).
 * Provides internal links to all public pages for SEO interlinking.
 */
export async function PublicFooter({ lng }: PublicFooterProps) {
  const { t } = await initI18next(lng);
  const lang = lng as Language;
  const year = new Date().getFullYear();

  const navLinks = [
    { href: buildLocalizedPath('/', lang), label: t('public_footer.home') },
    { href: buildLocalizedPath('/blog', lang), label: t('public_footer.blog') },
    { href: buildLocalizedPath('/faq', lang), label: t('public_footer.faq') },
    { href: buildLocalizedPath('/how', lang), label: t('public_footer.technical') },
    { href: buildLocalizedPath('/why', lang), label: t('public_footer.philosophy') },
  ];

  const legalLinks = [
    { href: buildLocalizedPath('/privacy', lang), label: t('public_footer.privacy') },
    { href: buildLocalizedPath('/terms', lang), label: t('public_footer.terms') },
  ];

  return (
    <footer className="border-t border-border/40 py-8 mt-12">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Logo */}
        <div className="flex justify-center mb-6">
          <Link href={buildLocalizedPath('/', lang)} className="flex items-center gap-2">
            <Image
              src="/v4-lia-brain.svg"
              alt="LIA"
              width={24}
              height={24}
              className="rounded-md"
            />
            <span className="font-bold text-foreground">LIA</span>
          </Link>
        </div>

        {/* Navigation links */}
        <nav className="flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-sm text-muted-foreground mb-4">
          {navLinks.map(({ href, label }) => (
            <Link key={href} href={href} className="hover:text-foreground transition-colors">
              {label}
            </Link>
          ))}
        </nav>

        {/* Legal links */}
        <div className="flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-sm text-muted-foreground mb-6">
          {legalLinks.map(({ href, label }) => (
            <Link key={href} href={href} className="hover:text-foreground transition-colors">
              {label}
            </Link>
          ))}
        </div>

        {/* Copyright + GitHub */}
        <div className="flex items-center justify-center gap-4 text-xs text-muted-foreground">
          <span>
            {t('landing.footer.copyright', { year })} · v{APP_VERSION}
          </span>
          <a
            href={GITHUB_REPO_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 hover:text-foreground transition-colors"
          >
            <Github className="w-3.5 h-3.5" />
            GitHub
          </a>
        </div>
      </div>
    </footer>
  );
}
