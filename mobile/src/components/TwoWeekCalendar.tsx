/**
 * 行程頁上方的兩週日曆（週一開始，兩排各 7 天）：
 *   有預約的日子 → 日期數字外圈＋下方「N 個」；選中的日子 → 實心圓；今天 → 主題色字
 * 左右箭頭一次移動兩週，「今天」回到本週。
 */
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { colors } from './ui';
import { parseDate, toDateString } from '@/lib/dates';

const WEEKDAYS = ['一', '二', '三', '四', '五', '六', '日'];

/** 這一天所在週的星期一 */
export function mondayOf(day: string): string {
  const d = parseDate(day);
  d.setDate(d.getDate() - ((d.getDay() + 6) % 7));
  return toDateString(d);
}

export function addDays(day: string, n: number): string {
  const d = parseDate(day);
  d.setDate(d.getDate() + n);
  return toDateString(d);
}

const md = (day: string) => `${Number(day.slice(5, 7))}/${Number(day.slice(8, 10))}`;

export function TwoWeekCalendar(props: {
  start: string; // 星期一
  selected: string;
  today: string;
  counts: Record<string, number>;
  onSelect: (day: string) => void;
  onShift: (weeks: number) => void;
  onToday: () => void;
}) {
  const days = Array.from({ length: 14 }, (_, i) => addDays(props.start, i));
  const end = days[13];
  const showToday = !days.includes(props.today) || props.selected !== props.today;

  return (
    <View style={s.card}>
      <View style={s.head}>
        <Pressable onPress={() => props.onShift(-2)} hitSlop={10} accessibilityLabel="前兩週" style={s.arrow}>
          <Text style={s.arrowText}>‹</Text>
        </Pressable>
        <Text style={s.range}>
          {md(props.start)} – {md(end)}
        </Text>
        <Pressable onPress={() => props.onShift(2)} hitSlop={10} accessibilityLabel="後兩週" style={s.arrow}>
          <Text style={s.arrowText}>›</Text>
        </Pressable>
        <View style={{ flex: 1 }} />
        {showToday && (
          <Pressable onPress={props.onToday} hitSlop={8} style={s.todayButton}>
            <Text style={s.todayButtonText}>今天</Text>
          </Pressable>
        )}
      </View>

      <View style={s.row}>
        {WEEKDAYS.map((w, i) => (
          <Text key={w} style={[s.weekday, i >= 5 && s.weekend]}>
            {w}
          </Text>
        ))}
      </View>
      {[0, 7].map((offset) => (
        <View key={offset} style={s.row}>
          {days.slice(offset, offset + 7).map((day) => {
            const count = props.counts[day] ?? 0;
            const selected = day === props.selected;
            const isToday = day === props.today;
            const n = Number(day.slice(8, 10));
            return (
              <Pressable
                key={day}
                onPress={() => props.onSelect(day)}
                style={s.cell}
                accessibilityLabel={`${md(day)}${isToday ? '（今天）' : ''}${count ? `，${count} 個行程` : '，沒有行程'}`}
                accessibilityState={{ selected }}
              >
                <View style={[s.circle, count > 0 && s.circleBusy, selected && s.circleSelected]}>
                  <Text style={[s.num, n === 1 && s.numMonth, isToday && s.numToday, selected && s.numSelected]}>
                    {n === 1 ? `${Number(day.slice(5, 7))}/1` : n}
                  </Text>
                </View>
                <Text style={[s.count, !count && s.countEmpty]}>{count ? `${count} 個` : ' '}</Text>
              </Pressable>
            );
          })}
        </View>
      ))}
    </View>
  );
}

const CIRCLE = 34;
const s = StyleSheet.create({
  card: { backgroundColor: colors.card, borderRadius: 12, paddingVertical: 10, paddingHorizontal: 6, gap: 4 },
  head: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 6, marginBottom: 4, gap: 4 },
  arrow: { paddingHorizontal: 8, paddingVertical: 2 },
  arrowText: { fontSize: 22, color: colors.primary, fontWeight: '600' },
  range: { fontSize: 16, fontWeight: '700', color: colors.text },
  todayButton: { borderWidth: 1, borderColor: colors.primary, borderRadius: 999, paddingHorizontal: 12, paddingVertical: 3 },
  todayButtonText: { color: colors.primary, fontSize: 13, fontWeight: '600' },
  row: { flexDirection: 'row' },
  weekday: { flex: 1, textAlign: 'center', fontSize: 12, color: colors.muted },
  weekend: { color: colors.faint },
  cell: { flex: 1, alignItems: 'center', paddingVertical: 3 },
  circle: { width: CIRCLE, height: CIRCLE, borderRadius: CIRCLE / 2, alignItems: 'center', justifyContent: 'center', borderWidth: 2, borderColor: 'transparent' },
  circleBusy: { borderColor: colors.primary }, // 有行程：外圈
  circleSelected: { backgroundColor: colors.primary, borderColor: colors.primary },
  num: { fontSize: 15, color: colors.text, fontWeight: '600' },
  numMonth: { fontSize: 11 }, // 月初顯示「11/1」
  numToday: { color: colors.primary, fontWeight: '800' },
  numSelected: { color: colors.onPrimary },
  count: { fontSize: 11, color: colors.textSecondary, marginTop: 2, fontWeight: '600' },
  countEmpty: { color: 'transparent' },
});
