'use client';

import { ArrowRight, Search } from 'lucide-react';
import { useTranslation } from 'react-i18next';

/**
 * The toolbar above a brick map: a search box (Enter opens the first match) and
 * the legend of the two kinds of links the map traces.
 */
export function BrickSearch({
  value,
  placeholder,
  onChange,
  onSubmit,
}: {
  value: string;
  placeholder: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="lm-toolbar">
      <div className="lm-search">
        <Search aria-hidden="true" width={16} height={16} className="lm-ic" />
        <input
          type="search"
          aria-label={t('maps.common.search_label')}
          value={value}
          placeholder={placeholder}
          autoComplete="off"
          onChange={event => onChange(event.target.value)}
          onKeyDown={event => {
            if (event.key !== 'Enter') return;
            // The detail it opens takes the focus at once: the rest of this key
            // press (its keypress) must not land on the detail's close button.
            event.preventDefault();
            onSubmit();
          }}
        />
      </div>
      <span className="lm-hint">
        <ArrowRight aria-hidden="true" width={14} height={14} className="lm-ic" />
        <span className="is-out">{t('maps.common.depends_on')}</span>
        <span aria-hidden="true">·</span>
        <span className="is-in">{t('maps.common.used_by')}</span>
      </span>
    </div>
  );
}
