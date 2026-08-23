'use client';

import { Eclipse, Moon, Sun } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { useThemeMode } from '@/hooks/useThemeMode';
import { nextInCycle } from '@/lib/theme-mode';

/**
 * The circular display-mode control: light → dark → OLED → light.
 *
 * Icon and accessible name describe the DESTINATION, not the current state —
 * the convention this control already used (dark mode showed a sun). With three
 * stops the name has to say where the press goes, because that is a different
 * place each time.
 *
 * `system` is deliberately NOT in the cycle: three stops a user can predict
 * beat four they cannot, and a circular control that sometimes lands on "follow
 * the OS" reads as broken when the OS is already on the mode you just left.
 * Settings › Theme keeps the full four-way choice, `system` included, so the
 * column's default stays reachable.
 */
const STEPS = {
  dark: { Icon: Moon, key: 'theme.to_dark' },
  oled: { Icon: Eclipse, key: 'theme.to_oled' },
  light: { Icon: Sun, key: 'theme.to_light' },
} as const;

export function ThemeToggle() {
  const { t } = useTranslation();
  const { mounted, resolved, oled, apply } = useThemeMode();

  // Computed once and shared by the icon, the accessible name and the handler,
  // so the label can never describe a different step from the one the click
  // performs.
  const next = nextInCycle(resolved, oled);

  // Before mount neither the resolved theme nor the stored flag is known, so
  // render the shell without a state-dependent icon rather than guess and flip.
  if (!mounted) {
    return (
      <Button variant="ghost" size="sm" className="w-11 h-11 px-0 max-[380px]:w-9 max-[380px]:h-9">
        <Sun className="h-[1.2rem] w-[1.2rem]" />
        <span className="sr-only">{t('theme.to_dark')}</span>
      </Button>
    );
  }

  const { Icon, key } = STEPS[next.oled ? 'oled' : next.mode];
  return (
    <Button
      variant="ghost"
      size="sm"
      className="w-11 h-11 px-0 max-[380px]:w-9 max-[380px]:h-9"
      onClick={event => {
        // The reveal opens from the button's centre, so the wipe visibly
        // starts where the user pressed rather than from an arbitrary point.
        const box = event.currentTarget.getBoundingClientRect();
        apply(next, { x: box.left + box.width / 2, y: box.top + box.height / 2 });
      }}
      aria-label={t(key)}
    >
      <Icon className="h-[1.2rem] w-[1.2rem] transition-all" />
    </Button>
  );
}
