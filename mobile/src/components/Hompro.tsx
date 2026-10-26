/** HOMPRO 圓形按鈕：部門選單底部的品牌，以及各部門分頁列中間（點了回到部門選單） */
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { colors } from './ui';

export function HomproMark({ size = 64, onPress }: { size?: number; onPress?: () => void }) {
  const circle = (
    <View style={[s.circle, { width: size, height: size, borderRadius: size / 2 }]}>
      <Text style={[s.text, { fontSize: size * 0.17 }]} numberOfLines={1}>
        HOMPRO
      </Text>
    </View>
  );
  if (!onPress) return circle;
  return (
    <Pressable onPress={onPress} accessibilityRole="button" accessibilityLabel="HOMPRO：回到部門選單" style={({ pressed }) => pressed && { opacity: 0.8 }}>
      {circle}
    </Pressable>
  );
}

/** 分頁列中間的凸起按鈕（比其他分頁高一點） */
export function HomproTabButton({ onPress }: { onPress: () => void }) {
  return (
    <View style={s.tabSlot} pointerEvents="box-none">
      <View style={s.raised}>
        <HomproMark size={60} onPress={onPress} />
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  circle: {
    backgroundColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 3,
    borderColor: colors.card,
    shadowColor: '#000',
    shadowOpacity: 0.25,
    shadowRadius: 6,
    shadowOffset: { width: 0, height: 2 },
    elevation: 6,
  },
  text: { color: colors.onPrimary, fontWeight: '800' },
  tabSlot: { flex: 1, alignItems: 'center' },
  raised: { position: 'absolute', top: -24 },
});
