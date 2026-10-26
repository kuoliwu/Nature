import { router } from 'expo-router';
import { useState } from 'react';
import { FlatList, Pressable, RefreshControl, StyleSheet, Text, View } from 'react-native';

import { addDays, mondayOf, TwoWeekCalendar } from '@/components/TwoWeekCalendar';
import { Message, MAX_WIDTH, colors } from '@/components/ui';
import { api, ScheduleItem } from '@/lib/api';
import { dayLabel, shortTime, toDateString } from '@/lib/dates';
import { SERVICE_LABEL, STATUS_LABEL } from '@/lib/labels';
import { useLoad } from '@/lib/useLoad';


export default function InspectionScheduleScreen() {
  const today = toDateString(new Date());
  const [day, setDay] = useState(today);
  const [start, setStart] = useState(() => mondayOf(today)); // 兩週日曆的第一天（星期一）
  const { data: items, error, refresh, refreshing } = useLoad(() => api.schedule(day), [day]);
  const { data: countRows, refresh: refreshCounts } = useLoad(() => api.scheduleCounts(start, 14).catch(() => []), [start]);
  const counts = Object.fromEntries((countRows ?? []).map((r) => [r.date, r.count]));

  function shift(weeks: number) {
    const next = addDays(start, weeks * 7);
    setStart(next);
    setDay(next); // 換到另外兩週時，先看那兩週的第一天
  }
  const { data: overdue } = useLoad(() => api.overdue().catch(() => []), []);

  return (
    <FlatList
      contentInsetAdjustmentBehavior="automatic" // iOS 半透明標題列時避免內容被擋住
      style={{ backgroundColor: colors.bg }}
      contentContainerStyle={localStyles.content}
      data={items ?? []}
      keyExtractor={(i) => String(i.booking_id)}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => void Promise.all([refresh(), refreshCounts()])} />}
      ListHeaderComponent={
        <View style={{ gap: 10 }}>
          <TwoWeekCalendar
            start={start}
            selected={day}
            today={today}
            counts={counts}
            onSelect={setDay}
            onShift={shift}
            onToday={() => {
              setStart(mondayOf(today));
              setDay(today);
            }}
          />
          <Text style={localStyles.dayTitle}>
            {dayLabel(day)}
            {day === today ? '（今天）' : ''}
            {items ? `　${items.length} 個行程` : ''}
          </Text>
          {!!overdue?.length && (
            <Pressable onPress={() => router.push('/overdue')} style={localStyles.overdue}>
              <Text style={localStyles.overdueText}>⚠️ {overdue.length} 戶報告逾期未完成（預約日後超過 7 天）</Text>
              <Text style={localStyles.overdueText}>›</Text>
            </Pressable>
          )}
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
          <Text style={localStyles.service}>{SERVICE_LABEL[item.service_type]}　</Text>
          {item.project_name} {item.unit_no}
        </Text>
        <Text style={localStyles.meta}>
          {item.contact_name}　{item.contact_phone}
        </Text>
        <Text style={localStyles.meta}>
          {item.service_type === 'visit'
            ? item.checked_in_at ? `已於 ${shortTime(item.checked_in_at.slice(11))} 報到` : '到場後點此報到'
            : item.status === 'not_started' ? `共 ${item.total} 個檢查點` : `已檢查 ${item.checked}/${item.total}`}
          {item.fail_count ? `｜不合格 ${item.fail_count}` : ''}
        </Text>
      </View>
      <Text style={[localStyles.badge, { color: status.color, borderColor: status.color }]}>{status.text}</Text>
    </Pressable>
  );
}

const localStyles = StyleSheet.create({
  content: { padding: 16, gap: 10, width: '100%', maxWidth: MAX_WIDTH, alignSelf: 'center' },
  dayTitle: { fontSize: 15, fontWeight: '700', color: colors.textSecondary, marginLeft: 4, marginTop: 4 },
  empty: { textAlign: 'center', color: colors.muted, marginTop: 40 },
  overdue: { flexDirection: 'row', justifyContent: 'space-between', backgroundColor: colors.error.bg, borderColor: colors.error.border, borderWidth: 1, borderRadius: 12, padding: 12 },
  overdueText: { color: colors.error.fg, fontSize: 15, fontWeight: '600' },
  row: { backgroundColor: colors.card, borderRadius: 12, padding: 14, flexDirection: 'row', alignItems: 'center', gap: 12 },
  time: { alignItems: 'center', width: 54 },
  timeText: { fontSize: 18, fontWeight: '700', color: colors.text },
  timeSub: { fontSize: 12, color: colors.muted },
  title: { fontSize: 16, fontWeight: '700', color: colors.text },
  service: { fontSize: 13, fontWeight: '700', color: colors.primary },
  meta: { fontSize: 13, color: colors.muted },
  badge: { fontSize: 12, fontWeight: '600', borderWidth: 1, borderRadius: 999, paddingHorizontal: 8, paddingVertical: 2 },
});
