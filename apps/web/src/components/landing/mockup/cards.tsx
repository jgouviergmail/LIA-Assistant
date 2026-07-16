'use client';

import { CloudRain, CloudSun, Droplets, Mail, RotateCcw } from 'lucide-react';
import { cn } from '@/lib/utils';

/**
 * Rich domain cards for the landing mockup, faithful to the real app's card
 * mode: side accent border, header row, date/time badges, letter avatars.
 * Decorative only — "buttons" are non-interactive spans.
 */

/** Email draft preview embedded in the HITL approval bubble. */
export function DraftCard({ to, subject, quote }: { to: string; subject: string; quote: string }) {
  return (
    <span className="mt-2 block rounded-lg border border-amber-500/25 bg-background/70 px-2.5 py-1.5 text-foreground">
      <span className="block text-[10px] text-muted-foreground">
        {to} · <Mail className="inline w-3 h-3 align-[-1.5px] text-amber-600 dark:text-amber-400" />{' '}
        {subject}
      </span>
      <span className="block mt-0.5 text-[11px] italic text-muted-foreground">{quote}</span>
    </span>
  );
}

export interface WeatherSlot {
  icon: 'rain' | 'partly';
  label: string;
  temp: string;
}

/** Weather card with hourly slots — the real "HTML cards" display mode. */
export function WeatherCard({ title, slots }: { title: string; slots: WeatherSlot[] }) {
  return (
    <span className="block rounded-xl border border-border border-l-[3px] border-l-sky-600 bg-card overflow-hidden">
      <span className="flex items-center gap-1.5 px-2.5 py-1.5 text-[11px] font-semibold text-foreground">
        <CloudSun className="w-3.5 h-3.5 text-sky-600 dark:text-sky-400" />
        {title}
      </span>
      <span className="grid grid-cols-3 gap-px bg-border/60 border-t border-border/60">
        {slots.map(({ icon, label, temp }) => {
          const Icon = icon === 'rain' ? CloudRain : CloudSun;
          return (
            <span key={label} className="block bg-card px-2 py-1.5 text-center">
              <Icon className="w-3.5 h-3.5 mx-auto text-muted-foreground" />
              <span className="block text-[9px] text-muted-foreground mt-0.5">{label}</span>
              <span className="block text-[11px] font-semibold tabular-nums text-foreground">
                {temp}
              </span>
            </span>
          );
        })}
      </span>
    </span>
  );
}

/** Event / call-summary card: green side accent + metadata badges. */
export function AccentCard({
  icon,
  title,
  badges,
}: {
  icon: React.ReactNode;
  title: string;
  badges: string[];
}) {
  return (
    <span className="mt-2 block rounded-lg border border-border border-l-[3px] border-l-green-600 bg-card px-2.5 py-1.5 text-foreground">
      <span className="flex items-center gap-1.5 text-[11px] font-semibold">
        {icon}
        {title}
      </span>
      <span className="mt-1 flex flex-wrap gap-1">
        {badges.map(badge => (
          <span
            key={badge}
            className="rounded border border-border bg-muted px-1.5 py-px text-[9px] text-muted-foreground tabular-nums"
          >
            {badge}
          </span>
        ))}
      </span>
    </span>
  );
}

export interface HydrationWidgetProps {
  title: string;
  /** Glasses drunk so far (out of `total`). */
  filled: number;
  total: number;
  addLabel: string;
  resetLabel: string;
  note: string;
  /** One-shot press feedback on the add button (mirrors the fill step). */
  pressed: boolean;
}

/** Interactive skill mini-app, faithful to the real in-chat skill widgets. */
export function HydrationWidget({
  title,
  filled,
  total,
  addLabel,
  resetLabel,
  note,
  pressed,
}: HydrationWidgetProps) {
  return (
    <span className="mt-1.5 block rounded-xl border border-border bg-background px-3 py-2 text-center">
      <span className="block text-[11px] font-semibold text-foreground">{title}</span>
      <span className="mt-1 flex justify-center gap-0.5" aria-hidden="true">
        {Array.from({ length: total }, (_, i) => (
          <Droplets
            key={i}
            className={cn(
              'w-4 h-4',
              i < filled ? 'text-sky-500' : 'text-muted-foreground/30',
              // The glass that just got logged pops in.
              pressed && i === filled - 1 && 'animate-drop-fill'
            )}
          />
        ))}
      </span>
      <span className="mx-6 mt-1.5 block h-1 rounded-full bg-muted overflow-hidden">
        <span
          className="block h-full rounded-full bg-primary transition-[width] duration-500"
          style={{ width: `${Math.round((filled / total) * 100)}%` }}
        />
      </span>
      <span className="mt-1.5 flex justify-center gap-1.5">
        <span
          className={cn(
            'inline-flex items-center gap-1 rounded-md bg-primary px-2 py-0.5 text-[10px] font-medium text-primary-foreground transition-transform duration-200',
            pressed && 'scale-95 ring-2 ring-primary/40'
          )}
        >
          <Droplets className="w-2.5 h-2.5" />
          {addLabel}
        </span>
        <span className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-0.5 text-[10px] text-muted-foreground">
          <RotateCcw className="w-2.5 h-2.5" />
          {resetLabel}
        </span>
      </span>
      <span className="mt-1 block text-[9px] text-muted-foreground">{note}</span>
    </span>
  );
}
