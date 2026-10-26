import { router, useLocalSearchParams, useNavigation } from 'expo-router';
import { useEffect, useLayoutEffect, useState } from 'react';

import { DateTimeField } from '@/components/pickers';
import { Button, Card, Field, Loading, Message, Screen } from '@/components/ui';
import { api, UnitInput } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { confirm, errorText } from '@/lib/dialogs';

type Form = Omit<UnitInput, 'area_ping'> & { area_ping: string };

const EMPTY: Form = {
  unit_no: '', building: '', floor: '', address: '', owner_name: '', owner_phone: '', owner_email: '',
  area_ping: '', handover_date: null, note: '',
};

export default function UnitEditScreen() {
  const params = useLocalSearchParams<{ id: string; unitId: string }>();
  const projectId = Number(params.id);
  const isNew = params.unitId === 'new';
  const { can } = useAuth();
  const editable = can('project.manage');
  const navigation = useNavigation();
  const [form, setForm] = useState<Form | null>(isNew ? EMPTY : null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useLayoutEffect(() => {
    navigation.setOptions({ title: isNew ? '新增住戶' : form?.unit_no || '住戶資料' });
  }, [navigation, isNew, form?.unit_no]);

  useEffect(() => {
    if (isNew) return;
    api.unit(Number(params.unitId)).then(
      (u) => setForm({ ...u, area_ping: u.area_ping == null ? '' : String(u.area_ping) }),
      (e) => setError(errorText(e)),
    );
  }, [params.unitId, isNew]);

  if (!form) return error ? <Message kind="error" text={error} /> : <Loading />;

  const set = (key: keyof Form) => (value: string) => setForm({ ...form, [key]: value });
  const clean = (v?: string | null) => (v?.trim() ? v.trim() : null);

  async function save() {
    if (!form) return;
    if (!form.unit_no.trim()) return setError('請輸入戶別');
    const area = form.area_ping.trim() ? Number(form.area_ping) : null;
    if (area !== null && (Number.isNaN(area) || area < 0)) return setError('坪數請輸入數字');

    const body: UnitInput = {
      unit_no: form.unit_no.trim(),
      building: clean(form.building),
      floor: clean(form.floor),
      address: clean(form.address),
      owner_name: clean(form.owner_name),
      owner_phone: clean(form.owner_phone),
      owner_email: clean(form.owner_email),
      area_ping: area,
      handover_date: form.handover_date ?? null,
      note: clean(form.note),
    };
    setBusy(true);
    setError(null);
    try {
      if (isNew) await api.createUnit(projectId, body);
      else await api.updateUnit(Number(params.unitId), body);
      router.back();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!(await confirm('刪除住戶', `確定要刪除「${form?.unit_no}」？`, '刪除', true))) return;
    try {
      await api.deleteUnit(Number(params.unitId));
      router.back();
    } catch (e) {
      setError(errorText(e));
    }
  }

  return (
    <Screen>
      <Card title="住家資訊">
        <Field label="戶別 *" value={form.unit_no} onChangeText={set('unit_no')} placeholder="例：A-5F-1" editable={editable} />
        <Field label="棟別" value={form.building ?? ''} onChangeText={set('building')} placeholder="例：A" editable={editable} />
        <Field label="樓層" value={form.floor ?? ''} onChangeText={set('floor')} placeholder="例：5F" editable={editable} />
        <Field label="住家地址" value={form.address ?? ''} onChangeText={set('address')} editable={editable} />
        <Field label="坪數" value={form.area_ping} onChangeText={set('area_ping')} keyboardType="decimal-pad" placeholder="例：35.5" editable={editable} />
        {editable ? (
          <DateTimeField
            label="交屋日期"
            mode="date"
            value={form.handover_date ?? null}
            onChange={(v) => setForm({ ...form, handover_date: v })}
            clearable
          />
        ) : (
          <Field label="交屋日期" value={form.handover_date ?? ''} editable={false} />
        )}
      </Card>

      <Card title="屋主">
        <Field label="姓名" value={form.owner_name ?? ''} onChangeText={set('owner_name')} editable={editable} />
        <Field label="電話" value={form.owner_phone ?? ''} onChangeText={set('owner_phone')} keyboardType="phone-pad" editable={editable} />
        <Field
          label="Email"
          value={form.owner_email ?? ''}
          onChangeText={set('owner_email')}
          keyboardType="email-address"
          autoCapitalize="none"
          hint="預約參觀／驗屋／健檢的邀請會寄到這個信箱"
          editable={editable}
        />
      </Card>

      <Card>
        <Field label="備註" value={form.note ?? ''} onChangeText={set('note')} multiline style={{ minHeight: 80 }} editable={editable} />
      </Card>

      {error && <Message kind="error" text={error} />}
      {editable && <Button label={isNew ? '新增住戶' : '儲存'} onPress={save} loading={busy} />}
      {editable && !isNew && <Button label="刪除住戶" variant="danger" onPress={remove} />}
    </Screen>
  );
}
