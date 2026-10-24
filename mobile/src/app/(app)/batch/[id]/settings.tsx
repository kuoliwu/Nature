import { router, useLocalSearchParams, useNavigation } from 'expo-router';
import { useEffect, useLayoutEffect, useState } from 'react';
import { Text } from 'react-native';

import { DateTimeField } from '@/components/pickers';
import { Button, Card, Field, Loading, Message, Screen, styles as ui } from '@/components/ui';
import { api } from '@/lib/api';
import { errorText } from '@/lib/dialogs';

type Moment = { date: string | null; time: string | null };

/** "2026-12-01T09:00:00" ⇄ { date, time } */
const split = (iso: string | null): Moment => (iso ? { date: iso.slice(0, 10), time: iso.slice(11, 16) } : { date: null, time: null });
const join = (m: Moment, defaultTime: string): string | null => (m.date ? `${m.date}T${m.time ?? defaultTime}:00` : null);

export default function BatchSettingsScreen() {
  const id = Number(useLocalSearchParams<{ id: string }>().id);
  const navigation = useNavigation();
  const [description, setDescription] = useState<string | null>(null);
  const [openAt, setOpenAt] = useState<Moment>({ date: null, time: null });
  const [closeAt, setCloseAt] = useState<Moment>({ date: null, time: null });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useLayoutEffect(() => {
    navigation.setOptions({ title: '預約設定' });
  }, [navigation]);

  useEffect(() => {
    api.batch(id).then(
      (b) => {
        setDescription(b.description ?? '');
        setOpenAt(split(b.booking_open_at));
        setCloseAt(split(b.booking_close_at));
      },
      (e) => setError(errorText(e)),
    );
  }, [id]);

  if (description === null) return error ? <Message kind="error" text={error} /> : <Loading />;

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await api.updateBatchSettings(id, {
        description: description?.trim() || null,
        booking_open_at: join(openAt, '00:00'),
        booking_close_at: join(closeAt, '23:59'),
      });
      router.back();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Screen>
      <Card>
        <Field
          label="預約說明"
          value={description}
          onChangeText={setDescription}
          multiline
          style={{ minHeight: 120 }}
          placeholder={'例如：\n請由屋主或代理人到場，健檢約 30 分鐘。\n請攜帶交屋通知書。'}
        />
        <Text style={ui.hint}>會顯示在邀請信與屋主的預約網頁上</Text>
      </Card>

      <Card title="開放預約時間">
        <DateTimeField label="日期" mode="date" value={openAt.date} onChange={(d) => setOpenAt({ ...openAt, date: d })} clearable />
        {openAt.date && (
          <DateTimeField label="時間" mode="time" value={openAt.time ?? '00:00'} onChange={(t) => setOpenAt({ ...openAt, time: t })} />
        )}
        <Text style={ui.hint}>留空代表立即開放</Text>
      </Card>

      <Card title="預約截止時間">
        <DateTimeField label="日期" mode="date" value={closeAt.date} onChange={(d) => setCloseAt({ ...closeAt, date: d })} clearable />
        {closeAt.date && (
          <DateTimeField label="時間" mode="time" value={closeAt.time ?? '23:59'} onChange={(t) => setCloseAt({ ...closeAt, time: t })} />
        )}
        <Text style={ui.hint}>留空代表不限；截止後屋主只能查看，不能再預約或改期</Text>
      </Card>

      {error && <Message kind="error" text={error} />}
      <Button label="儲存" onPress={save} loading={busy} />
    </Screen>
  );
}
