import { router, useLocalSearchParams, useNavigation } from 'expo-router';
import { useLayoutEffect } from 'react';
import { RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';

import { Card, HeaderButton, ListRow, Loading, Message, MAX_WIDTH, colors } from '@/components/ui';
import { api } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { PHASES } from '@/lib/labels';
import { useLoad } from '@/lib/useLoad';

export default function ProjectScreen() {
  const id = Number(useLocalSearchParams<{ id: string }>().id);
  const { can } = useAuth();
  const navigation = useNavigation();
  const { data: project, error, refresh, refreshing } = useLoad(() => api.project(id), [id]);

  useLayoutEffect(() => {
    navigation.setOptions({
      title: project?.name ?? '建案',
      headerRight: can('project.manage')
        ? () => (
            <HeaderButton
              label="編輯"
              onPress={() => router.push({ pathname: '/project/[id]/edit', params: { id: String(id) } })}
            />
          )
        : undefined,
    });
  }, [navigation, project, can, id]);

  if (!project) return error ? <Message kind="error" text={error} /> : <Loading />;

  const go = (pathname: '/project/[id]/units' | '/project/[id]/batches' | '/project/[id]/checklist', extra: Record<string, string> = {}) =>
    router.push({ pathname, params: { id: String(id), ...extra } });

  return (
    <ScrollView
      contentInsetAdjustmentBehavior="automatic" // iOS 半透明標題列時避免內容被擋住
      style={{ backgroundColor: colors.bg }}
      contentContainerStyle={localStyles.content}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} />}
    >
      <Card title="建案基本資料">
        <Info label="案名" value={project.name} />
        <Info label="電話" value={project.phone} />
        <Info label="建案地址" value={project.address} />
        {!!project.community_address && <Info label="社區地址" value={project.community_address} />}
        <Info label="社區經理" value={project.community_manager} />
        {!!project.note && <Info label="備註" value={project.note} />}
      </Card>

      <Text style={localStyles.section}>第一階段：建立系統</Text>
      <ListRow title="住戶資訊" subtitle="戶別、屋主、坪數、交屋日期" right={`${project.unit_count} 戶`} onPress={() => go('/project/[id]/units')} />
      <ListRow title="驗屋檢查清單" subtitle="第三階段驗屋使用" onPress={() => go('/project/[id]/checklist', { service: 'inspection' })} />
      <ListRow title="健檢檢查清單" subtitle="第四階段健檢使用" onPress={() => go('/project/[id]/checklist', { service: 'health_check' })} />

      {PHASES.map((p) => (
        <View key={p.service} style={{ gap: 10 }}>
          <Text style={localStyles.section}>{p.phase}：{p.title}</Text>
          <ListRow
            title={`${p.title}日期與時段`}
            subtitle={p.desc}
            right={`${project.batch_counts?.[p.service] ?? 0} 組`}
            onPress={() => go('/project/[id]/batches', { service: p.service })}
          />
        </View>
      ))}
    </ScrollView>
  );
}

function Info({ label, value }: { label: string; value: string | null }) {
  return (
    <View style={localStyles.info}>
      <Text style={localStyles.infoLabel}>{label}</Text>
      <Text style={localStyles.infoValue}>{value || '—'}</Text>
    </View>
  );
}

const localStyles = StyleSheet.create({
  content: { padding: 16, gap: 10, width: '100%', maxWidth: MAX_WIDTH, alignSelf: 'center' },
  section: { fontSize: 13, color: colors.muted, marginTop: 8, marginLeft: 4 },
  info: { flexDirection: 'row', paddingVertical: 3 },
  infoLabel: { width: 76, fontSize: 15, color: colors.muted },
  infoValue: { flex: 1, fontSize: 15, color: colors.text },
});
