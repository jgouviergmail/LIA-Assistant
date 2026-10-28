'use client';

import { useState } from 'react';
import { Footprints } from 'lucide-react';
import { WorldWidgetButton } from './WorldWidgetButton';
import { Button } from '@/components/ui/button';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { WorldExperienceControl } from './useWorldExperiencePreferences';

export interface WorldExploration {
  control: WorldExperienceControl;
  enabled: boolean;
}
export function WorldExplorationControls({
  lng,
  exploration,
}: {
  lng: Language;
  exploration: WorldExploration;
}) {
  const { t } = useTranslation(lng);
  const { control, enabled } = exploration;
  const [failed, setFailed] = useState(false);
  const view = control.experience;
  const showRoute = view?.preferences.show_route ?? true;
  const blocked = !enabled || !view || view.needs_reset || control.saving;
  async function editRoute() {
    if (blocked || !view) return;
    try {
      setFailed(
        !(await control.save({
          expected_revision: view.preferences.revision,
          show_route: !view.preferences.show_route,
        }))
      );
    } catch {
      setFailed(true);
    }
  }
  async function retry() {
    // A re-read that lands vouches for what is shown again; a failed one keeps the notice.
    if (await control.reload()) setFailed(false);
  }
  return (
    <div className="contents">
      <WorldWidgetButton
        icon={Footprints}
        label={t('world.experience.route')}
        aria-pressed={showRoute}
        aria-disabled={blocked}
        onClick={() => void editRoute()}
      />
      {(failed || control.failed) && (
        <p role="status" className="w-full text-sm">
          {t('world.experience.failed')}
          <Button size="sm" variant="outline" className="min-h-11" onClick={() => void retry()}>
            {t('world.retry')}
          </Button>
        </p>
      )}
      {view?.needs_reset && (
        <Button
          variant="outline"
          size="sm"
          className="min-h-11"
          aria-disabled={!enabled || control.saving}
          onClick={async () => {
            if (!enabled || control.saving) return;
            try {
              setFailed(
                !(await control.save({ expected_revision: view.preferences.revision, reset: true }))
              );
            } catch {
              setFailed(true);
            }
          }}
        >
          {t('world.experience.repair')}
        </Button>
      )}
    </div>
  );
}
