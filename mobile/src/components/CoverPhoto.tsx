/** 建案的屋主預約頁封面照片（預售屋照片／成屋照片）：縮圖＋拍照／相簿／刪除 */
import { useState } from 'react';
import { ActivityIndicator, Image, Pressable, StyleSheet, Text, View } from 'react-native';

import type { Project, ServiceType } from '@/lib/api';
import { api } from '@/lib/api';
import { confirm } from '@/lib/dialogs';
import { openLink } from '@/lib/download';
import { pickImage, uploadFile } from '@/lib/files';
import { ActionSheet, SheetOption } from './overlays';
import { colors } from './ui';

export function CoverPhotoRow(props: {
  project: Project;
  service: ServiceType;
  title: string;
  hint: string;
  canEdit: boolean;
  onChanged: (p: Project) => void;
  onError: (e: unknown) => void;
}) {
  const url = props.project.covers?.[props.service] ?? null;
  const [menu, setMenu] = useState(false);
  const [busy, setBusy] = useState(false);

  async function upload(source: 'camera' | 'library') {
    try {
      const file = await pickImage(source);
      if (!file) return;
      setBusy(true);
      props.onChanged(await uploadFile<Project>(`/projects/${props.project.id}/covers/${props.service}`, file));
    } catch (e) {
      props.onError(e);
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!(await confirm('刪除照片', `確定要刪除「${props.title}」？屋主預約頁將不再顯示封面。`, '刪除', true))) return;
    try {
      props.onChanged(await api.deleteCover(props.project.id, props.service));
    } catch (e) {
      props.onError(e);
    }
  }

  const options: SheetOption[] = [
    ...(url ? [{ label: '查看大圖', onPress: () => void openLink(async () => url).catch(props.onError) }] : []),
    ...(props.canEdit
      ? [
          { label: url ? '拍照更換' : '拍照', onPress: () => void upload('camera') },
          { label: url ? '從相簿選擇更換' : '從相簿選擇', onPress: () => void upload('library') },
          ...(url ? [{ label: '刪除照片', destructive: true, onPress: () => void remove() }] : []),
        ]
      : []),
  ];

  return (
    <>
      <Pressable
        style={({ pressed }) => [s.row, pressed && { opacity: 0.7 }]}
        disabled={options.length === 0 || busy}
        onPress={() => setMenu(true)}
      >
        <View style={s.thumb}>
          {busy ? <ActivityIndicator /> : url ? <Image source={{ uri: url }} style={s.img} /> : <Text style={s.none}>無</Text>}
        </View>
        <View style={{ flex: 1 }}>
          <Text style={s.title}>{props.title}</Text>
          <Text style={s.hint}>{busy ? '上傳中…' : url ? props.hint : `尚未上傳・${props.hint}`}</Text>
        </View>
        {options.length > 0 && <Text style={s.chevron}>›</Text>}
      </Pressable>
      <ActionSheet visible={menu} title={props.title} options={options} onClose={() => setMenu(false)} />
    </>
  );
}

const s = StyleSheet.create({
  row: { backgroundColor: colors.card, borderRadius: 12, paddingHorizontal: 16, paddingVertical: 10, flexDirection: 'row', alignItems: 'center', gap: 12 },
  thumb: { width: 72, height: 48, borderRadius: 6, backgroundColor: colors.bg, alignItems: 'center', justifyContent: 'center', overflow: 'hidden' },
  img: { width: 72, height: 48 },
  none: { fontSize: 12, color: colors.muted },
  title: { fontSize: 16, fontWeight: '600', color: colors.text },
  hint: { fontSize: 13, color: colors.muted, marginTop: 2 },
  chevron: { fontSize: 22, color: '#9ca3af', marginLeft: 4 },
});
