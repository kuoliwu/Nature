import { useLocalSearchParams, useNavigation } from 'expo-router';
import { useLayoutEffect, useMemo, useState } from 'react';
import { FlatList, Platform, Pressable, RefreshControl, Share, StyleSheet, Text, View } from 'react-native';

import { ActionSheet, SheetOption } from '@/components/overlays';
import { useSheetTransfer } from '@/components/SheetTransfer';
import { Button, HeaderButton, ListRow, Message, MAX_WIDTH, colors } from '@/components/ui';
import { api, InviteStatus } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { dayLabel, shortTime } from '@/lib/dates';
import { confirm, errorText } from '@/lib/dialogs';
import { openLink } from '@/lib/download';
import { useLoad } from '@/lib/useLoad';

type Filter = 'all' | 'pending' | 'booked' | 'no_email';

const FILTERS: { key: Filter; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'pending', label: '未預約' },
  { key: 'booked', label: '已預約' },
  { key: 'no_email', label: '缺 Email' },
];

function statusText(r: InviteStatus): string {
  if (r.booking) return `✅ 已預約 ${dayLabel(r.booking.date)} ${shortTime(r.booking.start_time)}`;
  if (!r.owner_email) return r.link ? '缺 Email｜已產生連結' : '缺 Email，無法寄送';
  if (!r.sent_at) return '尚未寄送邀請';
  const opened = r.last_opened_at ? '，屋主已開啟' : '';
  return `已寄送 ${r.send_count} 次${opened}，尚未預約`;
}

