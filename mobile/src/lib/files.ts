/** 從手機選檔上傳（匯出則是用 api.unitsExportLink 取得短效連結，交給瀏覽器下載） */
import * as DocumentPicker from 'expo-document-picker';
import { File as FsFile, UploadType } from 'expo-file-system';
import * as ImagePicker from 'expo-image-picker';

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

/** 選一個建案備份檔（.zip）；取消時回傳 null */
export async function pickBackupZip(): Promise<PickedFile | null> {
  const result = await DocumentPicker.getDocumentAsync({
    type: ['application/zip', 'application/x-zip-compressed', 'application/octet-stream'],
    copyToCacheDirectory: true,
  });
  if (result.canceled || !result.assets?.length) return null;
  const a = result.assets[0];
  if (!a.name.toLowerCase().endsWith('.zip')) throw new ApiError('請選擇建案備份檔（.zip）');
  return { uri: a.uri, name: a.name, mimeType: 'application/zip', file: a.file };
}

/** 拍照或從相簿選一張照片；取消或沒有權限時回傳 null（沒有權限會丟出說明） */
export async function pickImage(source: 'camera' | 'library'): Promise<PickedFile | null> {
  const options: ImagePicker.ImagePickerOptions = { mediaTypes: ['images'], quality: 0.7 };
  let result: ImagePicker.ImagePickerResult;
  if (source === 'camera') {
    const perm = await ImagePicker.requestCameraPermissionsAsync();
    if (!perm.granted) throw new ApiError('沒有相機權限，請到手機「設定」允許此 APP 使用相機');
    result = await ImagePicker.launchCameraAsync(options);
  } else {
    result = await ImagePicker.launchImageLibraryAsync(options);
  }
  if (result.canceled || !result.assets?.length) return null;
  const a = result.assets[0];
  return { uri: a.uri, name: a.fileName ?? `photo-${Date.now()}.jpg`, mimeType: a.mimeType ?? 'image/jpeg', file: a.file };
}

/** 從相簿一次選多張照片（拍照仍是一次一張）；取消時回傳空陣列 */
export async function pickImages(): Promise<PickedFile[]> {
  const result = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ['images'], quality: 0.7, allowsMultipleSelection: true, selectionLimit: 20 });
  if (result.canceled || !result.assets?.length) return [];
  return result.assets.map((a, i) => ({
    uri: a.uri, name: a.fileName ?? `photo-${Date.now()}-${i}.jpg`, mimeType: a.mimeType ?? 'image/jpeg', file: a.file,
  }));
}

/**
 * 上傳檔案（multipart，欄位名稱 file）。
 * 手機：Expo 的全域 fetch 是 expo/fetch，不支援 React Native 舊式的 { uri, name, type } 檔案物件，
 *       所以改用 expo-file-system 的 File.upload。
 * 網頁：用瀏覽器的 File 物件 + fetch。
 */
/** 選一個 PDF（外部報告）；取消時回傳 null */
export async function pickPdf(): Promise<PickedFile | null> {
  const result = await DocumentPicker.getDocumentAsync({ type: 'application/pdf', copyToCacheDirectory: true });
  if (result.canceled || !result.assets?.length) return null;
  const a = result.assets[0];
  if (a.size && a.size > 30 * 1024 * 1024) throw new ApiError('報告 PDF 不能超過 30MB');
  return { uri: a.uri, name: a.name, mimeType: 'application/pdf', file: a.file };
}

export async function uploadFile<T>(path: string, file: PickedFile, fields: Record<string, string> = {}): Promise<T> {
  const { baseUrl, token } = apiState();
  const url = `${baseUrl}${path}`;
  const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
  const mimeType = file.mimeType ?? XLSX_MIME;

  let status: number;
  let text: string;
  try {
    if (file.file) {
      const form = new FormData();
      for (const [key, value] of Object.entries(fields)) form.append(key, value);
      form.append('file', file.file, file.name);
      const res = await fetch(url, { method: 'POST', headers, body: form });
      status = res.status;
      text = await res.text();
    } else {
      const result = await new FsFile(file.uri).upload(url, {
        httpMethod: 'POST',
        uploadType: UploadType.MULTIPART,
        fieldName: 'file',
        mimeType,
        parameters: fields,
        headers,
        sessionType: 'foreground',
      });
      status = result.status;
      text = result.body;
    }
  } catch (e) {
    throw new ApiError(`上傳失敗：${e instanceof Error ? e.message : String(e)}`);
  }

  let data: unknown = null;
  try {
    data = JSON.parse(text);
  } catch {
    // 非 JSON 回應（例如 204）
  }
  if (status < 200 || status >= 300) throw errorFromResponse(status, data);
  return data as T;
}
