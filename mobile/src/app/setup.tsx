import { Link } from 'expo-router';
import { useState } from 'react';
import { StyleSheet } from 'react-native';

import { Button, Card, Field, Message, Screen, colors } from '@/components/ui';
import { api } from '@/lib/api';
import { useAuth } from '@/lib/auth';

export default function SetupScreen() {
  const { server, signIn } = useAuth();
  const [name, setName] = useState('');
  const [phone, setPhone] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    if (!name.trim() || !phone.trim()) return setError('請輸入姓名與手機號碼');
    if (password.length < 8) return setError('密碼至少 8 碼');
    if (password !== confirm) return setError('兩次輸入的密碼不一致');
    if (!server.adminKey) return setError('請先到主機設定填寫管理金鑰');

    setBusy(true);
    setError(null);
    try {
      await signIn(await api.setup(server.adminKey, { name: name.trim(), phone: phone.trim(), password }));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Screen>
      <Message kind="info" text="這個帳號會成為最高管理者，擁有所有權限，之後可以再新增其他人員。" />
      <Card>
        <Field label="姓名" value={name} onChangeText={setName} />
        <Field label="手機號碼（登入帳號）" value={phone} onChangeText={setPhone} keyboardType="phone-pad" />
        <Field label="密碼" value={password} onChangeText={setPassword} secureTextEntry autoCapitalize="none" hint="至少 8 碼" />
        <Field label="再輸入一次密碼" value={confirm} onChangeText={setConfirm} secureTextEntry autoCapitalize="none" />
      </Card>
      {!server.adminKey && (
        <Message kind="error" text="尚未設定管理金鑰">
          <Link href="/connect" style={localStyles.link}>
            前往主機設定 →
          </Link>
        </Message>
      )}
      <Button label="建立並登入" onPress={submit} loading={busy} />
      {error && <Message kind="error" text={error} />}
    </Screen>
  );
}

const localStyles = StyleSheet.create({
  link: { color: colors.primary, fontSize: 15, marginTop: 6 },
});
