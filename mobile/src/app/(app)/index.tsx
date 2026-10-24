import { useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { FlatList, RefreshControl, StyleSheet, Text, View } from 'react-native';

import { Message, MAX_WIDTH, colors } from '@/components/ui';
import { api, Project } from '@/lib/api';

export default function ProjectsScreen() {
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      setProjects(await api.projects());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      void load();
    }, [load]),
  );

  async function refresh() {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  }

  return (
    <FlatList
      style={localStyles.list}
      contentContainerStyle={localStyles.content}
      data={projects ?? []}
      keyExtractor={(p) => String(p.id)}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} />}
      ListHeaderComponent={error ? <Message kind="error" text={error} /> : undefined}
      ListEmptyComponent={
        projects ? <Text style={localStyles.empty}>目前沒有建案資料（新增功能將在下一階段加入）</Text> : undefined
      }
      renderItem={({ item }) => (
        <View style={localStyles.row}>
          <Text style={localStyles.name}>{item.name}</Text>
          {item.community_address && <Text style={localStyles.meta}>{item.community_address}</Text>}
          <Text style={localStyles.meta}>
            {[item.phone, item.community_manager && `社區經理 ${item.community_manager}`].filter(Boolean).join('　')}
          </Text>
        </View>
      )}
    />
  );
}

const localStyles = StyleSheet.create({
  list: { backgroundColor: colors.bg },
  content: { padding: 16, gap: 10, width: '100%', maxWidth: MAX_WIDTH, alignSelf: 'center' },
  empty: { textAlign: 'center', color: colors.muted, marginTop: 40 },
  row: { backgroundColor: colors.card, borderRadius: 12, padding: 16, gap: 4 },
  name: { fontSize: 17, fontWeight: '700', color: colors.text },
  meta: { fontSize: 14, color: colors.muted },
});
