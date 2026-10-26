import { router, useLocalSearchParams, useNavigation } from 'expo-router';
import { useLayoutEffect, useMemo, useState } from 'react';
import { Alert, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import { Button, Card, Message, Screen, colors, styles as ui } from '@/components/ui';
import { api } from '@/lib/api';
import { errorText } from '@/lib/dialogs';
import { generateUnits, UNIT_FORMATS, UnitFormat } from '@/lib/units';

const PREVIEW_COUNT = 12;

export default function UnitGenerateScreen() {
  const projectId = Number(useLocalSearchParams<{ id: string }>().id);
  const navigation = useNavigation();
  const [letterFrom, setLetterFrom] = useState('A');
  const [letterTo, setLetterTo] = useState('B');
  const [floorFrom, setFloorFrom] = useState('2');
  const [floorTo, setFloorTo] = useState('10');
  const [perFrom, setPerFrom] = useState('');
  const [perTo, setPerTo] = useState('');
  const [format, setFormat] = useState<UnitFormat>('dash');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useLayoutEffect(() => {
    navigation.setOptions({ title: '依棟別與樓層產生' });
  }, [navigation]);

  const num = (s: string) => (s.trim() === '' ? null : Number(s));
  const result = useMemo(
    () =>
      generateUnits({
        letterFrom,
        letterTo,
        floorFrom: num(floorFrom) ?? NaN,
        floorTo: num(floorTo) ?? NaN,
        perFloorFrom: num(perFrom),
        perFloorTo: num(perTo),
        format,
      }),
    [letterFrom, letterTo, floorFrom, floorTo, perFrom, perTo, format],
  );
  const units = 'units' in result ? result.units : null;

  async function create() {
    if (!units?.length) return;
    setBusy(true);
    setError(null);
    try {
      const r = await api.bulkCreateUnitsDetailed(projectId, units);
      router.back();
      if (r.skipped.length) {
        // 返回清單頁後再提示略過的戶別（通常是已經存在）
        const list = r.skipped.slice(0, 20).join('、') + (r.skipped.length > 20 ? '…' : '');
        setTimeout(() => Alert.alert('新增完成', `已新增 ${r.created.length} 戶；${r.skipped.length} 戶已存在而略過：\n${list}`), 400);
      }
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Screen>
      <Card title="棟別（英文字母）">
        <RangeRow from={letterFrom} to={letterTo} onFrom={setLetterFrom} onTo={setLetterTo} placeholder={['A', 'C']} letters />
        <Text style={ui.hint}>只有一棟時，兩格填一樣的字母</Text>
      </Card>

      <Card title="樓層">
        <RangeRow from={floorFrom} to={floorTo} onFrom={setFloorFrom} onTo={setFloorTo} placeholder={['2', '15']} suffix="樓" />
      </Card>

      <Card title="每層戶號（選填）">
        <RangeRow from={perFrom} to={perTo} onFrom={setPerFrom} onTo={setPerTo} placeholder={['1', '4']} suffix="號" />
        <Text style={ui.hint}>例如每層有 1～4 號；留空則每層只產生一戶</Text>
      </Card>

      <Card title="戶別格式">
        <View style={localStyles.chips}>
          {UNIT_FORMATS.map((f) => (
            <Pressable key={f.key} onPress={() => setFormat(f.key)} style={[localStyles.chip, format === f.key && localStyles.chipOn]}>
              <Text style={[localStyles.chipText, format === f.key && localStyles.chipTextOn]}>{f.label}</Text>
            </Pressable>
          ))}
        </View>
      </Card>

      {'error' in result ? (
        <Message kind="error" text={result.error} />
      ) : (
        <Message kind="info" text={`將產生 ${result.units.length} 戶`}>
          <Text style={localStyles.preview}>
            {result.units.slice(0, PREVIEW_COUNT).map((u) => u.unit_no).join('、')}
            {result.units.length > PREVIEW_COUNT ? ` …（共 ${result.units.length} 戶）` : ''}
          </Text>
        </Message>
      )}
      <Text style={ui.hint}>棟別與樓層會一併填入每一戶；已存在的戶別會自動略過。屋主等資料之後再逐戶補上。</Text>

      {error && <Message kind="error" text={error} />}
      <Button label={units ? `新增 ${units.length} 戶` : '新增'} onPress={create} loading={busy} disabled={!units?.length} />
    </Screen>
  );
}

function RangeRow(props: {
  from: string;
  to: string;
  onFrom: (v: string) => void;
  onTo: (v: string) => void;
  placeholder: [string, string];
  letters?: boolean;
  suffix?: string;
}) {
  const inputProps = props.letters
    ? ({ autoCapitalize: 'characters', maxLength: 1 } as const)
    : ({ keyboardType: 'number-pad', maxLength: 2 } as const);
  return (
    <View style={localStyles.range}>
      <TextInput style={localStyles.rangeInput} value={props.from} onChangeText={props.onFrom} placeholder={props.placeholder[0]} placeholderTextColor={colors.faint} {...inputProps} />
      {props.suffix && <Text style={localStyles.suffix}>{props.suffix}</Text>}
      <Text style={localStyles.to}>到</Text>
      <TextInput style={localStyles.rangeInput} value={props.to} onChangeText={props.onTo} placeholder={props.placeholder[1]} placeholderTextColor={colors.faint} {...inputProps} />
      {props.suffix && <Text style={localStyles.suffix}>{props.suffix}</Text>}
    </View>
  );
}

const localStyles = StyleSheet.create({
  range: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  rangeInput: {
    width: 72,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 8,
    paddingVertical: 10,
    fontSize: 18,
    textAlign: 'center',
    color: colors.text,
    backgroundColor: colors.input,
  },
  suffix: { fontSize: 16, color: colors.muted },
  to: { fontSize: 16, color: colors.text, marginHorizontal: 6 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: { borderWidth: 1, borderColor: colors.border, borderRadius: 999, paddingHorizontal: 16, paddingVertical: 8 },
  chipOn: { backgroundColor: colors.primary, borderColor: colors.primary },
  chipText: { fontSize: 15, color: colors.text },
  chipTextOn: { color: colors.onPrimary, fontWeight: '600' },
  preview: { fontSize: 14, color: colors.textSecondary, lineHeight: 20 },
});
