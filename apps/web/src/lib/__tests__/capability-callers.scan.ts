/**
 * Reading the web's sources for `capability-callers.guard.test.ts`.
 *
 * Three readings of one parse per module, each on the AST — a string that
 * LOOKS like a path, an import written in a comment or a door named in prose
 * are not what the browser runs:
 *
 * - which API paths a module SPELLS, resolved against the API's own table of
 *   its routes (`capability_route_table.json`) — never against a prefix;
 * - which modules it IMPORTS at runtime (type-only imports leave no edge);
 * - which capability DOORS it reads: a door closes a capability's routes
 *   under the operator's switch, so `capabilityMounted` — the deployment flag
 *   alone, for a record the API keeps open — is not one.
 */
import path from 'node:path';

import ts from 'typescript';

/** The API's table of what each capability switch closes. */
export interface RouteTable {
  /** Path template → method → the capability switches that close it. */
  operations: Record<string, Record<string, string[]>>;
  /** Capability → the flags that mount its router without being its ceiling. */
  router_flags: Record<string, string[]>;
}

/** A hole of a template string nothing in the module gives a value to. */
export const HOLE = '\u0000';

/** `client.<verb>(path)` → the HTTP method of the call. */
const VERBS: Readonly<Record<string, string>> = {
  get: 'GET',
  post: 'POST',
  put: 'PUT',
  patch: 'PATCH',
  delete: 'DELETE',
};

/** The doors that close a capability's routes under the operator's switch. */
const CLOSING_DOORS: ReadonlySet<string> = new Set(['capabilityAvailable', 'capabilityEnabled']);

/** An API path a module spells. */
export interface Spelling {
  /** The path's segments, `/api/v1` and any query removed; a hole is `HOLE`. */
  segments: string[];
  /** 1-based line of the string. */
  line: number;
  /** The HTTP method, when the string is the argument of `client.<verb>(…)`. */
  method: string | null;
}

/** `ROOT.A.B` read somewhere in a module: a path, when ROOT is a table of paths. */
export interface MemberRead {
  root: string;
  members: string[];
  line: number;
  method: string | null;
}

/** One module of `src/`, parsed once. */
export interface ParsedModule {
  /** Path relative to `src/`, forward slashes. */
  relative: string;
  /** Every string that could be an API path. */
  spellings: Spelling[];
  /** Runtime imports that resolve inside `src/`: target → imported names (`*` for all). */
  imports: Map<string, Set<string>>;
  /** Capabilities whose closing door the module calls itself, with a literal key. */
  doorCalls: Set<string>;
  /** Local name → where it was imported from. */
  importedNames: Map<string, { from: string; name: string }>;
  /** Every identifier the module's own code mentions (imports excluded). */
  mentions: Set<string>;
  /** Exported functions (lower-case initial) → the capabilities their body's door calls close. */
  doorExports: Map<string, Set<string>>;
  /** Local names of the JSX elements that wrap `{children}`. */
  childrenWrappers: Set<string>;
  /** Top-level object literal → `A.B` → the string it holds: a table of paths names no call. */
  tables: Map<string, Map<string, string>>;
  /** Member chains read in the module, resolved by {@link linkTables}. */
  memberReads: MemberRead[];
}

/**
 * Where a module specifier leads inside `src/`.
 *
 * @param from - The importing module, relative to `src/`.
 * @param specifier - What it imports.
 * @param known - Every module of `src/`.
 * @returns The imported module, or null for a package or an unknown file.
 */
export function resolveImport(
  from: string,
  specifier: string,
  known: ReadonlySet<string>
): string | null {
  let base: string;
  if (specifier.startsWith('@/')) base = specifier.slice(2);
  else if (specifier.startsWith('.')) base = path.posix.join(path.posix.dirname(from), specifier);
  else return null;
  const candidates = [base, `${base}.ts`, `${base}.tsx`, `${base}/index.ts`, `${base}/index.tsx`];
  return candidates.find(candidate => known.has(candidate)) ?? null;
}

function literalText(node: ts.Node): string | null {
  return ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node) ? node.text : null;
}

/** Top-level `const NAME = '…'`: what gives a `${NAME}` hole its value. */
function stringConstants(sourceFile: ts.SourceFile): Map<string, string> {
  const constants = new Map<string, string>();
  for (const statement of sourceFile.statements) {
    if (!ts.isVariableStatement(statement)) continue;
    for (const declaration of statement.declarationList.declarations) {
      const text = declaration.initializer ? literalText(declaration.initializer) : null;
      if (ts.isIdentifier(declaration.name) && text !== null) {
        constants.set(declaration.name.text, text);
      }
    }
  }
  return constants;
}

