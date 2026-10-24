export const DEFAULT_PORT = 8000;

/**
 * 把使用者輸入的主機位址轉成 base URL：
 *   192.168.68.109              → http://192.168.68.109:8000
 *   192.168.68.109:8000         → http://192.168.68.109:8000
 *   192．168．68．109：8000      → http://192.168.68.109:8000（中文鍵盤的全形符號）
 *   http://100.64.1.2:8000/docs → http://100.64.1.2:8000（網址後面的路徑會忽略）
 *   https://laptop.xxx.ts.net   → https://laptop.xxx.ts.net（有寫協定就不補 port）
 * 格式不對時回傳 null。
 */
export function normalizeBaseUrl(input: string): string | null {
  // NFKC 把全形英數與「：／．」轉成半形；「。」不在其中，另外處理
  let s = input.normalize('NFKC').replace(/[。､、]/g, '.').replace(/\s+/g, '');
  if (!s) return null;

  const hasScheme = /^https?:\/\//i.test(s);
  if (!hasScheme) s = `http://${s}`;

  // 只取「協定://主機[:port]」，後面的 /路徑、?參數 一律忽略
  const match = s.match(/^(https?):\/\/([^\s/:?#]+)(?::(\d{1,5}))?(?:[/?#].*)?$/i);
  if (!match) return null;

  const [, scheme, host, port] = match;
  if (port && Number(port) > 65535) return null;
  if (!/^[a-z0-9.-]+$/i.test(host) || host.startsWith('.') || host.endsWith('.')) return null;

  const finalPort = port ?? (hasScheme ? undefined : String(DEFAULT_PORT));
  return `${scheme.toLowerCase()}://${host.toLowerCase()}${finalPort ? `:${finalPort}` : ''}`;
}

/**
 * 用 Expo Go 開發時，APP 是從電腦的開發伺服器（例如 192.168.68.109:8081）載入的，
 * 後端通常在同一台電腦的 8000，所以可以直接建議「同一個 IP + 8000」。正式安裝版沒有此資訊，回傳 null。
 */
/**
 * 網頁版：後端通常和網頁在同一台電腦，用網頁本身的主機名稱（例如 localhost）+ 8000。
 * WSL mirrored 模式下，Windows 用自己的區網 IP 連 WSL 會逾時，所以電腦上一定要用 localhost。
 */
export function suggestHostForWeb(pageHostname: string | null | undefined): string | null {
  return pageHostname ? `${pageHostname}:${DEFAULT_PORT}` : null;
}

/** 由後端提供的電腦版（網址為 http://主機:8000/app/...）：後端就是網頁本身的主機 */
export function hostWhenServedByBackend(loc: { host: string; pathname: string } | null | undefined): string | null {
  return loc && (loc.pathname === '/app' || loc.pathname.startsWith('/app/')) ? loc.host : null;
}

export function suggestHostFromDevServer(hostUri: string | null | undefined): string | null {
  const ip = hostUri?.split(':')[0];
  return ip && /^[\d.]+$/.test(ip) ? `${ip}:${DEFAULT_PORT}` : null;
}
