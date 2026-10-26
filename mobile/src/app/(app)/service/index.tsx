import { router, useNavigation } from 'expo-router';
import { useLayoutEffect, useRef, useState } from 'react';
import { Animated, ImageBackground, Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';

import { useDragSort } from '@/components/DragSort';
import { ActionSheet } from '@/components/overlays';
import { useSheetTransfer } from '@/components/SheetTransfer';
import { Timeline } from '@/components/Timeline';
import { SwipeRow, SwipeSide } from '@/components/SwipeRow';
import { HeaderButton, Message, MAX_WIDTH, colors } from '@/components/ui';
import { api, Project, ProjectImportResult } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { confirm, errorText } from '@/lib/dialogs';
import { openLink } from '@/lib/download';
import { pickBackupZip, uploadFile } from '@/lib/files';
import { useLoad } from '@/lib/useLoad';

export default function ProjectsScreen() {
  const { can } = useAuth();
  const navigation = useNavigation();
  // 建案與時間軸一起載入；時間軸失敗不影響列表
  const { data, error, setError, reload, refresh, refreshing } = useLoad(
    () => Promise.all([api.projects(), api.timelines().catch(() => [])]),
    [],
  );
  const projects = data?.[0];
  const timelines = new Map((data?.[1] ?? []).map((t) => [t.project.id, t]));
  const [menu, setMenu] = useState(false);
  // 目前滑開的那一列（一次只開一列）
  const [swiped, setSwiped] = useState<{ id: number; side: SwipeSide } | null>(null);
  // 滑動剛結束時（電腦滑鼠拖曳放開），卡片還會收到一次點擊，要忽略
  const swipedAt = useRef(0);
  // 長按後上下拖曳排序：釘選的固定在前面，只能在同一群裡移動；放開後存成自己的順序
  const drag = useDragSort({
    items: projects,
    keyOf: (p) => p.id,
    groupOf: (p) => p.pinned,
    onDrop: (ordered) => {
      swipedAt.current = Date.now();
      void run(() => api.saveProjectOrder(ordered.map((p) => p.id)));
    },
  });

  async function run(action: () => Promise<unknown>) {
    try {
      setError(null);
      await action();
      await reload();
    } catch (e) {
      setError(errorText(e));
    }
  }

  const [notice, setNotice] = useState<string | null>(null);

  /** 建案備份檔（.zip）：資料＋照片、簽名、報告等檔案；刪除後可以從右上角「匯入匯出」還原 */
  async function backup(p: Project) {
    setError(null);
    setNotice(null);
    try {
      await openLink(async () => (await api.projectBackupLink(p.id)).url);
      setNotice(`已開始下載「${p.name}」的建案備份檔（.zip），請妥善保存`);
    } catch (e) {
      setError(errorText(e));
    }
  }

  async function restore() {
    setNotice(null);
    try {
      const file = await pickBackupZip();
      if (!file) return;
      setNotice(`還原中：${file.name}…`);
      const result = await uploadFile<ProjectImportResult>('/projects/import', file);
      await reload();
      const c = result.counts;
      setNotice(`已還原「${result.project.name}」：${c.units ?? 0} 戶、${c.bookings ?? 0} 筆預約、${(c.inspection_photos ?? 0) + (c.handbook_photos ?? 0)} 張照片`);
    } catch (e) {
      setNotice(null);
      setError(errorText(e));
    }
  }

  const togglePin = (p: Project) => run(() => (p.pinned ? api.unpinProject(p.id) : api.pinProject(p.id)));

  async function remove(p: Project) {
    const ok = await confirm(
      '刪除建案',
      `確定要刪除「${p.name}」？\n住戶、預約、驗屋結果、照片、住屋手冊會一併刪除。\n\n建議先往左滑按「備份」下載建案備份檔，之後可以從右上角「匯入匯出」→「從建案備份檔還原」救回來。`,
      '刪除',
      true,
    );
    if (ok) await run(() => api.deleteProject(p.id));
  }
  const sheet = useSheetTransfer('projects', {}, { label: '建案', unit: '個建案', canImport: can('project.manage'), onImported: reload });

  useLayoutEffect(() => {
    navigation.setOptions({
      headerRight: () => (
        <View style={{ flexDirection: 'row' }}>
          <HeaderButton label="匯入匯出" onPress={() => setMenu(true)} />
          {can('project.manage') && (
            <HeaderButton label="＋ 新增" onPress={() => router.push({ pathname: '/project/[id]/edit', params: { id: 'new' } })} />
          )}
        </View>
      ),
    });
  }, [navigation, can]);

  return (
    <>
    <ScrollView
      contentInsetAdjustmentBehavior="automatic" // iOS 半透明標題列時避免內容被擋住
      style={localStyles.list}
      contentContainerStyle={localStyles.content}
      scrollEnabled={drag.dragging === null} // 拖曳排序時不要捲動
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} />}
    >
      {(error || notice || sheet.status) && (
        <View style={{ gap: 8 }}>
          {error && <Message kind="error" text={error} />}
          {notice && <Message kind="ok" text={notice} />}
          {sheet.status}
        </View>
      )}
      {drag.dragging !== null && <Text style={localStyles.dragHint}>拖到想要的位置後放開</Text>}
      {projects && projects.length === 0 && (
        <Text style={localStyles.empty}>
          {can('project.manage') ? '還沒有建案，點右上角「＋ 新增」建立第一個建案' : '目前沒有建案資料'}
        </Text>
      )}
      {drag.list.map((item) => {
        const timeline = timelines.get(item.id);
        const open = swiped?.id === item.id ? swiped.side : null;
        return (
          <Animated.View key={item.id} {...drag.rowProps(item.id)}>
            <SwipeRow
              open={open}
              onOpenChange={(side) => {
                swipedAt.current = Date.now();
                setSwiped(side ? { id: item.id, side } : null);
              }}
              left={{
                label: item.pinned ? '取消釘選' : '釘選',
                icon: '📌',
                color: colors.primary,
                textColor: colors.onPrimary,
                onPress: () => void togglePin(item),
              }}
              right={
                can('project.manage')
                  ? [
                      { label: '備份', icon: '💾', color: colors.green, textColor: colors.onPrimary, onPress: () => void backup(item) },
                      { label: '刪除', icon: '🗑', color: colors.danger, textColor: colors.onPrimary, onPress: () => void remove(item) },
                    ]
                  : undefined
              }
            >
              <Pressable
                style={({ pressed }) => [
                  localStyles.card,
                  pressed && drag.dragging === null && { opacity: 0.7 },
                  drag.dragging === item.id && localStyles.cardLifted,
                ]}
                delayLongPress={350}
                onLongPress={() => {
                  setSwiped(null);
                  drag.begin(item.id);
                }}
                onPressOut={drag.endIfIdle}
                // 滑開時點一下先收回，不進入建案
                onPress={() => {
                  if (Date.now() - swipedAt.current < 400) return;
                  if (open) setSwiped(null);
                  else router.push({ pathname: '/project/[id]', params: { id: String(item.id) } });
                }}
              >
                {/* 左：案名方塊（有封面照片就當背景）｜右：售服時間軸 */}
                <ProjectTile
                  name={item.name}
                  units={item.unit_count}
                  photo={item.covers.health_check ?? item.covers.inspection ?? item.covers.visit}
                  pinned={item.pinned}
                />
                <View style={localStyles.timeline}>
                  {timeline ? <Timeline data={timeline} compact /> : <Text style={localStyles.sub}>—</Text>}
                </View>
              </Pressable>
            </SwipeRow>
          </Animated.View>
        );
      })}
    </ScrollView>
    <ActionSheet
      visible={menu}
      title="建案列表 匯入匯出"
      options={[
        ...sheet.options,
        ...(can('project.manage') ? [{ label: '從建案備份檔還原（.zip）', onPress: () => void restore() }] : []),
      ]}
      onClose={() => setMenu(false)}
    />
    </>
  );
}