/**
 * The segments of an API path a string spells, or null when it spells none.
 *
 * @param text - The string, holes written as `HOLE`.
 * @param heads - The first segments the API's table knows.
 * @returns The path's segments, without `/api/v1` nor a query.
 */
export function apiSegments(text: string, heads: ReadonlySet<string>): string[] | null {
  let value = text;
  const query = value.search(/[?#]/);
  if (query >= 0) value = value.slice(0, query);
  // A trailing hole glued to a word is a query string or a suffix (`/export${query}`).
  value = value.replace(/([A-Za-z0-9_-])\u0000$/, '$1');
  // `/x/:id`, the placeholder a table of paths keeps for a later `.replace`.
  value = value.replace(/\/:[A-Za-z_]+/g, `/${HOLE}`);
  if (value.startsWith('/api/v1/')) value = value.slice('/api/v1'.length);
  if (!/^\/[a-z]/.test(value)) return null;
  const segments = value.split('/').filter(Boolean);
  if (segments.length === 0 || !heads.has(segments[0])) return null;
  return segments.every(segment => /^[A-Za-z0-9_.\-\u0000]+$/.test(segment)) ? segments : null;
}

function methodOf(node: ts.Node): string | null {
  const call = node.parent;
  if (!ts.isCallExpression(call) || !call.arguments.includes(node as ts.Expression)) return null;
  const callee = call.expression;
  return ts.isPropertyAccessExpression(callee) ? (VERBS[callee.name.text] ?? null) : null;
}

function templateText(node: ts.TemplateExpression, constants: Map<string, string>): string {
  let text = node.head.text;
  node.templateSpans.forEach((span, index) => {
    const known = ts.isIdentifier(span.expression)
      ? constants.get(span.expression.text)
      : undefined;
    // An unknown hole that OPENS the string is an origin (`${API_URL}/x`): dropped.
    if (known !== undefined) text += known;
    else if (index > 0 || node.head.text !== '') text += HOLE;
    text += span.literal.text;
  });
  return text;
}

function stringOf(node: ts.Node, constants: Map<string, string>): string | null {
  return ts.isTemplateExpression(node) ? templateText(node, constants) : literalText(node);
}

function closingDoorCall(node: ts.Node): string | null {
  if (!ts.isCallExpression(node) || !ts.isIdentifier(node.expression)) return null;
  if (!CLOSING_DOORS.has(node.expression.text)) return null;
  const key = node.arguments[1];
  return key ? literalText(key) : null;
}

function doorCallsIn(node: ts.Node): Set<string> {
  const found = new Set<string>();
  const visit = (child: ts.Node): void => {
    const capability = closingDoorCall(child);
    if (capability !== null) found.add(capability);
    ts.forEachChild(child, visit);
  };
  visit(node);
  return found;
}

function isExported(node: ts.Node): boolean {
  return (
    ts.canHaveModifiers(node) &&
    (ts.getModifiers(node) ?? []).some(modifier => modifier.kind === ts.SyntaxKind.ExportKeyword)
  );
}

/** A function, not a component: React requires a component's name to be capitalised. */
function isFunctionName(name: string): boolean {
  return /^[a-z]/.test(name);
}

function importBindings(clause: ts.ImportClause): [local: string, imported: string][] {
  const bindings: [string, string][] = [];
  if (clause.name) bindings.push([clause.name.text, 'default']);
  const named = clause.namedBindings;
  if (named && ts.isNamespaceImport(named)) bindings.push([named.name.text, '*']);
  if (named && ts.isNamedImports(named)) {
    for (const element of named.elements) {
      if (!element.isTypeOnly) {
        bindings.push([element.name.text, (element.propertyName ?? element.name).text]);
      }
    }
  }
  return bindings;
}

function collectImports(
  sourceFile: ts.SourceFile,
  known: ReadonlySet<string>,
  parsed: ParsedModule
): void {
  const edge = (specifier: string, names: Iterable<string>): string | null => {
    const target = resolveImport(parsed.relative, specifier, known);
    if (target === null) return null;
    const entry = parsed.imports.get(target) ?? new Set<string>();
    for (const name of names) entry.add(name);
    parsed.imports.set(target, entry);
    return target;
  };
  const staticImport = (statement: ts.ImportDeclaration): void => {
    const clause = statement.importClause;
    if (clause?.isTypeOnly || !ts.isStringLiteral(statement.moduleSpecifier)) return;
    const bindings = clause ? importBindings(clause) : [];
    // An import of types alone leaves no edge; a bare `import './x'` does.
    if (clause && bindings.length === 0) return;
    const target = edge(
      statement.moduleSpecifier.text,
      bindings.map(([, imported]) => imported)
    );
    if (target === null) return;
    for (const [local, imported] of bindings) {
      parsed.importedNames.set(local, { from: target, name: imported });
    }
  };
  const visit = (node: ts.Node): void => {
    if (ts.isImportDeclaration(node)) staticImport(node);
    else if (ts.isExportDeclaration(node) && node.moduleSpecifier && !node.isTypeOnly) {
      const specifier = literalText(node.moduleSpecifier);
      if (specifier !== null) edge(specifier, ['*']);
    } else if (ts.isCallExpression(node) && node.expression.kind === ts.SyntaxKind.ImportKeyword) {
      const specifier = node.arguments[0] ? literalText(node.arguments[0]) : null;
      if (specifier !== null) edge(specifier, ['*']);
    }
    ts.forEachChild(node, visit);
  };
  visit(sourceFile);
}

function collectDoorExports(sourceFile: ts.SourceFile, parsed: ParsedModule): void {
  const record = (name: string, body: ts.Node): void => {
    const reads = doorCallsIn(body);
    if (isFunctionName(name) && reads.size > 0) parsed.doorExports.set(name, reads);
  };
  for (const statement of sourceFile.statements) {
    if (!isExported(statement)) continue;
    if (ts.isFunctionDeclaration(statement) && statement.name) {
      record(statement.name.text, statement);
    } else if (ts.isVariableStatement(statement)) {
      for (const declaration of statement.declarationList.declarations) {
        const init = declaration.initializer;
        if (
          ts.isIdentifier(declaration.name) &&
          init &&
          (ts.isArrowFunction(init) || ts.isFunctionExpression(init))
        ) {
          record(declaration.name.text, init);
        }
      }
    }
  }
}

function collectChildrenWrappers(sourceFile: ts.SourceFile, parsed: ParsedModule): void {
  const visit = (node: ts.Node): void => {
    if (
      ts.isJsxExpression(node) &&
      node.expression &&
      ts.isIdentifier(node.expression) &&
      node.expression.text === 'children'
    ) {
      for (let up: ts.Node | undefined = node.parent; up; up = up.parent) {
        const tag = ts.isJsxElement(up) ? up.openingElement.tagName : null;
        // A component, not a `<div>`: only a component can read a door.
        if (tag && ts.isIdentifier(tag) && !isFunctionName(tag.text)) {
          parsed.childrenWrappers.add(tag.text);
        }
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(sourceFile);
}

function unwrapped(node: ts.Expression): ts.Expression {
  let inner = node;
  while (
    ts.isAsExpression(inner) ||
    ts.isSatisfiesExpression(inner) ||
    ts.isParenthesizedExpression(inner)
  ) {
    inner = inner.expression;
  }
  return inner;
}

/**
 * The top-level object literals of a module, flattened: a table of paths.
 *
 * @returns The tables, and where their strings start — those strings DEFINE
 *   paths for whoever reads the table, and are no call of this module.
 */
function collectTables(
  sourceFile: ts.SourceFile,
  constants: Map<string, string>,
  parsed: ParsedModule
): Set<number> {
  const definitions = new Set<number>();
  const flatten = (node: ts.ObjectLiteralExpression, prefix: string, into: Map<string, string>) => {
    for (const property of node.properties) {
      if (!ts.isPropertyAssignment(property)) continue;
      const name = property.name;
      if (!ts.isIdentifier(name) && !ts.isStringLiteral(name)) continue;
      const key = prefix === '' ? name.text : `${prefix}.${name.text}`;
      let value = unwrapped(property.initializer);
      if (ts.isArrowFunction(value) && !ts.isBlock(value.body)) value = unwrapped(value.body);
      if (ts.isObjectLiteralExpression(value)) flatten(value, key, into);
      const text = stringOf(value, constants);
      if (text === null) continue;
      into.set(key, text);
      definitions.add(value.getStart());
    }
  };
  for (const statement of sourceFile.statements) {
    if (!ts.isVariableStatement(statement)) continue;
    for (const declaration of statement.declarationList.declarations) {
      const init = declaration.initializer ? unwrapped(declaration.initializer) : null;
      if (ts.isIdentifier(declaration.name) && init && ts.isObjectLiteralExpression(init)) {
        const table = new Map<string, string>();
        flatten(init, '', table);
        if (table.size > 0) parsed.tables.set(declaration.name.text, table);
      }
    }
  }
  return definitions;
}

/** `ROOT.A.B` as written, when the node is the outermost access of its chain. */
function memberChain(node: ts.Node): { root: string; members: string[] } | null {
  if (!ts.isPropertyAccessExpression(node)) return null;
  if (ts.isPropertyAccessExpression(node.parent) && node.parent.expression === node) return null;
  const members: string[] = [];
  let current: ts.Expression = node;
  while (ts.isPropertyAccessExpression(current)) {
    members.unshift(current.name.text);
    current = current.expression;
  }
  return ts.isIdentifier(current) ? { root: current.text, members } : null;
}

/**
 * Parse one module.
 *
 * @param relative - Its path relative to `src/`.
 * @param text - Its source.
 * @param known - Every module of `src/`, to resolve its imports.
 * @param heads - The first segments the API's table knows.
 * @returns What the guard reads from it.
 */
export function parseModule(
  relative: string,
  text: string,
  known: ReadonlySet<string>,
  heads: ReadonlySet<string>
): ParsedModule {
  const sourceFile = ts.createSourceFile(relative, text, ts.ScriptTarget.Latest, true);
  const parsed: ParsedModule = {
    relative,
    spellings: [],
    imports: new Map(),
    doorCalls: new Set(),
    importedNames: new Map(),
    mentions: new Set(),
    doorExports: new Map(),
    childrenWrappers: new Set(),
    tables: new Map(),
    memberReads: [],
  };
  const constants = stringConstants(sourceFile);
  const definitions = collectTables(sourceFile, constants, parsed);
  const lineOf = (node: ts.Node): number =>
    sourceFile.getLineAndCharacterOfPosition(node.getStart()).line + 1;
  const visit = (node: ts.Node): void => {
    if (ts.isImportDeclaration(node)) return;
    const spelled = definitions.has(node.getStart()) ? null : stringOf(node, constants);
    const segments = spelled === null ? null : apiSegments(spelled, heads);
    if (segments !== null) {
      parsed.spellings.push({ segments, line: lineOf(node), method: methodOf(node) });
    }
    if (ts.isIdentifier(node)) parsed.mentions.add(node.text);
    const chain = memberChain(node);
    if (chain !== null) {
      parsed.memberReads.push({ ...chain, line: lineOf(node), method: methodOf(node) });
    }
    const capability = closingDoorCall(node);
    if (capability !== null) parsed.doorCalls.add(capability);
    ts.forEachChild(node, visit);
  };
  visit(sourceFile);
  collectImports(sourceFile, known, parsed);
  collectDoorExports(sourceFile, parsed);
  collectChildrenWrappers(sourceFile, parsed);
  return parsed;
}

/**
 * Give every read of a table of paths (`API_ENDPOINTS.X.Y`) to the module that READS it.
 *
 * @param modules - The parsed modules, by relative path; their spellings grow.
 * @param heads - The first segments the API's table knows.
 */
export function linkTables(
  modules: ReadonlyMap<string, ParsedModule>,
  heads: ReadonlySet<string>
): void {
  for (const parsed of modules.values()) {
    for (const read of parsed.memberReads) {
      const imported = parsed.importedNames.get(read.root);
      const table = imported
        ? modules.get(imported.from)?.tables.get(imported.name)
        : parsed.tables.get(read.root);
      if (!table) continue;
      // The longest member chain the table knows: `.BY_ID.replace` reads `BY_ID`.
      for (let length = read.members.length; length > 0; length -= 1) {
        const text = table.get(read.members.slice(0, length).join('.'));
        if (text === undefined) continue;
        const segments = apiSegments(text, heads);
        if (segments !== null) {
          parsed.spellings.push({ segments, line: read.line, method: read.method });
        }
        break;
      }
    }
  }
}

// ---------------------------------------------------------------------------
// Resolving a spelled path against the API's table
// ---------------------------------------------------------------------------

/** How a spelled path met the table. */
export interface Resolution {
  /**
   * `exact`: its literal segments are a template's; `loose`: a hole stands
   * where the only templates have a literal; `base`: it is the prefix of
   * longer templates (a constant other paths are built on).
   */
  how: 'exact' | 'loose' | 'base';
  templates: string[];
}

const segmentsOf = (template: string): string[] => template.split('/').filter(Boolean);
const isParameter = (segment: string): boolean => segment.startsWith('{');
const literalCount = (template: string): number =>
  segmentsOf(template).filter(segment => !isParameter(segment)).length;

/** `fits`: a template's opening segments are the spelled ones; `onLiteral`: through a hole. */
function meets(theirs: readonly string[], spelled: readonly string[]): 'no' | 'fits' | 'onLiteral' {
  let onLiteral = false;
  for (let index = 0; index < spelled.length; index += 1) {
    if (isParameter(theirs[index])) continue;
    if (spelled[index].includes(HOLE)) onLiteral = true;
    else if (spelled[index] !== theirs[index]) return 'no';
  }
  return onLiteral ? 'onLiteral' : 'fits';
}

/**
 * The templates of the table a spelled path names.
 *
 * @param table - The API's table.
 * @param spelled - The path's segments.
 * @returns The most literal templates of the same shape; else the templates a
 *   hole could reach; else the longer templates it prefixes; null when it
 *   names nothing the table knows.
 */
export function resolvePath(table: RouteTable, spelled: readonly string[]): Resolution | null {
  const exact: string[] = [];
  const loose: string[] = [];
  const under: string[] = [];
  for (const template of Object.keys(table.operations)) {
    const theirs = segmentsOf(template);
    if (theirs.length < spelled.length) continue;
    const met = meets(theirs, spelled);
    if (met === 'no') continue;
    if (theirs.length > spelled.length) under.push(template);
    else (met === 'onLiteral' ? loose : exact).push(template);
  }
  if (exact.length > 0) {
    // `/attachments/upload` over `/attachments/{attachment_id}`.
    const most = Math.max(...exact.map(literalCount));
    return { how: 'exact', templates: exact.filter(t => literalCount(t) === most) };
  }
  if (loose.length > 0) return { how: 'loose', templates: loose };
  return under.length > 0 ? { how: 'base', templates: under } : null;
}

/**
 * The capability switches that close what a spelled path names.
 *
 * @param table - The API's table.
 * @param resolution - How the path met it.
 * @param method - The call's HTTP method, when the source says it.
 * @returns For a template: the switches closing that method — or ANY of its
 *   methods when the source does not say which. For a base: the switches
 *   closing EVERY operation built on it.
 */
export function closingCapabilities(
  table: RouteTable,
  resolution: Resolution,
  method: string | null
): string[] {
  const perOperation = resolution.templates.flatMap(template => {
    const methods = table.operations[template];
    if (resolution.how === 'base' || method === null) return Object.values(methods);
    return method in methods ? [methods[method]] : [];
  });
  if (perOperation.length === 0) return [];
  if (resolution.how === 'base') {
    return perOperation.reduce((common, guards) => common.filter(g => guards.includes(g)));
  }
  return [...new Set(perOperation.flat())].sort();
}

/** A module that names an operation a capability closes. */
export interface Caller {
  module: string;
  capability: string;
  /** `line path` of every spelling that makes it one. */
  evidence: string[];
}

/**
 * Every (module, capability) where the module spells a path the capability closes.
 *
 * @param table - The API's table.
 * @param modules - The parsed modules, tables linked.
 * @returns The callers, sorted by capability then module.
 */
export function callersOf(table: RouteTable, modules: Iterable<ParsedModule>): Caller[] {
  const found = new Map<string, Caller>();
  for (const parsed of modules) {
    for (const spelling of parsed.spellings) {
      const resolution = resolvePath(table, spelling.segments);
      if (resolution === null) continue;
      const shown = `${spelling.line} /${spelling.segments.join('/').replaceAll(HOLE, '${…}')}`;
      for (const capability of closingCapabilities(table, resolution, spelling.method)) {
        const key = `${capability}\n${parsed.relative}`;
        const caller = found.get(key) ?? { module: parsed.relative, capability, evidence: [] };
        caller.evidence.push(shown);
        found.set(key, caller);
      }
    }
  }
  return [...found.values()].sort(
    (a, b) => a.capability.localeCompare(b.capability) || a.module.localeCompare(b.module)
  );
}

// ---------------------------------------------------------------------------
// Who reads a door
// ---------------------------------------------------------------------------

/**
 * The capabilities whose closing door each module reads.
 *
 * A module reads a door when it calls one with a literal key, or mentions a
 * function another module exports whose own body does (`workbenchAvailable`,
 * `useLiveAvailability`): ONE hop, never a chain — a component that consults
 * a verdict fences what IT renders, not everything its importers render.
 *
 * @param modules - The parsed modules, by relative path.
 * @param notADoor - Modules whose exports hand out verdicts that fence
 *   nothing by themselves (the settings index reads them section by section).
 * @returns Module → the capabilities it closes for what it imports.
 */
export function doorReaders(
  modules: ReadonlyMap<string, ParsedModule>,
  notADoor: ReadonlySet<string> = new Set()
): Map<string, Set<string>> {
  const readers = new Map<string, Set<string>>();
  for (const [relative, parsed] of modules) {
    const reads = new Set(parsed.doorCalls);
    for (const [local, { from, name }] of parsed.importedNames) {
      if (!parsed.mentions.has(local) || notADoor.has(from)) continue;
      for (const capability of modules.get(from)?.doorExports.get(name) ?? []) {
        reads.add(capability);
      }
    }
    readers.set(relative, reads);
  }
  return readers;
}

// ---------------------------------------------------------------------------
// The App Router's tree, and the walk from its entries
// ---------------------------------------------------------------------------

const SPECIAL_FILE =
  /^(layout|page|template|default|loading|error|not-found|global-error)\.tsx$|^route\.ts$/;

/**
 * The edges Next adds to the import graph: a layout renders the pages and the
 * nested layouts of its folder as its `children`.
 *
 * @param known - Every module of `src/`.
 * @returns `roots`: the files nothing renders (root layouts, route handlers,
 *   a page under no layout); `children`: layout → what it renders.
 */
export function appRouterTree(known: ReadonlySet<string>): {
  roots: string[];
  children: Map<string, string[]>;
} {
  const special = [...known].filter(
    file => file.startsWith('app/') && SPECIAL_FILE.test(path.posix.basename(file))
  );
  const layouts = new Set(special.filter(file => path.posix.basename(file) === 'layout.tsx'));
  const roots: string[] = [];
  const children = new Map<string, string[]>();
  for (const file of special) {
    let folder = path.posix.dirname(file);
    // A layout is rendered by the layout ABOVE its own folder.
    if (layouts.has(file)) folder = path.posix.dirname(folder);
    let parent: string | null = null;
    for (; folder !== '.' && parent === null; folder = path.posix.dirname(folder)) {
      if (layouts.has(`${folder}/layout.tsx`)) parent = `${folder}/layout.tsx`;
    }
    if (parent === null || path.posix.basename(file) === 'route.ts') roots.push(file);
    else children.set(parent, [...(children.get(parent) ?? []), file]);
  }
  return { roots: roots.sort(), children };
}

/** What the walk needs to know about the graph. */
export interface Graph {
  roots: readonly string[];
  /** Module → the modules it leads to. */
  edges: ReadonlyMap<string, readonly string[]>;
  /** Module → the capabilities whose door it reads: the walk never leaves it for those. */
  readers: ReadonlyMap<string, ReadonlySet<string>>;
  /** `from\nto` → the capabilities that close this one edge (a gated section, a wrapped page). */
  closedEdges: ReadonlyMap<string, ReadonlySet<string>>;
}

/**
 * A chain of imports from an entry to a module that meets no door of a capability.
 *
 * @param graph - The import graph with its doors.
 * @param target - The module that names a closed operation.
 * @param capability - The capability that closes it.
 * @returns The chain, entry first; null when every chain meets a door.
 */
export function openChain(graph: Graph, target: string, capability: string): string[] | null {
  const previous = new Map<string, string | null>();
  const queue: string[] = [];
  for (const root of graph.roots) {
    previous.set(root, null);
    queue.push(root);
  }
  for (let head = 0; head < queue.length; head += 1) {
    const current = queue[head];
    if (current === target) {
      const chain: string[] = [];
      for (let step: string | null = current; step !== null; step = previous.get(step) ?? null) {
        chain.unshift(step);
      }
      return chain;
    }
    if (graph.readers.get(current)?.has(capability)) continue;
    for (const next of graph.edges.get(current) ?? []) {
      if (previous.has(next)) continue;
      if (graph.closedEdges.get(`${current}\n${next}`)?.has(capability)) continue;
      previous.set(next, current);
      queue.push(next);
    }
  }
  return null;
}
