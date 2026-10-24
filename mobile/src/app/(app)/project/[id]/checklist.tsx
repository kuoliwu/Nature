import { useLocalSearchParams, useNavigation } from 'expo-router';
import { useLayoutEffect, useState } from 'react';
import { Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';

import { ActionSheet, PromptModal, SheetOption } from '@/components/overlays';
import { Button, Card, Loading, Message, MAX_WIDTH, colors } from '@/components/ui';
import { api, ChecklistCategory, ChecklistItem, CheckPoint } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { confirm, errorText } from '@/lib/dialogs';
import { useLoad } from '@/lib/useLoad';

type Prompt = { title: string; message?: string; initial?: string; onConfirm: (name: string) => Promise<unknown> };
type Sheet = { title: string; options: SheetOption[] };

export default function ChecklistScreen() {
  const projectId = Number(useLocalSearchParams<{ id: string }>().id);
  const { can } = useAuth();
  const editable = can('project.manage');
  const navigation = useNavigation();
  const { data: categories, setData, error, setError, refresh, refreshing } = useLoad(
    () => api.checklist(projectId),
    [projectId],
  );
  const [prompt, setPrompt] = useState<Prompt | null>(null);
  const [sheet, setSheet] = useState<Sheet | null>(null);

  useLayoutEffect(() => {
    navigation.setOptions({ title: '檢查項目清單' });
  }, [navigation]);

  if (!categories) return error ? <Message kind="error" text={error} /> : <Loading />;

  /** 大部分 API 回傳修改後的整個類別，直接替換畫面上那一個類別 */
  const replaceCategory = (updated: ChecklistCategory) =>
    setData((list: ChecklistCategory[] | null) => list && list.map((c) => (c.id === updated.id ? updated : c)));

  async function run(action: () => Promise<unknown>) {
    try {
      setError(null);
      await action();
    } catch (e) {
      setError(errorText(e));
    }
  }

  const ask = (p: Prompt) => setPrompt(p);

  async function removeWithConfirm(label: string, action: () => Promise<unknown>) {
    if (await confirm('刪除', `確定要刪除「${label}」？\n已有檢查紀錄的項目不能刪除，請改用「停用」。`, '刪除', true)) {
      await run(action);
    }
  }

  function categoryMenu(c: ChecklistCategory) {
    setSheet({
      title: `類別：${c.name}`,
      options: [
        {
          label: '新增項目',
          onPress: () =>
            ask({
              title: `新增「${c.name}」的項目`,
              message: '會自動帶入同類別第一個項目的檢查點，之後可以再調整',
              onConfirm: async (name) => replaceCategory(await api.addItem(c.id, name)),
            }),
        },
        { label: '重新命名', onPress: () => ask({ title: '重新命名類別', initial: c.name, onConfirm: async (name) => replaceCategory(await api.updateCategory(c.id, { name })) }) },
        { label: c.is_active ? '停用' : '重新啟用', onPress: () => run(async () => replaceCategory(await api.updateCategory(c.id, { is_active: !c.is_active }))) },
        {
          label: '刪除類別',
          destructive: true,
          onPress: () =>
            removeWithConfirm(c.name, async () => {
              await api.deleteCategory(c.id);
              setData((list: ChecklistCategory[] | null) => list && list.filter((x) => x.id !== c.id));
            }),
        },
      ],
    });
  }

  function itemMenu(item: ChecklistItem) {
    setSheet({
      title: `項目：${item.name}`,
      options: [
        { label: '新增檢查點', onPress: () => ask({ title: `新增「${item.name}」的檢查點`, onConfirm: async (name) => replaceCategory(await api.addPoint(item.id, name)) }) },
        { label: '重新命名', onPress: () => ask({ title: '重新命名項目', initial: item.name, onConfirm: async (name) => replaceCategory(await api.updateItem(item.id, { name })) }) },
        { label: item.is_active ? '停用' : '重新啟用', onPress: () => run(async () => replaceCategory(await api.updateItem(item.id, { is_active: !item.is_active }))) },
        { label: '刪除項目', destructive: true, onPress: () => removeWithConfirm(item.name, async () => replaceCategory(await api.deleteItem(item.id))) },
      ],
    });
  }

  function pointMenu(point: CheckPoint) {
    setSheet({
      title: `檢查點：${point.name}`,
      options: [
        { label: '重新命名', onPress: () => ask({ title: '重新命名檢查點', initial: point.name, onConfirm: async (name) => replaceCategory(await api.updatePoint(point.id, { name })) }) },
        { label: point.is_active ? '停用' : '重新啟用', onPress: () => run(async () => replaceCategory(await api.updatePoint(point.id, { is_active: !point.is_active }))) },
        { label: '刪除檢查點', destructive: true, onPress: () => removeWithConfirm(point.name, async () => replaceCategory(await api.deletePoint(point.id))) },
      ],
    });
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
          text={editable ? '點類別、項目或檢查點可新增、改名、停用或刪除。此清單只影響這個建案。' : '此建案驗屋時使用的檢查項目'}
        />
        {error && <Message kind="error" text={error} />}

        {categories.map((c) => (
          <Card key={c.id} style={!c.is_active ? localStyles.inactiveCard : undefined}>
            <Pressable disabled={!editable} onPress={() => categoryMenu(c)} style={localStyles.categoryRow}>
              <Text style={[localStyles.categoryName, !c.is_active && localStyles.inactiveText]}>{c.name}</Text>
              {!c.is_active && <Text style={localStyles.badge}>已停用</Text>}
              {editable && <Text style={localStyles.more}>⋯</Text>}
            </Pressable>

            {c.items.map((item) => (
              <View key={item.id} style={localStyles.itemBlock}>
                <Pressable disabled={!editable} onPress={() => itemMenu(item)} style={localStyles.itemRow}>
                  <Text style={[localStyles.itemName, !item.is_active && localStyles.inactiveText]}>{item.name}</Text>
                  {!item.is_active && <Text style={localStyles.badge}>已停用</Text>}
                </Pressable>
                <View style={localStyles.points}>
                  {item.check_points.map((p) => (
                    <Pressable
                      key={p.id}
                      disabled={!editable}
                      onPress={() => pointMenu(p)}
                      style={[localStyles.point, !p.is_active && localStyles.pointInactive]}
                    >
                      <Text style={[localStyles.pointText, !p.is_active && localStyles.inactiveText]}>{p.name}</Text>
                    </Pressable>
                  ))}
                  {item.check_points.length === 0 && <Text style={localStyles.noPoints}>（沒有檢查點）</Text>}
                </View>
              </View>
            ))}
            {c.items.length === 0 && <Text style={localStyles.noPoints}>（沒有項目）</Text>}
          </Card>
        ))}

        {editable && (
          <Button
            label="＋ 新增類別"
            variant="outline"
            onPress={() =>
              ask({
                title: '新增類別',
                message: '例如：門、地板、牆面',
                onConfirm: async (name) => {
                  const created = await api.addCategory(projectId, name);
                  setData((list: ChecklistCategory[] | null) => list && [...list, created]);
                },
              })
            }
          />
        )}
      </ScrollView>

      <ActionSheet visible={!!sheet} title={sheet?.title} options={sheet?.options ?? []} onClose={() => setSheet(null)} />
      <PromptModal
        visible={!!prompt}
        title={prompt?.title ?? ''}
        message={prompt?.message}
        initialValue={prompt?.initial}
        onCancel={() => setPrompt(null)}
        onConfirm={(name) => {
          const p = prompt;
          setPrompt(null);
          if (p) void run(() => p.onConfirm(name));
        }}
      />
    </View>
  );
}

const localStyles = StyleSheet.create({
  content: { padding: 16, gap: 10, width: '100%', maxWidth: MAX_WIDTH, alignSelf: 'center' },
  inactiveCard: { opacity: 0.7 },
  categoryRow: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingBottom: 6 },
  categoryName: { flex: 1, fontSize: 18, fontWeight: '700', color: colors.text },
  more: { fontSize: 22, color: colors.primary, paddingHorizontal: 6 },
  itemBlock: {
    paddingVertical: 8,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.border,
    gap: 6,
  },
  itemRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  itemName: { fontSize: 16, fontWeight: '600', color: colors.text },
  points: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  point: { borderWidth: 1, borderColor: '#93c5fd', backgroundColor: '#eff6ff', borderRadius: 999, paddingHorizontal: 12, paddingVertical: 5 },
  pointInactive: { borderColor: colors.border, backgroundColor: '#f3f4f6' },
  pointText: { fontSize: 14, color: colors.text },
  inactiveText: { color: '#9ca3af', textDecorationLine: 'line-through' },
  badge: { fontSize: 12, color: colors.muted, borderWidth: 1, borderColor: colors.border, borderRadius: 999, paddingHorizontal: 8, paddingVertical: 1 },
  noPoints: { fontSize: 13, color: colors.muted },
});
