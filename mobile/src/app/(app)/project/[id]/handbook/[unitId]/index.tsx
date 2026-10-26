import { router, useLocalSearchParams, useNavigation } from 'expo-router';
import { useLayoutEffect, useState } from 'react';
import { Image, Pressable, RefreshControl, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';

import { HandbookAttachmentList } from '@/components/HandbookAttachments';
import { PromptModal } from '@/components/overlays';
import { Button, Card, Loading, Message, MAX_WIDTH, colors } from '@/components/ui';
import { api, HandbookStatus, UnitHandbook } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { confirm, errorText } from '@/lib/dialogs';
import { openLink } from '@/lib/download';
import { pickPdf, uploadFile } from '@/lib/files';
import { useLoad } from '@/lib/useLoad';

/** 步驟 5：單戶的生產履歷＋住屋手冊 */
export default function UnitHandbookScreen() {
  const { id: projectId, unitId: unitParam } = useLocalSearchParams<{ id: string; unitId: string }>();
  const unitId = Number(unitParam);
  const { can } = useAuth();
  const canEdit = can('project.manage') || can('report.manage');
  const canReport = can('report.manage');
  const navigation = useNavigation();
  const { data, setData, error, setError, refresh, refreshing } = useLoad(() => api.unitHandbook(unitId), [unitId]);
  const [edits, setEdits] = useState<Record<number, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [askEmail, setAskEmail] = useState(false);

  useLayoutEffect(() => {
    navigation.setOptions({ title: data ? `${data.unit_no} 手冊` : '住屋手冊' });
  }, [navigation, data?.unit_no]);

  if (!data) return error ? <Message kind="error" text={error} /> : <Loading />;

  const editable = canEdit && data.status === 'draft';
  const dirty = Object.keys(edits).length > 0;

  async function run(label: string | null, action: () => Promise<unknown>) {
    setBusy(label);
    setNotice(null);
    try {
      setError(null);
      await action();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(null);
    }
  }

  const openEntry = (entryId: number | null) =>
    router.push({
      pathname: '/project/[id]/handbook/[unitId]/entry',
      params: { id: projectId, unitId: String(unitId), ...(entryId ? { entryId: String(entryId) } : {}) },
    });

  /** 有未儲存的修改時先存（預覽、Review OK 前都會自動存） */
  async function saveIfDirty(): Promise<UnitHandbook> {
    if (!dirty) return data!;
    const updated = await api.saveHandbookValues(unitId, edits);
    setEdits({});
    setData(updated);
    return updated;
  }

  const save = () => run('儲存中…', async () => {
    await saveIfDirty();
    setNotice('已儲存');
  });

  async function preview() {
    await run('產生手冊 PDF 中…', async () => {
      await openLink(async () => {
        await saveIfDirty();
        return (await api.handbookPreviewLink(unitId)).url;
      });
    });
  }

  async function approve() {
    if (!(await confirm('Review OK', '確認手冊內容無誤？確認後內容與該戶 PDF 會鎖定，要修改請先「取消確認」。', '確認'))) return;
    await run('確認中…', async () => {
      await saveIfDirty();
      setData(await api.approveHandbook(unitId));
    });
  }

  async function unapprove() {
    const message = data!.status === 'sent' ? '已寄出的手冊取消確認後可以修改，修改完要重新確認並再寄一次。' : '取消後可以再修改內容。';
    if (!(await confirm('取消確認', message, '取消確認', true))) return;
    await run(null, async () => setData(await api.unapproveHandbook(unitId)));
  }

  async function send(to: string) {
    setAskEmail(false);
    await run('寄送中…', async () => {
      const updated = await api.sendHandbook(unitId, to);
      setData(updated);
      setNotice(`已匯出並寄送至 ${updated.sent_to}`);
    });
  }

  async function uploadPdf() {
    const file = await pickPdf().catch((e) => {
      setError(errorText(e));
      return null;
    });
    if (!file) return;
    await run(`上傳「${file.name}」中…`, async () => setData(await uploadFile<UnitHandbook>(`/units/${unitId}/handbook/attachments`, file)));
  }

  return (
    <View style={{ flex: 1 }}>
      <ScrollView
        contentInsetAdjustmentBehavior="automatic" // iOS 半透明標題列時避免內容被擋住
        style={{ backgroundColor: colors.bg }}
        contentContainerStyle={localStyles.content}
        keyboardShouldPersistTaps="handled"
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => (dirty ? undefined : refresh())} />}
      >
        <Card>
          <Text style={localStyles.owner}>
            {data.unit_no}
            {data.owner_name ? `　${data.owner_name}` : ''}
          </Text>
          <Text style={localStyles.meta}>Email：{data.owner_email || '（未登錄）'}</Text>
          <Steps status={data.status} />
          {data.missing.length > 0 ? (
            <Text style={[localStyles.meta, { color: colors.danger }]}>必填尚缺 {data.missing.length} 項：{data.missing.slice(0, 4).map((m) => m.split('／').pop()).join('、')}{data.missing.length > 4 ? '…' : ''}</Text>
          ) : (
            // 範本有必填欄位時才顯示（預設範本全部選填）
            data.sections.some((s) => s.fields.some((f) => f.required)) && (
              <Text style={[localStyles.meta, { color: colors.green }]}>✓ 必填欄位已完整</Text>
            )
          )}
        </Card>

        {error && <Message kind="error" text={error} />}
        {busy && <Message kind="info" text={busy} />}
        {notice && <Message kind="ok" text={notice} />}

        <Card title="生產履歷紀錄">
          <Text style={localStyles.hint}>施工過程的日期、照片與說明，依日期排在手冊裡。</Text>
          {data.entries.length === 0 && <Text style={localStyles.empty}>（尚無紀錄）</Text>}
          {data.entries.map((e) => (
            <Pressable
              key={e.id}
              disabled={!editable}
              onPress={() => openEntry(e.id)}
              style={({ pressed }) => [localStyles.entry, pressed && { opacity: 0.6 }]}
            >
              <View style={localStyles.entryHead}>
                <Text style={localStyles.entryDate}>{e.entry_date}</Text>
                <Text style={localStyles.entryMeta}>
                  {e.photos.length} 張照片{e.created_by ? `・${e.created_by}` : ''}
                </Text>
                {editable && <Text style={localStyles.chevron}>›</Text>}
              </View>
              {!!e.note && <Text style={localStyles.entryNote}>{e.note}</Text>}
              {e.photos.length > 0 && (
                <View style={localStyles.thumbs}>
                  {e.photos.slice(0, 4).map((p) => (
                    <Image key={p.id} source={{ uri: p.url }} style={localStyles.thumb} />
                  ))}
                  {e.photos.length > 4 && <Text style={localStyles.more}>+{e.photos.length - 4}</Text>}
                </View>
              )}
            </Pressable>
          ))}
          {editable && (
            <View style={{ marginTop: 8 }}>
              <Button label="＋ 新增紀錄（日期、照片、說明）" variant="outline" onPress={() => openEntry(null)} />
            </View>
          )}
        </Card>

        {data.sections.map((s) => (
          <Card key={s.id} title={s.name}>
            {s.fields.map((f) => {
              const value = edits[f.field_id] ?? f.value ?? '';
              const missing = f.required && !value.trim() && !f.default_value;
              return (
                <View key={f.field_id} style={localStyles.field}>
                  <Text style={localStyles.label}>
                    {f.label}
                    {f.required && <Text style={{ color: colors.danger }}> ＊</Text>}
                  </Text>
                  <TextInput
                    style={[localStyles.input, !editable && localStyles.inputDisabled, missing && { borderColor: colors.danger }]}
                    value={value}
                    editable={editable}
                    multiline
                    placeholder={f.default_value ? `共用：${f.default_value}` : editable ? '請輸入' : '—'}
                    placeholderTextColor={colors.faint}
                    onChangeText={(text) => setEdits((e) => ({ ...e, [f.field_id]: text }))}
                  />
                </View>
              );
            })}
          </Card>
        ))}
        {editable && <Text style={localStyles.hint}>灰字是建案共用的預設內容，留空就會用它；在這裡填寫則只改這一戶。</Text>}
        {editable && <Button label={dirty ? '儲存' : '已儲存'} onPress={save} disabled={!dirty} />}

        <Card title="外部 PDF">
          <Text style={localStyles.hint}>依下列順序接在系統手冊後面，合併成一份完整 PDF。建案共用的 PDF 在「範本」頁調整。</Text>
          <HandbookAttachmentList
            items={data.attachments}
            editable={editable}
            lockShared
            onMove={(a, direction) => run(null, async () => setData(await api.moveHandbookAttachment<UnitHandbook>(a.id, direction)))}
            onDelete={async (a) => {
              if (await confirm('刪除 PDF', `確定要刪除「${a.title}」？`, '刪除', true)) {
                await run(null, async () => setData(await api.deleteHandbookAttachment<UnitHandbook>(a.id)));
              }
            }}
          />
          {editable && (
            <View style={{ marginTop: 8 }}>
              <Button label="上傳外部文件 PDF（這一戶）" variant="outline" onPress={uploadPdf} />
            </View>
          )}
        </Card>

        <Card title="手冊">
          {data.approved_at && (
            <Text style={localStyles.meta}>
              Review OK：{data.approved_by ?? ''} {data.approved_at.replace('T', ' ').slice(0, 16)}
            </Text>
          )}
          {data.sent_at && (
            <Text style={localStyles.meta}>
              已寄送：{data.sent_at.replace('T', ' ').slice(0, 16)} → {data.sent_to}
            </Text>
          )}
          <View style={{ gap: 8, marginTop: 8 }}>
            <Button label="預覽手冊 PDF" variant="outline" onPress={preview} />
            {data.status === 'draft' && canReport && (
              <Button label="Review OK（確認手冊內容）" variant="secondary" onPress={approve} disabled={data.missing.length > 0 && !dirty} />
            )}
            {data.status === 'approved' && canReport && <Button label="匯出檔案並寄送至售服" onPress={() => setAskEmail(true)} />}
            {data.status === 'sent' && canReport && <Button label="重新匯出並寄送至售服" variant="outline" onPress={() => setAskEmail(true)} />}
            {data.status !== 'draft' && canReport && (
              <Text style={localStyles.link} onPress={unapprove}>
                取消確認
              </Text>
            )}
          </View>
        </Card>
        <View style={{ height: 30 }} />
      </ScrollView>

      <PromptModal
        visible={askEmail}
        title={data.status === 'sent' ? '重新匯出並寄送至售服' : '匯出檔案並寄送至售服'}
        message="會匯出完整的手冊 PDF，寄到售服信箱（可改收件人）："
        initialValue={data.sent_to ?? data.service_email ?? ''}
        placeholder="service@example.com"
        confirmText="寄送"
        onCancel={() => setAskEmail(false)}
        onConfirm={send}
      />
    </View>
  );
}

