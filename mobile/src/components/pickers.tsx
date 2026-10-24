/** 日期 / 時間欄位：iOS 用內嵌的精簡選擇器，Android 點一下跳出系統對話框，網頁版用瀏覽器內建的選擇器 */
import DateTimePicker, { DateTimePickerAndroid } from '@react-native-community/datetimepicker';
import { createElement } from 'react';
import { Platform, Pressable, StyleSheet, Text, View } from 'react-native';

import { parseDate, parseTime, snapMinutes, toDateString, toTimeString } from '@/lib/dates';
import { colors, styles as ui } from './ui';

type Props = {
  label: string;
  mode: 'date' | 'time';
  value: string | null; // YYYY-MM-DD 或 HH:MM
  onChange: (value: string | null) => void;
  clearable?: boolean;
  hint?: string;
  minuteStep?: 30; // 時間對齊 30 分鐘
};

export function DateTimeField({ label, mode, value, onChange, clearable, hint, minuteStep }: Props) {
  const current = value ? (mode === 'date' ? parseDate(value) : parseTime(value)) : new Date();

  const commit = (d: Date) => {
    if (mode === 'date') onChange(toDateString(d));
    else onChange(toTimeString(minuteStep ? snapMinutes(d, minuteStep) : d));
  };

  return (
    <View style={ui.field}>
      <Text style={ui.label}>{label}</Text>
      <View style={localStyles.row}>
        {Platform.OS === 'web' ? (
          // datetimepicker 沒有網頁版；react-native-web 底下可以直接用 HTML 的 <input type="date|time">
          createElement('input', {
            type: mode,
            value: value ?? '',
            step: minuteStep ? minuteStep * 60 : undefined,
            onChange: (e: { target: { value: string } }) => onChange(e.target.value || null),
            style: { fontSize: 16, padding: '8px 12px', border: `1px solid ${colors.border}`, borderRadius: 8 },
          })
        ) : Platform.OS === 'ios' ? (
          value ? (
            <DateTimePicker
              value={current}
              mode={mode}
              display="compact"
              locale="zh-TW"
              minuteInterval={minuteStep}
              onChange={(_, d) => d && commit(d)}
            />
          ) : (
            <Pressable style={localStyles.button} onPress={() => commit(new Date())}>
              <Text style={localStyles.placeholder}>選擇{mode === 'date' ? '日期' : '時間'}</Text>
            </Pressable>
          )
        ) : (
          <Pressable
            style={localStyles.button}
            onPress={() =>
              DateTimePickerAndroid.open({
                value: current,
                mode,
                is24Hour: true,
                onChange: (event, d) => event.type === 'set' && d && commit(d),
              })
            }
          >
            <Text style={value ? localStyles.value : localStyles.placeholder}>
              {value ?? `選擇${mode === 'date' ? '日期' : '時間'}`}
            </Text>
          </Pressable>
        )}
        {clearable && value && (
          <Pressable onPress={() => onChange(null)} hitSlop={8}>
            <Text style={localStyles.clear}>清除</Text>
          </Pressable>
        )}
      </View>
      {hint && <Text style={ui.hint}>{hint}</Text>}
    </View>
  );
}

const localStyles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  button: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 8,
    paddingHorizontal: 14,
    paddingVertical: 10,
    backgroundColor: '#fff',
  },
  value: { fontSize: 16, color: colors.text },
  placeholder: { fontSize: 16, color: '#9ca3af' },
  clear: { color: colors.primary, fontSize: 15 },
});
