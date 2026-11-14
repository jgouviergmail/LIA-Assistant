/**
 * Busy-not-disabled guard — a list or a switch saving its own choice is `busy`, never `disabled`.
 *
 * `disabled` put on a control WHILE IT HOLDS FOCUS makes the browser blur it and
 * drop it from the tab order: a keyboard user lands back on `<body>` (measured
 * on Radix, which calls `trigger.focus()` on a trigger it has just disabled —
 * 2026-11-13). `Select` and `Switch` take `busy` for that: still focusable,
 * `aria-busy` + `aria-disabled`, and a choice refused. The lists and the
 * switches of the settings were moved to it by hand; nothing stopped the next
 * one from coming back, and two had been left behind — the telephony domains,
 * and the heartbeat's hours, which reached their lists through a wrapper.
 *
 * So every `disabled` on a busy-aware control is DECLARED here with the reason
 * it cannot be changed at all, or belongs to a form its own button is sending —
 * where the focus is on that button, which takes `isLoading`. The declaration
 * only shrinks: a new `disabled` is refused, and so is an entry whose control
 * is gone. The scan reads the JSX tree (TypeScript's parser) and follows the
 * IMPORT, never the tag's spelling: an alias cannot evade it, and a homonym from
 * another module is not guarded. A wrapper that forwards a `disabled` prop to
 * one of these controls is guarded as one: what its callers pass is read at
 * THEIR call sites. A wrapper declared inside the file that uses it is beyond
 * what an import can say — its entry states what that file passes.
 */

import path from 'node:path';

import ts from 'typescript';
import { describe, expect, it } from 'vitest';

import { readSources } from '@/__tests__/source-scan';

/** The controls that can be `busy`, by the module under `src/` that exports them. */
const BUSY_AWARE: Readonly<Record<string, readonly string[]>> = {
  'components/ui/select': ['Select'],
  'components/ui/switch': ['Switch'],
  'components/workboard/GlyphSelect': ['GlyphSelect'],
  // Wrappers that forward a `disabled` prop to one of the above.
  'components/workboard/CategorySelect': ['CategorySelect'],
  'components/workboard/StatusSelect': ['StatusSelect'],
  'components/settings/llm-config/ReasoningWidget': ['ReasoningWidget'],
};

/** The module under `src/` an import names, whether by the `@/` alias or by a relative path. */
function importedModule(importer: string, specifier: string): string {
  if (specifier.startsWith('@/')) return specifier.slice(2);
  if (!specifier.startsWith('.')) return specifier;
  return path.posix.join(path.posix.dirname(importer), specifier);
}

/** One `disabled` found on a busy-aware control. */
interface Found {
  /** `file | <Tag> | expression`: what a declaration names. */
  readonly key: string;
  /** `file:line`, for the report. */
  readonly at: string;
}

/**
 * Every `disabled` attribute a file puts on a busy-aware control.
 *
 * @param relative - The file, as the report names it.
 * @param text - Its TSX source.
 * @returns One entry per attribute, in source order.
 */
