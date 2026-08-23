'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { FileQuestion } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { buildLocalizedPath, getLanguageFromPath } from '@/utils/i18n-path-utils';

/**
 * The 404 page.
 *
 * Deliberately inside `[lng]/` rather than at `app/`: `[lng]/layout.tsx` IS the
 * root layout — it is the only one that renders `<html>` and `<body>` — so a
 * sibling `app/not-found.tsx` would have no document to live in, and no i18n
 * provider either. Placed here it inherits both, and a missing page finally
 * answers in the visitor's own language instead of Next's built-in English
 * default.
 *
 * The home link is rebuilt from the current path rather than hardcoded: the
 * locale prefix is part of the URL, and sending a Spanish visitor to the French
 * home page is its own small 404.
 */
export default function NotFound() {
  const { t } = useTranslation();
  const pathname = usePathname();
  const lng = getLanguageFromPath(pathname ?? '/');

  return (
    <main className="flex min-h-[60dvh] items-center justify-center p-4">
      <Card className="w-full max-w-md p-8 text-center">
        <FileQuestion
          className="mx-auto mb-4 h-12 w-12 text-muted-foreground"
          aria-hidden="true"
        />
        <h1 className="text-2xl font-bold tracking-tight text-foreground">
          {t('errors.not_found')}
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">{t('errors.not_found_description')}</p>
        <Button asChild className="mt-6">
          <Link href={buildLocalizedPath('/', lng)}>{t('errors.go_home')}</Link>
        </Button>
      </Card>
    </main>
  );
}
