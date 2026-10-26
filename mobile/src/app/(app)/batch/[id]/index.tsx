import { router, useLocalSearchParams, useNavigation } from 'expo-router';
import { useLayoutEffect, useState } from 'react';
import { Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';

import { Meter, pct } from '@/components/charts';
import { ActionSheet, PromptModal } from '@/components/overlays';
import { useSheetTransfer } from '@/components/SheetTransfer';
import { Card, HeaderButton, ListRow, Loading, Message, MAX_WIDTH, colors } from '@/components/ui';
import { api, BatchDetail, Slot } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { dayLabel, shortTime } from '@/lib/dates';
import { confirm, errorText } from '@/lib/dialogs';
import { SERVICE_LABEL } from '@/lib/labels';
import { useLoad } from '@/lib/useLoad';

export default function BatchScreen() {
  const id = Number(useLocalSearchParams<{ id: string }>().id);
  const { can } = useAuth();
  const editable = can('batch.manage');
  const canSeeBookings = can('booking.view') || can('booking.manage');
  const navigation = useNavigation();
  const { data: batch, setData: setBatch, error, setError, reload, refresh, refreshing } = useLoad(() => api.batch(id), [id]);
  const [selected, setSelected] = useState<{ date: string; slotId: number } | null>(null);
  const [menu, setMenu] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const excel = useSheetTransfer('slots', { batch_id: id }, { label: '時段', unit: '個時段', canImport: editable, onImported: reload });

  useLayoutEffect(() => {
    navigation.setOptions({
      title: batch?.name ?? '健檢日期',
      headerRight: editable ? () => <HeaderButton label="設定" onPress={() => setMenu(true)} /> : undefined,
    });
  }, [navigation, batch?.name, editable]);

  if (!batch) return error ? <Message kind="error" text={error} /> : <Loading />;

  // 完成率 = 開放時段的已預約組數 ÷ 開放名額
  const openSlots = batch.days.flatMap((d) => d.slots.filter((s) => s.is_open));
  const openCapacity = openSlots.reduce((n, s) => n + s.capacity, 0);
  const openBooked = openSlots.reduce((n, s) => n + Math.min(s.booked, s.capacity), 0);

  const selectedSlot = selected
    ? batch.days.find((d) => d.date === selected.date)?.slots.find((s) => s.id === selected.slotId)
    : undefined;

  /** 只更新畫面上那一格，不用整頁重新載入 */
  function patchSlot(updated: Slot) {
    setBatch((b: BatchDetail | null) =>
      b && {
        ...b,
        days: b.days.map((d) => ({ ...d, slots: d.slots.map((s) => (s.id === updated.id ? updated : s)) })),
        open_slot_count: b.open_slot_count + (updated.is_open ? 1 : 0) - (findSlot(b, updated.id)?.is_open ? 1 : 0),
      },
    );
  }

  async function run(action: () => Promise<unknown>) {
    try {
      setError(null);
      await action();
    } catch (e) {
      setError(errorText(e));
    }
  }

  const updateSlot = (slot: Slot, body: { is_open?: boolean; capacity?: number }) =>
    run(async () => patchSlot(await api.updateSlot(slot.id, body)));

  const toggleDay = (date: string, open: boolean) =>
    run(async () => {
      await api.updateDay(id, date, open);
      await reload();
    });

  async function removeBatch() {
    if (!batch || !(await confirm(`刪除${SERVICE_LABEL[batch.service_type]}日期`, `確定要刪除「${batch.name}」與所有時段？`, '刪除', true))) return;
    await run(async () => {
      await api.deleteBatch(id);
      // 從網址直接開啟（例如 PWA 重新整理）時沒有上一頁，改回到日期列表
      if (router.canGoBack()) router.back();
      else
        router.replace({
          pathname: '/project/[id]/batches',
          params: { id: String(batch.project_id), service: batch.service_type },
        });
    });
  }

  return (
    <View style={localStyles.flex}>
      <ScrollView
        contentInsetAdjustmentBehavior="automatic" // iOS 半透明標題列時避免內容被擋住
        style={{ backgroundColor: colors.bg }}
        contentContainerStyle={localStyles.content}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} />}
      >
        <Card>
          <View style={localStyles.heroRow}>
            <View style={localStyles.flex}>
              <Text style={localStyles.heroLabel}>完成率（已預約 ÷ 開放名額）</Text>
              <Text style={localStyles.heroValue}>{pct(openBooked, openCapacity)}</Text>
            </View>
            <Text style={localStyles.heroSide}>
              {openBooked} / {openCapacity} 組
            </Text>
          </View>
          <Meter value={openBooked} total={openCapacity} label={`已預約 ${openBooked} 組，開放名額 ${openCapacity} 組`} />
          <Text style={[localStyles.summary, { marginTop: 8 }]}>
            {SERVICE_LABEL[batch.service_type]}｜{batch.day_count} 天｜{batch.open_slot_count}/{batch.slot_count} 個時段開放｜已預約 {batch.booked_count} 組
          </Text>
          {!batch.is_active && <Text style={[localStyles.summary, { color: colors.danger }]}>此設定已停用，客戶看不到</Text>}
          {editable && <Text style={localStyles.hint}>點時段可關閉 / 開放或調整名額；灰色為已關閉。</Text>}
        </Card>
        {error && <Message kind="error" text={error} />}
        {excel.status}
        {canSeeBookings && (
          <ListRow
            title="📨 寄送邀請／預約名單"
            subtitle="寄邀請信給住戶、查看誰預約了哪個時段"
            right={`${batch.booked_count} 戶已預約`}
            onPress={() => router.push({ pathname: '/batch/[id]/invites', params: { id: String(id) } })}
          />
        )}

        {batch.days.map((day) => {
          const open = day.slots.filter((s) => s.is_open);
          const openCount = open.length;
          const dayCapacity = open.reduce((n, s) => n + s.capacity, 0);
          const dayBooked = open.reduce((n, s) => n + Math.min(s.booked, s.capacity), 0);
          return (
            <Card key={day.date}>
              <View style={localStyles.dayHeader}>
                <Text style={localStyles.dayTitle}>{dayLabel(day.date)}</Text>
                <Text style={localStyles.dayMeta}>
                  開放 {openCount}/{day.slots.length}｜已預約 {dayBooked}/{dayCapacity}
                </Text>
                {editable && (
                  <Pressable onPress={() => toggleDay(day.date, openCount === 0)} hitSlop={8}>
                    <Text style={localStyles.dayAction}>{openCount === 0 ? '整天開放' : '整天關閉'}</Text>
                  </Pressable>
                )}
              </View>
              {dayCapacity > 0 && (
                <View style={{ marginBottom: 10 }}>
                  <Meter value={dayBooked} total={dayCapacity} height={6} label={`${dayLabel(day.date)} 已預約 ${dayBooked}/${dayCapacity}`} />
                </View>
              )}
              <View style={localStyles.grid}>
                {day.slots.map((slot) => {
                  const isSelected = selected?.slotId === slot.id;
                  const full = slot.booked >= slot.capacity;
                  return (
                    <Pressable
                      key={slot.id}
                      disabled={!editable}
                      onPress={() => setSelected(isSelected ? null : { date: day.date, slotId: slot.id })}
                      style={[
                        localStyles.slot,
                        !slot.is_open && localStyles.slotClosed,
                        full && slot.is_open && localStyles.slotFull,
                        isSelected && localStyles.slotSelected,
                      ]}
                    >
                      <Text style={[localStyles.slotTime, !slot.is_open && localStyles.closedText]}>
                        {shortTime(slot.start_time)}
                      </Text>
                      <Text style={[localStyles.slotCount, !slot.is_open && localStyles.closedText]}>
                        {slot.is_open ? `${slot.booked}/${slot.capacity}` : '關閉'}
                      </Text>
                    </Pressable>
                  );
                })}
              </View>
            </Card>
          );
        })}
        <View style={{ height: selectedSlot ? 170 : 20 }} />
      </ScrollView>

      {selectedSlot && selected && (
        <View style={localStyles.panel}>
          <View style={localStyles.panelInner}>
            <Text style={localStyles.panelTitle}>
              {dayLabel(selected.date)} {shortTime(selectedSlot.start_time)}–{shortTime(selectedSlot.end_time)}
            </Text>
            <Text style={localStyles.panelMeta}>
              已預約 {selectedSlot.booked} 組／名額 {selectedSlot.capacity} 組｜{selectedSlot.is_open ? '開放中' : '已關閉'}
            </Text>
            {selectedSlot.units.length > 0 && (
              <Text style={localStyles.panelMeta}>預約戶別：{selectedSlot.units.join('、')}</Text>
            )}
            <View style={localStyles.panelButtons}>
              <PanelButton
                label={selectedSlot.is_open ? '關閉時段' : '開放時段'}
                onPress={() => updateSlot(selectedSlot, { is_open: !selectedSlot.is_open })}
                danger={selectedSlot.is_open}
              />
              <PanelButton
                label="名額 －"
                disabled={selectedSlot.capacity <= Math.max(1, selectedSlot.booked)}
                onPress={() => updateSlot(selectedSlot, { capacity: selectedSlot.capacity - 1 })}
              />
              <PanelButton label="名額 ＋" onPress={() => updateSlot(selectedSlot, { capacity: selectedSlot.capacity + 1 })} />
            </View>
          </View>
        </View>
      )}

      <ActionSheet
        visible={menu}
        title={batch.name}
        onClose={() => setMenu(false)}
        options={[
          {
            label: '預約設定（說明、開放與截止時間）',
            onPress: () => router.push({ pathname: '/batch/[id]/settings', params: { id: String(id) } }),
          },
          {
            label: '追加日期',
            onPress: () =>
              router.push({
                pathname: '/project/[id]/batch-new',
                params: { id: String(batch.project_id), batchId: String(batch.id) },
              }),
          },
          { label: '修改名稱', onPress: () => setRenaming(true) },
          ...excel.options,
          {
            label: batch.is_active ? '停用（客戶看不到）' : '重新啟用',
            onPress: () => run(async () => {
              await api.updateBatch(id, { is_active: !batch.is_active });
              await reload();
            }),
          },
          { label: '刪除', destructive: true, onPress: removeBatch },
        ]}
      />
      <PromptModal
        visible={renaming}
        title="修改名稱"
        initialValue={batch.name}
        onCancel={() => setRenaming(false)}
        onConfirm={(name) => {
          setRenaming(false);
          void run(async () => {
            await api.updateBatch(id, { name });
            await reload();
          });
        }}
      />
    </View>
  );
}

