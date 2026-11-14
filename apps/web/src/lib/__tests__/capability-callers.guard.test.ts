// @vitest-environment node
/**
 * Every module that calls a route a capability switch closes is tied to that
 * capability's door (ADR-280).
 *
 * An operator switches a capability off and its routes refuse at the door. The
 * web must then OFFER nothing of it — and ASK nothing of it: a reader nobody
 * closed sends a request whose only answer is a refusal it shows to no one.
 * The chat's in-call band did, on every turn; it was found by reading the code,
 * one screen after another. This guard finds the next one by itself.
 *
 * WHICH routes a switch closes is the API's to say, and it says it in
 * `capability_route_table.json` — written from the application's own routers
 * and held true by `test_capability_route_table_guard.py`. Every API path a
 * module of `src/` spells is resolved against that table (a constant other
 * paths are built on, a table of paths read elsewhere, a `${hole}` included),
 * which gives the pairs « this module calls a route that capability closes ».
 *
 * A pair is CLOSED when no chain of imports leads from a route of the
 * application to the module without meeting that capability's door:
 *
 * - a module that reads the door (`capabilityAvailable(config, 'x')`, or a
 *   door function such as `workbenchAvailable`) closes what it imports;
 * - a settings section is mounted by the index only when its gate's verdict
 *   holds (`SETTINGS_SEARCH_META`, `settingsCapabilityVerdicts`);
 * - a layout that renders its pages inside a shell reading the door closes
 *   them (`ROUTE_SHELLS`, declared and checked).
 *
 * What it cannot see, it does not pretend to: a module that reads a door
 * closes EVERYTHING it imports, whether or not its code conditions that
 * particular child; and an act only a click sends, from a control a sibling
 * module withdraws, has no door on its own chain. The first is this guard's
 * blind spot; the second lands in `OPEN_CHAINS` until its screen passes the
 * verdict down.
 *
 * `OPEN_CHAINS` is what was open the day the guard was written. It only
 * shrinks: close a chain, delete its line, lower the ceiling.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import ts from 'typescript';
import { describe, expect, it } from 'vitest';

import { readSources } from '@/__tests__/source-scan';
import { SETTINGS_SEARCH_META } from '@/lib/settings-search';

import {
  appRouterTree,
  callersOf,
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

/** The settings verdicts: read by the index section by section, they fence nothing by themselves. */
const SETTINGS_VERDICTS = 'hooks/useSettingsAvailability.ts';
/** Section token → the component the pane mounts for it. */
const SECTION_REGISTRY = 'components/settings/settings-section-registry.tsx';

/**
 * A layout whose pages render inside a shell that reads a door: closed with it.
 *
 * Declared, because « wraps `children` » does not say « conditions them »: the
 * root layout wraps every page in providers that read doors for themselves.
 */
const ROUTE_SHELLS: Readonly<Record<string, { shell: string; closes: readonly string[] }>> = {
  'app/[lng]/dashboard/tools/layout.tsx': {
    shell: 'components/workbench/WorkbenchShell.tsx',
    closes: ['workbench'],
  },
};

/**
 * A path whose methods are not all closed by the same switches, spelled where
 * the source does not say the method: module → template → the method it uses.
 */
const METHOD_OF: Readonly<Record<string, Readonly<Record<string, string>>>> = {
  // The list of kept answers is the record: only KEEPING (POST) is the switch's.
  'components/chat/BookmarkPickerDialog.tsx': { '/bookmarks': 'GET' },
  'hooks/useBookmarks.ts': { '/bookmarks': 'GET' },
};

/**
 * Capability → the modules that call one of its closed routes with no door on
 * the way, as of 2026-11-12. SHRINK-ONLY: never add a line — read the door.
 */
