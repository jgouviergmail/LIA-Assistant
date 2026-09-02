/**
 * Shared Components Barrel Export
 *
 * Centralizes all shared component exports for simplified imports.
 */

// Badges & chips
export * from './badges';
export { ActionBadge, type ActionBadgeProps, type ActionType } from './ActionBadge';
export { DebugChip, type DebugChipProps } from './DebugChip';
export { NodeChip, type NodeChipProps } from './NodeChip';

// Row components
export { MetricRow, type MetricRowProps } from './MetricRow';
export { ThresholdRow, type ThresholdRowProps, type ThresholdCheck } from './ThresholdRow';
export { InfoRow, type InfoRowProps, type ThresholdInfo } from './InfoRow';

// Score visualization
export { BudgetBar, type BudgetBarProps } from './BudgetBar';
export { ScoreBar, type ScoreBarProps } from './ScoreBar';
export { ScoreLegend, type ScoreLegendProps } from './ScoreLegend';
export {
  RetrievalSettingsBar,
  type RetrievalSettingsBarProps,
} from './RetrievalSettingsBar';

// List components
export { ScoresList, type ScoresListProps } from './ScoresList';
export { ToolMatchRow, type ToolMatchRowProps, type ToolMatch } from './ToolMatchRow';

// Section wrappers
export { DebugSection, type DebugSectionProps } from './DebugSection';
export { EmptySection, type EmptySectionProps } from './EmptySection';
export { SubSectionHeader, type SubSectionHeaderProps } from './SubSectionHeader';
