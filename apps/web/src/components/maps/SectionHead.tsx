/** The opening of a section of a map page: kicker, heading, one line of guidance. */
export function SectionHead({
  id,
  kicker,
  title,
  text,
}: {
  id: string;
  kicker: string;
  title: string;
  text: string;
}) {
  return (
    <div className="lm-section-head">
      <p className="lm-kicker">{kicker}</p>
      <h2 id={id}>{title}</h2>
      <p className="lm-section-text">{text}</p>
    </div>
  );
}
