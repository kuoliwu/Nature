import { router } from 'expo-router';
import { useState } from 'react';
import { FlatList, Pressable, RefreshControl, StyleSheet, Text, View } from 'react-native';

import { Message, MAX_WIDTH, colors } from '@/components/ui';
import { api, ScheduleItem } from '@/lib/api';
import { dayLabel, parseDate, shortTime, toDateString } from '@/lib/dates';
import { STATUS_LABEL } from '@/lib/labels';
import { useLoad } from '@/lib/useLoad';


function shiftDay(day: string, delta: number): string {
  const d = parseDate(day);
  d.setDate(d.getDate() + delta);
  return toDateString(d);
}

export default function InspectionScheduleScreen() {
  const today = toDateString(new Date());
  const [day, setDay] = useState(today);
  const { data: items, error, refresh, refreshing } = useLoad(() => api.schedule(day), [day]);

  return (
    <FlatList
      contentInsetAdjustmentBehavior="automatic" // iOS 半透明標題列時避免內容被擋住
      style={{ backgroundColor: colors.bg }}
      contentContainerStyle={localStyles.content}
      data={items ?? []}
      keyExtractor={(i) => String(i.booking_id)}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} />}
      ListHeaderComponent={
        <View style={{ gap: 10 }}>
          <View style={localStyles.dayBar}>
            <DayButton label="‹ 前一天" onPress={() => setDay(shiftDay(day, -1))} />
            <Pressable onPress={() => setDay(today)} style={localStyles.dayCenter}>
              <Text style={localStyles.dayText}>{dayLabel(day)}</Text>
              <Text style={localStyles.daySub}>{day === today ? '今天' : '點此回到今天'}</Text>
            </Pressable>
            <DayButton label="後一天 ›" onPress={() => setDay(shiftDay(day, 1))} />
          </View>
          {error && <Message kind="error" text={error} />}
        </View>
      }
      ListEmptyComponent={items ? <Text style={localStyles.empty}>這天沒有預約</Text> : undefined}
      renderItem={({ item }) => <ScheduleRow item={item} />}
    />
  );
}

function ScheduleRow({ item }: { item: ScheduleItem }) {
  const status = STATUS_LABEL[item.status];
  return (
    <Pressable
      onPress={() => router.push({ pathname: '/inspection/[bookingId]', params: { bookingId: String(item.booking_id) } })}
      style={({ pressed }) => [localStyles.row, pressed && { opacity: 0.7 }]}
    >
      <View style={localStyles.time}>
        <Text style={localStyles.timeText}>{shortTime(item.start_time)}</Text>
        <Text style={localStyles.timeSub}>{shortTime(item.end_time)}</Text>
      </View>
      <View style={{ flex: 1, gap: 2 }}>
        <Text style={localStyles.title}>
          {item.project_name} {item.unit_no}
        </Text>
        <Text style={localStyles.meta}>
          {item.contact_name}　{item.contact_phone}
        </Text>
        <Text style={localStyles.meta}>
          {item.status === 'not_started' ? `共 ${item.total} 個檢查點` : `已檢查 ${item.checked}/${item.total}`}
          {item.fail_count ? `｜不合格 ${item.fail_count}` : ''}
        </Text>
      </View>
      <Text style={[localStyles.badge, { color: status.color, borderColor: status.color }]}>{status.text}</Text>
    </Pressable>
  );
}

function DayButton({ label, onPress }: { label: string; onPress: () => void }) {
  return (
    <Pressable onPress={onPress} hitSlop={8} style={localStyles.dayButton}>
      <Text style={localStyles.dayButtonText}>{label}</Text>
    </Pressable>
  );
}

const localStyles = StyleSheet.create({
  content: { padding: 16, gap: 10, width: '100%', maxWidth: MAX_WIDTH, alignSelf: 'center' },
  dayBar: { flexDirection: 'row', alignItems: 'center', backgroundColor: colors.card, borderRadius: 12, padding: 8 },
  dayCenter: { flex: 1, alignItems: 'center' },
  dayText: { fontSize: 18, fontWeight: '700', color: colors.text },
  daySub: { fontSize: 12, color: colors.muted },
  dayButton: { paddingHorizontal: 10, paddingVertical: 8 },
  dayButtonText: { color: colors.primary, fontSize: 15 },
  empty: { textAlign: 'center', color: colors.muted, marginTop: 40 },
  row: { backgroundColor: colors.card, borderRadius: 12, padding: 14, flexDirection: 'row', alignItems: 'center', gap: 12 },
  time: { alignItems: 'center', width: 54 },
  timeText: { fontSize: 18, fontWeight: '700', color: colors.text },
  timeSub: { fontSize: 12, color: colors.muted },
  title: { fontSize: 16, fontWeight: '700', color: colors.text },
  meta: { fontSize: 13, color: colors.muted },
  badge: { fontSize: 12, fontWeight: '600', borderWidth: 1, borderRadius: 999, paddingHorizontal: 8, paddingVertical: 2 },
});
