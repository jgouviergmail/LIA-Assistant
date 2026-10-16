'use client';

import { CalendarDays, Clock3, MapPin, MessageCircle, Sparkles, Sun } from 'lucide-react';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { ReactNode } from 'react';
import type { ResponseDisplayMode } from '@/types/settings';

type PreviewCopy = {
  introduction: string;
  weather: { title: string; location: string; condition: string };
  meeting: { title: string; name: string; time: string; location: string };
};

const EXAMPLE_TEMPERATURE = '20 °C';

function WeatherPreviewCard({ copy }: { copy: PreviewCopy['weather'] }) {
  return (
    <article className="min-w-0 rounded-xl border border-primary/15 bg-primary/5 p-4">
      <h4 className="flex items-center gap-2 text-sm font-medium">
        <Sun className="size-4 shrink-0 text-primary" aria-hidden="true" />
        {copy.title}
      </h4>
      <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1">
        <p className="text-3xl font-semibold tracking-tight tabular-nums">{EXAMPLE_TEMPERATURE}</p>
        <p className="text-sm text-muted-foreground">{copy.condition}</p>
      </div>
      <p className="mt-2 flex items-start gap-1.5 text-xs text-muted-foreground">
        <MapPin className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
        <span className="min-w-0 break-words">{copy.location}</span>
      </p>
    </article>
  );
}

function MeetingPreviewCard({ copy }: { copy: PreviewCopy['meeting'] }) {
  return (
    <article className="min-w-0 rounded-xl border border-primary/15 bg-background p-4">
      <h4 className="flex items-center gap-2 text-sm font-medium">
        <CalendarDays className="size-4 shrink-0 text-primary" aria-hidden="true" />
        {copy.title}
      </h4>
      <p className="mt-3 break-words text-sm font-semibold">{copy.name}</p>
      <div className="mt-2 space-y-1.5 text-xs text-muted-foreground">
        <p className="flex items-start gap-1.5">
          <Clock3 className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
          <span className="min-w-0 break-words tabular-nums">{copy.time}</span>
        </p>
        <p className="flex items-start gap-1.5">
          <MapPin className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
          <span className="min-w-0 break-words">{copy.location}</span>
        </p>
      </div>
    </article>
  );
}

function CardsPreview({ copy }: { copy: PreviewCopy }) {
  return (
    <div className="grid min-w-0 gap-3">
      <WeatherPreviewCard copy={copy.weather} />
      <MeetingPreviewCard copy={copy.meeting} />
    </div>
  );
}

function HtmlPreview({ copy }: { copy: PreviewCopy }) {
  return (
    <div className="space-y-5 text-sm leading-relaxed">
      <p>{copy.introduction}</p>
      <section className="space-y-2">
        <h4 className="flex items-center gap-2 font-semibold">
          <Sun className="size-4 shrink-0 text-primary" aria-hidden="true" />
          {copy.weather.title}
        </h4>
        <p>
          <strong className="font-semibold">{EXAMPLE_TEMPERATURE}</strong>
          {' · '}
          {copy.weather.condition}
        </p>
        <p className="text-muted-foreground">{copy.weather.location}</p>
      </section>
      <section className="space-y-2 border-t border-border/60 pt-4">
        <h4 className="flex items-center gap-2 font-semibold">
          <CalendarDays className="size-4 shrink-0 text-primary" aria-hidden="true" />
          {copy.meeting.title}
        </h4>
        <p className="font-medium">{copy.meeting.name}</p>
        <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
          <li>{copy.meeting.time}</li>
          <li>{copy.meeting.location}</li>
        </ul>
      </section>
    </div>
  );
}

function MarkdownPreview({ copy }: { copy: PreviewCopy }) {
  return (
    <div className="space-y-5 text-sm leading-relaxed">
      <section className="space-y-2">
        <h4 className="flex items-center gap-2 font-semibold">
          <Sun className="size-4 shrink-0 text-primary" aria-hidden="true" />
          {copy.weather.title}
        </h4>
        <p>{copy.weather.location}</p>
        <p>
          {EXAMPLE_TEMPERATURE}
          {' · '}
          {copy.weather.condition}
        </p>
      </section>
      <section className="space-y-2">
        <h4 className="flex items-center gap-2 font-semibold">
          <CalendarDays className="size-4 shrink-0 text-primary" aria-hidden="true" />
          {copy.meeting.title}
        </h4>
        <ul className="list-disc space-y-1 pl-5">
          <li>{copy.meeting.name}</li>
          <li>{copy.meeting.time}</li>
          <li>{copy.meeting.location}</li>
        </ul>
      </section>
    </div>
  );
}

export function ResponseDisplayPreview({
  mode,
  lng,
}: {
  mode: ResponseDisplayMode;
  lng: Language;
}) {
  const { t } = useTranslation(lng);
  const prefix = 'settings.preferences.display_mode.preview';
  const copy: PreviewCopy = {
    introduction: t(`${prefix}.introduction`),
    weather: {
      title: t(`${prefix}.weather.title`),
      location: t(`${prefix}.weather.location`),
      condition: t(`${prefix}.weather.condition`),
    },
    meeting: {
      title: t(`${prefix}.meeting.title`),
      name: t(`${prefix}.meeting.name`),
      time: t(`${prefix}.meeting.time`),
      location: t(`${prefix}.meeting.location`),
    },
  };
  const presentations = {
    cards: <CardsPreview copy={copy} />,
    html: <HtmlPreview copy={copy} />,
    html_cards: (
      <div className="space-y-4">
        <p className="text-sm leading-relaxed">{copy.introduction}</p>
        <CardsPreview copy={copy} />
      </div>
    ),
    markdown: <MarkdownPreview copy={copy} />,
  } satisfies Record<ResponseDisplayMode, ReactNode>;

  return (
    <figure className="min-w-0 space-y-4 break-words">
      <figcaption className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2">
        <span className="flex items-center gap-2 text-sm font-medium">
          <Sparkles className="size-4 shrink-0 text-primary" aria-hidden="true" />
          {t(`${prefix}.title`)}
        </span>
        <span className="rounded-full border border-primary/20 bg-primary/5 px-2.5 py-1 text-xs text-primary">
          {t(`${prefix}.example_label`)}
        </span>
      </figcaption>
      <div className="flex items-start gap-2.5 rounded-xl bg-card px-3 py-3 text-sm leading-relaxed">
        <MessageCircle className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden="true" />
        <p className="min-w-0">{t(`${prefix}.question`)}</p>
      </div>
      <div className="min-w-0 rounded-xl border border-border/60 bg-card p-4 sm:p-5">
        <p className="mb-4 flex items-center gap-2 text-xs font-semibold text-primary">
          <span aria-hidden="true" className="size-1.5 rounded-full bg-primary" />
          LIA
        </p>
        {presentations[mode]}
      </div>
    </figure>
  );
}
