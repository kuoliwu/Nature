import { router, useLocalSearchParams, useNavigation } from 'expo-router';
import { ReactNode, useLayoutEffect, useState } from 'react';
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

  const go = (
    pathname: '/project/[id]/units' | '/project/[id]/batches' | '/project/[id]/checklist' | '/project/[id]/handbooks' | '/project/[id]/handbook-template',
    extra: Record<string, string> = {},
  ) =>
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

      <StepGroup no={1} title="開案資訊" timeline={timeline} stepKey="created">
        <ListRow title="住戶資訊" subtitle="戶別、屋主、坪數、交屋日期" right={`${project.unit_count} 戶`} onPress={() => go('/project/[id]/units')} />
        <ListRow title="驗屋檢查清單" subtitle="步驟 4 驗屋使用" onPress={() => go('/project/[id]/checklist', { service: 'inspection' })} />
        <ListRow title="健檢檢查清單" subtitle="步驟 7 健檢使用" onPress={() => go('/project/[id]/checklist', { service: 'health_check' })} />
      </StepGroup>

      <StepGroup no={2} title="預約參觀" timeline={timeline} stepKey="visit">
        {batchesRow('visit')}
        {cover('visit')}
      </StepGroup>

      <StepGroup no={3} title="預約驗屋" timeline={timeline} stepKey="inspection_booking">
        {batchesRow('inspection')}
        {cover('inspection')}
      </StepGroup>

      <StepGroup no={4} title="驗屋" timeline={timeline} stepKey="inspection">
        <ListRow
          title="驗屋與報告"
          subtitle="逐項檢查、屋主簽名、Review OK、寄送驗屋報告（從預約批次進入）"
          right={progress('inspection')}
          onPress={() => go('/project/[id]/batches', { service: 'inspection' })}
        />
      </StepGroup>

      <StepGroup no={5} title="生產履歷＋住屋手冊" timeline={timeline} stepKey="handbook">
        <ListRow
          title="住屋手冊（逐戶）"
          subtitle="生產履歷紀錄、保固與聯絡資訊、該戶 PDF，Review OK 後匯出寄送至售服"
          right={progress('handbook')}
          onPress={() => go('/project/[id]/handbooks')}
        />
        <ListRow
          title="手冊範本與共用 PDF"
          subtitle="保固、聯絡資訊的共用內容，建材型錄、設備說明書等共用 PDF"
          onPress={() => go('/project/[id]/handbook-template')}
        />
      </StepGroup>

      <StepGroup no={6} title="預約健檢" timeline={timeline} stepKey="health_check_booking">
        {batchesRow('health_check')}
        {cover('health_check')}
      </StepGroup>

      <StepGroup no={7} title="健檢" timeline={timeline} stepKey="health_check">
        <ListRow
          title="健檢與報告"
          subtitle="逐項檢查、屋主簽名、Review OK、寄送健檢報告（從預約批次進入）"
          right={progress('health_check')}
          onPress={() => go('/project/[id]/batches', { service: 'health_check' })}
        />
      </StepGroup>
    </ScrollView>
  );
}

/**
 * 一個步驟：左邊直式長方形（步驟編號＋直書標題＋狀態），右邊是這個步驟的各個項目
 *
 *   ┌─┐ 住戶資訊
 *   │1│ 驗屋檢查清單
 *   │開│ 健檢檢查清單
 *   │案│
 *   └─┘
 * 長方形高度跟右邊方塊一樣（上下對齊，不撐高整列）；直書標題放不下時自動縮小字。
 */
function StepGroup(props: { no: number; title: string; timeline: ProjectTimeline | null; stepKey: string; children: ReactNode }) {
  const status = props.timeline?.steps.find((x) => x.key === props.stepKey)?.status;
  const done = status === 'done';
  const active = status === 'active';
  const chars = Array.from(props.title);
  const [height, setHeight] = useState(0);
  // 編號、狀態、上下留白約佔 62px，其餘平分給每個字
  const lineHeight = height ? Math.max(11, Math.min(RAIL_LINE, (height - 62) / chars.length)) : RAIL_LINE;
  const tone = [done && localStyles.railTextDone, active && localStyles.railTextActive];
  return (
    <View style={localStyles.group}>
      <View
        style={[localStyles.rail, done && localStyles.railDone, active && localStyles.railActive]}
        onLayout={(e) => setHeight(e.nativeEvent.layout.height)}
        accessibilityLabel={`步驟 ${props.no}：${props.title}${status ? `（${STEP_STATUS_LABEL[status]}）` : ''}`}
      >
        <View style={localStyles.railInner}>
          <Text style={[localStyles.railNo, done && localStyles.railTextDone]}>{props.no}</Text>
          {chars.map((ch, i) => (
            <Text key={i} style={[localStyles.railChar, { lineHeight, fontSize: Math.min(15, lineHeight * 0.85) }, ...tone]}>
              {ch}
            </Text>
          ))}
          {status && <Text style={[localStyles.railStatus, ...tone]}>{done ? '✓' : active ? '●' : '○'}</Text>}
        </View>
      </View>
      <View style={localStyles.groupBody}>{props.children}</View>
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

const RAIL_LINE = 18; // 直書標題每個字的行高（放得下時）
const localStyles = StyleSheet.create({
  content: { padding: 16, gap: 10, width: '100%', maxWidth: MAX_WIDTH, alignSelf: 'center' },
  group: { flexDirection: 'row', gap: 8, marginTop: 6 },
  groupBody: { flex: 1, gap: 8 },
  // 直式長方形：完成＝實心主題色、進行中＝主題色外框、未開始＝灰底
  rail: { width: 40, borderRadius: 10, overflow: 'hidden', backgroundColor: colors.chip, borderWidth: 1, borderColor: colors.chip },
  // 內容絕對定位：長方形本身不撐高，高度由右邊方塊決定
  railInner: { ...StyleSheet.absoluteFill, alignItems: 'center', justifyContent: 'center', paddingVertical: 8 },
  railDone: { backgroundColor: colors.primary, borderColor: colors.primary },
  railActive: { backgroundColor: colors.accentBg, borderColor: colors.primary },
  railNo: { fontSize: 13, lineHeight: 16, fontWeight: '800', color: colors.muted, marginBottom: 4 },
  railChar: { fontWeight: '700', color: colors.textSecondary },
  railStatus: { fontSize: 12, lineHeight: 15, color: colors.muted, marginTop: 4 },
  railTextDone: { color: colors.onPrimary },
  railTextActive: { color: colors.primary },
  info: { flexDirection: 'row', paddingVertical: 3 },
  infoLabel: { width: 76, fontSize: 15, color: colors.muted },
  infoValue: { flex: 1, fontSize: 15, color: colors.text },
});
