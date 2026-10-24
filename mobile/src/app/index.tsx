import { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

import { api, ApiConfig } from '@/lib/api';
import { loadSettings, saveSettings } from '@/lib/settings';
import { normalizeBaseUrl } from '@/lib/url';

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

export default function ConnectionScreen() {
  const [host, setHost] = useState('');
  const [adminKey, setAdminKey] = useState('');
  const [showKey, setShowKey] = useState(false);
  const [busy, setBusy] = useState<Action | null>(null);
  const [result, setResult] = useState<Result | null>(null);

  useEffect(() => {
    loadSettings().then((s) => {
      setHost(s.host);
      setAdminKey(s.adminKey);
    });
  }, []);

  const baseUrl = normalizeBaseUrl(host);

  async function run(action: Action) {
    if (!baseUrl) {
      setResult({ ok: false, title: '主機位址格式不正確', lines: ['例如：192.168.68.109:8000'] });
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

    const cfg: ApiConfig = { baseUrl, adminKey: adminKey.trim() };
    setBusy(action);
    setResult(null);
    try {
      await saveSettings({ host: host.trim(), adminKey: cfg.adminKey });

      if (action === 'health') {
        const h = await api.health(cfg);
        setResult({
          ok: true,
          title: '連線成功',
          lines: [
            h.app,
            `主機時間：${h.server_time.replace('T', ' ').slice(0, 19)}`,
            `資料庫：${h.db_initialized ? '已初始化' : '尚未初始化，請按「初始化資料庫」'}`,
          ],
        });
      } else if (action === 'init') {
        const r = await api.initDb(cfg);
        const seeded = r.seeded
          ? `新增檢查項目：${r.seeded.categories} 類 / ${r.seeded.items} 項 / ${r.seeded.check_points} 個檢查點`
          : null;
        setResult({
          ok: true,
          title: r.message,
          lines: [`資料表：${r.tables.length} 張`, ...(seeded ? [seeded] : [])],
        });
      } else {
        const s = await api.dbStatus(cfg);
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
    <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <ScrollView contentContainerStyle={styles.container} keyboardShouldPersistTaps="handled">
        <View style={styles.card}>
          <Text style={styles.label}>主機位址</Text>
          <TextInput
            style={styles.input}
            value={host}
            onChangeText={setHost}
            placeholder="192.168.68.109:8000"
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType="url"
            returnKeyType="done"
          />
          <Text style={styles.hint}>
            {host.trim() ? (baseUrl ? `將連線到 ${baseUrl}` : '格式不正確') : '輸入 run.py 印出的 IP；未填 port 時預設 8000'}
          </Text>

          <Text style={[styles.label, styles.mt]}>管理金鑰</Text>
          <View style={styles.row}>
            <TextInput
              style={[styles.input, styles.flex]}
              value={adminKey}
              onChangeText={setAdminKey}
              placeholder="backend/.env 的 ADMIN_INIT_KEY"
              autoCapitalize="none"
              autoCorrect={false}
              secureTextEntry={!showKey}
            />
            <Pressable style={styles.eye} onPress={() => setShowKey((v) => !v)}>
              <Text style={styles.eyeText}>{showKey ? '隱藏' : '顯示'}</Text>
            </Pressable>
          </View>
        </View>

        <ActionButton label="連線測試" busy={busy === 'health'} disabled={!!busy} onPress={() => run('health')} />
        <ActionButton
          label="初始化資料庫"
          busy={busy === 'init'}
          disabled={!!busy}
          onPress={() => run('init')}
          variant="secondary"
        />
        <ActionButton
          label="資料庫狀態"
          busy={busy === 'status'}
          disabled={!!busy}
          onPress={() => run('status')}
          variant="outline"
        />

        {result && (
          <View style={[styles.result, result.ok ? styles.resultOk : styles.resultError]}>
            <Text style={[styles.resultTitle, { color: result.ok ? '#166534' : '#991b1b' }]}>
              {result.ok ? '✓ ' : '✕ '}
              {result.title}
            </Text>
            {result.lines?.map((line) => (
              <Text key={line} style={styles.resultLine}>
                {line}
              </Text>
            ))}
            {result.tables && (
              <View style={styles.table}>
                {result.tables.map((t) => (
                  <View key={t.table} style={styles.tableRow}>
                    <Text style={styles.tableName}>{t.table}</Text>
                    <Text style={styles.tableCount}>{t.rows}</Text>
                  </View>
                ))}
              </View>
            )}
          </View>
        )}
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

function ActionButton(props: {
  label: string;
  busy: boolean;
  disabled: boolean;
  onPress: () => void;
  variant?: 'primary' | 'secondary' | 'outline';
}) {
  const variant = props.variant ?? 'primary';
  const textColor = variant === 'outline' ? '#1d4ed8' : '#fff';
  return (
    <Pressable
      onPress={props.onPress}
      disabled={props.disabled}
      style={({ pressed }) => [
        styles.button,
        styles[variant],
        (pressed || props.disabled) && styles.dimmed,
      ]}
    >
      {props.busy ? (
        <ActivityIndicator color={textColor} />
      ) : (
        <Text style={[styles.buttonText, { color: textColor }]}>{props.label}</Text>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  container: { padding: 16, gap: 12, backgroundColor: '#f3f4f6', flexGrow: 1 },
  card: { backgroundColor: '#fff', borderRadius: 12, padding: 16 },
  label: { fontSize: 14, fontWeight: '600', color: '#374151', marginBottom: 6 },
  mt: { marginTop: 14 },
  input: {
    borderWidth: 1,
    borderColor: '#d1d5db',
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 16,
    color: '#111827',
  },
  hint: { fontSize: 12, color: '#6b7280', marginTop: 6 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  eye: { paddingHorizontal: 10, paddingVertical: 10 },
  eyeText: { color: '#1d4ed8', fontSize: 14 },
  button: { borderRadius: 10, paddingVertical: 14, alignItems: 'center', minHeight: 50, justifyContent: 'center' },
  primary: { backgroundColor: '#1d4ed8' },
  secondary: { backgroundColor: '#047857' },
  outline: { backgroundColor: '#fff', borderWidth: 1, borderColor: '#1d4ed8' },
  dimmed: { opacity: 0.6 },
  buttonText: { fontSize: 16, fontWeight: '600' },
  result: { borderRadius: 12, padding: 14, borderWidth: 1, gap: 4 },
  resultOk: { backgroundColor: '#f0fdf4', borderColor: '#86efac' },
  resultError: { backgroundColor: '#fef2f2', borderColor: '#fca5a5' },
  resultTitle: { fontSize: 16, fontWeight: '700', marginBottom: 4 },
  resultLine: { fontSize: 14, color: '#374151' },
  table: { marginTop: 8, borderTopWidth: 1, borderTopColor: '#d1d5db' },
  tableRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 5,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: '#d1d5db',
  },
  tableName: { fontSize: 13, color: '#374151', fontFamily: Platform.select({ ios: 'Menlo', default: 'monospace' }) },
  tableCount: { fontSize: 13, color: '#111827', fontWeight: '600' },
});
