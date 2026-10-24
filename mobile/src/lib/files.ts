/** 從手機選檔上傳（匯出則是用 api.unitsExportLink 取得短效連結，交給瀏覽器下載） */
import * as DocumentPicker from 'expo-document-picker';

import { ApiError, apiState, errorFromResponse } from './api';

export const XLSX_MIME = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';

// file：網頁版才有的瀏覽器 File 物件（網頁的 FormData 要直接放 File，不能用 uri）
export type PickedFile = { uri: string; name: string; mimeType?: string; file?: File };

/** 讓使用者選一個 Excel 或 CSV / TXT 檔；取消時回傳 null */
export async function pickSpreadsheet(): Promise<PickedFile | null> {
  const result = await DocumentPicker.getDocumentAsync({
    type: [XLSX_MIME, 'text/csv', 'text/comma-separated-values', 'text/plain', 'application/vnd.ms-excel', 'application/octet-stream'],
    copyToCacheDirectory: true,
  });
  if (result.canceled || !result.assets?.length) return null;
  const a = result.assets[0];
  return { uri: a.uri, name: a.name, mimeType: a.mimeType, file: a.file };
}

export async function uploadFile<T>(path: string, file: PickedFile): Promise<T> {
  const { baseUrl, token } = apiState();
  const form = new FormData();
  if (file.file) {
    form.append('file', file.file, file.name); // 網頁版
  } else {
    // React Native 的 FormData 接受 { uri, name, type } 物件代表本機檔案
    form.append('file', { uri: file.uri, name: file.name, type: file.mimeType ?? XLSX_MIME } as unknown as Blob);
  }

  let res: Response;
  try {
    res = await fetch(`${baseUrl}${path}`, {
      method: 'POST',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: form,
    });
  } catch (e) {
    throw new ApiError(`無法連線到主機：${e instanceof Error ? e.message : String(e)}`);
  }
  const data = await res.json().catch(() => null);
  if (!res.ok) throw errorFromResponse(res.status, data);
  return data as T;
}