export function disabledBusyAwareControls(relative: string, text: string): Found[] {
  const source = ts.createSourceFile(
    relative,
    text,
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TSX
  );
  const guarded = new Map<string, string>();
  for (const statement of source.statements) {
    if (!ts.isImportDeclaration(statement) || !ts.isStringLiteral(statement.moduleSpecifier)) {
      continue;
    }
    const exported = BUSY_AWARE[importedModule(relative, statement.moduleSpecifier.text)];
    const bindings = statement.importClause?.namedBindings;
    if (!exported || !bindings || !ts.isNamedImports(bindings)) continue;
    for (const element of bindings.elements) {
      const original = (element.propertyName ?? element.name).text;
      if (exported.includes(original)) guarded.set(element.name.text, original);
    }
  }
  const found: Found[] = [];
  const visit = (node: ts.Node): void => {
    if (ts.isJsxOpeningElement(node) || ts.isJsxSelfClosingElement(node)) {
      const control = guarded.get(node.tagName.getText(source));
      for (const property of control ? node.attributes.properties : []) {
        if (!ts.isJsxAttribute(property) || property.name.getText(source) !== 'disabled') continue;
        const initializer = property.initializer;
        const expression =
          initializer === undefined
            ? 'true'
            : ts.isJsxExpression(initializer)
              ? (initializer.expression?.getText(source) ?? '')
              : initializer.getText(source);
        const line = source.getLineAndCharacterOfPosition(property.getStart(source)).line + 1;
        found.push({
          key: `${relative} | <${control}> | ${expression.replace(/\s+/g, ' ')}`,
          at: `${relative}:${line}`,
        });
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(source);
  return found;
}

const FORWARDED = 'forwarded from the caller, whose own `disabled` is read at its call site';
const FORM_SENDING =
  'a field of a form its own button is sending: the focus is on that button, which takes `isLoading`';

/**
 * Every `disabled` left on a busy-aware control, and why it is not a `busy`.
 * SHRINK-ONLY: remove an entry with its control; never add one for a control
 * that saves its own choice — give it `busy`.
 */
const DECLARED: Readonly<Record<string, { readonly times: number; readonly reason: string }>> = {
  'components/meetings/MeetingImportDialog.tsx | <Select> | sending': {
    times: 1,
    reason: FORM_SENDING,
  },
  'components/settings/AdminCapabilitiesSection.tsx | <Switch> | blockedByDeployment': {
    times: 1,
    reason: 'the deployment forbids the capability: nothing the administrator can switch',
  },
  'components/settings/AdminPublicDemoLinkSection.tsx | <Switch> | !deployed': {
    times: 1,
    reason: 'no demonstrator is deployed: there is no link to publish',
  },
  'components/settings/AvatarSettings.tsx | <Switch> | !enabled && (!config.connected || !config.available)':
    {
      times: 1,
      reason: 'the video avatar is not connected or not available: it cannot be switched on',
    },
  'components/settings/CallModeField.tsx | <GlyphSelect> | unavailable': {
    times: 1,
    reason: 'Live cannot run on this instance: the call mode is not a choice',
  },
  'components/settings/LiveModeSettings.tsx | <Select> | saving': {
    times: 1,
    reason: FORM_SENDING,
  },
  'components/settings/LiveModeSettings.tsx | <Select> | disabled': {
    times: 1,
    reason: `inside the file, ${FORM_SENDING}`,
  },
  'components/settings/LiveModeSettings.tsx | <Select> | disabled || voices === undefined': {
    times: 1,
    reason: `inside the file, ${FORM_SENDING}; or the voices are not read yet`,
  },
  'components/settings/llm-config/ReasoningWidget.tsx | <Select> | disabled': {
    times: 1,
    reason: FORWARDED,
  },
  'components/settings/llm-config/ReasoningWidget.tsx | <Switch> | disabled': {
    times: 1,
    reason: FORWARDED,
  },
  "components/settings/LocationSettings.tsx | <Switch> | permission === 'unsupported'": {
    times: 1,
    reason: 'this browser has no geolocation: nothing to switch on',
  },
  "components/settings/MCPServerCard.tsx | <Switch> | !server.is_enabled && server.status !== 'active'":
    {
      times: 1,
      reason: 'a server that is not active cannot be enabled: it must be connected first',
    },
  "components/settings/NotificationSettings.tsx | <Switch> | !isSupported || !isConfigured || permissionStatus === 'denied'":
    {
      times: 1,
      reason: 'notifications are unsupported, not configured or refused by the browser',
    },
  'components/workbench/lights/LightControls.tsx | <Switch> | !reachable': {
    times: 1,
    reason: 'the lamp is unreachable: the bridge would refuse the order',
  },
  'components/workboard/CategorySelect.tsx | <GlyphSelect> | disabled': {
    times: 1,
    reason: FORWARDED,
  },
  'components/workboard/GlyphSelect.tsx | <Select> | disabled': { times: 1, reason: FORWARDED },
  'components/workboard/StatusSelect.tsx | <GlyphSelect> | disabled': {
    times: 1,
    reason: FORWARDED,
  },
};

const SOURCES = readSources(file => file.relative.endsWith('.tsx') && !file.isTest).filter(file =>
  file.text.includes('disabled')
);
const FOUND = SOURCES.flatMap(file => disabledBusyAwareControls(file.relative, file.text));

function counted(found: readonly Found[]): Map<string, number> {
  const times = new Map<string, number>();
  for (const { key } of found) times.set(key, (times.get(key) ?? 0) + 1);
  return times;
}

describe('a list or a switch saving its own choice is busy, never disabled', () => {
  it('reads the tree it guards', () => {
    // No floor on what is FOUND: the declaration is meant to shrink to nothing, and a
    // scan that saw nothing is caught by « only shrinks » and by the fixtures below.
    expect(SOURCES.length).toBeGreaterThan(100);
  });

  it('refuses a `disabled` nobody declared: a control saving its own choice takes `busy`', () => {
    const times = counted(FOUND);
    const undeclared = FOUND.filter(
      ({ key }) => (times.get(key) ?? 0) > (DECLARED[key]?.times ?? 0)
    ).map(({ key, at }) => `${at} — ${key}`);

    expect(undeclared).toEqual([]);
  });

  it('only shrinks: a declaration whose control is gone is removed', () => {
    const times = counted(FOUND);
    const stale = Object.entries(DECLARED)
      .filter(([key, declared]) => (times.get(key) ?? 0) < declared.times)
      .map(([key, declared]) => `${key}: declared ${declared.times}, found ${times.get(key) ?? 0}`);

    expect(stale).toEqual([]);
  });

  it('gives every declaration its reason', () => {
    for (const [key, declared] of Object.entries(DECLARED)) {
      expect(declared.reason.length, key).toBeGreaterThan(20);
    }
  });
});

describe('the scan follows the import, not the spelling', () => {
  const scan = (text: string) =>
    disabledBusyAwareControls('fixture.tsx', text).map(found => found.key);

  it('sees a switch disabled while it saves', () => {
    const text = `
      import { Switch } from '@/components/ui/switch';
      export const Row = ({ saving }: { saving: boolean }) => <Switch disabled={saving} />;
    `;
    expect(scan(text)).toEqual(['fixture.tsx | <Switch> | saving']);
  });

  it('sees it under another name, and with no value', () => {
    const text = `
      import { Select as Picker } from '@/components/ui/select';
      export const Row = () => <Picker disabled><span /></Picker>;
    `;
    expect(scan(text)).toEqual(['fixture.tsx | <Select> | true']);
  });

  it('sees it through a relative import, and on a wrapper that forwards it', () => {
    const text = `
      import { Switch } from '../ui/switch';
      import { StatusSelect as Status } from '../workboard/StatusSelect';
      export const Row = ({ saving }: { saving: boolean }) => (
        <>
          <Switch disabled={saving} />
          <Status disabled={saving} />
        </>
      );
    `;
    expect(
      disabledBusyAwareControls('components/settings/Row.tsx', text).map(found => found.key)
    ).toEqual([
      'components/settings/Row.tsx | <Switch> | saving',
      'components/settings/Row.tsx | <StatusSelect> | saving',
    ]);
  });

  it('lets a busy control and a homonym from another module be', () => {
    const text = `
      import { Switch } from '@/components/ui/switch';
      import { Select } from './native';
      export const Row = ({ saving }: { saving: boolean }) => (
        <>
          <Switch busy={saving} aria-disabled={saving} />
          <Select disabled={saving} />
          <button disabled={saving} />
        </>
      );
    `;
    expect(scan(text)).toEqual([]);
  });
});
