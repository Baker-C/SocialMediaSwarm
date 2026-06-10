type StatTileProps = {
  kicker?: string;
  title: string;
  value: React.ReactNode;
  caption?: React.ReactNode;
};

export function StatTile({ kicker, title, value, caption }: StatTileProps) {
  return (
    <article className="bento-tile bento-tile--stat">
      {kicker ? <span className="bento-tile-kicker">{kicker}</span> : null}
      <h2 className="bento-tile-title">{title}</h2>
      <p className="bento-tile-value" aria-live="polite">
        {value}
      </p>
      {caption ? <p className="bento-tile-caption">{caption}</p> : null}
    </article>
  );
}
