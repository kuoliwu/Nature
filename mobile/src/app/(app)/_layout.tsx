import { Stack } from 'expo-router';

// 登入後的頁面：部門選單（index）→ 各部門（售服部 service 為底部分頁）→ 點進去的各個畫面
export const unstable_settings = { initialRouteName: 'index' };

export default function AppStack() {
  return (
    <Stack screenOptions={{ headerTitleAlign: 'center', headerBackTitle: '返回' }}>
      <Stack.Screen name="index" options={{ title: 'HOMPRO' }} />
      <Stack.Screen name="service" options={{ headerShown: false }} />
      <Stack.Screen name="user/[id]" options={{ title: '人員資料', presentation: 'modal' }} />
      {/* 簽名頁不允許手勢返回，避免簽到一半滑動誤關 */}
      <Stack.Screen name="inspection/[bookingId]/sign" options={{ gestureEnabled: false }} />
    </Stack>
  );
}
