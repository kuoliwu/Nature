import { Alert, Platform } from 'react-native';

/** 跨平台確認對話框；destructive 會把確定按鈕標成紅色（iOS） */
export function confirm(title: string, message: string, confirmText = '確定', destructive = false): Promise<boolean> {
  if (Platform.OS === 'web') return Promise.resolve(window.confirm(`${title}\n\n${message}`));
  return new Promise((resolve) =>
    Alert.alert(title, message, [
      { text: '取消', style: 'cancel', onPress: () => resolve(false) },
      { text: confirmText, style: destructive ? 'destructive' : 'default', onPress: () => resolve(true) },
    ]),
  );
}

export function errorText(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}
