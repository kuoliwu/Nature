import { router, useLocalSearchParams, useNavigation } from 'expo-router';
import { useEffect, useLayoutEffect, useState } from 'react';

import { Button, Card, Field, Loading, Message, Screen } from '@/components/ui';
import { api, ProjectInput } from '@/lib/api';
import { confirm, errorText } from '@/lib/dialogs';

/** 新增（id = new）與編輯共用 */
export default function ProjectEditScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const isNew = id === 'new';
  const navigation = useNavigation();
  const [form, setForm] = useState<ProjectInput | null>(isNew ? { name: '' } : null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useLayoutEffect(() => {
    navigation.setOptions({ title: isNew ? '新增建案' : '編輯建案' });
  }, [navigation, isNew]);

  useEffect(() => {
    if (!isNew) api.project(Number(id)).then(setForm, (e) => setError(errorText(e)));
  }, [id, isNew]);

  if (!form) return error ? <Message kind="error" text={error} /> : <Loading />;

  const set = (key: keyof ProjectInput) => (value: string) => setForm({ ...form, [key]: value });
  const clean = (v?: string | null) => (v?.trim() ? v.trim() : null);

  async function save() {
    if (!form?.name.trim()) return setError('請輸入案名');
    const body: ProjectInput = {
      name: form.name.trim(),
      phone: clean(form.phone),
      address: clean(form.address),
      community_manager: clean(form.community_manager),
      note: clean(form.note),
    };
    setBusy(true);
    setError(null);
    try {
      if (isNew) {
        const created = await api.createProject(body);
        router.replace({ pathname: '/project/[id]', params: { id: String(created.id) } });
      } else {
        await api.updateProject(Number(id), body);
        router.back();
      }
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!(await confirm('刪除建案', `確定要刪除「${form?.name}」？\n住戶、健檢日期、檢查項目會一併刪除，無法復原。`, '刪除', true))) return;
    try {
      await api.deleteProject(Number(id));
      router.dismissTo('/service'); // 回到售服部的建案列表
    } catch (e) {
      setError(errorText(e));
    }
  }

  return (
    <Screen>
      <Card>
        <Field label="案名 *" value={form.name} onChangeText={set('name')} />
        <Field label="建案電話" value={form.phone ?? ''} onChangeText={set('phone')} keyboardType="phone-pad" />
        <Field label="建案地址" value={form.address ?? ''} onChangeText={set('address')} />
        <Field label="社區經理" value={form.community_manager ?? ''} onChangeText={set('community_manager')} />
        <Field label="備註" value={form.note ?? ''} onChangeText={set('note')} multiline style={{ minHeight: 80 }} />
      </Card>
      {isNew && <Message kind="info" text="建立後會自動帶入公司預設的檢查項目（窗戶、水電、其他），之後可以針對此建案修改。" />}
      {error && <Message kind="error" text={error} />}
      <Button label={isNew ? '建立建案' : '儲存'} onPress={save} loading={busy} />
      {!isNew && <Button label="刪除建案" variant="danger" onPress={remove} />}
    </Screen>
  );
}
