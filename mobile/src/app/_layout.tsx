import { DarkTheme, DefaultTheme, Stack, ThemeProvider } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useEffect } from 'react';
import { Platform } from 'react-native';

import { Loading, colors } from '@/components/ui';
import { AuthProvider, useAuth } from '@/lib/auth';

// 標題列、分頁列、頁面底色跟著配色主題（lib/theme.ts）
const base = colors.dark ? DarkTheme : DefaultTheme;
const navTheme = {
  ...base,
  colors: { ...base.colors, primary: colors.primary, background: colors.bg, card: colors.card, text: colors.text, border: colors.border },
};

export default function RootLayout() {
  useEffect(() => {
    if (Platform.OS !== 'web') return;
    // 網頁版：頁面底色與瀏覽器網址列顏色
    document.body.style.backgroundColor = colors.bg;
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', colors.card);
  }, []);

  return (
    <ThemeProvider value={navTheme}>
      <AuthProvider>
        <StatusBar style={colors.dark ? 'light' : 'dark'} />
        <RootStack />
      </AuthProvider>
    </ThemeProvider>
  );
}

function RootStack() {
  const { ready, user } = useAuth();
  if (!ready) return <Loading />;

  return (
    <Stack screenOptions={{ headerTitleAlign: 'center' }}>
      {/* 登入後才看得到：(app) 底下的所有頁面 */}
      <Stack.Protected guard={!!user}>
        <Stack.Screen name="(app)" options={{ headerShown: false }} />
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
