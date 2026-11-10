'use client';

import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Library, Star } from '@/lib/icons';
import { HeadingRule } from '@/components/ui/heading-rule';
import type { RAGSpace } from '@/types/rag-spaces';

/** Keep each filtered, ordered space in exactly one of the owner's lists. */
export function SpaceCardList({
  spaces,
  gridClassName,
  children,
}: {
  spaces: RAGSpace[];
  gridClassName: string;
  children: (space: RAGSpace) => ReactNode;
}) {
  const { t } = useTranslation();
  const groups = [
    { key: 'favorites_title', icon: Star, items: spaces.filter(space => space.is_favorite) },
    { key: 'others_title', icon: Library, items: spaces.filter(space => !space.is_favorite) },
  ];
  return (
    <div className="space-y-7">
      {groups
        .filter(group => group.items.length > 0)
        .map(({ key, icon: Icon, items }) => (
          <section key={key} aria-label={t(`spaces.${key}`)}>
            <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-foreground">
              <Icon className="h-4 w-4 text-primary" aria-hidden="true" />
              {t(`spaces.${key}`)}
              <span className="rounded-full bg-muted px-2 py-px text-px-11 font-medium tabular-nums text-muted-foreground">
                {items.length}
              </span>
              <HeadingRule />
            </h2>
            <ul className={gridClassName} role="list">
              {items.map(space => (
                <li key={space.id} className="min-w-0">
                  {children(space)}
                </li>
              ))}
            </ul>
          </section>
        ))}
    </div>
  );
}
