import FontAwesome from '@expo/vector-icons/FontAwesome';
import { router, Tabs } from 'expo-router';

import { HomproTabButton } from '@/components/Hompro';
import { colors } from '@/components/ui';
import { useAuth } from '@/lib/auth';

type IconName = React.ComponentProps<typeof FontAwesome>['name'];
type IconColor = React.ComponentProps<typeof FontAwesome>['color'];
const icon =
  (name: IconName) =>
  ({ color }: { color: unknown }) => <FontAwesome size={22} name={name} color={color as IconColor} />;

/** 售服部：建案、行程、（HOMPRO）、人員、我的帳號 */
export default function AppTabs() {
  const { can } = useAuth();

  return (
    <Tabs screenOptions={{ tabBarActiveTintColor: colors.primary, headerTitleAlign: 'center' }}>
      <Tabs.Screen name="index" options={{ title: '建案', tabBarIcon: icon('building') }} />
      <Tabs.Screen
        name="inspections"
        options={{
          title: '行程',
          tabBarIcon: icon('check-square-o'),
          href: can('inspection.edit') || can('booking.view') ? undefined : null,
        }}
      />
      {/* 中間凸起的 HOMPRO：回到部門選單 */}
      <Tabs.Screen
        name="hompro"
        options={{
          title: '',
          // dismissTo：堆疊裡已有部門選單就退回去，沒有（例如直接開網址）就開啟它
          tabBarButton: () => <HomproTabButton onPress={() => router.dismissTo('/')} />,
        }}
      />
      <Tabs.Screen
        name="users"
        options={{
          title: '人員',
          tabBarIcon: icon('users'),
          href: can('user.manage') ? undefined : null, // 沒有人員管理權限就不顯示此分頁
        }}
      />
      <Tabs.Screen name="account" options={{ title: '我的帳號', tabBarIcon: icon('user') }} />
    </Tabs>
  );
}
