// @vitest-environment node
/**
 * The readings `capability-callers.guard.test.ts` stands on, each proven on a
 * source that must FAIL it: a guard that runs for no case guards nothing.
 */
import { describe, expect, it } from 'vitest';

import {
  HOLE,
  apiSegments,
  appRouterTree,
  callersOf,
  closingCapabilities,
  doorReaders,
  linkTables,
  openChain,
  parseModule,
  resolveImport,
  resolvePath,
  type Graph,
  type ParsedModule,
  type RouteTable,
} from './capability-callers.scan';

const TABLE: RouteTable = {
  operations: {
    '/files/upload': { POST: ['files'] },
    '/files/{file_id}': { GET: [], DELETE: [] },
    '/files/{file_id}/share': { POST: ['files', 'sharing'] },
    '/kept': { GET: [], POST: ['keeping'] },
    '/board/tickets': { GET: ['board'] },
    '/board/tickets/{ticket_id}': { GET: ['board'], PATCH: ['board'] },
    '/voice/ws/audio': { WS: ['dictation'] },
    '/voice/voices': { GET: [] },
  },
  router_flags: {},
};
const HEADS = new Set(['files', 'kept', 'board', 'voice']);

function modulesOf(sources: Record<string, string>): Map<string, ParsedModule> {
  const known = new Set(Object.keys(sources));
  const modules = new Map(
    Object.entries(sources).map(([relative, text]) => [
      relative,
      parseModule(relative, text, known, HEADS),
    ])
  );
  linkTables(modules, HEADS);
  return modules;
}

/** `capability module` of every caller a set of sources holds. */
function callers(sources: Record<string, string>): string[] {
  return callersOf(TABLE, modulesOf(sources).values()).map(c => `${c.capability} ${c.module}`);
}

describe('apiSegments', () => {
  it('reads a path, with or without the API prefix, and drops its query', () => {
    expect(apiSegments('/board/tickets', HEADS)).toEqual(['board', 'tickets']);
    expect(apiSegments('/api/v1/board/tickets?limit=3', HEADS)).toEqual(['board', 'tickets']);
  });

  it('reads a suffix hole as a query, and a placeholder as a hole', () => {
    expect(apiSegments(`/board/tickets${HOLE}`, HEADS)).toEqual(['board', 'tickets']);
    expect(apiSegments('/files/:fileId/share', HEADS)).toEqual(['files', HOLE, 'share']);
  });

  it('reads nothing in what is no path of the API', () => {
    // A route of the web, a relative path, a sentence, an asset under an API head.
    for (const text of ['/dashboard/settings', 'board/tickets', '/board is closed', 'https://x.y'])
      expect(apiSegments(text, HEADS), text).toBeNull();
  });
});

describe('resolvePath', () => {
  it('prefers the literal template over the parameter of the same shape', () => {
    expect(resolvePath(TABLE, ['files', 'upload'])).toEqual({
      how: 'exact',
      templates: ['/files/upload'],
    });
  });

  it('gives a hole to the parameter, never to a literal beside it', () => {
    // A read by id must not become an upload.
    expect(resolvePath(TABLE, ['files', HOLE])).toEqual({
      how: 'exact',
      templates: ['/files/{file_id}'],
    });
  });

  it('falls back on the literals a hole could reach where no parameter stands', () => {
    expect(resolvePath(TABLE, ['voice', HOLE])).toEqual({
      how: 'loose',
      templates: ['/voice/voices'],
    });
  });

  it('reads a shorter path as the base of the longer ones', () => {
    expect(resolvePath(TABLE, ['board'])).toEqual({
      how: 'base',
      templates: ['/board/tickets', '/board/tickets/{ticket_id}'],
    });
  });

  it('knows nothing of a path the table does not hold', () => {
    expect(resolvePath(TABLE, ['board', 'tickets', 'x', 'y'])).toBeNull();
    expect(resolvePath(TABLE, ['users'])).toBeNull();
  });
});

describe('closingCapabilities', () => {
  const at = (segments: string[], method: string | null) => {
    const resolution = resolvePath(TABLE, segments);
    return resolution === null ? null : closingCapabilities(TABLE, resolution, method);
  };

  it('answers for the method the source names', () => {
    expect(at(['kept'], 'GET')).toEqual([]);
    expect(at(['kept'], 'POST')).toEqual(['keeping']);
  });

  it('answers for every method where the source names none', () => {
    expect(at(['kept'], null)).toEqual(['keeping']);
  });

  it('carries every switch of an operation two of them close', () => {
    expect(at(['files', HOLE, 'share'], 'POST')).toEqual(['files', 'sharing']);
  });

  it('gives a base the switches that close EVERYTHING built on it', () => {
    expect(at(['board'], null)).toEqual(['board']);
    // One open operation under the base: the base alone names no closed call.
    expect(at(['files'], null)).toEqual([]);
  });
});

