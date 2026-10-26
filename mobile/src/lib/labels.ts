import { colors } from '@/components/ui';
import type { InspectionStatus } from './api';

export const SERVICE_LABEL = { visit: '參觀', inspection: '驗屋', health_check: '健檢' } as const;

/**
 * 售服七步驟中的三種預約（步驟 2 參觀、步驟 3～4 驗屋、步驟 6～7 健檢），各自對應一種服務。
 * cover：屋主預約頁最上方的封面照片
 */
export const PHASES = [
  { service: 'visit', phase: '步驟 2', title: '預約參觀', desc: '屋主線上預約參觀時段，當天現場報到', defaultName: '預約參觀',
    cover: { title: '參觀頁封面照片', hint: '選填，顯示在預約參觀頁面最上方' } },
  { service: 'inspection', phase: '步驟 3', title: '預約驗屋', desc: '屋主線上預約驗屋時段', defaultName: '交屋驗屋',
    cover: { title: '預售屋照片', hint: '顯示在預約驗屋頁面最上方' } },
  { service: 'health_check', phase: '步驟 6', title: '預約健檢', desc: '屋主線上預約健檢時段', defaultName: '保固健檢',
    cover: { title: '成屋照片', hint: '顯示在預約健檢頁面最上方' } },
] as const;

export const STATUS_LABEL: Record<InspectionStatus, { text: string; color: string }> = {
  not_started: { text: '未開始', color: colors.muted },
  in_progress: { text: '驗屋中', color: colors.primary },
  signed: { text: '已簽名', color: colors.green },
  approved: { text: '已確認', color: colors.green },
  sent: { text: '報告已寄出', color: colors.green },
  checked_in: { text: '已報到', color: colors.green },
};

