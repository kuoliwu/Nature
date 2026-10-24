import { router, useLocalSearchParams, useNavigation } from 'expo-router';
import { useEffect, useLayoutEffect, useState } from 'react';

import { Button, Card, Field, Loading, Message, Screen, ToggleRow } from '@/components/ui';
import { api, Permission, User, UserInput } from '@/lib/api';
import { useAuth } from '@/lib/auth';

export default function UserEditScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const isNew = id === 'new';
  const navigation = useNavigation();
  const { user: me, setUser: setMe } = useAuth();

  const [catalog, setCatalog] = useState<Permission[] | null>(null);
  const [original, setOriginal] = useState<User | null>(null);
  const [name, setName] = useState('');
  const [phone, setPhone] = useState('');
  const [password, setPassword] = useState('');
  const [superAdmin, setSuperAdmin] = useState(false);
  const [active, setActive] = useState(true);
  const [perms, setPerms] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useLayoutEffect(() => {
    navigation.setOptions({ title: isNew ? '新增人員' : '編輯人員' });
  }, [navigation, isNew]);

  useEffect(() => {
    (async () => {
      try {
        const [permissions, users] = await Promise.all([api.permissions(), isNew ? null : api.users()]);
        setCatalog(permissions);
        const u = users?.find((x) => String(x.id) === id);
        if (u) {
          setOriginal(u);
          setName(u.name);
          setPhone(u.phone);
          setSuperAdmin(u.role === 'super_admin');
          setActive(u.is_active);
          setPerms(new Set(u.role === 'super_admin' ? [] : u.permissions));
        } else if (!isNew) {
          setError('找不到此人員');
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    })();
  }, [id, isNew]);

  if (!catalog) return error ? <Screen><Message kind="error" text={error} /></Screen> : <Loading />;

  const isSelf = original?.id === me?.id;

  function togglePerm(code: string, on: boolean) {
    setPerms((prev) => {
      const next = new Set(prev);
      if (on) next.add(code);
      else next.delete(code);
      return next;
    });
  }

  async function save() {
    if (!name.trim() || !phone.trim()) return setError('請輸入姓名與手機號碼');
    if ((isNew || password) && password.length < 8) return setError('密碼至少 8 碼');

    const body: UserInput = {
      name: name.trim(),
      phone: phone.trim(),
      role: superAdmin ? 'super_admin' : 'staff',
      permissions: superAdmin ? [] : [...perms],
      ...(isNew ? {} : { is_active: active }),
      ...(password ? { password } : {}),
    };
    setBusy(true);
    setError(null);
    try {
      const saved = isNew ? await api.createUser(body) : await api.updateUser(Number(id), body);
      if (isSelf) setMe(saved);
      router.back();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Screen>
      <Card title="基本資料">
        <Field label="姓名" value={name} onChangeText={setName} />
        <Field label="手機號碼（登入帳號）" value={phone} onChangeText={setPhone} keyboardType="phone-pad" />
        <Field
          label={isNew ? '密碼' : '重設密碼'}
          value={password}
          onChangeText={setPassword}
          secureTextEntry
          autoCapitalize="none"
          placeholder={isNew ? '' : '不修改請留空'}
          hint={isNew ? '至少 8 碼，請告知本人登入後自行修改' : '重設後此人員需要用新密碼重新登入'}
        />
      </Card>

      <Card title="身分">
        <ToggleRow
          label="最高管理者"
          description="擁有所有權限，包含人員管理"
          value={superAdmin}
          onValueChange={setSuperAdmin}
          disabled={isSelf}
        />
        {!isNew && (
          <ToggleRow
            label="帳號啟用"
            description="停用後無法登入，已登入的裝置也會被登出"
            value={active}
            onValueChange={setActive}
            disabled={isSelf}
          />
        )}
      </Card>

      <Card title="權限">
        {catalog.map((p) => (
          <ToggleRow
            key={p.code}
            label={p.label}
            value={superAdmin || perms.has(p.code)}
            onValueChange={(on) => togglePerm(p.code, on)}
            disabled={superAdmin}
          />
        ))}
      </Card>

      {error && <Message kind="error" text={error} />}
      <Button label={isNew ? '建立人員' : '儲存'} onPress={save} loading={busy} />
    </Screen>
  );
}
