'use client';

/**
 * Registry Context — Lightweight React Context for registry access deep in the component tree.
 *
 * Provides registry items to McpAppWidget without prop drilling through
 * MarkdownContent (which only receives a content string).
 *
 * Phase: evolution F2.5 — MCP Apps
 */

import { createContext, useContext } from 'react';
import type { RegistryItem } from '@/types/chat';

const RegistryContext = createContext<Record<string, RegistryItem>>({});

export const RegistryProvider = RegistryContext.Provider;

export function useRegistryItem(id: string): RegistryItem | undefined {
  return useContext(RegistryContext)[id];
}