const OPEN_CHAINS: Readonly<Record<string, readonly string[]>> = {
  attachments: ['components/workbench/mail/useDeviceFiles.ts'],
  avatar: ['lib/avatars/api.ts'],
  email_share: ['hooks/useRecipientSuggestions.ts'],
  habits: ['hooks/useHabitProposals.ts'],
  journals: ['hooks/useJournalPortrait.ts'],
  live: ['lib/live/session-controller.ts', 'lib/live/standby.ts'],
  mcp: ['lib/api/mcp-apps.ts'],
  meetings: [
    'components/workbench/assist/useEventAssist.ts',
    'lib/meetings/api.ts',
    'lib/meetings/segment-uploader.ts',
  ],
  open_loops: ['hooks/useCommitmentActions.ts', 'hooks/useOpenLoops.ts'],
  peers: [
    'components/notifications/NotificationsHub.tsx',
    'hooks/useCapabilityRecipients.ts',
    'hooks/useCapabilityTransfer.ts',
    'hooks/usePeerRecipients.ts',
  ],
  radio: ['hooks/useRadioArticle.ts', 'hooks/useTtsVoiceSample.ts', 'lib/radio/api.ts'],
  rag_spaces: [
    'app/[lng]/dashboard/spaces/[id]/page.tsx',
    'app/api/rag-upload/[spaceId]/route.ts',
    'components/chat/KnowledgeDocumentPickerDialog.tsx',
    'hooks/useAttachableDocuments.ts',
    'hooks/useDriveSources.ts',
    'hooks/useMailSources.ts',
    'hooks/useSpaceDocuments.ts',
    'hooks/useSpaces.ts',
  ],
  sms: [
    'components/chat/ApplicationIngestionTokenCard.tsx',
    'components/sms/SmsArchive.tsx',
    'components/sms/SmsFocusedMessage.tsx',
    'components/sms/SmsIdentityRefresh.tsx',
    'hooks/useSmsArchive.ts',
    'hooks/useSmsManagement.ts',
    'hooks/useSmsReceivedToast.ts',
  ],
  stt: ['lib/voice-input-service.ts'],
  tool_assists: [
    'components/selection-assist/SelectionAssistProvider.tsx',
    'components/selection-assist/SelectionSession.tsx',
    'components/workbench/assist/ComposerAssist.tsx',
    'components/workbench/assist/NewContactAssist.tsx',
    'components/workbench/assist/SearchWords.tsx',
    'components/workbench/assist/useContactAssist.tsx',
    'components/workbench/assist/useFileAssist.tsx',
    'components/workbench/assist/useMailAssist.tsx',
    'components/workbench/assist/useMailTriage.tsx',
    'components/workbench/assist/useTaskAssist.tsx',
    'components/workbench/assist/writingLines.ts',
    'components/workbench/calendar/EventEditor.tsx',
    'components/workbench/mail/MailFilters.tsx',
  ],
  tts: [
    'components/selection-assist/SelectionSession.tsx',
    'components/settings/voice-mode/LiaVoicesFields.tsx',
    'components/workbench/assist/useMailAssist.tsx',
    'hooks/useTtsVoiceSample.ts',
  ],
  workbench: [
    'components/dashboard/cards/useHomeActs.tsx',
    'lib/workbench/files.ts',
    'lib/workbench/mail.ts',
  ],
  workboard: [
    'components/notifications/NotificationsHub.tsx',
    'hooks/useWorkboardCategories.ts',
    'hooks/useWorkboardSummary.ts',
    'lib/workboard/api.ts',
  ],
  world: [
    'features/world/WorldPeerPanel.tsx',
    'features/world/mailbox-client.ts',
    'features/world/useWorldEnvironment.ts',
    'features/world/useWorldSession.ts',
  ],
};

/** The size of `OPEN_CHAINS`; lowered with every line that leaves. */
const OPEN_CHAINS_CEILING = 64;

// ---------------------------------------------------------------------------
// One reading of the API's table and of `src/`, at collection
// ---------------------------------------------------------------------------

const TABLE = JSON.parse(
  readFileSync(
    join(process.cwd(), '..', 'api', 'tests', 'unit', 'capability_route_table.json'),
    'utf-8'
  )
) as RouteTable;
const HEADS = new Set(
  Object.keys(TABLE.operations).map(template => template.split('/').filter(Boolean)[0])
);

const SOURCES = readSources(
  file =>
    !file.isTest &&
    /\.tsx?$/.test(file.relative) &&
    !/\.(test|d)\.tsx?$/.test(file.relative) &&
    // Content compiled from the repository (guides, maps): no call lives there.
    !file.relative.startsWith('data/')
);
const KNOWN = new Set(SOURCES.map(file => file.relative));
const TEXT = new Map(SOURCES.map(file => [file.relative, file.text]));
const MODULES = new Map<string, ParsedModule>(
  SOURCES.map(file => [file.relative, parseModule(file.relative, file.text, KNOWN, HEADS)])
);
linkTables(MODULES, HEADS);
for (const [module, methods] of Object.entries(METHOD_OF)) {
  for (const spelling of MODULES.get(module)?.spellings ?? []) {
    const template = resolvePath(TABLE, spelling.segments)?.templates[0];
    if (spelling.method === null && template && template in methods) {
      spelling.method = methods[template];
    }
  }
}
const CALLERS = callersOf(TABLE, MODULES.values());
const READERS = doorReaders(MODULES, new Set([SETTINGS_VERDICTS]));

function parse(relative: string): ts.SourceFile {
  return ts.createSourceFile(relative, TEXT.get(relative) ?? '', ts.ScriptTarget.Latest, true);
}

