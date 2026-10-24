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

export const colors = {
  primary: '#1d4ed8',
  green: '#047857',
  danger: '#b91c1c',
  text: '#111827',
  muted: '#6b7280',
  border: '#d1d5db',
  bg: '#f3f4f6',
  card: '#ffffff',
};

export const MAX_WIDTH = 720;

export function Screen({ children, scroll = true }: { children: ReactNode; scroll?: boolean }) {
  const inner = <View style={styles.inner}>{children}</View>;
  return (
    <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      {scroll ? (
        <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
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
        placeholderTextColor="#9ca3af"
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
  const textColor = variant === 'outline' ? colors.primary : '#fff';
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
  const palette = {
    ok: { bg: '#f0fdf4', border: '#86efac', fg: '#166534', icon: '✓ ' },
    error: { bg: '#fef2f2', border: '#fca5a5', fg: '#991b1b', icon: '✕ ' },
    info: { bg: '#eff6ff', border: '#93c5fd', fg: '#1e40af', icon: '' },
  }[kind];
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
  outline: { backgroundColor: '#fff', borderWidth: 1, borderColor: colors.primary },
});

export const styles = StyleSheet.create({
  flex: { flex: 1 },
  center: { alignItems: 'center', justifyContent: 'center' },
  scroll: { padding: 16, backgroundColor: colors.bg, flexGrow: 1 },
  inner: { width: '100%', maxWidth: MAX_WIDTH, alignSelf: 'center', gap: 12 },
  card: { backgroundColor: colors.card, borderRadius: 12, padding: 16, gap: 4 },
  cardTitle: { fontSize: 16, fontWeight: '700', color: colors.text, marginBottom: 6 },
  field: { marginBottom: 10 },
  label: { fontSize: 14, fontWeight: '600', color: '#374151', marginBottom: 6 },
  input: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 16,
    color: colors.text,
    backgroundColor: '#fff',
  },
  inputDisabled: { backgroundColor: '#f9fafb', color: colors.muted },
  hint: { fontSize: 12, color: colors.muted, marginTop: 4 },
  toggleRow: { flexDirection: 'row', alignItems: 'center', paddingVertical: 8, gap: 12 },
  toggleLabel: { fontSize: 15, color: colors.text },
  button: { borderRadius: 10, paddingVertical: 14, alignItems: 'center', justifyContent: 'center', minHeight: 50 },
  buttonText: { fontSize: 16, fontWeight: '600' },
  dimmed: { opacity: 0.6 },
  message: { borderRadius: 12, padding: 14, borderWidth: 1, gap: 4 },
  messageText: { fontSize: 15, fontWeight: '600' },
});
