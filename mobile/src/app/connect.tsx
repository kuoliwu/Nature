import Constants from 'expo-constants';
import { useState } from 'react';
import { Alert, Platform, StyleSheet, Text, View } from 'react-native';

import { Button, Card, Field, Message, Screen, colors } from '@/components/ui';
import { api } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { normalizeBaseUrl, suggestHostFromDevServer } from '@/lib/url';

type Action = 'health' | 'init' | 'status';

type Result = {
  ok: boolean;
  title: string;
  lines?: string[];
  tables?: { table: string; rows: number }[];
};

function confirm(title: string, message: string): Promise<boolean> {
  if (Platform.OS === 'web') return Promise.resolve(window.confirm(`${title}\n\n${message}`));
  return new Promise((resolve) =>
    Alert.alert(title, message, [
      { text: '取消', style: 'cancel', onPress: () => resolve(false) },
      { text: '確定', onPress: () => resolve(true) },
    ]),
  );
}

export default function ConnectScreen() {
  const { server, updateServer } = useAuth();
  // 尚未設定時，預先帶入開發伺服器所在電腦的 IP（用 Expo Go 開啟時才有）
  const [host, setHost] = useState(server.host || suggestHostFromDevServer(Constants.expoConfig?.hostUri) || '');
  const [adminKey, setAdminKey] = useState(server.adminKey);
  const [showKey, setShowKey] = useState(false);
  const [busy, setBusy] = useState<Action | null>(null);
  const [result, setResult] = useState<Result | null>(null);

  const baseUrl = normalizeBaseUrl(host);

  async function run(action: Action) {
    if (!host.trim()) {
      setResult({ ok: false, title: '請先填寫「主機位址」', lines: ['在最上面的欄位輸入，例如：192.168.68.109:8000'] });
      return;
    }
    if (!baseUrl) {
      setResult({
        ok: false,
        title: '主機位址格式不正確',
        lines: [`目前輸入：「${host}」`, '正確範例：192.168.68.109:8000'],
      });
      return;
    }
    if (action !== 'health' && !adminKey.trim()) {
      setResult({ ok: false, title: '請輸入管理金鑰', lines: ['即 backend/.env 的 ADMIN_INIT_KEY'] });
      return;
    }
    if (
      action === 'init' &&
      !(await confirm('初始化資料庫', '將建立所有資料表並寫入預設檢查項目。\n已存在的資料不會被刪除。'))
    ) {
      return;
    }

    const key = adminKey.trim();
    setBusy(action);
    setResult(null);
    try {
      await updateServer({ host: host.trim(), adminKey: key });

      if (action === 'health') {
        const h = await api.health(baseUrl);
        setResult({
          ok: true,
          title: '連線成功',
          lines: [
            h.app,
            `主機時間：${h.server_time.replace('T', ' ').slice(0, 19)}`,
            `資料庫：${h.db_initialized ? '已初始化' : '尚未初始化，請按「初始化資料庫」'}`,
            ...(h.needs_setup ? ['尚未建立管理者帳號：回到登入頁按「建立第一位管理者」'] : []),
          ],
        });
      } else if (action === 'init') {
        const r = await api.initDb(key, baseUrl);
        const seeded = r.seeded
          ? `新增檢查項目：${r.seeded.categories} 類 / ${r.seeded.items} 項 / ${r.seeded.check_points} 個檢查點`
          : null;
        setResult({
          ok: true,
          title: r.message,
          lines: [`資料表：${r.tables.length} 張`, ...(seeded ? [seeded] : [])],
        });
      } else {
        const s = await api.dbStatus(key, baseUrl);
        setResult({
          ok: true,
          title: s.db_initialized ? '資料庫狀態' : '資料庫尚未初始化',
          lines: [s.database],
          tables: s.tables,
        });
      }
    } catch (e) {
      setResult({ ok: false, title: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy(null);
    }
  }

  return (
    <Screen>
      <Card>
        <Field
          label="主機位址"
          value={host}
          onChangeText={setHost}
          placeholder="例：192.168.68.109:8000"
          autoCapitalize="none"
          keyboardType="url"
          hint={
            host.trim() ? (baseUrl ? `將連線到 ${baseUrl}` : '格式不正確') : '輸入 run.py 印出的 IP；未填 port 時預設 8000'
          }
        />
        <Field
          label="管理金鑰（系統設定用）"
          value={adminKey}
          onChangeText={setAdminKey}
          placeholder="backend/.env 的 ADMIN_INIT_KEY"
          autoCapitalize="none"
          secureTextEntry={!showKey}
          hint="只有初始化資料庫、建立第一位管理者時需要；一般操作使用帳號登入"
        />
        <Text style={localStyles.link} onPress={() => setShowKey((v) => !v)}>
          {showKey ? '隱藏金鑰' : '顯示金鑰'}
        </Text>
      </Card>

      <Button label="連線測試" loading={busy === 'health'} disabled={!!busy} onPress={() => run('health')} />
      <Button
        label="初始化資料庫"
        variant="secondary"
        loading={busy === 'init'}
        disabled={!!busy}
        onPress={() => run('init')}
      />
      <Button
        label="資料庫狀態"
        variant="outline"
        loading={busy === 'status'}
        disabled={!!busy}
        onPress={() => run('status')}
      />

      {result && (
        <Message kind={result.ok ? 'ok' : 'error'} text={result.title}>
          {result.lines?.map((line) => (
            <Text key={line} style={localStyles.line}>
              {line}
            </Text>
          ))}
          {result.tables && (
            <View style={localStyles.table}>
              {result.tables.map((t) => (
                <View key={t.table} style={localStyles.tableRow}>
                  <Text style={localStyles.tableName}>{t.table}</Text>
                  <Text style={localStyles.tableCount}>{t.rows}</Text>
                </View>
              ))}
            </View>
          )}
        </Message>
      )}
    </Screen>
  );
}

const localStyles = StyleSheet.create({
  link: { color: colors.primary, fontSize: 14, alignSelf: 'flex-end' },
  line: { fontSize: 14, color: '#374151' },
  table: { marginTop: 8, borderTopWidth: 1, borderTopColor: colors.border },
  tableRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 5,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
  tableName: { fontSize: 13, color: '#374151', fontFamily: Platform.select({ ios: 'Menlo', default: 'monospace' }) },
  tableCount: { fontSize: 13, color: colors.text, fontWeight: '600' },
});
