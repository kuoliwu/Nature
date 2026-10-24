/** 跨平台的輸入對話框與選單（Alert.prompt 只有 iOS 有，所以自己做） */
import { useEffect, useState } from 'react';
import { KeyboardAvoidingView, Modal, Platform, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import { colors } from './ui';

export function PromptModal(props: {
  visible: boolean;
  title: string;
  message?: string;
  initialValue?: string;
  placeholder?: string;
  multiline?: boolean;
  confirmText?: string;
  onCancel: () => void;
  onConfirm: (value: string) => void;
}) {
  const [value, setValue] = useState(props.initialValue ?? '');
  useEffect(() => {
    if (props.visible) setValue(props.initialValue ?? '');
  }, [props.visible, props.initialValue]);

  return (
    <Modal visible={props.visible} transparent animationType="fade" onRequestClose={props.onCancel}>
      <KeyboardAvoidingView style={localStyles.backdrop} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <View style={localStyles.dialog}>
          <Text style={localStyles.title}>{props.title}</Text>
          {props.message && <Text style={localStyles.message}>{props.message}</Text>}
          <TextInput
            style={[localStyles.input, props.multiline && localStyles.multiline]}
            value={value}
            onChangeText={setValue}
            placeholder={props.placeholder}
            placeholderTextColor="#9ca3af"
            multiline={props.multiline}
            autoFocus
            autoCorrect={false}
            textAlignVertical={props.multiline ? 'top' : 'center'}
          />
          <View style={localStyles.buttons}>
            <Pressable style={localStyles.button} onPress={props.onCancel}>
              <Text style={localStyles.cancel}>取消</Text>
            </Pressable>
            <Pressable
              style={localStyles.button}
              disabled={!value.trim()}
              onPress={() => props.onConfirm(value.trim())}
            >
              <Text style={[localStyles.ok, !value.trim() && { opacity: 0.4 }]}>{props.confirmText ?? '確定'}</Text>
            </Pressable>
          </View>
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}

export type SheetOption = { label: string; onPress: () => void; destructive?: boolean };

export function ActionSheet(props: { visible: boolean; title?: string; options: SheetOption[]; onClose: () => void }) {
  return (
    <Modal visible={props.visible} transparent animationType="slide" onRequestClose={props.onClose}>
      <Pressable style={[localStyles.backdrop, { justifyContent: 'flex-end' }]} onPress={props.onClose}>
        <View style={localStyles.sheet}>
          {props.title && <Text style={localStyles.sheetTitle}>{props.title}</Text>}
          {props.options.map((o) => (
            <Pressable
              key={o.label}
              style={({ pressed }) => [localStyles.sheetOption, pressed && { backgroundColor: '#f3f4f6' }]}
              onPress={() => {
                props.onClose();
                // iOS 上一個 Modal 還在關閉動畫時無法開下一個 Modal / Alert，稍等再執行
                setTimeout(o.onPress, Platform.OS === 'ios' ? 400 : 0);
              }}
            >
              <Text style={[localStyles.sheetText, o.destructive && { color: colors.danger }]}>{o.label}</Text>
            </Pressable>
          ))}
          <Pressable style={localStyles.sheetOption} onPress={props.onClose}>
            <Text style={[localStyles.sheetText, { color: colors.muted }]}>取消</Text>
          </Pressable>
        </View>
      </Pressable>
    </Modal>
  );
}

const localStyles = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: 'rgba(0,0,0,0.4)', justifyContent: 'center', padding: 24 },
  dialog: { backgroundColor: '#fff', borderRadius: 14, padding: 20, gap: 12, width: '100%', maxWidth: 480, alignSelf: 'center' },
  title: { fontSize: 18, fontWeight: '700', color: colors.text },
  message: { fontSize: 14, color: colors.muted },
  input: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 16,
    color: colors.text,
  },
  multiline: { minHeight: 160 },
  buttons: { flexDirection: 'row', justifyContent: 'flex-end', gap: 8 },
  button: { paddingHorizontal: 16, paddingVertical: 10 },
  cancel: { fontSize: 16, color: colors.muted },
  ok: { fontSize: 16, color: colors.primary, fontWeight: '700' },
  sheet: {
    backgroundColor: '#fff',
    borderRadius: 14,
    overflow: 'hidden',
    width: '100%',
    maxWidth: 480,
    alignSelf: 'center',
    marginBottom: 12,
  },
  sheetTitle: { fontSize: 14, color: colors.muted, textAlign: 'center', paddingVertical: 12 },
  sheetOption: {
    paddingVertical: 16,
    alignItems: 'center',
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.border,
  },
  sheetText: { fontSize: 17, color: colors.primary },
});
