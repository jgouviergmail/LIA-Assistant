'use client';

import { LayoutGrid, Rows3 } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type { BrickMapKind, FamilyView } from '@/lib/maps/types';

/**
 * The families (functional) or layers (technical) of a map, each a toggle that
 * isolates it on the diagram — `aria-pressed` states which one is isolated.
 */
export function FamilyLegend({
  kind,
  families,
  selected,
  onToggle,
}: {
  kind: BrickMapKind;
  families: readonly FamilyView[];
  selected: string | null;
  onToggle: (id: string) => void;
}) {
  const { t } = useTranslation();
  const Icon = kind === 'functional' ? LayoutGrid : Rows3;
  return (
    <div className="lm-card">
      <h3>
        <Icon aria-hidden="true" width={18} height={18} className="lm-ic" />
        {t(`maps.${kind}.legend_title`)}
      </h3>
      <p className="lm-sub">{t(`maps.${kind}.legend_text`)}</p>
      <ul className="lm-legend">
        {families.map(family => (
          <li key={family.id}>
            <button
              type="button"
              data-tone={family.tone}
              aria-pressed={selected === family.id}
              onClick={() => onToggle(family.id)}
            >
              <span className="lm-sw" aria-hidden="true" />
              {family.name}
              <span className="lm-n">{family.count}</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
