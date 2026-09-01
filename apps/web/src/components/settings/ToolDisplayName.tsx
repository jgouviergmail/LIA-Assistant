/**
 * How an MCP tool is named on screen.
 *
 * The MCP spec fixes the precedence — `title`, then `annotations.title`, then
 * `name` — and the backend resolves the first two, so a caller only ever has a
 * title or nothing. A raw MCP name is a machine identifier: a column of
 * `accounts__list_financial_accounts` tells a reader nothing about what a
 * server can do. So the title leads when there is one.
 *
 * The identifier never disappears. It is the string that turns up in logs, in
 * automation rules and in the call the model actually makes, so the title adds
 * a name rather than hiding one.
 *
 * Both MCP screens — the user's servers and the admin's — show the same thing,
 * and their two copies of the list markup had already drifted apart. The rule
 * lives here; each screen keeps its own chrome, which is why this renders a
 * fragment rather than a wrapper element.
 */
export function ToolDisplayName({ title, name }: { title?: string | null; name: string }) {
  const displayTitle = title?.trim() ? title.trim() : null;
  return (
    <>
      <span className="font-medium">{displayTitle ?? name}</span>
      {displayTitle && (
        <span className="ml-2 font-mono text-[11px] font-normal text-muted-foreground">{name}</span>
      )}
    </>
  );
}
