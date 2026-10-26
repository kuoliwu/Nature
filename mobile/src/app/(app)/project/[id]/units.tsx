import { router, useLocalSearchParams, useNavigation } from 'expo-router';
import { useLayoutEffect, useMemo, useState } from 'react';
import { FlatList, RefreshControl, StyleSheet, Text, TextInput, View } from 'react-native';

import { ActionSheet, PromptModal, SheetOption } from '@/components/overlays';
import { HeaderButton, ListRow, Message, MAX_WIDTH, colors } from '@/components/ui';
import { api, Unit, UnitImportResult } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { confirm, errorText } from '@/lib/dialogs';
import { openLink } from '@/lib/download';
import { pickSpreadsheet, uploadFile } from '@/lib/files';
import { parseUnitList } from '@/lib/units';
import { useLoad } from '@/lib/useLoad';

export default function UnitsScreen() {
  const projectId = Number(useLocalSearchParams<{ id: string }>().id);
  const { can } = useAuth();
  const navigation = useNavigation();
  const { data: units, error, reload, refresh, refreshing } = useLoad(() => api.units(projectId), [projectId]);
  const [query, setQuery] = useState('');
  const [menu, setMenu] = useState(false);
  const [bulk, setBulk] = useState(false);
  const [notice, setNotice] = useState<{ ok: boolean; text: string } | null>(null);
  const [importErrors, setImportErrors] = useState<UnitImportResult['errors'] | null>(null);
  const [working, setWorking] = useState<string | null>(null);
  const canManage = can('project.manage');

  const openUnit = (unitId: string) =>
    router.push({ pathname: '/project/[id]/unit/[unitId]', params: { id: String(projectId), unitId } });

  useLayoutEffect(() => {
    navigation.setOptions({
      title: '住戶資訊',
      headerRight: () => <HeaderButton label={canManage ? '＋ 新增' : '匯出'} onPress={() => setMenu(true)} />,
    });
  }, [navigation, canManage]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!units || !q) return units ?? [];
    return units.filter((u) =>
      [u.unit_no, u.owner_name, u.owner_phone, u.building].some((v) => v?.toLowerCase().includes(q)),
    );
  }, [units, query]);

  async function bulkCreate(text: string) {
    setBulk(false);
    try {
      const r = await api.bulkCreateUnits(projectId, parseUnitList(text));
      setNotice({
        ok: true,
        text: `已新增 ${r.created.length} 戶` + (r.skipped.length ? `；略過 ${r.skipped.length} 戶（已存在）：${r.skipped.join('、')}` : ''),
      });
      await reload();
    } catch (e) {
      setNotice({ ok: false, text: errorText(e) });
    }
  }

  /** 取得 5 分鐘有效的下載連結，交給手機瀏覽器下載；之後可在瀏覽器裡預覽、儲存或分享 */
  async function exportFile(format: 'xlsx' | 'csv') {
    setNotice(null);
    try {
      let filename = '';
      await openLink(async () => {
        const link = await api.unitsExportLink(projectId, format);
        filename = link.filename;
        return link.url;
      });
      setNotice({ ok: true, text: `已在瀏覽器開啟「${filename}」，可從瀏覽器儲存或分享（連結 5 分鐘內有效）` });
    } catch (e) {
      setNotice({ ok: false, text: errorText(e) });
    }
  }

  async function importExcel() {
    setNotice(null);
    setImportErrors(null);
    const file = await pickSpreadsheet();
    if (!file) return;
    const path = `/projects/${projectId}/units/import`;
    try {
      // 先預覽（不寫入），確認後才真的匯入
      setWorking('正在檢查 Excel…');
      const preview = await uploadFile<UnitImportResult>(`${path}?dry_run=true`, file);
      setWorking(null);
      if (preview.errors.length) {
        setImportErrors(preview.errors);
        return;
      }
      if (!preview.created.length && !preview.updated.length) {
        setNotice({ ok: true, text: `Excel 與目前資料相同（${preview.unchanged} 戶），沒有需要更新的內容` });
        return;
      }
      const summary = `新增 ${preview.created.length} 戶、更新 ${preview.updated.length} 戶` + (preview.unchanged ? `，${preview.unchanged} 戶不變` : '');
      if (!(await confirm('匯入 Excel', `${file.name}\n\n將${summary}。\nExcel 裡沒有的戶別不會被刪除。確定匯入？`, '匯入'))) return;

      setWorking('正在匯入…');
      const result = await uploadFile<UnitImportResult>(path, file);
      setNotice({ ok: true, text: `匯入完成：新增 ${result.created.length} 戶、更新 ${result.updated.length} 戶` });
      await reload();
    } catch (e) {
      setNotice({ ok: false, text: errorText(e) });
    } finally {
      setWorking(null);
    }
  }

  const menuOptions: SheetOption[] = [
    ...(canManage
      ? [
          { label: '新增一戶（填寫完整資料）', onPress: () => openUnit('new') },
          { label: '一次新增多戶（貼上戶別清單）', onPress: () => setBulk(true) },
          {
            label: '依棟別與樓層自動產生',
            onPress: () => router.push({ pathname: '/project/[id]/unit-generate', params: { id: String(projectId) } }),
          },
          { label: '從 Excel / CSV 匯入', onPress: importExcel },
        ]
      : []),
    { label: units?.length ? '匯出 Excel（.xlsx）' : '下載空白 Excel 範本', onPress: () => exportFile('xlsx') },
    { label: units?.length ? '匯出 CSV（純文字）' : '下載空白 CSV 範本', onPress: () => exportFile('csv') },
  ];

  return (
    <View style={localStyles.flex}>
      <FlatList
        contentInsetAdjustmentBehavior="automatic" // iOS 半透明標題列時避免內容被擋住
        style={localStyles.list}
        contentContainerStyle={localStyles.content}
        data={filtered}
        keyExtractor={(u) => String(u.id)}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} />}
        keyboardShouldPersistTaps="handled"
        ListHeaderComponent={
          <View style={{ gap: 10 }}>
            {error && <Message kind="error" text={error} />}
            {working && <Message kind="info" text={working} />}
            {notice && <Message kind={notice.ok ? 'ok' : 'error'} text={notice.text} />}
            {importErrors && (
              <Message kind="error" text={`Excel 有 ${importErrors.length} 個錯誤，沒有匯入任何資料。請修正後再匯入：`}>
                {importErrors.slice(0, 30).map((e) => (
                  <Text key={`${e.row}-${e.message}`} style={localStyles.errorLine}>
                    第 {e.row} 列：{e.message}
                  </Text>
                ))}
                {importErrors.length > 30 && <Text style={localStyles.errorLine}>…還有 {importErrors.length - 30} 個錯誤</Text>}
              </Message>
            )}
            {!!units?.length && (
              <TextInput
                style={localStyles.search}
                value={query}
                onChangeText={setQuery}
                placeholder={`搜尋戶別、屋主、電話（共 ${units.length} 戶）`}
                placeholderTextColor={colors.faint}
                autoCorrect={false}
                clearButtonMode="while-editing"
              />
            )}
          </View>
        }
        ListEmptyComponent={
          units && !query ? (
            <Text style={localStyles.empty}>
              {canManage ? '還沒有住戶。點右上角「＋ 新增」：可逐戶新增、貼上清單、依棟別樓層產生，或從 Excel 匯入。' : '還沒有住戶資料'}
            </Text>
          ) : undefined
        }
        renderItem={({ item }) => (
          <ListRow
            title={item.unit_no}
            subtitle={unitSubtitle(item)}
            right={item.owner_email ? undefined : '缺 Email'}
            onPress={() => openUnit(String(item.id))}
          />
        )}
      />

      <ActionSheet visible={menu} title="住戶資料" onClose={() => setMenu(false)} options={menuOptions} />
      <PromptModal
        visible={bulk}
        title="一次新增多戶"
        message={'每行一戶，或用逗號分隔。\n屋主等資料之後再逐戶補上。'}
        placeholder={'A-1F-1\nA-1F-2\nA-2F-1'}
        multiline
        confirmText="新增"
        onCancel={() => setBulk(false)}
        onConfirm={bulkCreate}
      />
    </View>
  );
}

function unitSubtitle(u: Unit): string {
  return [
    u.owner_name,
    u.owner_phone,
    u.area_ping != null && `${u.area_ping} 坪`,
    u.handover_date && `交屋 ${u.handover_date}`,
  ]
    .filter(Boolean)
    .join('　');
}

const localStyles = StyleSheet.create({
  flex: { flex: 1 },
  list: { backgroundColor: colors.bg },
  content: { padding: 16, gap: 10, width: '100%', maxWidth: MAX_WIDTH, alignSelf: 'center' },
  empty: { textAlign: 'center', color: colors.muted, marginTop: 40, lineHeight: 22 },
  errorLine: { fontSize: 14, color: colors.error.fg },
  search: {
    backgroundColor: colors.input,
    borderRadius: 10,
    paddingHorizontal: 14,
    paddingVertical: 10,
    fontSize: 16,
    borderWidth: 1,
    borderColor: colors.border,
  },
});
