/**
 * 配色主題：暗夜墨綠（預設）／亮色。
 * 各畫面的 StyleSheet 在載入時就固定顏色，所以主題在 APP 啟動時同步讀出，切換後重新載入畫面。
 * 每台裝置（瀏覽器）各自記住；網頁存在 localStorage，手機存在 APP 文件資料夾。
 */
import { File, Paths } from 'expo-file-system';
import { DevSettings, Platform } from 'react-native';

export type ThemeName = 'dark' | 'light';

export const THEME_OPTIONS: { value: ThemeName; label: string }[] = [
  { value: 'dark', label: '暗夜墨綠' },
  { value: 'light', label: '亮色' },
];

const STORAGE_KEY = 'ui.theme';
const FILE_NAME = 'ui-theme.txt';

export type Palette = {
  dark: boolean;
  primary: string; // 主要強調色（連結、外框按鈕、選取）
  onPrimary: string; // 實心按鈕（主要／次要／危險）上的文字
  green: string;
  danger: string;
  text: string;
  textSecondary: string; // 標籤、說明文字
  muted: string;
  faint: string; // 預留文字、停用、箭頭
  border: string;
  bg: string; // 頁面底色
  card: string; // 卡片
  input: string; // 輸入框、白底元件
  subtle: string; // 次要底色（停用輸入框、表頭、按下）
  chip: string; // 標籤、縮圖底色、進度條軌道
  overlay: string;
  accentBg: string; // 開放中的時段、檢查點
  signPad: { bg: string; ink: string; hint: string }; // 簽名板（存檔的簽名圖由後端另外繪製，不受主題影響）
  accentBorder: string;
  ok: { bg: string; border: string; fg: string };
  error: { bg: string; border: string; fg: string };
  info: { bg: string; border: string; fg: string };
  warn: { bg: string; border: string };
  chart: {
    surface: string;
    track: string;
    stage: { completed: string; booked: string; invited: string; not_invited: string };
    service: { visit: string; inspection: string; health_check: string };
    single: string;
    good: string;
    critical: string;
    grid: string;
  };
};

const light: Palette = {
  dark: false,
  primary: '#1d4ed8',
  onPrimary: '#ffffff',
  green: '#047857',
  danger: '#b91c1c',
  text: '#111827',
  textSecondary: '#374151',
  muted: '#6b7280',
  faint: '#9ca3af',
  border: '#d1d5db',
  bg: '#f3f4f6',
  card: '#ffffff',
  input: '#ffffff',
  subtle: '#f9fafb',
  chip: '#e5e7eb',
  overlay: 'rgba(0,0,0,0.4)',
  accentBg: '#eff6ff',
  signPad: { bg: '#ffffff', ink: '#111827', hint: '#9ca3af' },
  accentBorder: '#93c5fd',
  ok: { bg: '#f0fdf4', border: '#86efac', fg: '#166534' },
  error: { bg: '#fef2f2', border: '#fca5a5', fg: '#991b1b' },
  info: { bg: '#eff6ff', border: '#93c5fd', fg: '#1e40af' },
  warn: { bg: '#fef3c7', border: '#fcd34d' },
  // 色票已用 dataviz 驗證工具檢查（色盲可辨識、亮度順序）
  chart: {
    surface: '#ffffff',
    track: '#cde2fb',
    stage: { completed: '#1c5cab', booked: '#3987e5', invited: '#86b6ef', not_invited: '#cde2fb' },
    service: { visit: '#2a78d6', inspection: '#eb6834', health_check: '#1baf7a' },
    single: '#2a78d6',
    good: '#0ca30c',
    critical: '#d03b3b',
    grid: '#e1e0d9',
  },
};

// 暗夜墨綠：文字對比 內文 13.9、次要 6.5、按鈕 ≥ 6.4（WCAG）
const dark: Palette = {
  dark: true,
  primary: '#5fc49b',
  onPrimary: '#06120d',
  green: '#3fae84',
  danger: '#e37474',
  text: '#e7efeb',
  textSecondary: '#c2d2ca',
  muted: '#93a99e',
  faint: '#6f877c',
  border: '#2b4339',
  bg: '#0c1714',
  card: '#14231e',
  input: '#1b2e27',
  subtle: '#1b2e27',
  chip: '#24392f',
  overlay: 'rgba(0,0,0,0.6)',
  accentBg: '#17352b',
  signPad: { bg: '#0f1d18', ink: '#9be3b8', hint: '#6f877c' }, // 淺綠筆跡 對比 11.6:1
  accentBorder: '#2f6b55',
  ok: { bg: '#12301f', border: '#2f6b47', fg: '#9be3b8' },
  error: { bg: '#3a1a1c', border: '#7a3434', fg: '#ffb8b8' },
  info: { bg: '#15302a', border: '#2f6355', fg: '#a8e2cd' },
  warn: { bg: '#3a3014', border: '#8a6a1f' },
  // 同一組色相換成暗色底用的階：階段由亮到暗（亮＝完成），已在 #14231e 上驗證
  chart: {
    surface: '#14231e',
    track: '#1d3b5c',
    stage: { completed: '#9ec5f4', booked: '#5598e7', invited: '#256abf', not_invited: '#184f95' },
    service: { visit: '#3987e5', inspection: '#d95926', health_check: '#199e70' },
    single: '#3987e5',
    good: '#0ca30c',
    critical: '#d03b3b',
    grid: '#2b4339',
  },
};

function themeFile(): File {
  return new File(Paths.document, FILE_NAME);
}

function readThemeSync(): ThemeName {
  try {
    const saved =
      Platform.OS === 'web' ? window.localStorage.getItem(STORAGE_KEY) : themeFile().exists ? themeFile().textSync() : null;
    return saved === 'light' ? 'light' : 'dark';
  } catch {
    return 'dark';
  }
}

export const themeName: ThemeName = readThemeSync();
export const palette: Palette = themeName === 'light' ? light : dark;

/** 存下新主題並重新載入畫面；手機正式版無法自動重新載入時回傳 false（請使用者重開 APP） */
export async function setTheme(name: ThemeName): Promise<boolean> {
  if (Platform.OS === 'web') {
    window.localStorage.setItem(STORAGE_KEY, name);
    window.location.reload();
    return true;
  }
  await themeFile().write(name);
  if (__DEV__) {
    DevSettings.reload();
    return true;
  }
  return false;
}
