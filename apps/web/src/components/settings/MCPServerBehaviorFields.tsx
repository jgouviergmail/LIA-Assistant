'use client';

import type { TFunction } from 'i18next';
import { Bot, Layers, ListChecks, ShieldCheck, Workflow, Wrench } from 'lucide-react';

import {
  driverAvailability,
  MCP_DRIVERS,
  type MCPConfirmationChoice,
  type MCPDriver,
  type UserMCPDefaults,
} from '@/lib/mcp-behavior';
import { MCPChoiceCards, type MCPChoice } from './MCPChoiceCards';
import { currentlyLabel } from './MCPConfirmationStrategy';

const CONFIRMATION = 'settings.mcp.confirmation';
const DRIVER = 'settings.mcp.driver';

const DRIVER_ICONS = {
  direct: Wrench,
  pipeline_agent: Workflow,
  agent_everywhere: Bot,
} as const satisfies Record<MCPDriver, unknown>;

interface Props {
  confirmation: MCPConfirmationChoice;
  driver: MCPDriver;
  onConfirmation: (choice: MCPConfirmationChoice) => void;
  onDriver: (driver: MCPDriver) => void;
  /** Not read yet: nothing is offered, never a guess at what the choices give. */
  defaults: UserMCPDefaults | undefined;
  /** From the server's synthesis; unknown before the server exists. */
  isMcpApp: boolean;
  t: TFunction;
}

/**
 * A server's confirmation and who drives it (spec 2026-10-30 D3, D4).
 *
 * Settings-page only: the assistant's private form keeps its own fields, because the
 * assistant may only make LIA ask more (D7). « Like my strategy » says what the
 * account's strategy currently gives; a driver this server cannot take here is shown
 * disabled with the reason (an MCP App keeps its dedicated agent in ReAct; dedicated
 * agents off on the instance).
 */
export function MCPServerBehaviorFields({
  confirmation,
  driver,
  onConfirmation,
  onDriver,
  defaults,
  isMcpApp,
  t,
}: Props) {
  if (!defaults) return null;
  const confirmationChoices: MCPChoice<MCPConfirmationChoice>[] = [
    {
      value: 'always',
      label: t(`${CONFIRMATION}.server_options.always.label`),
      description: t(`${CONFIRMATION}.server_options.always.description`),
      icon: ShieldCheck,
    },
    {
      value: 'as_declared',
      label: t(`${CONFIRMATION}.server_options.as_declared.label`),
      description: t(`${CONFIRMATION}.server_options.as_declared.description`),
      icon: ListChecks,
    },
    {
      value: 'inherit',
      label: t(`${CONFIRMATION}.server_options.inherit.label`),
      description: t(`${CONFIRMATION}.server_options.inherit.description`, {
        value: currentlyLabel(defaults.confirmation_effective, t),
      }),
      icon: Layers,
    },
  ];
  const driverChoices: MCPChoice<MCPDriver>[] = MCP_DRIVERS.map(value => {
    const availability = driverAvailability(value, defaults, isMcpApp);
    return {
      value,
      label: t(`${DRIVER}.options.${value}.label`),
      description: t(`${DRIVER}.options.${value}.description`),
      icon: DRIVER_ICONS[value],
      unavailable: availability === 'available' ? null : t(`${DRIVER}.unavailable.${availability}`),
    };
  });
  return (
    <div className="space-y-5">
      <MCPChoiceCards
        legend={t(`${CONFIRMATION}.server_legend`)}
        value={confirmation}
        choices={confirmationChoices}
        onChange={onConfirmation}
      />
      <MCPChoiceCards
        legend={t(`${DRIVER}.legend`)}
        hint={t(`${DRIVER}.hint`)}
        value={driver}
        choices={driverChoices}
        onChange={onDriver}
      />
    </div>
  );
}
