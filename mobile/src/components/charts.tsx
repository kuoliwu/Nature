/**
 * 儀表板圖表（純 View 繪製，手機 / 平板 / 網頁一致）
 * 規格：長條 ≤24px、相鄰區段間 2px 表面色間隔、資料端 4px 圓角；文字一律用文字色，不用資料色；
 * 兩個以上系列一定有圖例；點一下長條顯示數值（等同滑鼠移上去）；每張圖都能切換「表格檢視」。
 */
import { ReactNode, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { colors } from './ui';

// 色票已用 dataviz 驗證工具檢查（色盲可辨識、亮度順序）
export const chartColors = {
  surface: '#ffffff',
  track: '#cde2fb', // 未完成（同色系最淺）
  stage: { completed: '#1c5cab', booked: '#3987e5', invited: '#86b6ef', not_invited: '#cde2fb' },
  service: { visit: '#2a78d6', inspection: '#eb6834', health_check: '#1baf7a' },
  single: '#2a78d6',
  critical: '#d03b3b',
  grid: '#e1e0d9',
};

export type Segment = { key: string; label: string; value: number; color: string };

export function StatTile(props: { label: string; value: string | number; sub?: string; status?: 'critical' | 'good' }) {
  return (
    <View style={s.tile}>
      <Text style={s.tileLabel}>{props.label}</Text>
      <View style={s.tileRow}>
        {props.status && <Text style={{ color: props.status === 'critical' ? chartColors.critical : '#0ca30c' }}>{props.status === 'critical' ? '⚠︎ ' : '✓ '}</Text>}
        <Text style={s.tileValue}>{props.value}</Text>
      </View>
      {!!props.sub && <Text style={s.tileSub}>{props.sub}</Text>}
    </View>
  );
}

export function ChartCard(props: { title: string; subtitle?: string; table: ReactNode; children: ReactNode; legend?: Segment[] }) {
  const [showTable, setShowTable] = useState(false);
  return (
    <View style={s.card}>
      <View style={s.cardHead}>
        <View style={{ flex: 1 }}>
          <Text style={s.cardTitle}>{props.title}</Text>
          {!!props.subtitle && <Text style={s.cardSub}>{props.subtitle}</Text>}
        </View>
        <Pressable onPress={() => setShowTable((v) => !v)} hitSlop={8}>
          <Text style={s.toggle}>{showTable ? '圖表' : '表格'}</Text>
        </Pressable>
      </View>
      {props.legend && !showTable && <Legend items={props.legend} />}
      {showTable ? props.table : props.children}
    </View>
  );
}

function Legend({ items }: { items: Segment[] }) {
  return (
    <View style={s.legend}>
      {items.map((i) => (
        <View key={i.key} style={s.legendItem}>
          <View style={[s.swatch, { backgroundColor: i.color }]} />
          <Text style={s.legendText}>{i.label}</Text>
        </View>
      ))}
    </View>
  );
}

/** 每列一條水平堆疊長條（例如各階段的住戶進度），總長 = total */
export function StackedRows(props: { rows: { key: string; label: string; total: number; segments: Segment[]; note?: string }[] }) {
  const [picked, setPicked] = useState<string | null>(null);
  const pickedInfo = (() => {
    for (const r of props.rows) for (const seg of r.segments) if (`${r.key}:${seg.key}` === picked) return `${r.label}・${seg.label} ${seg.value} 戶（${pct(seg.value, r.total)}）`;
    return null;
  })();
  return (
    <View style={{ gap: 14 }}>
      {props.rows.map((r) => {
        const visible = r.segments.filter((seg) => seg.value > 0);
        return (
          <View key={r.key} style={{ gap: 6 }}>
            <View style={s.rowHead}>
              <Text style={s.rowLabel}>{r.label}</Text>
              <Text style={s.rowValue}>{r.note ?? ''}</Text>
            </View>
            <View style={s.stack}>
              {r.total === 0 ? (
                <View style={[s.segment, { flex: 1, backgroundColor: chartColors.track }]} />
              ) : (
                visible.map((seg, i) => (
                  <Pressable
                    key={seg.key}
                    onPress={() => setPicked(picked === `${r.key}:${seg.key}` ? null : `${r.key}:${seg.key}`)}
                    style={[
                      s.segment,
                      { flex: seg.value, backgroundColor: seg.color },
                      i === 0 && s.startRadius,
                      i === visible.length - 1 && s.endRadius,
                      picked === `${r.key}:${seg.key}` && s.picked,
                    ]}
                    accessibilityLabel={`${r.label} ${seg.label} ${seg.value}`}
                  />
                ))
              )}
            </View>
          </View>
        );
      })}
      <Text style={s.readout}>{pickedInfo ?? '點長條可看數字'}</Text>
    </View>
  );
}

/**
 * 依日期的直條（多系列堆疊），例如每日預約數。
 * 欄數多時每欄固定寬度、可左右捲動；只標最高的一天，其餘點直條看明細（不在每根長條都標數字）。
 */
export function StackedColumns(props: { columns: { key: string; label: string; segments: Segment[] }[] }) {
  const [picked, setPicked] = useState<string | null>(null);
  const totals = props.columns.map((c) => c.segments.reduce((n, seg) => n + seg.value, 0));
  const max = Math.max(1, ...totals);
  const peak = totals.indexOf(max);
  const height = 140;
  const col = props.columns.find((c) => c.key === picked);
  const scroll = props.columns.length > 8;
  const plot = (
    <View style={[s.columns, { height: height + 40 }, scroll && { width: props.columns.length * 50 }]}>
      <View style={[s.gridLine, { bottom: 22 }]} />
      {props.columns.map((c, ci) => {
        const total = totals[ci];
        const visible = c.segments.filter((seg) => seg.value > 0);
        return (
          <Pressable key={c.key} style={[s.column, scroll && { flexGrow: 0, flexShrink: 0, flexBasis: 46, width: 46 }]} onPress={() => setPicked(picked === c.key ? null : c.key)}>
            <Text style={s.colValue}>{ci === peak && total ? `最多 ${total}` : ''}</Text>
              <View style={{ height: (total / max) * height, width: '100%', maxWidth: 24, justifyContent: 'flex-end', gap: 2 }}>
                {[...visible].reverse().map((seg, i) => (
                  <View
                    key={seg.key}
                    style={[
                      { flex: seg.value, backgroundColor: seg.color },
                      i === 0 && { borderTopLeftRadius: 4, borderTopRightRadius: 4 },
                      picked === c.key && s.picked,
                    ]}
                  />
                ))}
              </View>
              <Text style={s.colLabel}>{c.label}</Text>
            </Pressable>
          );
        })}
    </View>
  );
  return (
    <View>
      {scroll ? <ScrollView horizontal showsHorizontalScrollIndicator>{plot}</ScrollView> : plot}
      <Text style={s.readout}>
        {col ? `${col.label}：` + col.segments.map((seg) => `${seg.label} ${seg.value}`).join('、') : '點直條可看當天明細'}
      </Text>
    </View>
  );
}

/** 單一系列水平長條（例如不合格項目 Top 10），數值標在長條末端 */
export function HBars(props: { rows: { key: string; label: string; value: number; tag?: string }[]; color?: string }) {
  const max = Math.max(1, ...props.rows.map((r) => r.value));
  return (
    <View style={{ gap: 10 }}>
      {props.rows.map((r) => (
        <View key={r.key} style={{ gap: 4 }}>
          <Text style={s.hbarLabel} numberOfLines={2}>
            {r.tag ? <Text style={s.hbarTag}>{r.tag}　</Text> : null}
            {r.label}
          </Text>
          <View style={s.hbarRow}>
            <View style={{ flex: r.value / max, height: 14, backgroundColor: props.color ?? chartColors.single, borderTopRightRadius: 4, borderBottomRightRadius: 4 }} />
            <Text style={s.hbarValue}>{r.value}</Text>
            <View style={{ flex: 1 - r.value / max }} />
          </View>
        </View>
      ))}
    </View>
  );
}

export function DataTable(props: { headers: string[]; rows: (string | number)[][] }) {
  return (
    <View style={s.table}>
      <View style={[s.tr, s.thead]}>
        {props.headers.map((h, i) => (
          <Text key={h} style={[s.td, s.th, i > 0 && s.num]}>{h}</Text>
        ))}
      </View>
      {props.rows.map((r, ri) => (
        <View key={ri} style={s.tr}>
          {r.map((v, i) => (
            <Text key={i} style={[s.td, i > 0 && s.num]}>{v}</Text>
          ))}
        </View>
      ))}
    </View>
  );
}

export const pct = (n: number, total: number) => (total ? `${Math.round((n / total) * 100)}%` : '—');

const s = StyleSheet.create({
  tile: { flexGrow: 1, flexBasis: 140, backgroundColor: colors.card, borderRadius: 12, padding: 14, gap: 2 },
  tileLabel: { fontSize: 13, color: colors.muted },
  tileRow: { flexDirection: 'row', alignItems: 'baseline' },
  tileValue: { fontSize: 26, fontWeight: '600', color: colors.text },
  tileSub: { fontSize: 12, color: colors.muted },
  card: { backgroundColor: colors.card, borderRadius: 12, padding: 16, gap: 12 },
  cardHead: { flexDirection: 'row', alignItems: 'flex-start', gap: 8 },
  cardTitle: { fontSize: 16, fontWeight: '700', color: colors.text },
  cardSub: { fontSize: 12, color: colors.muted, marginTop: 2 },
  toggle: { fontSize: 13, color: colors.primary },
  legend: { flexDirection: 'row', flexWrap: 'wrap', gap: 12 },
  legendItem: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  swatch: { width: 12, height: 12, borderRadius: 3 },
  legendText: { fontSize: 12, color: '#374151' },
  rowHead: { flexDirection: 'row', justifyContent: 'space-between' },
  rowLabel: { fontSize: 14, fontWeight: '600', color: colors.text },
  rowValue: { fontSize: 13, color: colors.muted },
  stack: { flexDirection: 'row', height: 20, gap: 2 },
  segment: { height: 20 },
  startRadius: { borderTopLeftRadius: 4, borderBottomLeftRadius: 4 },
  endRadius: { borderTopRightRadius: 4, borderBottomRightRadius: 4 },
  picked: { opacity: 0.75 },
  readout: { fontSize: 13, color: '#374151', minHeight: 18 },
  columns: { flexDirection: 'row', alignItems: 'flex-end', gap: 4 },
  gridLine: { position: 'absolute', left: 0, right: 0, height: 1, backgroundColor: chartColors.grid },
  column: { flex: 1, alignItems: 'center', justifyContent: 'flex-end', minWidth: 22, overflow: 'visible' },
  colValue: { fontSize: 11, color: '#374151', marginBottom: 2, width: 60, textAlign: 'center' },
  colLabel: { fontSize: 10, color: colors.muted, marginTop: 4, height: 16, width: 44, textAlign: 'center' },
  hbarLabel: { fontSize: 13, color: colors.text },
  hbarTag: { fontSize: 12, color: colors.muted },
  hbarRow: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  hbarValue: { fontSize: 12, color: '#374151', minWidth: 18 },
  table: { borderTopWidth: 1, borderTopColor: colors.border },
  tr: { flexDirection: 'row', borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border },
  thead: { backgroundColor: '#f9fafb' },
  td: { flex: 1, fontSize: 13, paddingVertical: 6, paddingHorizontal: 4, color: colors.text },
  th: { fontWeight: '700', color: '#374151' },
  num: { textAlign: 'right', fontVariant: ['tabular-nums'] },
});
