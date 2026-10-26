import { router, useLocalSearchParams, useNavigation } from 'expo-router';
import { useLayoutEffect, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { DateTimeField } from '@/components/pickers';
import { Button, Card, Field, Message, Screen, colors, styles as ui } from '@/components/ui';
import { api, ServiceType } from '@/lib/api';
import { daysBetween, parseDate, slotsPerDay, TimeRange, toDateString } from '@/lib/dates';
import { errorText } from '@/lib/dialogs';
import { PHASES, SERVICE_LABEL } from '@/lib/labels';

/**
 * 新增健檢日期（params.batchId 有值時改為「追加日期」到既有設定）
 */
export default function BatchNewScreen() {
  const params = useLocalSearchParams<{ id: string; batchId?: string; service?: ServiceType }>();
  const projectId = Number(params.id);
  const addingTo = params.batchId ? Number(params.batchId) : null;
  const navigation = useNavigation();

  const today = toDateString(new Date());
  const fixed = PHASES.find((p) => p.service === params.service); // 從某個階段進來時類型固定
  const [service, setService] = useState<ServiceType>(fixed?.service ?? 'health_check');
  const [name, setName] = useState<string>(fixed?.defaultName ?? '保固健檢');
  const [startDate, setStartDate] = useState<string | null>(today);
  const [endDate, setEndDate] = useState<string | null>(today);
  const [dayStart, setDayStart] = useState<string | null>('09:00');
  const [dayEnd, setDayEnd] = useState<string | null>('17:00');
  const [capacity, setCapacity] = useState(3);
  const [breaks, setBreaks] = useState<TimeRange[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useLayoutEffect(() => {
    navigation.setOptions({ title: addingTo ? '追加日期' : `新增${SERVICE_LABEL[service]}日期` });
  }, [navigation, addingTo, service]);

  const days = startDate && endDate ? daysBetween(parseDate(startDate), parseDate(endDate)) : 0;
  const perDay = dayStart && dayEnd ? slotsPerDay(dayStart, dayEnd, breaks) : 0;

  const updateBreak = (index: number, patch: Partial<TimeRange>) =>
    setBreaks((list) => list.map((b, i) => (i === index ? { ...b, ...patch } : b)));

  function addBreak() {
    // 第一組預設午休；之後的接在上一組後面
    const last = breaks[breaks.length - 1];
    const next = last ? addHour(last.end) : null;
    setBreaks([...breaks, last && next ? { start: last.end, end: next } : { start: '12:00', end: '13:00' }]);
  }

  async function save() {
    if (!startDate || !endDate || !dayStart || !dayEnd) return setError('請選擇日期與時間');
    if (days < 1) return setError('結束日期不能早於開始日期');
    const badBreak = breaks.find((b) => b.end <= b.start);
    if (badBreak) return setError(`屏蔽區段 ${badBreak.start}–${badBreak.end} 的結束時間必須晚於開始時間`);
    if (perDay < 1) return setError('扣除屏蔽區段後沒有任何時段，請調整時間');
    if (!addingTo && !name.trim()) return setError('請輸入名稱');

    setBusy(true);
    setError(null);
    try {
      const range = { start_date: startDate, end_date: endDate, day_start: dayStart, day_end: dayEnd, breaks };
      const batch = addingTo
        ? await api.addBatchDates(addingTo, range)
        : await api.createBatch(projectId, { ...range, name: name.trim(), service_type: service, slot_capacity: capacity });
      router.replace({ pathname: '/batch/[id]', params: { id: String(batch.id) } });
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Screen>
      {!addingTo && (
        <Card>
          <Field label="名稱" value={name} onChangeText={setName} placeholder="例：預約參觀、交屋驗屋、一年保固健檢" />
          {!fixed && (
            <>
              <Text style={ui.label}>類型</Text>
              <View style={localStyles.chips}>
                {PHASES.map((p) => (
                  <Pressable
                    key={p.service}
                    onPress={() => {
                      setService(p.service);
                      setName(p.defaultName);
                    }}
                    style={[localStyles.chip, service === p.service && localStyles.chipOn]}
                  >
                    <Text style={[localStyles.chipText, service === p.service && localStyles.chipTextOn]}>{SERVICE_LABEL[p.service]}</Text>
                  </Pressable>
                ))}
              </View>
            </>
          )}
        </Card>
      )}

      <Card title="日期區間">
        <DateTimeField label="開始日期" mode="date" value={startDate} onChange={setStartDate} />
        <DateTimeField label="結束日期" mode="date" value={endDate} onChange={setEndDate} />
      </Card>

      <Card title="每天的時段">
        <DateTimeField label="第一個時段開始" mode="time" minuteStep={30} value={dayStart} onChange={setDayStart} />
        <DateTimeField label="最後一個時段結束" mode="time" minuteStep={30} value={dayEnd} onChange={setDayEnd} />
        <Text style={ui.hint}>以 30 分鐘為一個時段。</Text>
      </Card>

      <Card title="每天的屏蔽區段（不開放預約）">
        {breaks.map((b, i) => (
          <View key={i} style={localStyles.breakRow}>
            <View style={localStyles.breakField}>
              <DateTimeField label={`第 ${i + 1} 組 開始`} mode="time" minuteStep={30} value={b.start} onChange={(v) => v && updateBreak(i, { start: v })} />
            </View>
            <View style={localStyles.breakField}>
              <DateTimeField label="結束" mode="time" minuteStep={30} value={b.end} onChange={(v) => v && updateBreak(i, { end: v })} />
            </View>
            <Pressable onPress={() => setBreaks(breaks.filter((_, j) => j !== i))} hitSlop={10} style={localStyles.removeBreak}>
              <Text style={localStyles.removeText}>✕</Text>
            </Pressable>
          </View>
        ))}
        <Pressable onPress={addBreak} style={localStyles.addBreak}>
          <Text style={localStyles.addBreakText}>＋ 新增屏蔽區段</Text>
        </Pressable>
        <Text style={ui.hint}>例如午休 12:00–13:00；與屏蔽區段重疊的時段不會產生。產生後也可以再個別關閉時段。</Text>
      </Card>

      {!addingTo && (
        <Card title="每個時段的名額">
          <View style={localStyles.stepper}>
            <Pressable style={localStyles.stepButton} onPress={() => setCapacity((c) => Math.max(1, c - 1))}>
              <Text style={localStyles.stepText}>－</Text>
            </Pressable>
            <Text style={localStyles.capacity}>{capacity} 組</Text>
            <Pressable style={localStyles.stepButton} onPress={() => setCapacity((c) => Math.min(50, c + 1))}>
              <Text style={localStyles.stepText}>＋</Text>
            </Pressable>
          </View>
          <Text style={ui.hint}>同一時段最多可讓幾組客戶勾選（預設 3 組）</Text>
        </Card>
      )}

      {days > 0 && perDay > 0 && (
        <Message kind="info" text={`將產生 ${days} 天 × 每天 ${perDay} 個時段 = ${days * perDay} 個時段`} />
      )}
      {error && <Message kind="error" text={error} />}
      <Button label={addingTo ? '追加日期' : '產生時段'} onPress={save} loading={busy} />
    </Screen>
  );
}

function addHour(time: string): string | null {
  const [h, m] = time.split(':').map(Number);
  return h >= 23 ? null : `${String(h + 1).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
}

const localStyles = StyleSheet.create({
  breakRow: { flexDirection: 'row', alignItems: 'flex-end', gap: 8 },
  breakField: { flex: 1 },
  removeBreak: { paddingBottom: 22, paddingHorizontal: 6 },
  removeText: { fontSize: 18, color: colors.danger },
  addBreak: {
    borderWidth: 1,
    borderStyle: 'dashed',
    borderColor: colors.primary,
    borderRadius: 10,
    paddingVertical: 12,
    alignItems: 'center',
    marginTop: 4,
  },
  addBreakText: { fontSize: 15, color: colors.primary, fontWeight: '600' },
  chips: { flexDirection: 'row', gap: 8 },
  chip: { borderWidth: 1, borderColor: colors.border, borderRadius: 999, paddingHorizontal: 18, paddingVertical: 8 },
  chipOn: { backgroundColor: colors.primary, borderColor: colors.primary },
  chipText: { fontSize: 15, color: colors.text },
  chipTextOn: { color: colors.onPrimary, fontWeight: '600' },
  stepper: { flexDirection: 'row', alignItems: 'center', gap: 16 },
  stepButton: {
    width: 44,
    height: 44,
    borderRadius: 22,
    borderWidth: 1,
    borderColor: colors.border,
    alignItems: 'center',
    justifyContent: 'center',
  },
  stepText: { fontSize: 22, color: colors.primary },
  capacity: { fontSize: 20, fontWeight: '700', minWidth: 60, textAlign: 'center', color: colors.text },
});
