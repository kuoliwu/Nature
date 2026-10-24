import { router, useLocalSearchParams, useNavigation } from 'expo-router';
import { useLayoutEffect, useState } from 'react';
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, Text, View } from 'react-native';

import { SignaturePad, Strokes } from '@/components/SignaturePad';
import { Button, Card, Field, Loading, Message, MAX_WIDTH, colors } from '@/components/ui';
import { api } from '@/lib/api';
import { dayLabel, shortTime } from '@/lib/dates';
import { errorText } from '@/lib/dialogs';
import { useLoad } from '@/lib/useLoad';

export default function SignScreen() {
  const bookingId = Number(useLocalSearchParams<{ bookingId: string }>().bookingId);
  const navigation = useNavigation();
  const { data: ins, error } = useLoad(() => api.inspection(bookingId), [bookingId]);
  const [name, setName] = useState<string | null>(null);
  const [strokes, setStrokes] = useState<Strokes>([]);
  const [size, setSize] = useState({ width: 0, height: 0 });
  const [drawing, setDrawing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  useLayoutEffect(() => {
    navigation.setOptions({ title: '屋主簽名確認' });
  }, [navigation]);

  if (!ins) return error ? <Message kind="error" text={error} /> : <Loading />;

  const signer = name ?? ins.contact_name;
  const fails = ins.categories.flatMap((c) =>
    c.items.flatMap((i) => i.points.filter((p) => p.result === 'fail').map((p) => ({ label: `${c.name}／${i.name}／${p.name}`, note: p.note }))),
  );
  const count = (r: string) => ins.categories.flatMap((c) => c.items.flatMap((i) => i.points)).filter((p) => p.result === r).length;

  async function submit() {
    if (!signer.trim()) return setSubmitError('請輸入簽名人姓名');
    if (!strokes.length) return setSubmitError('請先簽名');
    setBusy(true);
    setSubmitError(null);
    try {
      await api.signInspection(bookingId, { signer_name: signer.trim(), strokes, width: size.width, height: size.height });
      router.back();
    } catch (e) {
      setSubmitError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <ScrollView
        contentInsetAdjustmentBehavior="automatic" // iOS 半透明標題列時避免內容被擋住
        style={{ backgroundColor: colors.bg }}
        contentContainerStyle={localStyles.content}
        scrollEnabled={!drawing} // 簽名時不要讓頁面跟著捲動
        keyboardShouldPersistTaps="handled"
      >
        <Card title={`${ins.project_name} ${ins.unit_no}`}>
          <Text style={localStyles.meta}>{dayLabel(ins.date)} {shortTime(ins.start_time)}｜{ins.place}</Text>
          <View style={localStyles.summary}>
            <Summary label="合格" value={count('pass')} color={colors.green} />
            <Summary label="不合格" value={count('fail')} color={colors.danger} />
            <Summary label="不適用" value={count('na')} color={colors.muted} />
          </View>
        </Card>

        <Card title={fails.length ? `不合格項目（${fails.length}）` : '不合格項目'}>
          {fails.length === 0 && <Text style={localStyles.meta}>沒有不合格項目</Text>}
          {fails.map((f) => (
            <View key={f.label} style={localStyles.fail}>
              <Text style={localStyles.failLabel}>✗ {f.label}</Text>
              {!!f.note && <Text style={localStyles.failNote}>{f.note}</Text>}
            </View>
          ))}
          {!!ins.general_note && <Text style={[localStyles.meta, { marginTop: 8 }]}>整體備註：{ins.general_note}</Text>}
        </Card>

        <Card title="簽名">
          <Field label="簽名人（屋主或代理人）" value={signer} onChangeText={setName} />
          <SignaturePad
            strokes={strokes}
            onChange={(s, sz) => {
              setStrokes(s);
              setSize(sz);
            }}
            onDrawingChange={setDrawing}
          />
          <View style={localStyles.padActions}>
            <Text style={localStyles.meta}>簽名即表示確認以上檢查結果</Text>
            <Text style={localStyles.clear} onPress={() => setStrokes([])}>
              清除重簽
            </Text>
          </View>
        </Card>

        {submitError && <Message kind="error" text={submitError} />}
        <Button label="確認簽名並完成驗屋" onPress={submit} loading={busy} disabled={!strokes.length} />
        <View style={{ height: 30 }} />
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

function Summary({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <View style={{ flex: 1, alignItems: 'center' }}>
      <Text style={{ fontSize: 24, fontWeight: '700', color }}>{value}</Text>
      <Text style={{ fontSize: 13, color: colors.muted }}>{label}</Text>
    </View>
  );
}

const localStyles = StyleSheet.create({
  content: { padding: 16, gap: 10, width: '100%', maxWidth: MAX_WIDTH, alignSelf: 'center' },
  meta: { fontSize: 14, color: colors.muted },
  summary: { flexDirection: 'row', marginTop: 12 },
  fail: { paddingVertical: 6, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border },
  failLabel: { fontSize: 15, color: '#991b1b', fontWeight: '600' },
  failNote: { fontSize: 14, color: '#374151', marginTop: 2 },
  padActions: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: 8 },
  clear: { color: colors.primary, fontSize: 15 },
});
