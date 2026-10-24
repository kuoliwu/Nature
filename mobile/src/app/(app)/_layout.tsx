import { Stack } from 'expo-router';

// 登入後的頁面：底部分頁 + 從分頁點進去的各個畫面
export default function AppStack() {
  return (
    <Stack screenOptions={{ headerTitleAlign: 'center', headerBackTitle: '返回' }}>
      <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
      <Stack.Screen name="user/[id]" options={{ title: '人員資料', presentation: 'modal' }} />
      {/* 簽名頁不允許手勢返回，避免簽到一半滑動誤關 */}
      <Stack.Screen name="inspection/[bookingId]/sign" options={{ gestureEnabled: false }} />
    </Stack>
  );
}
