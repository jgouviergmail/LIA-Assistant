'use client';

import ConsumptionExportSection from '@/components/settings/ConsumptionExportSection';
import type { BaseSettingsProps } from '@/types/settings';

export default function AdminConsumptionExportSection(props: BaseSettingsProps) {
  return <ConsumptionExportSection {...props} mode="admin" />;
}
