import { useFocusEffect } from 'expo-router';
import { useCallback, useRef, useState } from 'react';

import { errorText } from './dialogs';

/** 進入（或從下一頁返回）畫面時載入資料；回傳 reload 供下拉更新或修改後重新整理 */
export function useLoad<T>(loader: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const loaderRef = useRef(loader);
  loaderRef.current = loader;

  const reload = useCallback(async () => {
    try {
      setData(await loaderRef.current());
      setError(null);
    } catch (e) {
      setError(errorText(e));
    }
  }, []);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useFocusEffect(useCallback(() => void reload(), [reload, ...deps]));

  const refresh = useCallback(async () => {
    setRefreshing(true);
    await reload();
    setRefreshing(false);
  }, [reload]);

  return { data, setData, error, setError, reload, refresh, refreshing };
}
