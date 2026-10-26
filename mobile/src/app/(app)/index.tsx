import FontAwesome from '@expo/vector-icons/FontAwesome';
import { router, useNavigation } from 'expo-router';
import { useLayoutEffect } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { HomproMark } from '@/components/Hompro';
import { HeaderButton, MAX_WIDTH, colors } from '@/components/ui';
import { useAuth } from '@/lib/auth';
import { DEPARTMENTS } from '@/lib/departments';

type IconName = React.ComponentProps<typeof FontAwesome>['name'];

/** 登入後的第一頁：選擇部門（標題列是 HOMPRO 圓圈） */
export default function DepartmentsScreen() {
  const { user } = useAuth();
  const navigation = useNavigation();

  useLayoutEffect(() => {
    navigation.setOptions({
      headerTitle: () => <HomproMark size={44} />, // 標題列中間放 HOMPRO 圓圈
      headerRight: () => <HeaderButton label="我的帳號" onPress={() => router.push('/service/account')} />,
    });
  }, [navigation]);

  return (
    <ScrollView
      contentInsetAdjustmentBehavior="automatic" // iOS 半透明標題列時避免內容被擋住
      style={{ backgroundColor: colors.bg }}
      contentContainerStyle={s.content}
    >
      {user && <Text style={s.hello}>{user.name}，您好</Text>}
      {DEPARTMENTS.map((d) => (
        <Pressable
          key={d.key}
          onPress={() => router.push(d.href)}
          style={({ pressed }) => [s.card, pressed && { opacity: 0.7 }]}
        >
          <View style={s.icon}>
            <FontAwesome name={d.icon as IconName} size={24} color={colors.onPrimary} />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={s.name}>{d.name}</Text>
            <Text style={s.desc}>{d.desc}</Text>
          </View>
          <Text style={s.chevron}>›</Text>
        </Pressable>
      ))}
    </ScrollView>
  );
}

const s = StyleSheet.create({
  content: { padding: 16, gap: 10, width: '100%', maxWidth: MAX_WIDTH, alignSelf: 'center' },
  hello: { fontSize: 14, color: colors.muted, marginLeft: 4, marginBottom: 2 },
  card: { flexDirection: 'row', alignItems: 'center', gap: 14, backgroundColor: colors.card, borderRadius: 14, padding: 16 },
  icon: { width: 48, height: 48, borderRadius: 24, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.primary },
  name: { fontSize: 18, fontWeight: '700', color: colors.text },
  desc: { fontSize: 13, color: colors.muted, marginTop: 2 },
  chevron: { fontSize: 24, color: colors.faint },
});
