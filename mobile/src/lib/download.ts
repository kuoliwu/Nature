/**
 * 開啟下載 / 預覽連結（匯出 Excel、報表、報告 PDF…）
 *
 * 網頁版（含 iPhone 加到主畫面）：Safari 只允許在「點擊當下」開新分頁；先向後端要連結（await）再 window.open
 * 會被當成彈出式視窗擋掉（電腦版 Chrome 較寬鬆，所以只有手機跑不出來）。
 * → 點擊當下先開空白分頁，拿到連結後再把分頁導向該網址。必須在 onPress 裡「第一個 await 之前」呼叫。
 * 原生 APP：交給系統瀏覽器。
 */
import { Linking, Platform } from 'react-native';

export async function openLink(getUrl: () => Promise<string | null | undefined>): Promise<void> {
  if (Platform.OS !== 'web') {
    const url = await getUrl();
    if (url) await Linking.openURL(url);
    return;
  }
  const win = window.open('', '_blank'); // 同步開啟，保留點擊的使用者手勢
  try {
    const url = await getUrl();
    if (!url) {
      win?.close();
      return;
    }
    if (win) {
      win.opener = null;
      win.location.href = url;
    } else {
      window.location.href = url; // 分頁仍被擋（例如瀏覽器設定）：直接在目前頁面開啟
    }
  } catch (e) {
    win?.close();
    throw e;
  }
}
