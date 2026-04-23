'use client';

import { ChevronRight, HelpCircle, Settings } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';

/**
 * Premium Quick Access — sits ABOVE the "Mon dashboard" cards grid.
 *
 * Two large cards: Help + Settings. Each card has:
 *  - Gradient background (per-domain accent color)
 *  - Large icon in a colored badge with glow ring
 *  - Bold label + descriptive subline
 *  - Hover: lift + glow shadow + chevron slide
 *
 * Mobile-first: full width on small screens, side-by-side on ≥640 px.
 */
export function QuickAccessCompact() {
  const router = useRouter();
  const { t, i18n } = useTranslation();
  const lng = (i18n.language || 'fr').split('-')[0];

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 sm:gap-5">
      <QuickActionCard
        onClick={() => router.push(`/${lng}/dashboard/faq`)}
        icon={<HelpCircle className="h-6 w-6" />}
        label={t('dashboard.quick_access_compact.help')}
        sublabel={t('dashboard.quick_access_compact.help_sub')}
        tone="primary"
      />
      <QuickActionCard
        onClick={() => router.push(`/${lng}/dashboard/settings`)}
        icon={<Settings className="h-6 w-6" />}
        label={t('dashboard.quick_access_compact.settings')}
        sublabel={t('dashboard.quick_access_compact.settings_sub')}
        tone="warning"
      />
    </div>
  );
}

interface QuickActionCardProps {
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
  sublabel: string;
  tone: 'primary' | 'warning';
}

function QuickActionCard({ onClick, icon, label, sublabel, tone }: QuickActionCardProps) {
  const toneClasses =
    tone === 'primary'
      ? {
          gradient:
            'bg-gradient-to-br from-primary/12 via-primary/5 to-transparent dark:from-primary/20 dark:via-primary/8',
          border: 'border-primary/30',
          iconBg: 'bg-primary/15',
          iconText: 'text-primary',
          iconRing: 'ring-primary/20',
          hoverGlow: 'group-hover:shadow-primary/20',
        }
      : {
          gradient:
            'bg-gradient-to-br from-warning/12 via-warning/5 to-transparent dark:from-warning/20 dark:via-warning/8',
          border: 'border-warning/30',
          iconBg: 'bg-warning/15',
          iconText: 'text-warning',
          iconRing: 'ring-warning/20',
          hoverGlow: 'group-hover:shadow-warning/20',
        };

  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'group relative overflow-hidden rounded-2xl border p-5 sm:p-6 text-left',
        'transition-all duration-300 ease-out',
        'shadow-[var(--lia-shadow-md)]',
        'motion-safe:hover:-translate-y-1 motion-safe:hover:scale-[1.01]',
        'hover:shadow-2xl',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 focus-visible:ring-offset-2',
        toneClasses.gradient,
        toneClasses.border,
        toneClasses.hoverGlow,
      )}
    >
      <div className="flex items-center gap-4">
        <div
          className={cn(
            'flex h-14 w-14 items-center justify-center rounded-2xl ring-4 transition-transform duration-300',
            'motion-safe:group-hover:scale-110 motion-safe:group-hover:rotate-3',
            toneClasses.iconBg,
            toneClasses.iconText,
            toneClasses.iconRing,
          )}
        >
          {icon}
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-base sm:text-lg font-semibold text-foreground">{label}</div>
          <div className="text-xs sm:text-sm text-muted-foreground mt-0.5 truncate">
            {sublabel}
          </div>
        </div>
        <ChevronRight
          className={cn(
            'h-5 w-5 text-muted-foreground/50 transition-transform duration-300',
            'motion-safe:group-hover:translate-x-1 motion-safe:group-hover:text-foreground',
          )}
        />
      </div>

      {/* Subtle decorative gradient orb */}
      <div
        className={cn(
          'pointer-events-none absolute -bottom-12 -right-12 h-32 w-32 rounded-full opacity-30 blur-2xl transition-opacity duration-500',
          'motion-safe:group-hover:opacity-50',
          tone === 'primary' ? 'bg-primary' : 'bg-warning',
        )}
        aria-hidden="true"
      />
    </button>
  );
}
