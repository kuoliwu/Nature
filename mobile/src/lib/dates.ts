/** 日期 / 時間與 API 字串（YYYY-MM-DD、HH:MM）互轉；一律用手機本地時區 */

const pad = (n: number) => String(n).padStart(2, '0');
const WEEKDAYS = ['日', '一', '二', '三', '四', '五', '六'];

export function toDateString(d: Date): string {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export function parseDate(s: string): Date {
  const [y, m, d] = s.split('-').map(Number);
  return new Date(y, m - 1, d);
}

export function toTimeString(d: Date): string {
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** "09:30" 或 "09:30:00" → 今天該時刻的 Date（給時間選擇器用） */
export function parseTime(s: string): Date {
  const [h, m] = s.split(':').map(Number);
  const d = new Date();
  d.setHours(h, m, 0, 0);
  return d;
}

/** 對齊到最接近的 step 分鐘（時段以 30 分鐘為單位） */
export function snapMinutes(d: Date, step = 30): Date {
  const out = new Date(d);
  const total = Math.round((out.getHours() * 60 + out.getMinutes()) / step) * step;
  out.setHours(Math.floor(total / 60) % 24, total % 60, 0, 0);
  return out;
}

export function shortTime(s: string): string {
  return s.slice(0, 5);
}

/** "2026-12-01" → "12/01（二）" */
export function dayLabel(s: string): string {
  const d = parseDate(s);
  return `${pad(d.getMonth() + 1)}/${pad(d.getDate())}（${WEEKDAYS[d.getDay()]}）`;
}

export function daysBetween(start: Date, end: Date): number {
  const ms = parseDate(toDateString(end)).getTime() - parseDate(toDateString(start)).getTime();
  return Math.round(ms / 86400000) + 1;
}

export type TimeRange = { start: string; end: string };

const toMinutes = (s: string) => {
  const [h, m] = s.split(':').map(Number);
  return h * 60 + m;
};

/** 每天會產生幾個時段：與任一屏蔽區段重疊的時段不算（與後端 generate_slots 規則相同） */
export function slotsPerDay(dayStart: string, dayEnd: string, breaks: TimeRange[] = [], minutes = 30): number {
  const blocks = breaks.map((b) => [toMinutes(b.start), toMinutes(b.end)]);
  let count = 0;
  for (let t = toMinutes(dayStart); t + minutes <= toMinutes(dayEnd); t += minutes) {
    if (!blocks.some(([bs, be]) => t < be && t + minutes > bs)) count++;
  }
  return count;
}
