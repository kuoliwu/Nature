import { router, useLocalSearchParams, useNavigation } from 'expo-router';
import { useLayoutEffect } from 'react';
import { FlatList, RefreshControl, StyleSheet, Text } from 'react-native';

import { HeaderButton, ListRow, Message, MAX_WIDTH, colors } from '@/components/ui';
import { api, Batch } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { SERVICE_LABEL } from '@/lib/labels';
import { useLoad } from '@/lib/useLoad';

export default function BatchesScreen() {
  const projectId = Number(useLocalSearchParams<{ id: string }>().id);
  const { can } = useAuth();
  const navigation = useNavigation();
  const { data: batches, error, refresh, refreshing } = useLoad(() => api.batches(projectId), [projectId]);

  useLayoutEffect(() => {
    navigation.setOptions({
      title: '健檢日期與時段',
      headerRight: can('batch.manage')
        ? () => (
            <HeaderButton
              label="＋ 新增"
              onPress={() => router.push({ pathname: '/project/[id]/batch-new', params: { id: String(projectId) } })}
            />
          )
        : undefined,
    });
  }, [navigation, can, projectId]);

  return (
    <FlatList
      contentInsetAdjustmentBehavior="automatic" // iOS 半透明標題列時避免內容被擋住
      style={{ backgroundColor: colors.bg }}
      contentContainerStyle={localStyles.content}
      data={batches ?? []}
      keyExtractor={(b) => String(b.id)}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} />}
      ListHeaderComponent={error ? <Message kind="error" text={error} /> : undefined}
      ListEmptyComponent={
        batches ? (
          <Text style={localStyles.empty}>
            {can('batch.manage') ? '還沒有設定健檢日期。點右上角「＋ 新增」選擇日期區間，系統會自動產生 30 分鐘的時段。' : '還沒有設定健檢日期'}
          </Text>
        ) : undefined
      }
      renderItem={({ item }) => (
        <ListRow
          title={`${item.name}${item.is_active ? '' : '（已停用）'}`}
          subtitle={batchSubtitle(item)}
          right={`${item.booked_count} 組已預約`}
          muted={!item.is_active}
          onPress={() => router.push({ pathname: '/batch/[id]', params: { id: String(item.id) } })}
        />
      )}
    />
  );
}

function batchSubtitle(b: Batch): string {
  const range = b.first_date === b.last_date ? b.first_date : `${b.first_date} ～ ${b.last_date}`;
  return `${SERVICE_LABEL[b.service_type]}｜${range}｜${b.day_count} 天、${b.open_slot_count}/${b.slot_count} 個時段開放、每格 ${b.slot_capacity} 組`;
}

const localStyles = StyleSheet.create({
  content: { padding: 16, gap: 10, width: '100%', maxWidth: MAX_WIDTH, alignSelf: 'center' },
  empty: { textAlign: 'center', color: colors.muted, marginTop: 40, lineHeight: 22 },
});
