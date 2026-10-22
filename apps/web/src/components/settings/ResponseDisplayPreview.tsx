'use client';

import {
  CalendarDays,
  Clock3,
  LayoutGrid,
  Lightbulb,
  MapPin,
  MessageCircle,
  Sparkles,
  Sun,
} from 'lucide-react';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { ReactNode } from 'react';
import type { ResponseDisplayMode } from '@/types/settings';

type PreviewCopy = {
  introduction: string;
  classicTitle: string;
  classicAnswer: string;
  richLabel: string;
  richTitle: string;
  richSummary: string;
  highlightTitle: string;
  highlightText: string;
  cardsTitle: string;
  cardsHint: string;
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
    <section className="min-w-0 space-y-3" aria-label={copy.cardsTitle}>
      <div className="space-y-1">
        <h4 className="flex min-w-0 items-start gap-2 text-xs font-semibold text-foreground">
          <LayoutGrid className="mt-0.5 size-3.5 shrink-0 text-primary" aria-hidden="true" />
          <span className="min-w-0">{copy.cardsTitle}</span>
        </h4>
        <p className="text-xs leading-relaxed text-muted-foreground">{copy.cardsHint}</p>
      </div>
      <div className="grid min-w-0 gap-3">
        <WeatherPreviewCard copy={copy.weather} />
        <MeetingPreviewCard copy={copy.meeting} />
      </div>
    </section>
  );
}

function RichSummaryPreview({ copy }: { copy: PreviewCopy }) {
  return (
    <section aria-label={copy.richTitle} className="space-y-3 text-sm leading-relaxed">
      <p className="text-xs font-semibold text-muted-foreground">{copy.richLabel}</p>
      <h4 className="flex min-w-0 items-start gap-2 text-lg font-semibold tracking-tight text-foreground">
        <Sparkles className="mt-1 size-5 shrink-0 text-primary" aria-hidden="true" />
        <span className="min-w-0">{copy.richTitle}</span>
      </h4>
      <p>{copy.richSummary}</p>
      <div className="rounded-xl border border-primary/20 bg-primary/5 p-3">
        <h5 className="flex min-w-0 items-start gap-2 font-semibold text-foreground">
          <Lightbulb className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden="true" />
          <span className="min-w-0">{copy.highlightTitle}</span>
        </h5>
        <p className="mt-1">{copy.highlightText}</p>
      </div>
    </section>
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
      <section className="space-y-2 border-t border-border pt-4">
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
    classicTitle: t(`${prefix}.classic_title`),
    classicAnswer: t(`${prefix}.classic_answer`, {
      temperature: EXAMPLE_TEMPERATURE,
      location: t(`${prefix}.weather.location`),
      condition: t(`${prefix}.weather.condition`),
      meeting: t(`${prefix}.meeting.name`),
      time: t(`${prefix}.meeting.time`),
      meetingLocation: t(`${prefix}.meeting.location`),
    }),
    richLabel: t(`${prefix}.rich_label`),
    richTitle: t(`${prefix}.rich_title`),
    richSummary: t(`${prefix}.rich_summary`),
    highlightTitle: t(`${prefix}.highlight_title`),
    highlightText: t(`${prefix}.highlight_text`),
    cardsTitle: t(`${prefix}.cards_title`),
    cardsHint: t(`${prefix}.cards_hint`),
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
    cards: (
      <div className="space-y-5">
        <div className="space-y-2 text-sm leading-relaxed">
          <p className="text-xs font-semibold text-muted-foreground">{copy.classicTitle}</p>
          <p>{copy.classicAnswer}</p>
        </div>
        <CardsPreview copy={copy} />
      </div>
    ),
    html: <HtmlPreview copy={copy} />,
    html_cards: (
      <div className="space-y-4">
        <RichSummaryPreview copy={copy} />
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
      <div className="min-w-0 rounded-xl border border-border bg-card p-4 sm:p-5">
        <p className="mb-4 flex items-center gap-2 text-xs font-semibold text-primary">
          <span aria-hidden="true" className="size-1.5 rounded-full bg-primary" />
          LIA
        </p>
        {presentations[mode]}
      </div>
    </figure>
  );
}