function eachNode(root: ts.Node, visit: (node: ts.Node) => void): void {
  visit(root);
  ts.forEachChild(root, child => eachNode(child, visit));
}

/** The capabilities whose closing door an expression reads, as the verdicts module spells it. */
function doorsReadBy(expression: ts.Node): Set<string> {
  const verdicts = MODULES.get(SETTINGS_VERDICTS);
  const closes = new Set<string>();
  eachNode(expression, node => {
    if (!ts.isCallExpression(node) || !ts.isIdentifier(node.expression)) return;
    const callee = node.expression.text;
    const key = node.arguments[1];
    if (callee === 'capabilityAvailable' && key && ts.isStringLiteral(key)) closes.add(key.text);
    const imported = verdicts?.importedNames.get(callee);
    const through = imported ? MODULES.get(imported.from)?.doorExports.get(imported.name) : null;
    for (const capability of through ?? []) closes.add(capability);
  });
  return closes;
}

/** Settings flag → the capabilities whose switch its verdict follows. */
function flagDoors(): Map<string, Set<string>> {
  const doors = new Map<string, Set<string>>();
  eachNode(parse(SETTINGS_VERDICTS), node => {
    if (ts.isPropertyAssignment(node) && ts.isIdentifier(node.name)) {
      const closes = doorsReadBy(node.initializer);
      if (closes.size > 0) doors.set(node.name.text, closes);
    }
  });
  return doors;
}

/** Section token → the modules its registry entry mounts. */
function sectionModules(): Map<string, string[]> {
  const found = new Map<string, string[]>();
  eachNode(parse(SECTION_REGISTRY), node => {
    if (!ts.isPropertyAssignment(node) || !ts.isObjectLiteralExpression(node.initializer)) return;
    const token = ts.isIdentifier(node.name) || ts.isStringLiteral(node.name) ? node.name.text : '';
    if (!(token in SETTINGS_SEARCH_META)) return;
    const mounted: string[] = [];
    eachNode(node.initializer, inner => {
      if (ts.isCallExpression(inner) && inner.expression.kind === ts.SyntaxKind.ImportKeyword) {
        const specifier = inner.arguments[0];
        const target =
          specifier && ts.isStringLiteral(specifier)
            ? resolveImport(SECTION_REGISTRY, specifier.text, KNOWN)
            : null;
        if (target !== null) mounted.push(target);
      }
    });
    found.set(token, mounted);
  });
  return found;
}

const FLAG_DOORS = flagDoors();
const SECTIONS = sectionModules();

/** The capabilities whose switch closes a section, read from its gate in the index. */
function sectionDoors(token: string): ReadonlySet<string> {
  const gate = SETTINGS_SEARCH_META[token as keyof typeof SETTINGS_SEARCH_META].gate;
  const flag = 'flag' in gate ? gate.flag : undefined;
  return (flag ? FLAG_DOORS.get(flag) : undefined) ?? new Set<string>();
}

function buildGraph(): Graph {
  const tree = appRouterTree(KNOWN);
  const edges = new Map<string, string[]>();
  for (const [relative, parsed] of MODULES) edges.set(relative, [...parsed.imports.keys()]);
  const closedEdges = new Map<string, ReadonlySet<string>>();
  for (const [layout, rendered] of tree.children) {
    edges.set(layout, [...(edges.get(layout) ?? []), ...rendered]);
    const closes = new Set(ROUTE_SHELLS[layout]?.closes ?? []);
    for (const child of rendered) closedEdges.set(`${layout}\n${child}`, closes);
  }
  for (const [token, mounted] of SECTIONS) {
    for (const target of mounted)
      closedEdges.set(`${SECTION_REGISTRY}\n${target}`, sectionDoors(token));
  }
  const roots = [...tree.roots, 'proxy.ts'].filter(root => KNOWN.has(root));
  return { roots, edges, readers: READERS, closedEdges };
}

const GRAPH = buildGraph();

/** `capability module` → the chain that reaches the module without a door. */
const OPEN = new Map<string, string[]>();
for (const caller of CALLERS) {
  if (READERS.get(caller.module)?.has(caller.capability)) continue;
  const chain = openChain(GRAPH, caller.module, caller.capability);
  if (chain !== null) OPEN.set(`${caller.capability} ${caller.module}`, chain);
}
const DECLARED = new Set(
  Object.entries(OPEN_CHAINS).flatMap(([capability, modules]) =>
    modules.map(module => `${capability} ${module}`)
  )
);

