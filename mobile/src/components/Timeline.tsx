/**
 * 售服時間軸：一條橫線上七個節點，標籤上下交錯排列（手機寬度也放得下）。
 *
 *          預約驗屋          履歷手冊
 *   ●━━━━━━━●━━━━━━━◐───────○───────○───────○───────○
 *  新建案  預約參觀       驗屋      預約健檢     健檢
 *
 * 實心＝完成、空心粗框＝進行中、灰框＝未開始；進度條填到目前步驟（含該步驟的完成比例）。
 */
import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import type { ProjectTimeline } from '@/lib/api';
import { STEP_STATUS_LABEL, stepRange, stepSubText, timelineProgress } from '@/lib/timeline';
import { colors } from './ui';

const DOT = 16;
const LABEL_H = 34; // 標籤區高度（兩行字）
const TRACK = colors.chip;

/** compact：建案列表裡和案名方塊並排時用（字小一點、標籤窄一點） */
export function Timeline({ data, interactive = false, compact = false }: { data: ProjectTimeline; interactive?: boolean; compact?: boolean }) {
  const [picked, setPicked] = useState<number | null>(null);
  const n = data.steps.length;
  const edge = `${50 / n}%` as const; // 線從第一個節點中心畫到最後一個節點中心
  const progress = timelineProgress(data);
  const detail = picked === null ? null : data.steps[picked];

  return (
    <View style={[s.wrap, compact && s.wrapCompact]}>
      <View style={s.row}>
        <View style={[s.track, { left: edge, right: edge }]}>
          <View style={[s.fill, { width: `${progress * 100}%` }]} />
        </View>
        {data.steps.map((step, i) => {
          const above = i % 2 === 0;
          const isCurrent = i === data.current && step.status !== 'done';
          const label = (
            <View style={[s.labelBox, compact && s.labelBoxCompact, above ? s.labelAbove : s.labelBelow]}>
              <Text numberOfLines={1} style={[s.label, compact && s.labelCompact, isCurrent && s.labelCurrent, step.status === 'todo' && s.labelTodo]}>
                {step.label}
              </Text>
              <Text numberOfLines={1} style={[s.sub, compact && s.subCompact]}>{stepSubText(step)}</Text>
            </View>
          );
          const dot = (
            <View style={[s.dot, step.status === 'done' ? s.dotDone : step.status === 'active' ? s.dotActive : s.dotTodo]}>
              {step.status === 'done' && <Text style={s.check}>✓</Text>}
            </View>
          );
          return (
            <Pressable
              key={step.key}
              style={s.col}
              disabled={!interactive}
              onPress={() => setPicked((p) => (p === i ? null : i))}
              accessibilityLabel={`${step.label}：${STEP_STATUS_LABEL[step.status]}`}
            >
              <View style={s.slot}>{above && label}</View>
              {dot}
              <View style={s.slot}>{!above && label}</View>
            </Pressable>
          );
        })}
      </View>
      {interactive && (
        <Text style={s.detail}>
          {detail
            ? `${detail.label}：${STEP_STATUS_LABEL[detail.status]}${detail.note ? `・${detail.note}` : ''}${stepRange(detail) ? `・${stepRange(detail)}` : ''}`
            : '點節點可看該步驟的詳細進度'}
        </Text>
      )}
    </View>
  );
}

const s = StyleSheet.create({
  wrap: { paddingHorizontal: 18 }, // 留空間給最左、最右的標籤
  wrapCompact: { paddingHorizontal: 14 },
  row: { flexDirection: 'row' },
  track: { position: 'absolute', top: LABEL_H + DOT / 2 - 2, height: 4, backgroundColor: TRACK, borderRadius: 2 },
  fill: { height: 4, backgroundColor: colors.primary, borderRadius: 2 },
  col: { flex: 1, alignItems: 'center' },
  slot: { height: LABEL_H, width: '100%', alignItems: 'center' },
  // 標籤比欄寬，置中後往左右兩邊延伸（上下交錯，所以不會撞到隔壁）
  labelBox: { width: 76, alignItems: 'center' },
  labelBoxCompact: { width: 58 },
  labelAbove: { position: 'absolute', bottom: 3 },
  labelBelow: { position: 'absolute', top: 3 },
  label: { fontSize: 12, fontWeight: '600', color: colors.text },
  labelCompact: { fontSize: 10.5 },
  labelCurrent: { color: colors.primary, fontWeight: '700' },
  labelTodo: { color: colors.muted, fontWeight: '400' },
  sub: { fontSize: 11, color: colors.muted },
  subCompact: { fontSize: 10 },
  dot: { width: DOT, height: DOT, borderRadius: DOT / 2, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.card },
  dotDone: { backgroundColor: colors.primary },
  dotActive: { borderWidth: 4, borderColor: colors.primary },
  dotTodo: { borderWidth: 2, borderColor: colors.faint },
  check: { color: colors.onPrimary, fontSize: 10, fontWeight: '700', lineHeight: 12 },
  detail: { fontSize: 13, color: colors.muted, marginTop: 6, textAlign: 'center' },
});
