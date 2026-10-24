import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';

import { Loading } from '@/components/ui';
import { AuthProvider, useAuth } from '@/lib/auth';

export default function RootLayout() {
  return (
    <AuthProvider>
      <StatusBar style="dark" />
      <RootStack />
    </AuthProvider>
  );
}

function RootStack() {
  const { ready, user } = useAuth();
  if (!ready) return <Loading />;

  return (
    <Stack screenOptions={{ headerTitleAlign: 'center' }}>
      {/* 登入後才看得到 */}
      <Stack.Protected guard={!!user}>
        <Stack.Screen name="(app)" options={{ headerShown: false }} />
        <Stack.Screen name="user/[id]" options={{ title: '人員資料', presentation: 'modal' }} />
      </Stack.Protected>

      {/* 未登入時 */}
      <Stack.Protected guard={!user}>
        <Stack.Screen name="login" options={{ title: '登入' }} />
        <Stack.Screen name="setup" options={{ title: '建立管理者帳號' }} />
      </Stack.Protected>

      <Stack.Screen name="connect" options={{ title: '主機連線設定' }} />
    </Stack>
  );
}
