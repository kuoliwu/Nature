export const DEFAULT_PORT = 8000;

/**
 * 把使用者輸入的主機位址轉成 base URL：
 *   192.168.68.109              → http://192.168.68.109:8000
 *   192.168.68.109:8000         → http://192.168.68.109:8000
 *   http://100.64.1.2:8000/     → http://100.64.1.2:8000
 *   https://laptop.xxx.ts.net   → https://laptop.xxx.ts.net（有寫協定就不補 port）
 * 格式不對時回傳 null。
 */
export function normalizeBaseUrl(input: string): string | null {
  let s = input.trim().replace(/\/+$/, '');
  if (!s) return null;

  const hasScheme = /^https?:\/\//i.test(s);
  if (!hasScheme) s = `http://${s}`;

  const match = s.match(/^(https?):\/\/([^\s/:?#]+)(?::(\d{1,5}))?$/i);
  if (!match) return null;

  const [, scheme, host, port] = match;
  if (port && Number(port) > 65535) return null;

  const finalPort = port ?? (hasScheme ? undefined : String(DEFAULT_PORT));
  return `${scheme.toLowerCase()}://${host}${finalPort ? `:${finalPort}` : ''}`;
}