export default function InvitesScreen() {
  const batchId = Number(useLocalSearchParams<{ id: string }>().id);
  const { can } = useAuth();
  const canManage = can('booking.manage');
  const navigation = useNavigation();
  const { data: rows, error, reload, refresh, refreshing } = useLoad(() => api.invites(batchId), [batchId]);
  const [filter, setFilter] = useState<Filter>('all');
  const [sheet, setSheet] = useState<{ title: string; options: SheetOption[] } | null>(null);
  const [notice, setNotice] = useState<{ ok: boolean; text: string } | null>(null);
  const [sending, setSending] = useState(false);
  const [excelMenu, setExcelMenu] = useState(false);
  const { data: batch } = useLoad(() => api.batch(batchId), [batchId]);
  const hasChecklist = !!batch && batch.service_type !== 'visit';
  const bookingsExcel = useSheetTransfer('bookings', { batch_id: batchId }, {
    label: '預約名單',
    unit: '戶',
    canImport: canManage,
    onImported: reload,
  });
  const resultsExcel = useSheetTransfer('results', { batch_id: batchId }, {
    label: '檢查結果',
    unit: '個檢查點',
    canImport: can('inspection.edit'),
  });

  useLayoutEffect(() => {
    navigation.setOptions({
      title: '預約邀請與名單',
      headerRight: () => <HeaderButton label="Excel" onPress={() => setExcelMenu(true)} />,
    });
  }, [navigation]);

  const counts = useMemo(() => {
    const list = rows ?? [];
    return {
      booked: list.filter((r) => r.booking).length,
      sent: list.filter((r) => !r.booking && r.sent_at).length,
      unsent: list.filter((r) => !r.booking && !r.sent_at && r.owner_email).length,
      noEmail: list.filter((r) => !r.booking && !r.owner_email).length,
    };
  }, [rows]);

  const filtered = useMemo(() => {
    const list = rows ?? [];
    if (filter === 'pending') return list.filter((r) => !r.booking);
    if (filter === 'booked') return [...list.filter((r) => r.booking)].sort((a, b) =>
      `${a.booking!.date}${a.booking!.start_time}`.localeCompare(`${b.booking!.date}${b.booking!.start_time}`));
    if (filter === 'no_email') return list.filter((r) => !r.owner_email && !r.booking);
    return list;
  }, [rows, filter]);

  async function run(action: () => Promise<unknown>) {
    try {
      setNotice(null);
      await action();
    } catch (e) {
      setNotice({ ok: false, text: errorText(e) });
    }
  }

  async function sendAll() {
    if (!counts.unsent) return;
    if (!(await confirm('寄送預約邀請', `將寄送邀請信給 ${counts.unsent} 戶尚未寄送的住戶。`, '寄送'))) return;
    setSending(true);
    await run(async () => {
      const r = await api.sendInvites(batchId, {});
      setNotice({
        ok: true,
        text: `已寄出 ${r.sent.length} 戶` + (r.no_email.length ? `；${r.no_email.length} 戶沒有 Email（可改用分享連結）` : ''),
      });
      await reload();
    });
    setSending(false);
  }

  async function shareLink(row: InviteStatus) {
    const link = row.link ?? (await api.inviteLink(batchId, row.unit_id)).link;
    if (!link) return;
    const message = `${row.owner_name ?? '屋主'} 您好，請點以下連結預約 ${row.unit_no} 的健檢時段：\n${link}`;
    if (Platform.OS === 'web') {
      // 網頁版不一定支援系統分享，改為顯示連結讓使用者複製
      window.prompt('預約連結（請複製後傳給屋主）', link);
    } else {
      await Share.share({ message });
    }
    await reload();
  }

  function openMenu(row: InviteStatus) {
    const options: SheetOption[] = [];
    if (canManage && row.owner_email && !row.booking) {
      options.push({
        label: row.sent_at ? '重新寄送邀請信' : '寄送邀請信',
        onPress: () => run(async () => {
          await api.sendInvites(batchId, { unit_ids: [row.unit_id], resend: true });
          setNotice({ ok: true, text: `已寄送邀請給 ${row.unit_no}（${row.owner_email}）` });
          await reload();
        }),
      });
    }
    if (canManage) {
      options.push({ label: '分享預約連結（LINE / 簡訊）', onPress: () => run(() => shareLink(row)) });
      options.push({
        label: row.booking ? '開啟預約頁（代為改期）' : '開啟預約頁（代為預約）',
        onPress: () => run(async () => {
          await openLink(async () => row.link ?? (await api.inviteLink(batchId, row.unit_id)).link);
        }),
      });
    }
    if (canManage && row.booking) {
      const b = row.booking;
      options.push({
        label: '取消預約',
        destructive: true,
        onPress: async () => {
          if (!(await confirm('取消預約', `確定要取消 ${row.unit_no} 的預約（${dayLabel(b.date)} ${shortTime(b.start_time)}）？\n系統會寄取消通知給屋主。`, '取消預約', true))) return;
          await run(async () => {
            await api.cancelBooking(b.id);
            setNotice({ ok: true, text: `已取消 ${row.unit_no} 的預約` });
            await reload();
          });
        },
      });
    }
    const contact = row.booking ? `${row.booking.contact_name} ${row.booking.contact_phone}` : row.owner_email ?? '沒有 Email';
    setSheet({ title: `${row.unit_no}｜${contact}`, options });
  }

  return (
    <View style={{ flex: 1 }}>
      <FlatList
        contentInsetAdjustmentBehavior="automatic" // iOS 半透明標題列時避免內容被擋住
        style={{ backgroundColor: colors.bg }}
        contentContainerStyle={localStyles.content}
        data={filtered}
        keyExtractor={(r) => String(r.unit_id)}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} />}
        ListHeaderComponent={
          <View style={{ gap: 10 }}>
            <View style={localStyles.stats}>
              <Stat label="已預約" value={counts.booked} color={colors.green} />
              <Stat label="已寄送" value={counts.sent} color={colors.primary} />
              <Stat label="未寄送" value={counts.unsent} color={colors.text} />
              <Stat label="缺 Email" value={counts.noEmail} color={colors.danger} />
            </View>
            {canManage && (
              <Button
                label={counts.unsent ? `寄送邀請給尚未寄送的住戶（${counts.unsent} 戶）` : '所有有 Email 的住戶都已寄送'}
                onPress={sendAll}
                loading={sending}
                disabled={!counts.unsent}
              />
            )}
            {error && <Message kind="error" text={error} />}
            {notice && <Message kind={notice.ok ? 'ok' : 'error'} text={notice.text} />}
            {bookingsExcel.status}
            {resultsExcel.status}
            <View style={localStyles.filters}>
              {FILTERS.map((f) => (
                <Pressable key={f.key} onPress={() => setFilter(f.key)} style={[localStyles.chip, filter === f.key && localStyles.chipOn]}>
                  <Text style={[localStyles.chipText, filter === f.key && localStyles.chipTextOn]}>{f.label}</Text>
                </Pressable>
              ))}
            </View>
          </View>
        }
        ListEmptyComponent={rows ? <Text style={localStyles.empty}>沒有符合的住戶</Text> : undefined}
        renderItem={({ item }) => (
          <ListRow
            title={`${item.unit_no}${item.owner_name ? `　${item.owner_name}` : ''}`}
            subtitle={statusText(item)}
            onPress={canManage ? () => openMenu(item) : undefined}
          />
        )}
      />
      <ActionSheet visible={!!sheet} title={sheet?.title} options={sheet?.options ?? []} onClose={() => setSheet(null)} />
      <ActionSheet
        visible={excelMenu}
        title="預約名單／檢查結果 Excel"
        options={[...bookingsExcel.options, ...(hasChecklist ? resultsExcel.options : [])]}
        onClose={() => setExcelMenu(false)}
      />
    </View>
  );
}

function Stat({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <View style={localStyles.stat}>
      <Text style={[localStyles.statValue, { color }]}>{value}</Text>
      <Text style={localStyles.statLabel}>{label}</Text>
    </View>
  );
}

const localStyles = StyleSheet.create({
  content: { padding: 16, gap: 10, width: '100%', maxWidth: MAX_WIDTH, alignSelf: 'center' },
  stats: { flexDirection: 'row', backgroundColor: colors.card, borderRadius: 12, paddingVertical: 12 },
  stat: { flex: 1, alignItems: 'center' },
  statValue: { fontSize: 22, fontWeight: '700' },
  statLabel: { fontSize: 12, color: colors.muted, marginTop: 2 },
  filters: { flexDirection: 'row', gap: 8, flexWrap: 'wrap' },
  chip: { borderWidth: 1, borderColor: colors.border, backgroundColor: '#fff', borderRadius: 999, paddingHorizontal: 14, paddingVertical: 6 },
  chipOn: { backgroundColor: colors.primary, borderColor: colors.primary },
  chipText: { fontSize: 14, color: colors.text },
  chipTextOn: { color: '#fff', fontWeight: '600' },
  empty: { textAlign: 'center', color: colors.muted, marginTop: 30 },
});
