'use client';

import type { useCapabilitySharing } from '@/hooks/useCapabilitySharing';
import { CapabilityTransferDialog } from './CapabilityTransferDialog';

export function CapabilitySharingDialog({
  sharing,
  ownerId,
  enabled,
}: {
  sharing: ReturnType<typeof useCapabilitySharing>;
  ownerId: string | undefined;
  enabled: boolean;
}) {
  if (!enabled || !ownerId || !sharing.selection) return null;
  const selection = sharing.selection;
  return (
    <CapabilityTransferDialog
      key={`${ownerId}:${selection.kind}:${selection.id}`}
      source={selection}
      onClose={sharing.close}
    />
  );
}
