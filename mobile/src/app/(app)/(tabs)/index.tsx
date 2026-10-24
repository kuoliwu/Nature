import { router, useNavigation } from 'expo-router';
import { useLayoutEffect } from 'react';
import { FlatList, RefreshControl, StyleSheet, Text } from 'react-native';

import { HeaderButton, ListRow, Message, MAX_WIDTH, colors } from '@/components/ui';
import { api } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { useLoad } from '@/lib/useLoad';

export default function ProjectsScreen() {
  const { can } = useAuth();
  const navigation = useNavigation();
  const { data: projects, error, refresh, refreshing } = useLoad(() => api.projects(), []);

  useLayoutEffect(() => {
    navigation.setOptions({
      headerRight: can('project.manage') ? () => <HeaderButton label="＋ 新增" onPress={() => router.push({ pathname: '/project/[id]/edit', params: { id: 'new' } })} /> : undefined,
    });
  }, [navigation, can]);

  return (
    <FlatList
      contentInsetAdjustmentBehavior="automatic" // iOS 半透明標題列時避免內容被擋住
      style={localStyles.list}
      contentContainerStyle={localStyles.content}
      data={projects ?? []}
      keyExtractor={(p) => String(p.id)}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} />}
      ListHeaderComponent={error ? <Message kind="error" text={error} /> : undefined}
      ListEmptyComponent={
        projects ? (
          <Text style={localStyles.empty}>
            {can('project.manage') ? '還沒有建案，點右上角「＋ 新增」建立第一個建案' : '目前沒有建案資料'}
          </Text>
        ) : undefined
      }
      renderItem={({ item }) => (
        <ListRow
          title={item.name}
          subtitle={[item.address ?? item.community_address, item.community_manager && `社區經理 ${item.community_manager}`]
            .filter(Boolean)
            .join('　')}
          right={`${item.unit_count} 戶`}
          onPress={() => router.push({ pathname: '/project/[id]', params: { id: String(item.id) } })}
        />
      )}
    />
  );
}

const localStyles = StyleSheet.create({
  list: { backgroundColor: colors.bg },
  content: { padding: 16, gap: 10, width: '100%', maxWidth: MAX_WIDTH, alignSelf: 'center' },
  empty: { textAlign: 'center', color: colors.muted, marginTop: 40, lineHeight: 22 },
});
