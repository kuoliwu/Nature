import { Link, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { StyleSheet, Text } from 'react-native';

import { Button, Card, Field, Message, Screen, colors } from '@/components/ui';
import { api, HealthOut } from '@/lib/api';
import { useAuth } from '@/lib/auth';

export default function LoginScreen() {
  const { baseUrl, signIn } = useAuth();
  const [phone, setPhone] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [health, setHealth] = useState<HealthOut | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);

  // 每次回到此頁（例如從主機設定回來）都重新檢查主機狀態
  useFocusEffect(
    useCallback(() => {
      setHealth(null);
      setHealthError(null);
      if (!baseUrl) return;
      api.health().then(setHealth, (e: Error) => setHealthError(e.message));
    }, [baseUrl]),
  );

  async function submit() {
    if (!phone.trim() || !password) {
      setError('請輸入手機號碼與密碼');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await signIn(await api.login(phone.trim(), password));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Screen>
      <Text style={localStyles.title}>驗屋與健檢預約管理</Text>

      <Card>
        <Text style={localStyles.server}>主機：{baseUrl ?? '尚未設定'}</Text>
        <Link href="/connect" style={localStyles.link}>
          變更主機設定
        </Link>
      </Card>

      {!baseUrl && <Message kind="info" text="請先設定主機位址" />}
      {healthError && <Message kind="error" text={healthError} />}
      {health && !health.db_initialized && (
        <Message kind="info" text="資料庫尚未建立：請到「變更主機設定」按「初始化資料庫」" />
      )}
      {health?.db_initialized && health.needs_setup && (
        <Message kind="info" text="還沒有任何管理者帳號">
          <Link href="/setup" style={localStyles.link}>
            建立第一位管理者 →
          </Link>
        </Message>
      )}

      <Card>
        <Field
          label="手機號碼"
          value={phone}
          onChangeText={setPhone}
          placeholder="0912345678"
          keyboardType="phone-pad"
          autoComplete="tel"
          textContentType="telephoneNumber"
        />
        <Field
          label="密碼"
          value={password}
          onChangeText={setPassword}
          secureTextEntry
          autoCapitalize="none"
          textContentType="password"
          returnKeyType="go"
          onSubmitEditing={submit}
        />
      </Card>

      <Button label="登入" onPress={submit} loading={busy} disabled={!baseUrl} />
      {error && <Message kind="error" text={error} />}
    </Screen>
  );
}

const localStyles = StyleSheet.create({
  title: { fontSize: 22, fontWeight: '700', textAlign: 'center', marginVertical: 12, color: colors.text },
  server: { fontSize: 14, color: colors.muted },
  link: { color: colors.primary, fontSize: 15, marginTop: 6 },
});
