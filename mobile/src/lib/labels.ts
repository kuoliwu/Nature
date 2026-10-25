import { colors } from '@/components/ui';
import type { InspectionStatus } from './api';

export const SERVICE_LABEL = { visit: '參觀', inspection: '驗屋', health_check: '健檢' } as const;

/** 建案的四個階段（第二～四階段各自對應一種預約） */
export const PHASES = [
  { service: 'visit', phase: '第二階段', title: '預約參觀', desc: '屋主線上預約參觀時段，當天現場報到', defaultName: '預約參觀' },
  { service: 'inspection', phase: '第三階段', title: '預約驗屋', desc: '預約驗屋、逐項檢查、屋主簽名、寄送驗屋報告', defaultName: '交屋驗屋' },
  { service: 'health_check', phase: '第四階段', title: '預約健檢', desc: '預約健檢、逐項檢查、屋主簽名、寄送健檢報告', defaultName: '保固健檢' },
] as const;

export const STATUS_LABEL: Record<InspectionStatus, { text: string; color: string }> = {
  not_started: { text: '未開始', color: colors.muted },
  in_progress: { text: '驗屋中', color: colors.primary },
  signed: { text: '已簽名', color: colors.green },
  approved: { text: '已確認', color: colors.green },
  sent: { text: '報告已寄出', color: colors.green },
  checked_in: { text: '已報到', color: colors.green },
};

