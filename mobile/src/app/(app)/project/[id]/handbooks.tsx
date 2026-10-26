import { router, useLocalSearchParams, useNavigation } from 'expo-router';
import { useLayoutEffect } from 'react';
import { FlatList, RefreshControl, StyleSheet, Text } from 'react-native';

import { HeaderButton, ListRow, Message, MAX_WIDTH, colors } from '@/components/ui';
import { api, HandbookUnitRow } from '@/lib/api';
import { HANDBOOK_STATUS_LABEL } from '@/lib/labels';
import { useLoad } from '@/lib/useLoad';

/** 步驟 5：各戶住屋手冊的進度 */
export default function HandbooksScreen() {
  const projectId = Number(useLocalSearchParams<{ id: string }>().id);
  const navigation = useNavigation();
  const { data: rows, error, refresh, refreshing } = useLoad(() => api.handbooks(projectId), [projectId]);

  useLayoutEffect(() => {
    navigation.setOptions({
      title: '生產履歷＋住屋手冊',
      headerRight: () => (
        <HeaderButton label="範本" onPress={() => router.push({ pathname: '/project/[id]/handbook-template', params: { id: String(projectId) } })} />
      ),
    });
  }, [navigation, projectId]);

  const sent = rows?.filter((r) => r.status === 'sent').length ?? 0;

  return (
    <FlatList
      contentInsetAdjustmentBehavior="automatic" // iOS 半透明標題列時避免內容被擋住
      style={{ backgroundColor: colors.bg }}
      contentContainerStyle={localStyles.content}
      data={rows ?? []}
      keyExtractor={(r) => String(r.unit_id)}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} />}
      ListHeaderComponent={
        <>
          {error && <Message kind="error" text={error} />}
          {rows && rows.length > 0 && (
            <Text style={localStyles.summary}>
              已寄送 {sent}/{rows.length} 戶。點住戶新增生產履歷紀錄、填寫手冊內容、上傳該戶 PDF，Review OK 後匯出寄送至售服；共用欄位與 PDF 在右上角「範本」。
            </Text>
          )}
        </>
      }
      ListEmptyComponent={rows ? <Text style={localStyles.empty}>還沒有住戶，請先到步驟 1「住戶資訊」新增。</Text> : undefined}
      renderItem={({ item }) => (
        <ListRow
          title={`${item.unit_no}${item.owner_name ? `　${item.owner_name}` : ''}`}
          subtitle={rowSubtitle(item)}
          right={HANDBOOK_STATUS_LABEL[item.status]}
          onPress={() => router.push({ pathname: '/project/[id]/handbook/[unitId]', params: { id: String(projectId), unitId: String(item.unit_id) } })}
        />
      )}
    />
  );
}

function rowSubtitle(r: HandbookUnitRow): string {
  if (r.status === 'sent' && r.sent_at) return `已寄送 ${r.sent_at.slice(0, 10)}`;
  const parts = [r.missing ? `必填尚缺 ${r.missing} 項` : '必填已完整'];
  if (r.entries) parts.push(`履歷紀錄 ${r.entries} 筆`);
  if (r.attachments) parts.push(`專屬 PDF ${r.attachments} 份`);
  return parts.join('・');
}

const localStyles = StyleSheet.create({
  content: { padding: 16, gap: 10, width: '100%', maxWidth: MAX_WIDTH, alignSelf: 'center' },
  summary: { fontSize: 13, color: colors.muted, lineHeight: 19, marginBottom: 4 },
  empty: { textAlign: 'center', color: colors.muted, marginTop: 40, lineHeight: 22 },
});
