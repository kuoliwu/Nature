import { router, useLocalSearchParams, useNavigation } from 'expo-router';
import { useLayoutEffect, useState } from 'react';
import { RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';

import { CoverPhotoRow } from '@/components/CoverPhoto';
import { ProjectDashboard } from '@/components/ProjectDashboard';
import { Timeline } from '@/components/Timeline';
import { Card, HeaderButton, ListRow, Loading, Message, MAX_WIDTH, colors } from '@/components/ui';
import { api, ProjectTimeline, ServiceType } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { errorText } from '@/lib/dialogs';
import { PHASES } from '@/lib/labels';
import { STEP_STATUS_LABEL } from '@/lib/timeline';
import { useLoad } from '@/lib/useLoad';

export default function ProjectScreen() {
  const id = Number(useLocalSearchParams<{ id: string }>().id);
  const { can } = useAuth();
  const navigation = useNavigation();
  const { data: project, setData: setProject, error, refresh, refreshing } = useLoad(() => api.project(id), [id]);
  const { data: dashboard, refresh: refreshDashboard } = useLoad(() => api.dashboard(id).catch(() => null), [id]);
  const { data: timeline, refresh: refreshTimeline } = useLoad(() => api.timeline(id).catch(() => null), [id]);
  const [coverError, setCoverError] = useState<string | null>(null);

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
  const phase = (service: ServiceType) => PHASES.find((p) => p.service === service)!;
  const cover = (service: ServiceType) => (
    <CoverPhotoRow
      project={project}
      service={service}
      title={phase(service).cover.title}
      hint={phase(service).cover.hint}
      canEdit={can('project.manage')}
      onChanged={(p) => {
        setCoverError(null);
        setProject(p);
      }}
      onError={(e) => setCoverError(errorText(e))}
    />
  );
  const batchesRow = (service: ServiceType) => (
    <ListRow
      title={`${phase(service).title}日期與時段`}
      subtitle={phase(service).desc}
      right={`${project.batch_counts?.[service] ?? 0} 組`}
      onPress={() => go('/project/[id]/batches', { service })}
    />
  );
  const progress = (key: string) => {
    const st = timeline?.steps.find((x) => x.key === key);
    return st ? `${st.done}/${st.total} 戶` : undefined;
  };

  return (
    <ScrollView
      contentInsetAdjustmentBehavior="automatic" // iOS 半透明標題列時避免內容被擋住
      style={{ backgroundColor: colors.bg }}
      contentContainerStyle={localStyles.content}
      refreshControl={
        <RefreshControl refreshing={refreshing} onRefresh={() => void Promise.all([refresh(), refreshDashboard(), refreshTimeline()])} />
      }
    >
      {timeline && (
        <Card title="售服進度">
          <Timeline data={timeline} interactive />
        </Card>
      )}

      {dashboard && <ProjectDashboard data={dashboard} projectId={id} />}

      <Card title="建案基本資料">
        <Info label="案名" value={project.name} />
        <Info label="電話" value={project.phone} />
        <Info label="建案地址" value={project.address} />
        {!!project.community_address && <Info label="社區地址" value={project.community_address} />}
        <Info label="社區經理" value={project.community_manager} />
        {!!project.note && <Info label="備註" value={project.note} />}
      </Card>

      {coverError && <Message kind="error" text={coverError} />}

      <StepHeader no={1} title="新建案" timeline={timeline} stepKey="created" />
      <ListRow title="住戶資訊" subtitle="戶別、屋主、坪數、交屋日期" right={`${project.unit_count} 戶`} onPress={() => go('/project/[id]/units')} />
      <ListRow title="驗屋檢查清單" subtitle="步驟 4 驗屋使用" onPress={() => go('/project/[id]/checklist', { service: 'inspection' })} />
      <ListRow title="健檢檢查清單" subtitle="步驟 7 健檢使用" onPress={() => go('/project/[id]/checklist', { service: 'health_check' })} />

      <StepHeader no={2} title="預約參觀" timeline={timeline} stepKey="visit" />
      {batchesRow('visit')}
      {cover('visit')}

      <StepHeader no={3} title="預約驗屋" timeline={timeline} stepKey="inspection_booking" />
      {batchesRow('inspection')}
      {cover('inspection')}

      <StepHeader no={4} title="驗屋" timeline={timeline} stepKey="inspection" />
      <ListRow
        title="驗屋與報告"
        subtitle="逐項檢查、屋主簽名、Review OK、寄送驗屋報告（從預約批次進入）"
        right={progress('inspection')}
        onPress={() => go('/project/[id]/batches', { service: 'inspection' })}
      />

      <StepHeader no={5} title="生產履歷＋住屋手冊" timeline={timeline} stepKey="handbook" />
      <ListRow title="生產履歷＋住屋手冊" subtitle="各戶工地照片、廠商通訊錄，交屋時製作 PDF 寄給屋主（下一版開放）" muted />

      <StepHeader no={6} title="預約健檢" timeline={timeline} stepKey="health_check_booking" />
      {batchesRow('health_check')}
      {cover('health_check')}

      <StepHeader no={7} title="健檢" timeline={timeline} stepKey="health_check" />
      <ListRow
        title="健檢與報告"
        subtitle="逐項檢查、屋主簽名、Review OK、寄送健檢報告（從預約批次進入）"
        right={progress('health_check')}
        onPress={() => go('/project/[id]/batches', { service: 'health_check' })}
      />
    </ScrollView>
  );
}

function StepHeader(props: { no: number; title: string; timeline: ProjectTimeline | null; stepKey: string }) {
  const status = props.timeline?.steps.find((x) => x.key === props.stepKey)?.status;
  return (
    <View style={localStyles.stepHead}>
      <Text style={localStyles.section}>
        步驟 {props.no}：{props.title}
      </Text>
      {status && (
        <Text style={[localStyles.badge, status === 'done' ? localStyles.badgeDone : status === 'active' ? localStyles.badgeActive : null]}>
          {STEP_STATUS_LABEL[status]}
        </Text>
      )}
    </View>
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
  section: { fontSize: 13, color: colors.muted, marginLeft: 4 },
  stepHead: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 8 },
  badge: { fontSize: 11, color: colors.muted, backgroundColor: '#e5e7eb', paddingHorizontal: 6, paddingVertical: 1, borderRadius: 8, overflow: 'hidden' },
  badgeDone: { color: '#fff', backgroundColor: colors.primary },
  badgeActive: { color: colors.primary, backgroundColor: '#dbeafe' },
  info: { flexDirection: 'row', paddingVertical: 3 },
  infoLabel: { width: 76, fontSize: 15, color: colors.muted },
  infoValue: { flex: 1, fontSize: 15, color: colors.text },
});
