/** 共用元件。平板上內容置中、限制寬度，避免表單被拉得太寬。 */
import { ReactNode } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  TextInputProps,
  View,
  ViewStyle,
} from 'react-native';

import { palette } from '@/lib/theme';

/** 目前主題的色票（暗夜墨綠／亮色，見 lib/theme.ts） */
export const colors = palette;

export const MAX_WIDTH = 720;

export function Screen({ children, scroll = true }: { children: ReactNode; scroll?: boolean }) {
  const inner = <View style={styles.inner}>{children}</View>;
  return (
    <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      {scroll ? (
        <ScrollView
          contentContainerStyle={styles.scroll}
          keyboardShouldPersistTaps="handled"
          contentInsetAdjustmentBehavior="automatic"
        >
          {inner}
        </ScrollView>
      ) : (
        <View style={[styles.flex, styles.scroll]}>{inner}</View>
      )}
    </KeyboardAvoidingView>
  );
}

export function Card({ children, title, style }: { children: ReactNode; title?: string; style?: ViewStyle }) {
  return (
    <View style={[styles.card, style]}>
      {title && <Text style={styles.cardTitle}>{title}</Text>}
      {children}
    </View>
  );
}

export function Field({ label, hint, ...props }: TextInputProps & { label: string; hint?: string }) {
  return (
    <View style={styles.field}>
      <Text style={styles.label}>{label}</Text>
      <TextInput
        placeholderTextColor={colors.faint}
        autoCorrect={false}
        {...props}
        style={[styles.input, props.editable === false && styles.inputDisabled, props.style]}
      />
      {hint && <Text style={styles.hint}>{hint}</Text>}
    </View>
  );
}

export function ToggleRow(props: {
  label: string;
  description?: string;
  value: boolean;
  onValueChange: (v: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <View style={styles.toggleRow}>
      <View style={styles.flex}>
        <Text style={[styles.toggleLabel, props.disabled && { color: colors.muted }]}>{props.label}</Text>
        {props.description && <Text style={styles.hint}>{props.description}</Text>}
      </View>
      <Switch value={props.value} onValueChange={props.onValueChange} disabled={props.disabled} />
    </View>
  );
}

export function Button(props: {
  label: string;
  onPress: () => void;
  loading?: boolean;
  disabled?: boolean;
  variant?: 'primary' | 'secondary' | 'outline' | 'danger';
}) {
  const variant = props.variant ?? 'primary';
  const textColor = variant === 'outline' ? colors.primary : colors.onPrimary;
  const disabled = props.disabled || props.loading;
  return (
    <Pressable
      onPress={props.onPress}
      disabled={disabled}
      style={({ pressed }) => [styles.button, buttonVariants[variant], (pressed || disabled) && styles.dimmed]}
    >
      {props.loading ? (
        <ActivityIndicator color={textColor} />
      ) : (
        <Text style={[styles.buttonText, { color: textColor }]}>{props.label}</Text>
      )}
    </Pressable>
  );
}

export function Message({ kind, text, children }: { kind: 'ok' | 'error' | 'info'; text: string; children?: ReactNode }) {
  const palette = { ...colors[kind], icon: { ok: '✓ ', error: '✕ ', info: '' }[kind] };
  return (
    <View style={[styles.message, { backgroundColor: palette.bg, borderColor: palette.border }]}>
      <Text style={[styles.messageText, { color: palette.fg }]}>
        {palette.icon}
        {text}
      </Text>
      {children}
    </View>
  );
}

export function Loading() {
  return (
    <View style={[styles.flex, styles.center]}>
      <ActivityIndicator size="large" color={colors.primary} />
    </View>
  );
}

const buttonVariants = StyleSheet.create({
  primary: { backgroundColor: colors.primary },
  secondary: { backgroundColor: colors.green },
  danger: { backgroundColor: colors.danger },
  outline: { backgroundColor: colors.input, borderWidth: 1, borderColor: colors.primary },
});

export const styles = StyleSheet.create({
  flex: { flex: 1 },
  center: { alignItems: 'center', justifyContent: 'center' },
  scroll: { padding: 16, backgroundColor: colors.bg, flexGrow: 1 },
  inner: { width: '100%', maxWidth: MAX_WIDTH, alignSelf: 'center', gap: 12 },
  card: { backgroundColor: colors.card, borderRadius: 12, padding: 16, gap: 4 },
  cardTitle: { fontSize: 16, fontWeight: '700', color: colors.text, marginBottom: 6 },
  field: { marginBottom: 10 },
  label: { fontSize: 14, fontWeight: '600', color: colors.textSecondary, marginBottom: 6 },
  input: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 16,
    color: colors.text,
    backgroundColor: colors.input,
  },
  inputDisabled: { backgroundColor: colors.subtle, color: colors.muted },
  hint: { fontSize: 12, color: colors.muted, marginTop: 4 },
  toggleRow: { flexDirection: 'row', alignItems: 'center', paddingVertical: 8, gap: 12 },
  toggleLabel: { fontSize: 15, color: colors.text },
  button: { borderRadius: 10, paddingVertical: 14, alignItems: 'center', justifyContent: 'center', minHeight: 50 },
  buttonText: { fontSize: 16, fontWeight: '600' },
  dimmed: { opacity: 0.6 },
  message: { borderRadius: 12, padding: 14, borderWidth: 1, gap: 4 },
  messageText: { fontSize: 15, fontWeight: '600' },
});

export function HeaderButton({ label, onPress }: { label: string; onPress: () => void }) {
  return (
    <Pressable onPress={onPress} hitSlop={12} style={{ paddingHorizontal: 12 }}>
      <Text style={{ color: colors.primary, fontSize: 16, fontWeight: '600' }}>{label}</Text>
    </Pressable>
  );
}

export function ListRow(props: { title: string; subtitle?: string | null; right?: string; onPress?: () => void; muted?: boolean }) {
  return (
    <Pressable
      onPress={props.onPress}
      disabled={!props.onPress}
      style={({ pressed }) => [rowStyles.row, pressed && { opacity: 0.7 }]}
    >
      <View style={styles.flex}>
        <Text style={[rowStyles.title, props.muted && { color: colors.muted }]}>{props.title}</Text>
        {!!props.subtitle && <Text style={rowStyles.subtitle}>{props.subtitle}</Text>}
      </View>
      {props.right !== undefined && <Text style={rowStyles.right}>{props.right}</Text>}
      {props.onPress && <Text style={rowStyles.chevron}>›</Text>}
    </Pressable>
  );
}

const rowStyles = StyleSheet.create({
  row: {
    backgroundColor: colors.card,
    borderRadius: 12,
    paddingHorizontal: 16,
    paddingVertical: 14,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  title: { fontSize: 16, fontWeight: '600', color: colors.text },
  subtitle: { fontSize: 13, color: colors.muted, marginTop: 2 },
  right: { fontSize: 14, color: colors.muted },
  chevron: { fontSize: 22, color: colors.faint, marginLeft: 4 },
});
