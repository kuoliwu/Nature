import { router, useNavigation } from 'expo-router';
import { useLayoutEffect, useState } from 'react';
import { FlatList, RefreshControl, StyleSheet, Text, View } from 'react-native';

import { Button, ListRow, Message, MAX_WIDTH, colors } from '@/components/ui';
import { api } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { dayLabel, shortTime } from '@/lib/dates';
import { confirm, errorText } from '@/lib/dialogs';
import { STATUS_LABEL } from '@/lib/labels';
import { useLoad } from '@/lib/useLoad';

/** 報告追蹤：預約日後超過 7 天、報告尚未完成（沒上傳外部報告、也沒寄出驗屋報告） */
export default function OverdueScreen() {
  const { can } = useAuth();
  const navigation = useNavigation();
  const { data: items, error, reload, refresh, refreshing } = useLoad(() => api.overdue(), []);
  const [notice, setNotice] = useState<{ ok: boolean; text: string } | null>(null);
  const [running, setRunning] = useState(false);

  useLayoutEffect(() => {
    navigation.setOptions({ title: '報告追蹤' });
  }, [navigation]);

  async function runNow() {
    if (!(await confirm('寄送提醒', '立即檢查並寄出 7 天／14 天報告未完成提醒（每戶每個階段只寄一次）。', '寄送'))) return;
    setRunning(true);
    try {
      const r = await api.runReminders();
      setNotice({
        ok: !r.error,
        text: r.error ? `寄送失敗：${r.error}` : r.sent ? `已寄出提醒：7 天 ${r.day7.length} 戶、14 天 ${r.day14.length} 戶` : '沒有需要寄送的新提醒',
      });
      await reload();
    } catch (e) {
      setNotice({ ok: false, text: errorText(e) });
    } finally {
      setRunning(false);
    }
  }

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
          <Message
            kind="info"
            text="預約日後超過 7 天、尚未完成報告的戶別。系統每天自動寄提醒信給內部人員（第 7 天、第 14 天各一次）；上傳外部報告或寄出驗屋報告後就會從清單移除。"
          />
          {can('report.manage') && <Button label="立即檢查並寄送提醒" variant="outline" onPress={runNow} loading={running} />}
          {error && <Message kind="error" text={error} />}
          {notice && <Message kind={notice.ok ? 'ok' : 'error'} text={notice.text} />}
        </View>
      }
      ListEmptyComponent={items ? <Text style={localStyles.empty}>🎉 目前沒有逾期未完成的報告</Text> : undefined}
      renderItem={({ item }) => (
        <ListRow
          title={`${item.project_name} ${item.unit_no}`}
          subtitle={
            `${dayLabel(item.date)} ${shortTime(item.start_time)}｜第 ${item.days} 天｜${STATUS_LABEL[item.inspection_status].text}` +
            (item.reminded.length ? `｜已提醒 ${item.reminded.map((d) => `${d}天`).join('、')}` : '')
          }
          right={item.days >= 14 ? '⚠️' : undefined}
          onPress={() => router.push({ pathname: '/inspection/[bookingId]', params: { bookingId: String(item.booking_id) } })}
        />
      )}
    />
  );
}

const localStyles = StyleSheet.create({
  content: { padding: 16, gap: 10, width: '100%', maxWidth: MAX_WIDTH, alignSelf: 'center' },
  empty: { textAlign: 'center', color: colors.muted, marginTop: 30, fontSize: 15 },
});
