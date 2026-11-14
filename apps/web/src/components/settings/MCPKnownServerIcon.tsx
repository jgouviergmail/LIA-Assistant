import { Server } from '@/lib/icons';
import { knownServerIconSrc, type KnownMCPServer } from '@/lib/mcp-known-servers';
import { cn } from '@/lib/utils';

/**
 * A known server's own icon, on a white chip whatever the theme: a vendor's mark
 * is drawn for a light ground (a black octocat vanishes on a dark card), so the
 * chip, not the theme, is what it stands on.
 *
 * Decorative: it always sits beside the server's name, which carries the name.
 * The file is this application's (`public/mcp-icons/`); no icon is fetched from
 * a vendor. A catalogue that names none shows the servers' generic glyph.
 */
export function MCPKnownServerIcon({
  server,
  className,
}: {
  server: KnownMCPServer;
  className?: string;
}) {
  const src = knownServerIconSrc(server);
  return (
    <span
      aria-hidden="true"
      className={cn(
        'flex size-10 shrink-0 items-center justify-center rounded-lg border bg-white',
        className
      )}
    >
      {src ? (
        // eslint-disable-next-line @next/next/no-img-element -- a static 128px vendor icon of public/, no optimizer
        <img
          src={src}
          alt=""
          width={28}
          height={28}
          loading="lazy"
          decoding="async"
          className="size-7 object-contain"
        />
      ) : (
        <Server className="size-5 text-primary" />
      )}
    </span>
  );
}
