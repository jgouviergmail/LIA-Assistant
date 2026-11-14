/**
 * Solid-surface icon guard — a glyph on a solid colour is drawn in its label colour.
 *
 * The coloured icon families paint fixed hues: Fluent's blues and violets.
 * Over a solid ground they clash with it, and the owner found the reset and
 * sign-out buttons « very unpleasant and hard to read », blue on red
 * (2026-11-11). The rule: a surface painting a solid colour (`bg-primary`,
 * `bg-destructive`, `from-primary`…, at 60 % or more) draws its icons through
 * `MonochromeIcons`, which renders the stroked glyph in `currentColor`.
 * `Button` does it for its solid variants and `Badge` for `alert`, so only
 * the surfaces written by hand need it.
 *
 * The scan reads the JSX tree (TypeScript's parser), never a regex over the
 * text: an icon is a descendant ELEMENT of the surface. It recognises a glyph
 * imported from `@/lib/icons` and a component variable named `Icon` or
 * `…Icon` (an icon chosen from a table); an icon reaching the surface through
 * a prop of another component is beyond what a file alone can say.
 */

import { describe, it, expect } from 'vitest';
import ts from 'typescript';

import { readSources } from './source-scan';

/** A solid ground: no opacity, or one of 60 % and more. Hover and focus states are not the rest state. */
const SOLID_TOKEN =
  /^(?:dark:)?(?:bg|from)-(?:primary|destructive|success|warning|info)(?:\/(\d+))?$/;
/** Cheap pre-filter: a file without one of these cannot hold a solid surface. */
const MAY_HOLD_SOLID = /\b(?:bg|from)-(?:primary|destructive|success|warning|info)\b/;

/** Primitives that apply the rule themselves, for the variants named. */
const SELF_MONOCHROME: Readonly<
  Record<string, { defaultSolid: boolean; solid: readonly string[] }>
> = {
  Button: { defaultSolid: true, solid: ['default', 'success', 'warning', 'destructive'] },
  Badge: { defaultSolid: false, solid: ['alert'] },
};

const ICON_VARIABLE = /^(?:[A-Z]\w*)?Icon$/;

function literalsOf(node: ts.Node, acc: string[] = []): string[] {
  if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) {
    acc.push(node.text);
  } else if (ts.isTemplateExpression(node)) {
    acc.push(node.head.text);
    for (const span of node.templateSpans) {
      literalsOf(span.expression, acc);
      acc.push(span.literal.text);
    }
  } else {
    // A block body: `forEachChild` stops at the first callback returning a truthy value.
    ts.forEachChild(node, child => {
      literalsOf(child, acc);
    });
  }
  return acc;
}

type JsxNode = ts.JsxElement | ts.JsxSelfClosingElement;

function opening(node: JsxNode): ts.JsxOpeningLikeElement {
  return ts.isJsxElement(node) ? node.openingElement : node;
}

function attribute(node: JsxNode, name: string): ts.JsxAttribute | undefined {
  return opening(node).attributes.properties.find(
    (prop): prop is ts.JsxAttribute => ts.isJsxAttribute(prop) && prop.name.getText() === name
  );
}

function paintsSolid(node: JsxNode): boolean {
  const className = attribute(node, 'className');
  if (!className?.initializer) return false;
  return literalsOf(className.initializer)
    .join(' ')
    .split(/\s+/)
    .some(token => {
      const match = SOLID_TOKEN.exec(token);
      return match !== null && (match[1] === undefined || Number(match[1]) >= 60);
    });
}

/** Whether a primitive draws its own glyphs in its label colour, from its literal `variant`. */
function selfMonochrome(node: JsxNode, tag: string): boolean {
  const rule = SELF_MONOCHROME[tag];
  if (!rule) return false;
  const variant = attribute(node, 'variant');
  if (!variant) return rule.defaultSolid;
  const init = variant.initializer;
  return init !== undefined && ts.isStringLiteral(init) && rule.solid.includes(init.text);
}

/**
 * Every icon drawn on a hand-written solid surface without `MonochromeIcons`.
 *
 * @param fileName - Reported in each finding.
 * @param text - The TSX source.
 * @returns `file:line <Icon>` for each offending glyph.
 */