const STEPS: { status: HandbookStatus; label: string }[] = [
  { status: 'draft', label: '填寫內容' },
  { status: 'approved', label: 'Review OK' },
  { status: 'sent', label: '寄送至售服' },
];

function Steps({ status }: { status: HandbookStatus }) {
  const current = STEPS.findIndex((s) => s.status === status);
  return (
    <View style={localStyles.steps}>
      {STEPS.map((s, i) => {
        const done = i < current || status === 'sent';
        const active = i === current && status !== 'sent';
        return (
          <View key={s.status} style={localStyles.step}>
            <View style={[localStyles.stepDot, done && localStyles.stepDotDone, active && localStyles.stepDotActive]}>
              <Text style={[localStyles.stepNum, done && { color: colors.onPrimary }]}>{done ? '✓' : i + 1}</Text>
            </View>
            <Text style={[localStyles.stepLabel, (done || active) && { color: colors.text, fontWeight: '600' }]}>{s.label}</Text>
          </View>
        );
      })}
    </View>
  );
}

const localStyles = StyleSheet.create({
  content: { padding: 16, gap: 10, width: '100%', maxWidth: MAX_WIDTH, alignSelf: 'center' },
  owner: { fontSize: 18, fontWeight: '700', color: colors.text },
  meta: { fontSize: 14, color: colors.textSecondary, marginTop: 2 },
  hint: { fontSize: 13, color: colors.muted, lineHeight: 19 },
  field: { marginBottom: 10 },
  label: { fontSize: 14, fontWeight: '600', color: colors.textSecondary, marginBottom: 6 },
  input: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 16,
    color: colors.text,
    backgroundColor: colors.input,
    minHeight: 44,
    textAlignVertical: 'top',
  },
  inputDisabled: { backgroundColor: colors.subtle, color: colors.textSecondary },
  empty: { fontSize: 13, color: colors.faint, marginTop: 6 },
  entry: { paddingVertical: 10, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border, gap: 4 },
  entryHead: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  entryDate: { fontSize: 15, fontWeight: '700', color: colors.text },
  entryMeta: { flex: 1, fontSize: 12, color: colors.muted },
  entryNote: { fontSize: 14, color: colors.textSecondary },
  chevron: { fontSize: 22, color: colors.faint },
  thumbs: { flexDirection: 'row', gap: 6, alignItems: 'center', marginTop: 2 },
  thumb: { width: 56, height: 56, borderRadius: 6, backgroundColor: colors.chip },
  more: { fontSize: 13, color: colors.muted, marginLeft: 4 },
  link: { color: colors.primary, fontSize: 15, textAlign: 'center', paddingVertical: 6 },
  steps: { flexDirection: 'row', alignItems: 'center', gap: 6, marginVertical: 10, flexWrap: 'wrap' },
  step: { flexDirection: 'row', alignItems: 'center', gap: 4, marginRight: 6 },
  stepDot: { width: 22, height: 22, borderRadius: 11, borderWidth: 2, borderColor: colors.faint, alignItems: 'center', justifyContent: 'center' },
  stepDotDone: { backgroundColor: colors.green, borderColor: colors.green },
  stepDotActive: { borderColor: colors.primary },
  stepNum: { fontSize: 11, fontWeight: '700', color: colors.muted },
  stepLabel: { fontSize: 13, color: colors.muted },
});
