import { GitCommitHorizontal } from 'lucide-react';

/** The product name inside a translated title, drawn in the brand gradient. */
const PRODUCT_NAME = 'LIA';

/**
 * A title with the product name in the brand gradient. The name is never
 * translated, so it is found in the translated sentence rather than spliced
 * into it — every language keeps its own word order.
 */
export function GradientTitle({ text }: { text: string }) {
  const at = text.indexOf(PRODUCT_NAME);
  if (at < 0) return <>{text}</>;
  return (
    <>
      {text.slice(0, at)}
      <span className="lm-grad">{PRODUCT_NAME}</span>
      {text.slice(at + PRODUCT_NAME.length)}
    </>
  );
}

export interface HeroStat {
  value: string;
  label: string;
}

/**
 * The opening of a map page: what the document is, its title, its lede, the
 * counts it rests on and the version it describes. Rendered on the server.
 */
export function MapsHero({
  eyebrow,
  title,
  lede,
  stats,
  stamp,
}: {
  eyebrow: string;
  title: string;
  lede: string;
  stats: HeroStat[];
  /** "Version 1.47.2", the release date, and what keeps the page current. */
  stamp: { version: string; date: string; note: string };
}) {
  return (
    <section className="lm-hero" aria-labelledby="lm-hero-title">
      <p className="lm-eyebrow">
        <span className="lm-pulse" aria-hidden="true" />
        {eyebrow}
      </p>
      <h1 id="lm-hero-title">
        <GradientTitle text={title} />
      </h1>
      <p className="lm-lede">{lede}</p>
      <ul className="lm-stats">
        {stats.map(stat => (
          <li key={stat.label} className="lm-stat">
            <b>{stat.value}</b>
            <span>{stat.label}</span>
          </li>
        ))}
      </ul>
      <p className="lm-stamp">
        <GitCommitHorizontal aria-hidden="true" width={16} height={16} className="lm-ic" />
        {stamp.version}
        <span className="lm-dot" aria-hidden="true" />
        {stamp.date}
        <span className="lm-dot" aria-hidden="true" />
        {stamp.note}
      </p>
    </section>
  );
}
