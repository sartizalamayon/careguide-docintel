/** Renders a ts_headline snippet: <b>match</b> becomes a highlight; everything else is plain text. */
export function Snippet({ text }: { text: string }) {
  const parts = text.split(/(<b>[\s\S]*?<\/b>)/);
  return (
    <p className="line-clamp-3 text-sm text-muted-foreground">
      {parts.map((part, i) => {
        const match = /^<b>([\s\S]*)<\/b>$/.exec(part);
        return match ? <mark key={i} className="rounded bg-brand-orange/20 px-0.5 text-foreground">{match[1]}</mark> : part.replace(/<\/?b>/g, "");
      })}
    </p>
  );
}
