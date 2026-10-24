import AsyncStorage from '@react-native-async-storage/async-storage';
import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

const HOST_KEY = 'server.host';
const ADMIN_KEY = 'server.adminKey';

// 管理金鑰存在 Keychain / Keystore；SecureStore 不支援 web，web 預覽時退回 AsyncStorage
const secret = {
  get: (key: string) =>
    Platform.OS === 'web' ? AsyncStorage.getItem(key) : SecureStore.getItemAsync(key),
  set: (key: string, value: string) =>
    Platform.OS === 'web' ? AsyncStorage.setItem(key, value) : SecureStore.setItemAsync(key, value),
};

export type SavedSettings = { host: string; adminKey: string };

export async function loadSettings(): Promise<SavedSettings> {
  const [host, adminKey] = await Promise.all([AsyncStorage.getItem(HOST_KEY), secret.get(ADMIN_KEY)]);
  return { host: host ?? '', adminKey: adminKey ?? '' };
}

export async function saveSettings(s: SavedSettings): Promise<void> {
  await Promise.all([AsyncStorage.setItem(HOST_KEY, s.host), secret.set(ADMIN_KEY, s.adminKey)]);
}