function findSlot(b: BatchDetail, slotId: number): Slot | undefined {
  for (const d of b.days) {
    const s = d.slots.find((x) => x.id === slotId);
    if (s) return s;
  }
  return undefined;
}

function PanelButton(props: { label: string; onPress: () => void; disabled?: boolean; danger?: boolean }) {
  return (
    <Pressable
      onPress={props.onPress}
      disabled={props.disabled}
      style={({ pressed }) => [
        localStyles.panelButton,
        props.danger && { borderColor: colors.danger },
        (pressed || props.disabled) && { opacity: 0.5 },
      ]}
    >
      <Text style={[localStyles.panelButtonText, props.danger && { color: colors.danger }]}>{props.label}</Text>
    </Pressable>
  );
}

const localStyles = StyleSheet.create({
  flex: { flex: 1 },
  content: { padding: 16, gap: 10, width: '100%', maxWidth: MAX_WIDTH, alignSelf: 'center' },
  summary: { fontSize: 15, color: colors.text },
  heroRow: { flexDirection: 'row', alignItems: 'flex-end', marginBottom: 8 },
  heroLabel: { fontSize: 13, color: colors.muted },
  heroValue: { fontSize: 34, fontWeight: '700', color: colors.text, lineHeight: 40 },
  heroSide: { fontSize: 14, color: colors.textSecondary, marginBottom: 6 },
  hint: { fontSize: 13, color: colors.muted, marginTop: 4 },
  dayHeader: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 8 },
  dayTitle: { fontSize: 16, fontWeight: '700', color: colors.text },
  dayMeta: { flex: 1, fontSize: 13, color: colors.muted },
  dayAction: { fontSize: 14, color: colors.primary },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  slot: {
    width: 72,
    paddingVertical: 8,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: colors.accentBorder,
    backgroundColor: colors.accentBg,
    alignItems: 'center',
  },
  slotClosed: { backgroundColor: colors.subtle, borderColor: colors.border },
  slotFull: { backgroundColor: colors.warn.bg, borderColor: colors.warn.border },
  slotSelected: { borderWidth: 2, borderColor: colors.primary },
  slotTime: { fontSize: 15, fontWeight: '600', color: colors.text },
  slotCount: { fontSize: 12, color: colors.muted, marginTop: 2 },
  closedText: { color: colors.faint },
  panel: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: colors.card,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    paddingBottom: 24,
  },
  panelInner: { padding: 16, gap: 6, width: '100%', maxWidth: MAX_WIDTH, alignSelf: 'center' },
  panelTitle: { fontSize: 17, fontWeight: '700', color: colors.text },
  panelMeta: { fontSize: 14, color: colors.muted },
  panelButtons: { flexDirection: 'row', gap: 8, marginTop: 6 },
  panelButton: {
    flex: 1,
    borderWidth: 1,
    borderColor: colors.primary,
    borderRadius: 10,
    paddingVertical: 12,
    alignItems: 'center',
  },
  panelButtonText: { fontSize: 15, fontWeight: '600', color: colors.primary },
});