function ProjectTile(props: { name: string; units: number; photo: string | null; pinned: boolean }) {
  const body = (
    <View style={localStyles.tileShade}>
      {props.pinned && <Text style={localStyles.pin} accessibilityLabel="已釘選">📌</Text>}
      <Text style={localStyles.tileName} numberOfLines={3}>
        {props.name}
      </Text>
      <Text style={localStyles.tileUnits}>{props.units} 戶</Text>
    </View>
  );
  return props.photo ? (
    <ImageBackground source={{ uri: props.photo }} style={localStyles.tile} imageStyle={{ borderRadius: 10 }}>
      {body}
    </ImageBackground>
  ) : (
    <View style={[localStyles.tile, localStyles.tilePlain]}>{body}</View>
  );
}

const TILE = 96;
const localStyles = StyleSheet.create({
  list: { backgroundColor: colors.bg },
  content: { padding: 16, gap: 10, width: '100%', maxWidth: MAX_WIDTH, alignSelf: 'center' },
  empty: { textAlign: 'center', color: colors.muted, marginTop: 40, lineHeight: 22 },
  dragHint: { textAlign: 'center', color: colors.primary, fontSize: 13, fontWeight: '600' },
  cardLifted: { borderWidth: 2, borderColor: colors.primary }, // 長按後浮起的卡片
  card: { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: colors.card, borderRadius: 12, padding: 8, borderWidth: 2, borderColor: 'transparent' },
  timeline: { flex: 1, justifyContent: 'center' },
  sub: { fontSize: 13, color: colors.muted, textAlign: 'center' },
  tile: { width: TILE, height: TILE, borderRadius: 10, overflow: 'hidden' },
  tilePlain: { backgroundColor: colors.accentBg, borderWidth: 1, borderColor: colors.accentBorder },
  // 照片上的字一律白字＋半透明黑底，不管主題
  tileShade: { flex: 1, justifyContent: 'flex-end', padding: 8, backgroundColor: 'rgba(0,0,0,0.38)' },
  tileName: { fontSize: 15, fontWeight: '700', color: '#fff', lineHeight: 19 },
  pin: { position: 'absolute', top: 4, right: 4, fontSize: 14 },
  tileUnits: { fontSize: 12, color: 'rgba(255,255,255,0.85)', marginTop: 2 },
});
