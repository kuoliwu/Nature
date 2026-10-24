import { colors } from '@/components/ui';
import type { InspectionStatus } from './api';

export const SERVICE_LABEL = { health_check: '健檢', inspection: '驗屋' } as const;

export const STATUS_LABEL: Record<InspectionStatus, { text: string; color: string }> = {
  not_started: { text: '未開始', color: colors.muted },
  in_progress: { text: '驗屋中', color: colors.primary },
  signed: { text: '已簽名', color: colors.green },
  approved: { text: '已確認', color: colors.green },
  sent: { text: '報告已寄出', color: colors.green },
};

