/**
 * ConnectorIcon component.
 * Renders a connector icon based on type (emoji or icon component).
 * All icons have the same neutral background for consistency.
 */

import {
  CONNECTOR_ICONS,
  ICON_BG_CLASS,
  ICON_TEXT_CLASSES,
  DEFAULT_CONNECTOR_ICON,
} from './constants';

interface ConnectorIconProps {
  connectorType: string;
  className?: string;
}

export function ConnectorIcon({ connectorType, className = '' }: ConnectorIconProps) {
  const config = CONNECTOR_ICONS[connectorType];

  if (!config) {
    // Fallback for unknown connectors
    const Icon = DEFAULT_CONNECTOR_ICON;
    return (
      <div className={`flex h-10 w-10 items-center justify-center rounded-full ${ICON_BG_CLASS} ${className}`}>
        <Icon className="h-5 w-5 text-primary" />
      </div>
    );
  }

  const textClass = ICON_TEXT_CLASSES[config.color] || ICON_TEXT_CLASSES.slate;

  // Prefer emoji for visual distinction
  if (config.emoji) {
    return (
      <div className={`flex h-10 w-10 items-center justify-center rounded-full ${ICON_BG_CLASS} ${className}`}>
        <span className="text-xl" role="img" aria-label={connectorType}>
          {config.emoji}
        </span>
      </div>
    );
  }

  // Fallback to icon
  const Icon = config.icon || DEFAULT_CONNECTOR_ICON;
  return (
    <div className={`flex h-10 w-10 items-center justify-center rounded-full ${ICON_BG_CLASS} ${className}`}>
      <Icon className={`h-5 w-5 ${textClass}`} />
    </div>
  );
}
