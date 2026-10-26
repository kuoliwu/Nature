import { Link } from 'expo-router';
import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { Button, Card, Field, Message, Screen, colors } from '@/components/ui';
import { api } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { setTheme, THEME_OPTIONS, themeName } from '@/lib/theme';

export default function AccountScreen() {
  const { user, baseUrl, signIn, signOut, can } = useAuth();
  const [backup, setBackup] = useState<{ ok: boolean; text: string } | null>(null);
  const [backingUp, setBackingUp] = useState(false);
  const [oldPassword, setOldPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);
  const [themeNote, setThemeNote] = useState<string | null>(null);

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

      <Card title="配色">
        <View style={localStyles.segments}>
          {THEME_OPTIONS.map((o) => {
            const on = o.value === themeName;
            return (
              <Pressable
                key={o.value}
                disabled={on}
                onPress={async () => {
                  if (!(await setTheme(o.value))) setThemeNote('已儲存，請關閉 APP 再重新開啟即可套用');
                }}
                style={({ pressed }) => [localStyles.segment, on && localStyles.segmentOn, pressed && { opacity: 0.7 }]}
              >
                <Text style={[localStyles.segmentText, on && localStyles.segmentTextOn]}>{on ? `✓ ${o.label}` : o.label}</Text>
              </Pressable>
            );
          })}
        </View>
        <Text style={localStyles.hint}>只套用在這台手機或這個瀏覽器，切換後畫面會重新載入</Text>
        {themeNote && <Message kind="info" text={themeNote} />}
      </Card>

      <Card title="修改密碼">
        <Field label="目前的密碼" value={oldPassword} onChangeText={setOldPassword} secureTextEntry autoCapitalize="none" />
        <Field label="新密碼" value={newPassword} onChangeText={setNewPassword} secureTextEntry autoCapitalize="none" hint="至少 8 碼" />
        <Field label="再輸入一次新密碼" value={confirm} onChangeText={setConfirm} secureTextEntry autoCapitalize="none" />
        <Button label="更新密碼" onPress={changePassword} loading={busy} disabled={!oldPassword} />
      </Card>
      {result && <Message kind={result.ok ? 'ok' : 'error'} text={result.text} />}

      {can('user.manage') && (
        <Card title="資料備份">
          <Text style={localStyles.meta}>系統每天自動備份資料庫與照片、簽名等檔案；也可以立即備份一次。</Text>
          <Button
            label="立即備份"
            variant="outline"
            loading={backingUp}
            onPress={async () => {
              setBackingUp(true);
              try {
                const r = await api.runBackup();
                setBackup({ ok: true, text: `備份完成：資料庫已備份、複製 ${r.files_copied} 個檔案
位置：${r.backup_dir}` });
              } catch (e) {
                setBackup({ ok: false, text: e instanceof Error ? e.message : String(e) });
              } finally {
                setBackingUp(false);
              }
            }}
          />
          {backup && <Message kind={backup.ok ? 'ok' : 'error'} text={backup.text} />}
        </Card>
      )}

      <Button label="登出" variant="danger" onPress={() => void signOut()} />
    </Screen>
  );
}

const localStyles = StyleSheet.create({
  meta: { fontSize: 15, color: colors.textSecondary },
  link: { color: colors.primary, fontSize: 15, marginTop: 8 },
  hint: { fontSize: 12, color: colors.muted, marginTop: 6 },
  segments: { flexDirection: 'row', gap: 8 },
  segment: { flex: 1, borderWidth: 1, borderColor: colors.border, borderRadius: 10, paddingVertical: 12, alignItems: 'center', backgroundColor: colors.input },
  segmentOn: { borderColor: colors.primary, backgroundColor: colors.primary },
  segmentText: { fontSize: 15, fontWeight: '600', color: colors.text },
  segmentTextOn: { color: colors.onPrimary },
});