describe('the paths a module spells', () => {
  it('finds a literal, a template, and the method of a client call', () => {
    expect(
      callers({
        'a.ts': "useQuery('/board/tickets');",
        'b.ts': 'const read = (id: string) => client.get(`/board/tickets/${id}`);',
        'c.ts': "client.post('/kept', body);",
        'd.ts': "client.get('/kept');",
      })
    ).toEqual(['board a.ts', 'board b.ts', 'keeping c.ts']);
  });

  it('follows a constant other paths are built on', () => {
    expect(
      callers({ 'a.ts': "const BASE = '/files';\nexport const up = () => post(`${BASE}/upload`);" })
    ).toEqual(['files a.ts']);
  });

  it('reads past an origin, and past the API prefix', () => {
    expect(
      callers({ 'a.ts': 'new WebSocket(`${wsBase}/api/v1/voice/ws/audio?ticket=${ticket}`);' })
    ).toEqual(['dictation a.ts']);
  });

  it('gives a table of paths to the module that reads it, never to the table', () => {
    const sources = {
      'paths.ts':
        'export const PATHS = { FILES: { UPLOAD: `${ORIGIN}/files/upload`, ONE: `${ORIGIN}/files/:id` } } as const;',
      'upload.ts': "import { PATHS } from './paths';\nxhr.open('POST', PATHS.FILES.UPLOAD);",
      'read.ts': "import { PATHS } from './paths';\nopen(PATHS.FILES.ONE.replace(':id', id));",
    };

    expect(callers(sources)).toEqual(['files upload.ts']);
  });

  it('reads no path in an import, a comment or prose', () => {
    expect(
      callers({
        'a.ts':
          "import x from '/board/tickets';\n// client.get('/board/tickets')\nconst t = 'see /board/tickets for more';",
      })
    ).toEqual([]);
  });
});

describe('the imports a module runs', () => {
  const known = new Set(['lib/a.ts', 'lib/b/index.ts', 'lib/types.ts', 'components/C.tsx']);

  it('resolves an alias, a relative path and a folder', () => {
    expect(resolveImport('components/C.tsx', '@/lib/a', known)).toBe('lib/a.ts');
    expect(resolveImport('lib/a.ts', './b', known)).toBe('lib/b/index.ts');
    expect(resolveImport('lib/a.ts', '../components/C', known)).toBe('components/C.tsx');
    expect(resolveImport('lib/a.ts', 'react', known)).toBeNull();
  });

  it('keeps a value import, a re-export and a lazy import, and no import of types', () => {
    const parsed = parseModule(
      'components/C.tsx',
      [
        "import { run } from '@/lib/a';",
        "import type { Shape } from '@/lib/types';",
        "import { type Other } from '@/lib/types';",
        "export * from '../lib/a';",
        "const Lazy = dynamic(() => import('../lib/b'));",
      ].join('\n'),
      known,
      HEADS
    );

    // `lib/types` is imported twice, for its types alone: no edge at runtime.
    expect([...parsed.imports.keys()].sort()).toEqual(['lib/a.ts', 'lib/b/index.ts']);
    expect([...(parsed.imports.get('lib/b/index.ts') ?? [])]).toEqual(['*']);
  });
});

