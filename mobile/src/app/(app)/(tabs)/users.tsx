import { router, useFocusEffect, useNavigation } from 'expo-router';
import { useCallback, useLayoutEffect, useState } from 'react';
import { FlatList, Pressable, RefreshControl, StyleSheet, Text, View } from 'react-native';

import { ActionSheet } from '@/components/overlays';
import { useSheetTransfer } from '@/components/SheetTransfer';
import { HeaderButton, Message, MAX_WIDTH, colors } from '@/components/ui';
import { api, User } from '@/lib/api';

export default function UsersScreen() {
  const [users, setUsers] = useState<User[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [menu, setMenu] = useState(false);
  const navigation = useNavigation();

  useLayoutEffect(() => {
    navigation.setOptions({
      headerRight: () => (
        <View style={{ flexDirection: 'row' }}>
          <HeaderButton label="Excel" onPress={() => setMenu(true)} />
          <HeaderButton label="＋ 新增" onPress={() => router.push('/user/new')} />
        </View>
      ),
    });
  }, [navigation]);

  const load = useCallback(async () => {
    try {
      setUsers(await api.users());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      void load();
    }, [load]),
  );
  const sheet = useSheetTransfer('users', {}, { label: '人員', unit: '人', canImport: true, onImported: load });

  return (
    <>
    <FlatList
      contentInsetAdjustmentBehavior="automatic" // iOS 半透明標題列時避免內容被擋住
      style={localStyles.list}
      contentContainerStyle={localStyles.content}
      data={users ?? []}
      keyExtractor={(u) => String(u.id)}
      refreshControl={
        <RefreshControl
          refreshing={refreshing}
          onRefresh={async () => {
            setRefreshing(true);
            await load();
            setRefreshing(false);
          }}
        />
      }
      ListHeaderComponent={
        error || sheet.status ? (
          <View style={{ gap: 8 }}>
            {error && <Message kind="error" text={error} />}
            {sheet.status}
          </View>
        ) : undefined
      }
      renderItem={({ item }) => (
        <Pressable
          onPress={() => router.push({ pathname: '/user/[id]', params: { id: String(item.id) } })}
          style={({ pressed }) => [localStyles.row, pressed && { opacity: 0.7 }]}
        >
          <View style={localStyles.flex}>
            <Text style={[localStyles.name, !item.is_active && localStyles.inactive]}>{item.name}</Text>
            <Text style={localStyles.meta}>{item.phone}</Text>
          </View>
          <View style={localStyles.badges}>
            {!item.is_active && <Badge text="已停用" color={colors.muted} />}
            {item.role === 'super_admin' ? (
              <Badge text="最高管理者" color={colors.primary} />
            ) : (
              <Badge text={`${item.permissions.length} 項權限`} color={colors.green} />
            )}
          </View>
        </Pressable>
      )}
    />
    <ActionSheet visible={menu} title="人員帳號 Excel" options={sheet.options} onClose={() => setMenu(false)} />
    </>
  );
}

function Badge({ text, color }: { text: string; color: string }) {
  return (
    <View style={[localStyles.badge, { borderColor: color }]}>
      <Text style={[localStyles.badgeText, { color }]}>{text}</Text>
    </View>
  );
}

const localStyles = StyleSheet.create({
  flex: { flex: 1 },
  list: { backgroundColor: colors.bg },
  content: { padding: 16, gap: 10, width: '100%', maxWidth: MAX_WIDTH, alignSelf: 'center' },
  row: { backgroundColor: colors.card, borderRadius: 12, padding: 16, flexDirection: 'row', alignItems: 'center', gap: 8 },
  name: { fontSize: 17, fontWeight: '700', color: colors.text },
  inactive: { color: colors.muted, textDecorationLine: 'line-through' },
  meta: { fontSize: 14, color: colors.muted, marginTop: 2 },
  badges: { alignItems: 'flex-end', gap: 4 },
  badge: { borderWidth: 1, borderRadius: 999, paddingHorizontal: 8, paddingVertical: 2 },
  badgeText: { fontSize: 12, fontWeight: '600' },
});
