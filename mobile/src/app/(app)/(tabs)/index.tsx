import { router, useNavigation } from 'expo-router';
import { useLayoutEffect, useState } from 'react';
import { FlatList, Pressable, RefreshControl, StyleSheet, Text, View } from 'react-native';

import { ActionSheet } from '@/components/overlays';
import { useSheetTransfer } from '@/components/SheetTransfer';
import { Timeline } from '@/components/Timeline';
import { HeaderButton, Message, MAX_WIDTH, colors } from '@/components/ui';
import { api } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { useLoad } from '@/lib/useLoad';

export default function ProjectsScreen() {
  const { can } = useAuth();
  const navigation = useNavigation();
  // 建案與時間軸一起載入；時間軸失敗不影響列表
  const { data, error, reload, refresh, refreshing } = useLoad(
    () => Promise.all([api.projects(), api.timelines().catch(() => [])]),
    [],
  );
  const projects = data?.[0];
  const timelines = new Map((data?.[1] ?? []).map((t) => [t.project.id, t]));
  const [menu, setMenu] = useState(false);
  const sheet = useSheetTransfer('projects', {}, { label: '建案', unit: '個建案', canImport: can('project.manage'), onImported: reload });

  useLayoutEffect(() => {
    navigation.setOptions({
      headerRight: () => (
        <View style={{ flexDirection: 'row' }}>
          <HeaderButton label="Excel" onPress={() => setMenu(true)} />
          {can('project.manage') && (
            <HeaderButton label="＋ 新增" onPress={() => router.push({ pathname: '/project/[id]/edit', params: { id: 'new' } })} />
          )}
        </View>
      ),
    });
  }, [navigation, can]);

  return (
    <>
    <FlatList
      contentInsetAdjustmentBehavior="automatic" // iOS 半透明標題列時避免內容被擋住
      style={localStyles.list}
      contentContainerStyle={localStyles.content}
      data={projects ?? []}
      keyExtractor={(p) => String(p.id)}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} />}
      ListHeaderComponent={
        error || sheet.status ? (
          <View style={{ gap: 8 }}>
            {error && <Message kind="error" text={error} />}
            {sheet.status}
          </View>
        ) : undefined
      }
      ListEmptyComponent={
        projects ? (
          <Text style={localStyles.empty}>
            {can('project.manage') ? '還沒有建案，點右上角「＋ 新增」建立第一個建案' : '目前沒有建案資料'}
          </Text>
        ) : undefined
      }
      renderItem={({ item }) => {
        const timeline = timelines.get(item.id);
        return (
          <Pressable
            style={({ pressed }) => [localStyles.card, pressed && { opacity: 0.7 }]}
            onPress={() => router.push({ pathname: '/project/[id]', params: { id: String(item.id) } })}
          >
            <View style={localStyles.head}>
              <View style={{ flex: 1 }}>
                <Text style={localStyles.name}>{item.name}</Text>
                <Text style={localStyles.sub} numberOfLines={1}>
                  {[item.address ?? item.community_address, item.community_manager && `社區經理 ${item.community_manager}`]
                    .filter(Boolean)
                    .join('　') || '—'}
                </Text>
              </View>
              <Text style={localStyles.right}>{item.unit_count} 戶</Text>
              <Text style={localStyles.chevron}>›</Text>
            </View>
            {timeline && <Timeline data={timeline} />}
          </Pressable>
        );
      }}
    />
    <ActionSheet visible={menu} title="建案列表 Excel" options={sheet.options} onClose={() => setMenu(false)} />
    </>
  );
}

const localStyles = StyleSheet.create({
  list: { backgroundColor: colors.bg },
  content: { padding: 16, gap: 10, width: '100%', maxWidth: MAX_WIDTH, alignSelf: 'center' },
  empty: { textAlign: 'center', color: colors.muted, marginTop: 40, lineHeight: 22 },
  card: { backgroundColor: colors.card, borderRadius: 12, paddingVertical: 14, paddingHorizontal: 12, gap: 6 },
  head: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: 4 },
  name: { fontSize: 16, fontWeight: '700', color: colors.text },
  sub: { fontSize: 13, color: colors.muted, marginTop: 2 },
  right: { fontSize: 14, color: colors.muted },
  chevron: { fontSize: 22, color: '#9ca3af', marginLeft: 4 },
});