export function solidSurfaceIconOffenders(fileName: string, text: string): string[] {
  const source = ts.createSourceFile(
    fileName,
    text,
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TSX
  );
  const imported = new Map<string, boolean>();
  for (const statement of source.statements) {
    if (!ts.isImportDeclaration(statement) || !ts.isStringLiteral(statement.moduleSpecifier))
      continue;
    const bindings = statement.importClause?.namedBindings;
    const fromIcons = statement.moduleSpecifier.text === '@/lib/icons';
    if (bindings && ts.isNamedImports(bindings)) {
      for (const element of bindings.elements) imported.set(element.name.text, fromIcons);
    }
    const defaultName = statement.importClause?.name?.text;
    if (defaultName) imported.set(defaultName, fromIcons);
  }
  const isIcon = (tag: string) => imported.get(tag) ?? ICON_VARIABLE.test(tag);

  const offenders: string[] = [];
  const visit = (node: ts.Node, onSolid: boolean, monochrome: boolean): void => {
    if (ts.isJsxElement(node) || ts.isJsxSelfClosingElement(node)) {
      const tag = opening(node).tagName.getText();
      if (tag === 'MonochromeIcons' || selfMonochrome(node, tag)) monochrome = true;
      else if (paintsSolid(node)) onSolid = true;
      if (onSolid && !monochrome && isIcon(tag)) {
        const line = source.getLineAndCharacterOfPosition(node.getStart()).line + 1;
        offenders.push(`${fileName}:${line} <${tag}>`);
      }
    }
    ts.forEachChild(node, child => {
      visit(child, onSolid, monochrome);
    });
  };
  visit(source, false, false);
  return offenders;
}

const SOURCES = readSources(file => file.relative.endsWith('.tsx') && !file.isTest).filter(file =>
  MAY_HOLD_SOLID.test(file.text)
);
const OFFENDERS = SOURCES.flatMap(file => solidSurfaceIconOffenders(file.relative, file.text));

describe('solid-surface icon guard', () => {
  it('reads the source tree', () => {
    // A filter that matched nothing would make the guard pass vacuously.
    expect(SOURCES.length).toBeGreaterThan(50);
  });

  it('flags a glyph on a hand-written solid surface, in every shape it takes', () => {
    const sample = `
      import { Check, LogOut } from '@/lib/icons';
      import { ConnectorIcon } from './ConnectorIcon';
      export const A = () => <button className="bg-destructive text-destructive-foreground"><LogOut /></button>;
      export const B = ({ on }) => <div className={cn('rounded', on ? 'bg-primary' : 'border')}>{on && <Check />}</div>;
      export const C = ({ Icon }) => <span className={\`flex \${x} bg-primary/90\`}><Icon /></span>;
      export const D = () => <div className="bg-gradient-to-br from-success to-success/80"><span><Check /></span></div>;
      export const E = () => <Button variant="ghost" className="bg-primary"><Check /></Button>;
      export const F = () => <div className="bg-primary"><ConnectorIcon /></div>;
    `;
    expect(solidSurfaceIconOffenders('sample.tsx', sample)).toEqual([
      'sample.tsx:4 <LogOut>',
      'sample.tsx:5 <Check>',
      'sample.tsx:6 <Icon>',
      'sample.tsx:7 <Check>',
      'sample.tsx:8 <Check>',
    ]);
  });

  it('accepts a glyph in its label colour, on a tint, or on a hover state', () => {
    const sample = `
      import { Check } from '@/lib/icons';
      export const A = () => <button className="bg-primary"><MonochromeIcons><Check /></MonochromeIcons></button>;
      export const B = () => <Button><Check /></Button>;
      export const C = () => <Button variant="destructive" className="bg-destructive"><Check /></Button>;
      export const D = () => <Badge variant="alert" icon={<Check />} />;
      export const E = () => <div className="bg-primary/10 text-primary"><Check /></div>;
      export const F = () => <div className="hover:bg-primary"><Check /></div>;
    `;
    expect(solidSurfaceIconOffenders('sample.tsx', sample)).toEqual([]);
  });

  it('draws every glyph of a solid surface in its label colour', () => {
    expect(
      OFFENDERS,
      'wrap the glyph in <MonochromeIcons> (lib/icon-style-context.tsx), or use a solid Button / Badge variant:\n' +
        OFFENDERS.join('\n')
    ).toEqual([]);
  });
});