describe('the reading the guard stands on', () => {
  it('reads the API table and the tree: an empty walk would guard nothing', () => {
    expect(Object.keys(TABLE.operations).length).toBeGreaterThan(300);
    expect(MODULES.size).toBeGreaterThan(1500);
    expect(CALLERS.length).toBeGreaterThan(100);
    expect(GRAPH.roots).toContain('app/[lng]/layout.tsx');
  });

  it.each([
    // A plain literal.
    ['hooks/useJournalPortrait.ts', 'journals'],
    // A constant other paths are built on.
    ['lib/workboard/api.ts', 'workboard'],
    // A table of paths, read by the module that sends the request.
    ['hooks/useFileUpload.ts', 'attachments'],
    // An origin hole, then the path.
    ['lib/voice-input-service.ts', 'stt'],
    // The one method of a path the switch closes.
    ['lib/bookmark-state-context.tsx', 'bookmarks'],
  ])('finds the caller %s of %s', (module, capability) => {
    expect(CALLERS.some(c => c.module === module && c.capability === capability)).toBe(true);
  });

  it('gives a table of paths to its readers, never to the table', () => {
    expect(CALLERS.filter(caller => caller.module === 'lib/api-config.ts')).toEqual([]);
  });

  it('reads the method where the source does not say it, for the paths declared', () => {
    for (const [module, methods] of Object.entries(METHOD_OF)) {
      for (const [template, method] of Object.entries(methods)) {
        // The declaration names a real method of a real template, spelled by that module.
        expect(TABLE.operations[template], `${module}: ${template}`).toHaveProperty(method);
        const spelled = (MODULES.get(module)?.spellings ?? []).filter(
          spelling => resolvePath(TABLE, spelling.segments)?.templates[0] === template
        );
        expect(spelled.length, `${module} no longer spells ${template}`).toBeGreaterThan(0);
        // Declared only where the methods disagree: elsewhere it would hide nothing, or a call.
        const guards = new Set(Object.values(TABLE.operations[template]).map(g => g.join()));
        expect(guards.size, `${template}: every method is closed alike`).toBeGreaterThan(1);
      }
    }
  });
});

describe('the doors the guard counts', () => {
  it('reads which switch closes each gated settings section', () => {
    expect(FLAG_DOORS.get('journalsEnabled')).toEqual(new Set(['journals']));
    expect(FLAG_DOORS.get('ragSpacesEnabled')).toEqual(new Set(['rag_spaces']));
    // A section that shows a RECORD stays under the switch: its gate closes nothing.
    expect(FLAG_DOORS.has('habitsEnabled')).toBe(false);
    expect(SECTIONS.size).toBe(Object.keys(SETTINGS_SEARCH_META).length);
    expect(SECTIONS.get('journals')).toEqual(['components/settings/JournalsSettings.tsx']);
    expect([...sectionDoors('image-generation')]).toEqual(['image_generation']);
    // Telephony's sections show records the API serves under the switch: their
    // gate closes nothing, and the section that offers acts reads the door itself.
    expect([...sectionDoors('telephony-calls')]).toEqual([]);
    expect([...sectionDoors('telephony-identity')]).toEqual([]);
    expect([...sectionDoors('theme')]).toEqual([]);
  });

  it('holds each route shell to what it declares', () => {
    for (const [layout, { shell, closes }] of Object.entries(ROUTE_SHELLS)) {
      const parsed = MODULES.get(layout);
      const wrappers = [...(parsed?.childrenWrappers ?? [])].filter(
        wrapper => parsed?.importedNames.get(wrapper)?.from === shell
      );
      expect(wrappers.length, `${layout} renders its pages outside ${shell}`).toBeGreaterThan(0);
      for (const capability of closes) {
        expect(READERS.get(shell)?.has(capability), `${shell} reads no ${capability} door`).toBe(
          true
        );
      }
    }
  });
});

describe('a module that calls a route a capability closes', () => {
  it('has a door of that capability on every way to it', () => {
    const undeclared = [...OPEN].filter(([pair]) => !DECLARED.has(pair));

    expect(
      undeclared.map(([pair, chain]) => `${pair}\n    reached by: ${chain.join(' -> ')}`),
      'A module now calls a route its capability closes, with no door on the way: under the ' +
        "operator's switch the request can only be refused. Read the door where the reader is " +
        "mounted (`capabilityAvailable(config, '<capability>')`), or pass its verdict down."
    ).toEqual([]);
  });

  it('keeps no line a door now closes', () => {
    const closed = [...DECLARED].filter(pair => !OPEN.has(pair));

    expect(closed, 'Closed since: delete these lines of OPEN_CHAINS, lower the ceiling.').toEqual(
      []
    );
  });

  it('only shrinks', () => {
    expect(DECLARED.size).toBeLessThanOrEqual(OPEN_CHAINS_CEILING);
    expect(OPEN_CHAINS_CEILING).toBe(DECLARED.size);
  });
});
