import AsyncStorage from '@react-native-async-storage/async-storage';
import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

import type { User } from './api';

const HOST_KEY = 'server.host';
const ADMIN_KEY = 'server.adminKey';
const TOKEN_KEY = 'auth.token';
const USER_KEY = 'auth.user';

// 金鑰與登入憑證存在 Keychain / Keystore；SecureStore 不支援 web，web 預覽時退回 AsyncStorage
const secret = {
  get: (key: string) =>
    Platform.OS === 'web' ? AsyncStorage.getItem(key) : SecureStore.getItemAsync(key),
  set: (key: string, value: string) =>
    Platform.OS === 'web' ? AsyncStorage.setItem(key, value) : SecureStore.setItemAsync(key, value),
  remove: (key: string) =>
    Platform.OS === 'web' ? AsyncStorage.removeItem(key) : SecureStore.deleteItemAsync(key),
};

export type SavedSettings = { host: string; adminKey: string };

export async function loadSettings(): Promise<SavedSettings> {
  const [host, adminKey] = await Promise.all([AsyncStorage.getItem(HOST_KEY), secret.get(ADMIN_KEY)]);
  return { host: host ?? '', adminKey: adminKey ?? '' };
}

export async function saveSettings(s: SavedSettings): Promise<void> {
  await Promise.all([AsyncStorage.setItem(HOST_KEY, s.host), secret.set(ADMIN_KEY, s.adminKey)]);
}

export type SavedSession = { token: string; user: User };

export async function loadSession(): Promise<SavedSession | null> {
  const [token, user] = await Promise.all([secret.get(TOKEN_KEY), AsyncStorage.getItem(USER_KEY)]);
  if (!token || !user) return null;
  try {
    return { token, user: JSON.parse(user) as User };
  } catch {
    return null;
  }
}

export async function saveSession(s: SavedSession | null): Promise<void> {
  if (s === null) {
    await Promise.all([secret.remove(TOKEN_KEY), AsyncStorage.removeItem(USER_KEY)]);
    return;
  }
  await Promise.all([secret.set(TOKEN_KEY, s.token), AsyncStorage.setItem(USER_KEY, JSON.stringify(s.user))]);
}
