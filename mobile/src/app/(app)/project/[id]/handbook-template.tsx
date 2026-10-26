import { useLocalSearchParams, useNavigation } from 'expo-router';
import { useLayoutEffect, useState } from 'react';
import { Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';

import { HandbookAttachmentList } from '@/components/HandbookAttachments';
import { ActionSheet, PromptModal, SheetOption } from '@/components/overlays';
import { Button, Card, Loading, Message, MAX_WIDTH, colors } from '@/components/ui';
import { api, HandbookField, HandbookSection, HandbookTemplate } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { confirm, errorText } from '@/lib/dialogs';
import { pickPdf, uploadFile } from '@/lib/files';
import { useLoad } from '@/lib/useLoad';

type Prompt = { title: string; message?: string; initial?: string; multiline?: boolean; onConfirm: (value: string) => Promise<unknown> };
type Sheet = { title: string; options: SheetOption[] };

/** 步驟 5：住屋手冊的欄位範本（每戶都用這份）與建案共用的外部 PDF */
export default function HandbookTemplateScreen() {
  const projectId = Number(useLocalSearchParams<{ id: string }>().id);
  const { can } = useAuth();
  const editable = can('project.manage');
  const navigation = useNavigation();
  const { data, setData, error, setError, refresh, refreshing } = useLoad(() => api.handbookTemplate(projectId), [projectId]);
  const [prompt, setPrompt] = useState<Prompt | null>(null);
  const [sheet, setSheet] = useState<Sheet | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  useLayoutEffect(() => {
    navigation.setOptions({ title: '手冊範本與共用 PDF' });
  }, [navigation]);

  if (!data) return error ? <Message kind="error" text={error} /> : <Loading />;

  async function run(action: () => Promise<HandbookTemplate | void>, label: string | null = null) {
    setBusy(label);
    try {
      setError(null);
      const updated = await action();
      if (updated) setData(updated);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(null);
    }
  }

  async function remove(label: string, action: () => Promise<HandbookTemplate>) {
    if (await confirm('刪除', `確定要刪除「${label}」？\n已有住戶填寫內容的欄位不能刪除，請改用「停用」。`, '刪除', true)) await run(action);
  }

  function sectionMenu(s: HandbookSection, index: number) {
    setSheet({
      title: `分類：${s.name}`,
      options: [
        {
          label: '新增欄位',
          onPress: () =>
            setPrompt({
              title: `新增「${s.name}」的欄位`,
              message: '新增後可再設定共用預設值、必填或選填',
              onConfirm: (label) => run(() => api.addHandbookField(s.id, { label })),
            }),
        },
        { label: '重新命名', onPress: () => setPrompt({ title: '重新命名分類', initial: s.name, onConfirm: (name) => run(() => api.updateHandbookSection(s.id, { name })) }) },
        ...(index > 0 ? [{ label: '上移', onPress: () => run(() => api.moveHandbookSection(s.id, 'up')) }] : []),
        ...(index < data!.sections.length - 1 ? [{ label: '下移', onPress: () => run(() => api.moveHandbookSection(s.id, 'down')) }] : []),
        { label: s.is_active ? '停用（手冊不顯示）' : '重新啟用', onPress: () => run(() => api.updateHandbookSection(s.id, { is_active: !s.is_active })) },
        { label: '刪除分類', destructive: true, onPress: () => remove(s.name, () => api.deleteHandbookSection(s.id)) },
      ],
    });
  }

  function fieldMenu(f: HandbookField, index: number, count: number) {
    setSheet({
      title: `欄位：${f.label}`,
      options: [
        {
          label: f.default_value ? '修改共用預設值' : '設定共用預設值',
          onPress: () =>
            setPrompt({
              title: `「${f.label}」的共用預設值`,
              message: '每戶都會帶入這個內容（例如廚具品牌）；個別住戶可以另外填寫覆蓋',
              initial: f.default_value ?? '',
              multiline: true,
              onConfirm: (value) => run(() => api.updateHandbookField(f.id, { default_value: value })),
            }),
        },
        ...(f.default_value ? [{ label: '清除共用預設值', onPress: () => run(() => api.updateHandbookField(f.id, { default_value: null })) }] : []),
        { label: '修改欄位名稱', onPress: () => setPrompt({ title: '修改欄位名稱', initial: f.label, onConfirm: (label) => run(() => api.updateHandbookField(f.id, { label })) }) },
        { label: f.required ? '改為選填' : '改為必填', onPress: () => run(() => api.updateHandbookField(f.id, { required: !f.required })) },
        ...(index > 0 ? [{ label: '上移', onPress: () => run(() => api.moveHandbookField(f.id, 'up')) }] : []),
        ...(index < count - 1 ? [{ label: '下移', onPress: () => run(() => api.moveHandbookField(f.id, 'down')) }] : []),
        { label: f.is_active ? '停用' : '重新啟用', onPress: () => run(() => api.updateHandbookField(f.id, { is_active: !f.is_active })) },
        { label: '刪除欄位', destructive: true, onPress: () => remove(f.label, () => api.deleteHandbookField(f.id)) },
      ],
    });
  }

  async function uploadShared() {
    const file = await pickPdf().catch((e) => {
      setError(errorText(e));
      return null;
    });
    if (!file) return;
    await run(() => uploadFile<HandbookTemplate>(`/projects/${projectId}/handbook/attachments`, file), `上傳「${file.name}」中…`);
  }

  return (
    <View style={{ flex: 1 }}>
      <ScrollView
        contentInsetAdjustmentBehavior="automatic" // iOS 半透明標題列時避免內容被擋住
        style={{ backgroundColor: colors.bg }}
        contentContainerStyle={localStyles.content}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} />}
      >
        <Message
          kind="info"
          text={
            editable
              ? '這個建案每一戶的手冊都用這份範本。點分類或欄位可新增、改名、設定共用預設值、排序或停用；有「共用」內容的欄位，各戶不必再填。'
              : '這個建案每一戶手冊的欄位與共用內容'
          }
        />
        {error && <Message kind="error" text={error} />}
        {busy && <Message kind="info" text={busy} />}

        <Card title="建案共用 PDF">
          <Text style={localStyles.hint}>例如建材型錄、設備說明書、社區規約。每一戶的手冊都會依序合併這些 PDF（接在系統產生的頁面後面、該戶專屬 PDF 前面）。</Text>
          <HandbookAttachmentList
            items={data.attachments}
            editable={editable}
            onMove={(a, direction) => run(() => api.moveHandbookAttachment<HandbookTemplate>(a.id, direction))}
            onDelete={async (a) => {
              if (await confirm('刪除 PDF', `確定要刪除「${a.title}」？`, '刪除', true)) await run(() => api.deleteHandbookAttachment<HandbookTemplate>(a.id));
            }}
          />
          {editable && (
            <View style={{ marginTop: 8 }}>
              <Button label="上傳共用 PDF" variant="outline" onPress={uploadShared} />
            </View>
          )}
        </Card>

        {data.sections.map((s, si) => (
          <Card key={s.id} style={!s.is_active ? localStyles.inactiveCard : undefined}>
            <Pressable disabled={!editable} onPress={() => sectionMenu(s, si)} style={localStyles.sectionRow}>
              <Text style={[localStyles.sectionName, !s.is_active && localStyles.inactiveText]}>{s.name}</Text>
              {!s.is_active && <Text style={localStyles.badge}>已停用</Text>}
              {editable && <Text style={localStyles.more}>⋯</Text>}
            </Pressable>
            {s.fields.map((f, fi) => (
              <Pressable
                key={f.id}
                disabled={!editable}
                onPress={() => fieldMenu(f, fi, s.fields.length)}
                style={({ pressed }) => [localStyles.fieldRow, pressed && { opacity: 0.6 }]}
              >
                <View style={localStyles.fieldHead}>
                  <Text style={[localStyles.fieldLabel, !f.is_active && localStyles.inactiveText]}>
                    {f.label}
                    {f.required && <Text style={localStyles.required}> ＊</Text>}
                  </Text>
                  {!f.is_active && <Text style={localStyles.badge}>已停用</Text>}
                </View>
                <Text style={f.default_value ? localStyles.shared : localStyles.perUnit} numberOfLines={2}>
                  {f.default_value ? `共用：${f.default_value}` : '各戶自行填寫'}
                </Text>
              </Pressable>
            ))}
            {s.fields.length === 0 && <Text style={localStyles.hint}>（沒有欄位）</Text>}
          </Card>
        ))}

        {editable && (
          <Button
            label="＋ 新增分類"
            variant="outline"
            onPress={() =>
              setPrompt({
                title: '新增分類',
                message: '例如：生產履歷：智慧家庭設備',
                onConfirm: (name) => run(() => api.addHandbookSection(projectId, name)),
              })
            }
          />
        )}
        <Text style={localStyles.hint}>＊ 必填：每戶這些欄位都有內容（自己填的或共用預設值）才能 Review OK。</Text>
      </ScrollView>

      <ActionSheet visible={!!sheet} title={sheet?.title} options={sheet?.options ?? []} onClose={() => setSheet(null)} />
      <PromptModal
        visible={!!prompt}
        title={prompt?.title ?? ''}
        message={prompt?.message}
        initialValue={prompt?.initial}
        multiline={prompt?.multiline}
        onCancel={() => setPrompt(null)}
        onConfirm={(value) => {
          const p = prompt;
          setPrompt(null);
          if (p) void p.onConfirm(value);
        }}
      />
    </View>
  );
}

const localStyles = StyleSheet.create({
  content: { padding: 16, gap: 10, width: '100%', maxWidth: MAX_WIDTH, alignSelf: 'center' },
  inactiveCard: { opacity: 0.7 },
  sectionRow: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingBottom: 6 },
  sectionName: { flex: 1, fontSize: 17, fontWeight: '700', color: colors.text },
  more: { fontSize: 22, color: colors.primary, paddingHorizontal: 6 },
  fieldRow: { paddingVertical: 8, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border, gap: 2 },
  fieldHead: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  fieldLabel: { flex: 1, fontSize: 15, fontWeight: '600', color: colors.text },
  required: { color: colors.danger },
  shared: { fontSize: 13, color: colors.textSecondary },
  perUnit: { fontSize: 13, color: colors.faint },
  inactiveText: { color: colors.faint, textDecorationLine: 'line-through' },
  badge: { fontSize: 12, color: colors.muted, borderWidth: 1, borderColor: colors.border, borderRadius: 999, paddingHorizontal: 8, paddingVertical: 1 },
  hint: { fontSize: 13, color: colors.muted, lineHeight: 19 },
});
