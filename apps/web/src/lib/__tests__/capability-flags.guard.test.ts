/**
 * A capability's deployment flag has ONE reader: its availability door.
 *
 * `features.<x>_enabled` is the deployment CEILING: it mounts a capability's
 * routes, and the operator's switch can still close them (ADR-280). A screen
 * that reads the ceiling itself keeps offering what the switch closed — the
 * world's links, the header's meetings, the recorder, the « + » of the
 * composer, the alerts hub and nine settings sections each did. `tsc` sees
 * nothing: the flag exists and it is a boolean. Only a rule about WHO reads
 * it does.
 *
 * Which flags are a capability's is read from the backend registry itself
 * (`feature_switches/registry.py`): the two languages cannot share a table.
 * Read on the raw source, comments included: a comment that names the flag
 * where the door is meant sends the next reader to the wrong place.
 *
 * One more kind of flag has the same single reader: the flag that mounts a
 * capability's ROUTER without being its ceiling. Which ones those are is read
 * from the API's own table of its routes (`capability_route_table.json`, held
 * true by `test_capability_route_table_guard.py`).
 */
import { readdirSync, readFileSync } from 'node:fs';
import { join, relative, resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

import { CAPABILITY_CEILING, CAPABILITY_ROUTER_FLAGS } from '@/lib/capability-availability';
import { DASHBOARD_DESTINATIONS } from '@/lib/dashboard-nav';

const SRC = resolve(__dirname, '../..');

/** The generic door: every capability with no module of its own. */
const GENERIC_DOOR = 'lib/capability-availability.ts';

/** The capabilities that own a door module, by deployment flag. */
const OWN_DOORS: Readonly<Record<string, string>> = {
  world_enabled: 'features/world/availability.ts',
  workbench_enabled: 'lib/workbench/availability.ts',
  tool_assists_enabled: 'lib/workbench/availability.ts',
  sms_enabled: 'lib/sms/availability.ts',
  meetings_enabled: 'lib/meetings/availability.ts',
  workboard_enabled: 'lib/workboard/availability.ts',
  rag_spaces_enabled: 'lib/rag-spaces/availability.ts',
  radio_enabled: 'lib/radio/availability.ts',
  bookmarks_enabled: 'lib/bookmarks/availability.ts',
  email_share_enabled: 'lib/email-share/share.ts',
  peers_enabled: 'lib/peers/image-share.ts',
  skill_library_enabled: 'lib/skill-library/availability.ts',
};

/** The generic door's flags: a capability with no published flag carries none. */
const GENERIC_FLAGS = Object.values(CAPABILITY_CEILING).filter(
  (flag): flag is NonNullable<typeof flag> => flag !== null
);

function registrySource(): string {
  return readFileSync(
    join(process.cwd(), '..', 'api', 'src', 'domains', 'feature_switches', 'registry.py'),
    'utf-8'
  );
}

/** Capability key → the flags that mount its router without being its ceiling, as the API finds them. */
function routerFlags(): Record<string, string[]> {
  const table = JSON.parse(
    readFileSync(
      join(process.cwd(), '..', 'api', 'tests', 'unit', 'capability_route_table.json'),
      'utf-8'
    )
  ) as { router_flags: Record<string, string[]> };
  return table.router_flags;
}

/** The deployment flag of every operator switch, read from the registry. */
function capabilityFlags(): string[] {
  return [...registrySource().matchAll(/env_flag="(\w+)"/g)].map(match => match[1]);
}

/** Capability key (`capabilities.<key>`) → its deployment flag, as the registry declares both. */
function flagByCapability(): Map<string, string> {
  const registry = registrySource();
  const keyOf = new Map(
    [...registry.matchAll(/^ {4}([A-Z][A-Z0-9_]*) = "(\w+)"$/gm)].map(match => [match[1], match[2]])
  );
  const declared = new Map<string, string>();
  const spec = /PlatformCapability\.([A-Z0-9_]+): CapabilitySpec\(([\s\S]*?)\n {4}\),/g;
  for (const match of registry.matchAll(spec)) {
    const key = keyOf.get(match[1]);
    const flag = /env_flag="(\w+)"/.exec(match[2])?.[1];
    if (key !== undefined && flag !== undefined) declared.set(key, flag);
  }
  return declared;
}

function sources(folder: string): string[] {
  return readdirSync(folder, { withFileTypes: true }).flatMap(entry => {
    const path = join(folder, entry.name);
    if (entry.isDirectory()) return entry.name === '__tests__' ? [] : sources(path);
    return /\.tsx?$/.test(entry.name) ? [path] : [];
  });
}

describe('a capability flag has one reader', () => {
  it('reads the registry: an empty list would guard nothing', () => {
    const flags = capabilityFlags();

    expect(flags.length).toBeGreaterThan(20);
    expect(flags).toEqual(expect.arrayContaining(['workboard_enabled', 'live_enabled']));
  });

  it('declares a door for every flag a destination names', () => {
    const named = DASHBOARD_DESTINATIONS.flatMap(d => (d.feature ? [d.feature] : []));

    for (const flag of new Set(named)) expect(OWN_DOORS[flag], flag).toBeDefined();
  });

  it('holds no door for a flag that is no capability', () => {
    const flags = new Set(capabilityFlags());
    const declared = [...Object.keys(OWN_DOORS), ...GENERIC_FLAGS];

    expect(declared.filter(flag => !flags.has(flag))).toEqual([]);
    // One door per flag: a capability is never both generic and its own.
    expect(GENERIC_FLAGS.filter(flag => flag in OWN_DOORS)).toEqual([]);
  });

  it('names for each capability of the generic door the flag the registry gives it', () => {
    const registry = flagByCapability();

    // The walk read the registry: it did not pass on an empty table.
    expect(registry.size).toBeGreaterThan(20);
    expect(registry.get('workboard')).toBe('workboard_enabled');
    for (const [capability, flag] of Object.entries(CAPABILITY_CEILING)) {
      expect(registry.has(capability), `${capability} is no capability of the registry`).toBe(true);
      if (flag !== null) expect(flag, capability).toBe(registry.get(capability));
    }
  });

  it('answers from the map alone only where the configuration publishes no flag', () => {
    // The day `/config` publishes the flag, the capability takes it like the
    // others: an unflagged entry must not outlive its reason.
    const registry = flagByCapability();
    const published = readFileSync(join(SRC, 'hooks/useAppConfig.ts'), 'utf-8');

    const unflagged = Object.entries(CAPABILITY_CEILING).filter(([, flag]) => flag === null);
    expect(unflagged.length).toBeGreaterThan(0);
    for (const [capability] of unflagged) {
      const flag = registry.get(capability) ?? '';
      expect(flag, `${capability} has no flag in the registry`).not.toBe('');
      expect(published.includes(flag), `${flag} is published: declare it`).toBe(false);
    }
  });

  it('closes on every flag that mounts a router its ceiling does not', () => {
    // The capability map says « offered » from the ceiling and the switch: it
    // cannot say a router ANOTHER flag mounts is absent. The door must.
    const named = routerFlags();

    // The walk read the table: it did not pass on an empty one.
    expect(named.mcp).toEqual(['mcp_user_enabled']);
    expect(CAPABILITY_ROUTER_FLAGS).toEqual(named);
    // Never a ceiling as well: one flag, one meaning.
    const ceilings = new Set(capabilityFlags());
    expect(
      Object.values(named)
        .flat()
        .filter(flag => ceilings.has(flag))
    ).toEqual([]);
  });

  it('lets nothing but its door read the flag', () => {
    const flags = new Set([...capabilityFlags(), ...Object.values(routerFlags()).flat()]);
    const read = /features\??\.(\w+)/g;
    const offenders: string[] = [];
    const doorsSeen = new Set<string>();
    for (const path of sources(SRC)) {
      const file = relative(SRC, path).replaceAll('\\', '/');
      for (const match of readFileSync(path, 'utf-8').matchAll(read)) {
        if (!flags.has(match[1])) continue;
        const door = OWN_DOORS[match[1]];
        if (door !== undefined && file === door) doorsSeen.add(door);
        else offenders.push(`${file}: ${match[0]}`);
      }
    }

    expect(offenders).toEqual([]);
    // The walk read the doors that spell their flag: it did not pass by default.
    expect(doorsSeen.size).toBeGreaterThanOrEqual(8);
    expect(readFileSync(join(SRC, GENERIC_DOOR), 'utf-8')).toContain('CAPABILITY_CEILING');
  });
});
