'use client';

import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import Link from 'next/link';
import Image from 'next/image';
import { Menu, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ThemeToggle } from '@/components/theme-toggle';
import { LanguageSelector } from '@/components/LanguageSelector';
import { cn } from '@/lib/utils';
import { buildLocalizedPath } from '@/utils/i18n-path-utils';
import type { Language } from '@/i18n/settings';

interface LandingHeaderProps {
  lng: string;
}

/** Anchor links to landing page sections */
const SECTION_ANCHORS = [
  { id: 'how-it-works', key: 'landing.nav.features' },
] as const;

/** Links to separate pages */
const PAGE_LINKS = [
  { id: 'blog', key: 'landing.nav.blog', href: '/blog' },
  { id: 'faq', key: 'landing.nav.faq', href: '/faq' },
  { id: 'why', key: 'landing.nav.philosophy', href: '/why' },
  { id: 'how', key: 'landing.nav.technical', href: '/how' },
] as const;

export function LandingHeader({ lng }: LandingHeaderProps) {
  const { t } = useTranslation();
  const [activeSection, setActiveSection] = useState<string>('');
  const [mobileOpen, setMobileOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);

  const loginHref = buildLocalizedPath('/login', lng as Language);
  const registerHref = buildLocalizedPath('/register', lng as Language);
  // Section anchors live on the landing root. Build absolute URLs (always
  // including the home path) so they work from secondary pages (Blog, FAQ,
  // Why, How) where the section IDs don't exist on the current document.
  // On the home itself, "/#id" still scrolls to the section without a reload.
  const homeHref = buildLocalizedPath('/', lng as Language);
  const buildAnchorHref = (id: string) => `${homeHref}#${id}`;

  // Scroll spy
  useEffect(() => {
    const handleScroll = () => {
      setScrolled(window.scrollY > 20);
    };

    const observer = new IntersectionObserver(
      entries => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setActiveSection(entry.target.id);
          }
        }
      },
      { rootMargin: '-20% 0px -70% 0px' }
    );

    const sections = SECTION_ANCHORS.map(({ id }) => document.getElementById(id)).filter(Boolean);
    sections.forEach(el => observer.observe(el!));

    window.addEventListener('scroll', handleScroll, { passive: true });
    handleScroll();

    return () => {
      observer.disconnect();
      window.removeEventListener('scroll', handleScroll);
    };
  }, []);

  // Close mobile menu on navigation or Escape key
  const handleNavClick = () => setMobileOpen(false);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && mobileOpen) {
        setMobileOpen(false);
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [mobileOpen]);

  return (
    <header
      className={cn(
        'fixed top-0 left-0 right-0 z-50 transition-all duration-300',
        scrolled || mobileOpen
          ? 'bg-background/95 backdrop-blur-xl shadow-sm border-b border-border/40'
          : 'bg-transparent'
      )}
    >
      <nav className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo */}
          <Link href={`/${lng}`} className="flex items-center gap-2 font-bold text-lg">
            <Image
              src="/v4-lia-brain.svg"
              alt="LIA"
              width={28}
              height={28}
              className="rounded-md"
            />
            <span>LIA</span>
          </Link>

          {/* Desktop nav — compact: anchors + page links */}
          <div className="hidden mobile:flex items-center gap-0.5">
            {SECTION_ANCHORS.map(({ id, key }) => (
              <a
                key={id}
                href={buildAnchorHref(id)}
                className={cn(
                  'px-2.5 py-2 text-sm font-medium rounded-md transition-colors',
                  activeSection === id
                    ? 'text-primary bg-primary/10'
                    : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'
                )}
              >
                {t(key)}
              </a>
            ))}
            <span className="w-px h-4 bg-border mx-1" aria-hidden="true" />
            {PAGE_LINKS.map(({ id, key, href }) => (
              <Link
                key={id}
                href={buildLocalizedPath(href, lng as Language)}
                className="px-2.5 py-2 text-sm font-medium rounded-md transition-colors text-muted-foreground hover:text-foreground hover:bg-muted/50"
              >
                {t(key)}
              </Link>
            ))}
          </div>

          {/* Right actions */}
          <div className="flex items-center gap-1.5">
            <div className="hidden sm:block">
              <LanguageSelector currentLocale={lng as Language} />
            </div>
            <ThemeToggle />
            <Button asChild variant="ghost" size="sm" className="hidden mobile:inline-flex">
              <Link href={loginHref}>{t('landing.nav.login')}</Link>
            </Button>
            <Button asChild size="sm" className="hidden mobile:inline-flex">
              <Link href={registerHref}>{t('landing.nav.get_started')}</Link>
            </Button>

            {/* Mobile hamburger */}
            <Button
              variant="ghost"
              size="sm"
              className="mobile:hidden w-10 h-10 p-0"
              onClick={() => setMobileOpen(!mobileOpen)}
              aria-label={
                mobileOpen ? t('common.close') || 'Close menu' : t('common.menu') || 'Menu'
              }
              aria-expanded={mobileOpen}
            >
              {mobileOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
            </Button>
          </div>
        </div>

        {/* Mobile menu — solid background */}
        {mobileOpen && (
          <div className="mobile:hidden border-t border-border/50 py-4 space-y-1 bg-background">
            {SECTION_ANCHORS.map(({ id, key }) => (
              <a
                key={id}
                href={buildAnchorHref(id)}
                onClick={handleNavClick}
                className={cn(
                  'block px-4 py-2.5 text-sm font-medium rounded-md transition-colors',
                  activeSection === id
                    ? 'text-primary bg-primary/10'
                    : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'
                )}
              >
                {t(key)}
              </a>
            ))}
            <div className="border-t border-border/30 my-2" />
            {PAGE_LINKS.map(({ id, key, href }) => (
              <Link
                key={id}
                href={buildLocalizedPath(href, lng as Language)}
                onClick={handleNavClick}
                className="block px-4 py-2.5 text-sm font-medium rounded-md transition-colors text-muted-foreground hover:text-foreground hover:bg-muted/50"
              >
                {t(key)}
              </Link>
            ))}
            <div className="border-t border-border/50 mt-3 pt-3 flex items-center gap-2 px-4">
              <LanguageSelector currentLocale={lng as Language} />
              <Link
                href={loginHref}
                onClick={handleNavClick}
                className="text-sm font-medium text-muted-foreground hover:text-foreground"
              >
                {t('landing.nav.login')}
              </Link>
            </div>
            <div className="px-4 pt-2">
              <Button asChild size="sm" className="w-full">
                <Link href={registerHref} onClick={handleNavClick}>
                  {t('landing.nav.get_started')}
                </Link>
              </Button>
            </div>
          </div>
        )}
      </nav>
    </header>
  );
}
