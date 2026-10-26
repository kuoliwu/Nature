/** 住屋手冊的外部 PDF 清單（依合併順序）：開啟、上移／下移、刪除 */
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { colors } from './ui';
import type { HandbookAttachment } from '@/lib/api';
import { openLink } from '@/lib/download';

export function HandbookAttachmentList(props: {
  items: HandbookAttachment[];
  editable: boolean;
  /** 單戶畫面：建案共用的 PDF 只顯示，在範本畫面才能調整 */
  lockShared?: boolean;
  onMove: (a: HandbookAttachment, direction: 'up' | 'down') => void;
  onDelete: (a: HandbookAttachment) => void;
}) {
  if (props.items.length === 0) return <Text style={s.empty}>（尚未上傳）</Text>;
  return (
    <View>
      {props.items.map((a, i) => {
        const group = props.items.filter((x) => x.shared === a.shared);
        const pos = group.indexOf(a);
        const canEdit = props.editable && !(props.lockShared && a.shared);
        return (
          <View key={a.id} style={s.row}>
            <Text style={s.no}>{i + 1}</Text>
            <Pressable style={s.main} onPress={() => void openLink(async () => a.url)}>
              <Text style={s.title} numberOfLines={2}>
                📄 {a.title}
              </Text>
              <Text style={s.meta}>
                {a.shared ? '建案共用・' : ''}
                {a.page_count} 頁・{fileSize(a.size)}
              </Text>
            </Pressable>
            {canEdit && (
              <View style={s.actions}>
                <Action label="↑" disabled={pos === 0} onPress={() => props.onMove(a, 'up')} />
                <Action label="↓" disabled={pos === group.length - 1} onPress={() => props.onMove(a, 'down')} />
                <Action label="✕" danger onPress={() => props.onDelete(a)} />
              </View>
            )}
          </View>
        );
      })}
    </View>
  );
}

const fileSize = (bytes: number) => (bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`);

function Action(props: { label: string; onPress: () => void; disabled?: boolean; danger?: boolean }) {
  return (
    <Pressable
      onPress={props.onPress}
      disabled={props.disabled}
      hitSlop={6}
      accessibilityLabel={{ '↑': '上移', '↓': '下移', '✕': '刪除' }[props.label]}
      style={({ pressed }) => [s.action, (pressed || props.disabled) && { opacity: 0.3 }]}
    >
      <Text style={[s.actionText, props.danger && { color: colors.danger }]}>{props.label}</Text>
    </Pressable>
  );
}

const s = StyleSheet.create({
  empty: { fontSize: 13, color: colors.faint, marginTop: 6 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 8, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border },
  no: { width: 18, fontSize: 13, color: colors.muted, textAlign: 'center' },
  main: { flex: 1 },
  title: { fontSize: 15, color: colors.primary },
  meta: { fontSize: 12, color: colors.muted, marginTop: 2 },
  actions: { flexDirection: 'row', gap: 4 },
  action: { width: 32, height: 32, borderRadius: 8, borderWidth: 1, borderColor: colors.border, alignItems: 'center', justifyContent: 'center' },
  actionText: { fontSize: 15, color: colors.text },
});
