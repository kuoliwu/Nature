/**
 * 通用 Excel / CSV 匯出匯入（建案、檢查清單、時段、預約名單、人員、驗屋結果）
 * 用法：const sheet = useSheetTransfer('slots', { batch_id }, {...})
 *       把 sheet.options 放進畫面的 ActionSheet，把 sheet.status 放在畫面上方顯示進度與錯誤。
 */
import { ReactNode, useState } from 'react';
import { Linking, StyleSheet, Text, View } from 'react-native';

import { SheetOption } from './overlays';
import { Message } from './ui';
import { api, SheetName, SheetParams, sheetQuery, UnitImportResult } from '@/lib/api';
import { confirm, errorText } from '@/lib/dialogs';
import { pickSpreadsheet, uploadFile } from '@/lib/files';

type Options = {
  label: string; // 資料名稱，例如「時段」
  canImport: boolean;
  unit?: string; // 計數單位，例如「筆」「戶」
  onImported?: () => void | Promise<void>;
};

export function useSheetTransfer(name: SheetName, params: SheetParams, opts: Options) {
  const [notice, setNotice] = useState<{ ok: boolean; text: string } | null>(null);
  const [errors, setErrors] = useState<UnitImportResult['errors'] | null>(null);
  const [working, setWorking] = useState<string | null>(null);
  const unit = opts.unit ?? '筆';

  /** 取得 5 分鐘有效的下載連結，交給瀏覽器下載；手機可在瀏覽器裡儲存或分享 */
  async function exportFile(format: 'xlsx' | 'csv') {
    setNotice(null);
    setErrors(null);
    try {
      const link = await api.sheetExportLink(name, params, format);
      await Linking.openURL(link.url);
      setNotice({ ok: true, text: `已在瀏覽器開啟「${link.filename}」，可儲存或分享（連結 5 分鐘內有效）` });
    } catch (e) {
      setNotice({ ok: false, text: errorText(e) });
    }
  }

  async function importFile() {
    setNotice(null);
    setErrors(null);
    const file = await pickSpreadsheet();
    if (!file) return;
    const path = `/sheets/${name}/import`;
    try {
      // 先預覽（不寫入），確認後才真的匯入
      setWorking('正在檢查檔案…');
      const preview = await uploadFile<UnitImportResult>(path + sheetQuery({ ...params, dry_run: true }), file);
      setWorking(null);
      if (preview.errors.length) {
        setErrors(preview.errors);
        return;
      }
      if (!preview.created.length && !preview.updated.length) {
        setNotice({ ok: true, text: `檔案與目前資料相同（${preview.unchanged} ${unit}），沒有需要更新的內容` });
        return;
      }
      const summary =
        `新增 ${preview.created.length} ${unit}、更新 ${preview.updated.length} ${unit}` +
        (preview.unchanged ? `，${preview.unchanged} ${unit}不變` : '');
      const sample = [...preview.created.map((n) => `＋ ${n}`), ...preview.updated.map((n) => `✎ ${n}`)].slice(0, 8);
      const more = preview.created.length + preview.updated.length - sample.length;
      const message = `${file.name}\n\n將${summary}：\n${sample.join('\n')}${more > 0 ? `\n…等 ${more} ${unit}` : ''}\n\n檔案裡沒有的資料不會被刪除。確定匯入？`;
      if (!(await confirm(`匯入${opts.label}`, message, '匯入'))) return;

      setWorking('正在匯入…');
      const result = await uploadFile<UnitImportResult>(path + sheetQuery(params), file);
      if (result.errors.length) {
        setErrors(result.errors); // 預覽後資料剛好被別人改動
        return;
      }
      setNotice({ ok: true, text: `匯入完成：新增 ${result.created.length} ${unit}、更新 ${result.updated.length} ${unit}` });
      await opts.onImported?.();
    } catch (e) {
      setNotice({ ok: false, text: errorText(e) });
    } finally {
      setWorking(null);
    }
  }

  const options: SheetOption[] = [
    { label: `匯出${opts.label} Excel（.xlsx）`, onPress: () => exportFile('xlsx') },
    { label: `匯出${opts.label} CSV`, onPress: () => exportFile('csv') },
    ...(opts.canImport ? [{ label: `從 Excel / CSV 匯入${opts.label}`, onPress: importFile }] : []),
  ];

  const status: ReactNode =
    working || notice || errors ? (
      <View style={{ gap: 8 }}>
        {working && <Message kind="info" text={working} />}
        {notice && <Message kind={notice.ok ? 'ok' : 'error'} text={notice.text} />}
        {errors && (
          <Message kind="error" text={`檔案有 ${errors.length} 個錯誤，沒有匯入任何資料。請修正後再匯入：`}>
            {errors.slice(0, 30).map((e) => (
              <Text key={`${e.row}-${e.message}`} style={localStyles.errorLine}>
                {e.row ? `第 ${e.row} 列：` : ''}
                {e.message}
              </Text>
            ))}
            {errors.length > 30 && <Text style={localStyles.errorLine}>…還有 {errors.length - 30} 個錯誤</Text>}
          </Message>
        )}
      </View>
    ) : null;

  return { options, status, exportFile, importFile };
}

const localStyles = StyleSheet.create({
  errorLine: { color: '#991b1b', fontSize: 13, marginTop: 4 },
});