describe('who reads a door', () => {
  const sources = {
    'door.ts':
      "export function boardAvailable(c: unknown) { return capabilityEnabled(c, 'board', true); }\n" +
      "export function Board() { return capabilityAvailable(config, 'board') ? 1 : 0; }",
    'direct.tsx': "const on = capabilityAvailable(config, 'board');",
    'through.tsx': "import { boardAvailable } from './door';\nconst on = boardAvailable(config);",
    'unused.tsx': "import { boardAvailable } from './door';",
    'component.tsx': "import { Board } from './door';\nconst x = <Board />;",
    'record.tsx': "const kept = capabilityMounted(config, 'board');",
    'dynamic.tsx': 'const on = capabilityAvailable(config, key);',
  };
  const readers = doorReaders(modulesOf(sources));
  const reads = (module: string) => [...(readers.get(module) ?? [])];

  it('counts a door called with a literal key, and a door function one hop away', () => {
    expect(reads('direct.tsx')).toEqual(['board']);
    expect(reads('through.tsx')).toEqual(['board']);
  });

  it('counts no door for an import nobody calls, nor through a component', () => {
    expect(reads('unused.tsx')).toEqual([]);
    // A component that consults a verdict fences what IT renders, not its importers.
    expect(reads('component.tsx')).toEqual([]);
  });

  it('counts no door for the flag of a record, nor for a key it cannot read', () => {
    expect(reads('record.tsx')).toEqual([]);
    expect(reads('dynamic.tsx')).toEqual([]);
  });

  it('leaves out the modules whose verdicts fence nothing by themselves', () => {
    const without = doorReaders(modulesOf(sources), new Set(['door.ts']));

    expect([...(without.get('through.tsx') ?? [])]).toEqual([]);
    expect([...(without.get('direct.tsx') ?? [])]).toEqual(['board']);
  });
});

describe('the application tree', () => {
  const known = new Set([
    'app/[lng]/layout.tsx',
    'app/[lng]/page.tsx',
    'app/[lng]/dashboard/layout.tsx',
    'app/[lng]/dashboard/page.tsx',
    'app/[lng]/dashboard/tools/mail/page.tsx',
    'app/[lng]/dashboard/tools/error.tsx',
    'app/[lng]/dashboard/export/route.ts',
    'app/api/upload/route.ts',
    'app/global-error.tsx',
    'components/C.tsx',
  ]);

  it('starts from what nothing renders, and hangs each page under its nearest layout', () => {
    const tree = appRouterTree(known);

    // A route handler answers by itself, wherever its folder sits: no layout renders it.
    expect(tree.roots).toEqual([
      'app/[lng]/dashboard/export/route.ts',
      'app/[lng]/layout.tsx',
      'app/api/upload/route.ts',
      'app/global-error.tsx',
    ]);
    expect(tree.children.get('app/[lng]/layout.tsx')).toEqual([
      'app/[lng]/page.tsx',
      'app/[lng]/dashboard/layout.tsx',
    ]);
    expect(tree.children.get('app/[lng]/dashboard/layout.tsx')).toEqual([
      'app/[lng]/dashboard/page.tsx',
      'app/[lng]/dashboard/tools/mail/page.tsx',
      'app/[lng]/dashboard/tools/error.tsx',
    ]);
  });

  it('names the element a layout renders its pages in', () => {
    const parsed = parseModule(
      'app/[lng]/dashboard/layout.tsx',
      "import { Shell } from '@/components/C';\nexport default function L({ children }) { return <Shell><main>{children}</main></Shell>; }",
      known,
      HEADS
    );

    expect([...parsed.childrenWrappers]).toEqual(['Shell']);
  });
});

describe('openChain', () => {
  const graph = (overrides: Partial<Graph> = {}): Graph => ({
    roots: ['root'],
    edges: new Map([
      ['root', ['gate', 'side']],
      ['gate', ['reader']],
      ['side', ['other']],
    ]),
    readers: new Map(),
    closedEdges: new Map(),
    ...overrides,
  });

  it('finds the way to a module no door stands before', () => {
    expect(openChain(graph(), 'reader', 'board')).toEqual(['root', 'gate', 'reader']);
  });

  it('stops at a module that reads the door, for that capability alone', () => {
    const closed = graph({ readers: new Map([['gate', new Set(['board'])]]) });

    expect(openChain(closed, 'reader', 'board')).toBeNull();
    expect(openChain(closed, 'reader', 'files')).toEqual(['root', 'gate', 'reader']);
  });

  it('finds the other way round a door', () => {
    const bypassed = graph({
      edges: new Map([
        ['root', ['gate', 'side']],
        ['gate', ['reader']],
        ['side', ['reader']],
      ]),
      readers: new Map([['gate', new Set(['board'])]]),
    });

    expect(openChain(bypassed, 'reader', 'board')).toEqual(['root', 'side', 'reader']);
  });

  it('does not cross an edge its capability closes', () => {
    const section = graph({ closedEdges: new Map([['gate\nreader', new Set(['board'])]]) });

    expect(openChain(section, 'reader', 'board')).toBeNull();
    expect(openChain(section, 'reader', 'files')).toEqual(['root', 'gate', 'reader']);
  });

  it('reaches nothing the application never mounts', () => {
    expect(openChain(graph(), 'orphan', 'board')).toBeNull();
  });
});
