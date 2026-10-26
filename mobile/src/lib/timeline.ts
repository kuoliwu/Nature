/** 售服時間軸的純計算（components/Timeline.tsx 使用；可在 node 測試） */
import type { ProjectTimeline, TimelineStep } from './api';

export const STEP_STATUS_LABEL = { done: '完成', active: '進行中', todo: '未開始' } as const;

/** 0～1：進度條要填多長（填到目前步驟，加上該步驟的完成比例） */
export function timelineProgress(t: ProjectTimeline): number {
  const last = t.steps.length - 1;
  if (t.steps.every((s) => s.status === 'done')) return 1;
  const cur = t.steps[t.current];
  const frac = cur.status === 'active' && cur.total ? Math.min(cur.done / cur.total, 1) : 0;
  return Math.max(0, Math.min(1, (t.current - 1 + frac) / last));
}

const md = (d: string | null) => (d ? `${Number(d.slice(5, 7))}/${Number(d.slice(8, 10))}` : '');

/** 節點標籤第二行：完成→日期、進行中→完成戶數、未開始→排定日期 */
export function stepSubText(s: TimelineStep): string {
  if (s.status === 'active') return s.total ? `${s.done}/${s.total}` : '進行中';
  if (s.status === 'done') return md(s.date_to ?? s.date_from);
  return md(s.date_from);
}

export function stepRange(s: TimelineStep): string {
  if (!s.date_from) return '';
  return s.date_to && s.date_to !== s.date_from ? `${md(s.date_from)}–${md(s.date_to)}` : md(s.date_from);
}
