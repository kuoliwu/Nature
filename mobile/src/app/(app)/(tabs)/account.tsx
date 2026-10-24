import { Link } from 'expo-router';
import { useState } from 'react';
import { StyleSheet, Text } from 'react-native';

import { Button, Card, Field, Message, Screen, colors } from '@/components/ui';
import { api } from '@/lib/api';
import { useAuth } from '@/lib/auth';

export default function AccountScreen() {
  const { user, baseUrl, signIn, signOut } = useAuth();
  const [oldPassword, setOldPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);

  if (!user) return null;

  async function changePassword() {
    if (newPassword.length < 8) return setResult({ ok: false, text: '新密碼至少 8 碼' });
    if (newPassword !== confirm) return setResult({ ok: false, text: '兩次輸入的新密碼不一致' });
    setBusy(true);
    try {
      // 改密碼後舊憑證會失效，改用回傳的新憑證
      await signIn(await api.changePassword(oldPassword, newPassword));
      setOldPassword('');
      setNewPassword('');
      setConfirm('');
      setResult({ ok: true, text: '密碼已更新，其他裝置需要重新登入' });
    } catch (e) {
      setResult({ ok: false, text: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Screen>
      <Card title={user.name}>
        <Text style={localStyles.meta}>手機：{user.phone}</Text>
        <Text style={localStyles.meta}>身分：{user.role === 'super_admin' ? '最高管理者' : '一般人員'}</Text>
        <Text style={localStyles.meta}>主機：{baseUrl}</Text>
        <Link href="/connect" style={localStyles.link}>
          主機連線設定
        </Link>
      </Card>

      <Card title="修改密碼">
        <Field label="目前的密碼" value={oldPassword} onChangeText={setOldPassword} secureTextEntry autoCapitalize="none" />
        <Field label="新密碼" value={newPassword} onChangeText={setNewPassword} secureTextEntry autoCapitalize="none" hint="至少 8 碼" />
        <Field label="再輸入一次新密碼" value={confirm} onChangeText={setConfirm} secureTextEntry autoCapitalize="none" />
        <Button label="更新密碼" onPress={changePassword} loading={busy} disabled={!oldPassword} />
      </Card>
      {result && <Message kind={result.ok ? 'ok' : 'error'} text={result.text} />}

      <Button label="登出" variant="danger" onPress={() => void signOut()} />
    </Screen>
  );
}

const localStyles = StyleSheet.create({
  meta: { fontSize: 15, color: '#374151' },
  link: { color: colors.primary, fontSize: 15, marginTop: 8 },
});
