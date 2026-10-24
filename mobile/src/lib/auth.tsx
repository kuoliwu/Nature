import { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { Platform } from 'react-native';

import { api, ApiError, configureApi, LoginOut, User } from './api';
import { loadSession, loadSettings, saveSession, saveSettings, SavedSettings } from './settings';
import { hostWhenServedByBackend, normalizeBaseUrl } from './url';

type AuthContextValue = {
  ready: boolean;
  user: User | null;
  server: SavedSettings;
  baseUrl: string | null;
  signIn: (result: LoginOut) => Promise<void>;
  signOut: () => Promise<void>;
  setUser: (user: User) => void;
  updateServer: (s: SavedSettings) => Promise<void>;
  can: (permission: string) => boolean;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [user, setUserState] = useState<User | null>(null);
  const [server, setServer] = useState<SavedSettings>({ host: '', adminKey: '' });

  const signOut = useCallback(async () => {
    configureApi({ token: null });
    setUserState(null);
    await saveSession(null);
  }, []);

  useEffect(() => {
    (async () => {
      const [settings, session] = await Promise.all([loadSettings(), loadSession()]);
      // 電腦版由後端提供時，主機就是網頁本身，不用另外設定
      const served = Platform.OS === 'web' ? hostWhenServedByBackend(window.location) : null;
      if (served && !settings.host) {
        settings.host = served;
        await saveSettings(settings);
      }
      setServer(settings);
      configureApi({ baseUrl: normalizeBaseUrl(settings.host) ?? '', onUnauthorized: () => void signOut() });
      if (session) {
        configureApi({ token: session.token });
        setUserState(session.user); // 先用快取，離線也能開啟
        api
          .me()
          .then((fresh) => {
            setUserState(fresh);
            void saveSession({ token: session.token, user: fresh });
          })
          .catch((e) => {
            if (e instanceof ApiError && e.status === 401) void signOut();
          });
      }
      setReady(true);
    })();
  }, [signOut]);

  const value = useMemo<AuthContextValue>(
    () => ({
      ready,
      user,
      server,
      baseUrl: normalizeBaseUrl(server.host),
      signIn: async (result) => {
        configureApi({ token: result.access_token });
        setUserState(result.user);
        await saveSession({ token: result.access_token, user: result.user });
      },
      signOut,
      setUser: (next) => {
        setUserState(next);
        void loadSession().then((s) => s && saveSession({ token: s.token, user: next }));
      },
      updateServer: async (s) => {
        await saveSettings(s);
        setServer(s);
        configureApi({ baseUrl: normalizeBaseUrl(s.host) ?? '' });
      },
      can: (permission) => !!user && (user.role === 'super_admin' || user.permissions.includes(permission)),
    }),
    [ready, user, server, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth 必須在 AuthProvider 之內使用');
  return ctx;
}
