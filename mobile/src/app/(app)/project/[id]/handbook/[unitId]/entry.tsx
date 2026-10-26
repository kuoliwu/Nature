import { router, useLocalSearchParams, useNavigation } from 'expo-router';
import { useEffect, useLayoutEffect, useState } from 'react';
import { Image, Pressable, StyleSheet, Text, View } from 'react-native';

import { ActionSheet } from '@/components/overlays';
import { DateTimeField } from '@/components/pickers';
import { Button, Card, Field, Loading, Message, Screen, colors } from '@/components/ui';
import { api, HandbookEntry } from '@/lib/api';
import { toDateString } from '@/lib/dates';
import { confirm, errorText } from '@/lib/dialogs';
import { PickedFile, pickImage, pickImages, uploadFile } from '@/lib/files';

/** 新增／修改一筆生產履歷紀錄：日期（預設今天）＋照片（可多張）＋選填文字 */
export default function HandbookEntryScreen() {
  const params = useLocalSearchParams<{ unitId: string; entryId?: string }>();
  const unitId = Number(params.unitId);
  const entryId = params.entryId ? Number(params.entryId) : null;
  const navigation = useNavigation();
  const [entry, setEntry] = useState<HandbookEntry | null>(null);
  const [date, setDate] = useState<string | null>(toDateString(new Date()));
  const [note, setNote] = useState('');
  const [pending, setPending] = useState<PickedFile[]>([]); // 還沒上傳的新照片
  const [loading, setLoading] = useState(entryId !== null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [menu, setMenu] = useState(false);

  useLayoutEffect(() => {
    navigation.setOptions({ title: entryId ? '修改生產履歷紀錄' : '新增生產履歷紀錄' });
  }, [navigation, entryId]);

  useEffect(() => {
    if (entryId === null) return;
    api.unitHandbook(unitId).then(
      (hb) => {
        const found = hb.entries.find((e) => e.id === entryId) ?? null;
        setEntry(found);
        if (found) {
          setDate(found.entry_date);
          setNote(found.note ?? '');
        } else setError('找不到這筆紀錄（可能已刪除）');
        setLoading(false);
      },
      (e) => {
        setError(errorText(e));
        setLoading(false);
      },
    );
  }, [unitId, entryId]);

  if (loading) return <Loading />;

  async function addPhotos(source: 'camera' | 'library') {
    try {
      const picked = source === 'camera' ? [await pickImage('camera')].filter((p): p is PickedFile => !!p) : await pickImages();
      if (picked.length) setPending((list) => [...list, ...picked]);
    } catch (e) {
      setError(errorText(e));
    }
  }

  async function removeSaved(photoId: number) {
    if (!(await confirm('刪除照片', '確定要刪除這張照片？', '刪除', true))) return;
    try {
      setEntry(await api.deleteHandbookPhoto(photoId));
    } catch (e) {
      setError(errorText(e));
    }
  }

  async function save() {
    if (!date) return setError('請選擇日期');
    if (!entry && !note.trim() && pending.length === 0) return setError('請加入照片或文字說明');
    setError(null);
    try {
      setBusy('儲存中…');
      const body = { entry_date: date, note: note.trim() || null };
      let saved = entry ? await api.updateHandbookEntry(entry.id, body) : await api.addHandbookEntry(unitId, body);
      setEntry(saved);
      // 照片一張一張上傳；中途失敗時已上傳的保留，畫面上只剩沒傳成功的
      for (let i = 0; i < pending.length; i++) {
        setBusy(`上傳照片 ${i + 1}/${pending.length}…`);
        saved = await uploadFile<HandbookEntry>(`/handbook/entries/${saved.id}/photos`, pending[i]);
        setEntry(saved);
        setPending((list) => list.slice(1));
      }
      router.back();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(null);
    }
  }

  async function remove() {
    if (!entry || !(await confirm('刪除紀錄', '確定要刪除這筆紀錄與所有照片？', '刪除', true))) return;
    try {
      await api.deleteHandbookEntry(entry.id);
      router.back();
    } catch (e) {
      setError(errorText(e));
    }
  }

  const photoCount = (entry?.photos.length ?? 0) + pending.length;

  return (
    <Screen>
      <Card>
        <DateTimeField label="日期" mode="date" value={date} onChange={setDate} />
        <Field
          label="文字說明（選填）"
          value={note}
          onChangeText={setNote}
          multiline
          style={{ minHeight: 90, textAlignVertical: 'top' }}
          placeholder="例如：浴室防水試水 48 小時，無滲漏"
        />
      </Card>

      <Card title={`照片（${photoCount} 張）`}>
        <View style={localStyles.grid}>
          {entry?.photos.map((p) => (
            <Thumb key={`s${p.id}`} uri={p.url} onRemove={() => removeSaved(p.id)} />
          ))}
          {pending.map((p, i) => (
            <Thumb key={`p${i}-${p.uri}`} uri={p.uri} pending onRemove={() => setPending((list) => list.filter((_, j) => j !== i))} />
          ))}
          <Pressable onPress={() => setMenu(true)} style={({ pressed }) => [localStyles.add, pressed && { opacity: 0.6 }]}>
            <Text style={localStyles.addText}>＋</Text>
            <Text style={localStyles.addLabel}>加入照片</Text>
          </Pressable>
        </View>
        {pending.length > 0 && <Text style={localStyles.hint}>標「待上傳」的照片會在按「儲存」時上傳</Text>}
      </Card>

      {error && <Message kind="error" text={error} />}
      {busy && <Message kind="info" text={busy} />}
      <Button label="儲存" onPress={save} loading={!!busy} />
      {entry && <Button label="刪除這筆紀錄" variant="danger" onPress={remove} />}

      <ActionSheet
        visible={menu}
        title="加入照片"
        onClose={() => setMenu(false)}
        options={[
          { label: '拍照', onPress: () => void addPhotos('camera') },
          { label: '從相簿選擇（可多選）', onPress: () => void addPhotos('library') },
        ]}
      />
    </Screen>
  );
}

function Thumb(props: { uri: string; pending?: boolean; onRemove: () => void }) {
  return (
    <View>
      <Image source={{ uri: props.uri }} style={localStyles.thumb} />
      {props.pending && <Text style={localStyles.pendingTag}>待上傳</Text>}
      <Pressable onPress={props.onRemove} hitSlop={6} style={localStyles.remove} accessibilityLabel="刪除照片">
        <Text style={localStyles.removeText}>✕</Text>
      </Pressable>
    </View>
  );
}

const THUMB = 96;
const localStyles = StyleSheet.create({
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  thumb: { width: THUMB, height: THUMB, borderRadius: 8, backgroundColor: colors.chip },
  pendingTag: { position: 'absolute', left: 4, bottom: 4, fontSize: 11, color: '#fff', backgroundColor: 'rgba(0,0,0,0.6)', paddingHorizontal: 4, borderRadius: 4, overflow: 'hidden' },
  remove: { position: 'absolute', top: 4, right: 4, width: 24, height: 24, borderRadius: 12, backgroundColor: 'rgba(0,0,0,0.6)', alignItems: 'center', justifyContent: 'center' },
  removeText: { color: '#fff', fontSize: 13, fontWeight: '700' },
  add: { width: THUMB, height: THUMB, borderRadius: 8, borderWidth: 1, borderStyle: 'dashed', borderColor: colors.primary, alignItems: 'center', justifyContent: 'center' },
  addText: { fontSize: 26, color: colors.primary },
  addLabel: { fontSize: 12, color: colors.primary },
  hint: { fontSize: 12, color: colors.muted, marginTop: 6 },
});
