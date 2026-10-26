import { router, useLocalSearchParams, useNavigation } from 'expo-router';
import { useLayoutEffect, useState } from 'react';
import { Image, Linking, Modal, Pressable, RefreshControl, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';

import { ActionSheet, PromptModal } from '@/components/overlays';
import { Button, Card, Loading, Message, MAX_WIDTH, colors } from '@/components/ui';
import { api, Inspection, InspectionPhoto, InspectionPoint, ResultValue } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { dayLabel, shortTime } from '@/lib/dates';
import { confirm, errorText } from '@/lib/dialogs';
import { openLink } from '@/lib/download';
import { pickImage, pickPdf, uploadFile } from '@/lib/files';
import { SERVICE_LABEL, STATUS_LABEL } from '@/lib/labels';
import { useLoad } from '@/lib/useLoad';

const RESULTS: { value: ResultValue; label: string; color: string; bg: string }[] = [
  { value: 'pass', label: '✓ 合格', color: '#166534', bg: '#dcfce7' },
  { value: 'fail', label: '✗ 不合格', color: '#991b1b', bg: '#fee2e2' },
  { value: 'na', label: '不適用', color: '#374151', bg: '#e5e7eb' },
];

export default function InspectionScreen() {
  const bookingId = Number(useLocalSearchParams<{ bookingId: string }>().bookingId);
  const { can } = useAuth();
  const navigation = useNavigation();
  const { data: ins, setData, error, setError, reload, refresh, refreshing } = useLoad(() => api.inspection(bookingId), [bookingId]);
  const [pointId, setPointId] = useState<number | null>(null); // 正在編輯備註 / 照片的檢查點；-1 代表整體照片
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [askEmail, setAskEmail] = useState(false);

  const editable = can('inspection.edit') && (ins?.status === 'not_started' || ins?.status === 'in_progress');

  useLayoutEffect(() => {
    navigation.setOptions({ title: ins ? `${ins.unit_no} ${SERVICE_LABEL[ins.service_type]}` : '' });
  }, [navigation, ins]);

  if (!ins) return error ? <Message kind="error" text={error} /> : <Loading />;

  const allPoints = ins.categories.flatMap((c) => c.items.flatMap((i) => i.points));
  const point = allPoints.find((p) => p.id === pointId);

  /** 單一檢查點更新後，只替換畫面上的那一個，並重新計算進度 */
  function applyPoint(updated: InspectionPoint) {
    setData((prev: Inspection | null) => {
      if (!prev) return prev;
      const categories = prev.categories.map((c) => ({
        ...c,
        items: c.items.map((i) => ({ ...i, points: i.points.map((p) => (p.id === updated.id ? updated : p)) })),
      }));
      const pts = categories.flatMap((c) => c.items.flatMap((i) => i.points));
      return {
        ...prev,
        categories,
        status: prev.status === 'not_started' ? 'in_progress' : prev.status,
        checked: pts.filter((p) => p.result !== 'pending').length,
        fail_count: pts.filter((p) => p.result === 'fail').length,
      };
    });
  }

  async function run(label: string | null, action: () => Promise<unknown>) {
    setBusy(label);
    try {
      setError(null);
      await action();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(null);
    }
  }

  const setResult = (p: InspectionPoint, result: ResultValue) =>
    run(null, async () => applyPoint(await api.setResult(bookingId, p.id, { result: p.result === result ? 'pending' : result })));

  const passAll = (points: InspectionPoint[]) =>
    run('整項標記合格…', async () => {
      for (const p of points.filter((x) => x.result === 'pending')) applyPoint(await api.setResult(bookingId, p.id, { result: 'pass' }));
    });

  async function previewReport() {
    await run('產生報告中…', async () => {
      await openLink(async () => (await api.reportLink(bookingId)).url);
    });
  }

  async function approve() {
    if (!(await confirm('Review OK', '確認報告內容無誤？確認後檢查結果不能再重新開啟修改。', '確認'))) return;
    await run('確認中…', async () => setData(await api.approveReport(bookingId)));
  }

  async function unapprove() {
    await run(null, async () => setData(await api.unapproveReport(bookingId)));
  }

  async function sendReport(to: string) {
    setAskEmail(false);
    await run('寄送中…', async () => {
      const updated = await api.sendReport(bookingId, to);
      setData(updated);
      setNotice(`已寄送報告與感謝信給 ${updated.sent_to}`);
    });
  }

  async function uploadExternal() {
    const file = await pickPdf().catch((e) => {
      setError(errorText(e));
      return null;
    });
    if (!file) return;
    await run('上傳報告中…', async () => {
      await uploadFile(`/bookings/${bookingId}/report`, file);
      setNotice(`已上傳「${file.name}」，此戶的上傳開關已自動關閉`);
      await reload();
    });
  }

  async function deleteExternal() {
    if (!(await confirm('刪除外部報告', '確定要刪除已上傳的報告？刪除後可以重新上傳。', '刪除', true))) return;
    await run(null, async () => {
      await api.deleteExternalReport(bookingId);
      await reload();
    });
  }

  async function allowReupload() {
    await run(null, async () => {
      await api.setUploadSwitch(ins!.unit_id, true);
      await reload();
    });
  }

  async function reopen() {
    if (!(await confirm('重新開啟', '會清除屋主的簽名，修改後需要請屋主重新簽名。確定？', '重新開啟', true))) return;
    await run('重新開啟…', async () => setData(await api.reopenInspection(bookingId)));
  }

  const status = STATUS_LABEL[ins.status];
  const done = ins.checked === ins.total && ins.total > 0;
  const isVisit = ins.service_type === 'visit';
  const canCheckIn = can('booking.manage') || can('inspection.edit');

  const checkIn = () => run('報到中…', async () => setData(await api.checkIn(bookingId)));
  const undoCheckIn = () => run(null, async () => setData(await api.undoCheckIn(bookingId)));

  return (
    <View style={{ flex: 1 }}>
      <ScrollView
        contentInsetAdjustmentBehavior="automatic" // iOS 半透明標題列時避免內容被擋住
        style={{ backgroundColor: colors.bg }}
        contentContainerStyle={localStyles.content}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} />}
      >
        <Card>
          <View style={localStyles.headRow}>
            <Text style={localStyles.headTitle}>{ins.project_name} {ins.unit_no}</Text>
            <Text style={[localStyles.badge, { color: status.color, borderColor: status.color }]}>{status.text}</Text>
          </View>
          <Text style={localStyles.meta}>{dayLabel(ins.date)} {shortTime(ins.start_time)}–{shortTime(ins.end_time)}　{ins.place}</Text>
          <Text style={localStyles.meta}>
            屋主：{ins.contact_name}{'　'}
            <Text style={localStyles.link} onPress={() => Linking.openURL(`tel:${ins.contact_phone}`)}>
              {ins.contact_phone}
            </Text>
          </Text>
          {!isVisit && (
            <>
              <View style={localStyles.progressTrack}>
                <View style={[localStyles.progressBar, { width: `${ins.total ? (ins.checked / ins.total) * 100 : 0}%` }]} />
              </View>
              <Text style={localStyles.meta}>
                已檢查 {ins.checked}/{ins.total}{ins.fail_count ? `｜不合格 ${ins.fail_count} 項` : ''}
              </Text>
            </>
          )}
        </Card>

        {error && <Message kind="error" text={error} />}
        {busy && <Message kind="info" text={busy} />}
        {notice && <Message kind="ok" text={notice} />}

        {isVisit ? (
          <Card title="參觀報到">
            {ins.checked_in_at ? (
              <>
                <Text style={localStyles.checkedIn}>✓ 已於 {ins.checked_in_at.replace('T', ' ').slice(0, 16)} 報到</Text>
                {canCheckIn && (
                  <Text style={[localStyles.link, { textAlign: 'center', marginTop: 8 }]} onPress={undoCheckIn}>取消報到</Text>
                )}
              </>
            ) : (
              <>
                <Text style={localStyles.meta}>參觀不需要填檢查項目，屋主到場後按「已到場」即可。</Text>
                {canCheckIn && <View style={{ marginTop: 8 }}><Button label="已到場（報到）" variant="secondary" onPress={checkIn} /></View>}
              </>
            )}
          </Card>
        ) : (
          <>
            {ins.categories.map((cat) => (
              <View key={cat.id} style={{ gap: 8 }}>
                <Text style={localStyles.category}>{cat.name}</Text>
                {cat.items.map((item) => (
                  <Card key={item.id}>
                    <View style={localStyles.itemHead}>
                      <Text style={localStyles.itemName}>{item.name}</Text>
                      {editable && item.points.some((p) => p.result === 'pending') && (
                        <Pressable onPress={() => passAll(item.points)} hitSlop={8}>
                          <Text style={localStyles.link}>其餘全部合格</Text>
                        </Pressable>
                      )}
                    </View>
                    {item.points.map((p) => (
                      <View key={p.id} style={localStyles.point}>
                        <Pressable style={localStyles.pointHead} onPress={() => setPointId(p.id)}>
                          <Text style={localStyles.pointName}>{p.name}</Text>
                          <Text style={localStyles.pointExtra}>
                            {p.note ? '📝 ' : ''}{p.photos.length ? `📷${p.photos.length} ` : ''}{editable ? '備註／拍照 ›' : p.note || p.photos.length ? '查看 ›' : ''}
                          </Text>
                        </Pressable>
                        <View style={localStyles.results}>
                          {RESULTS.map((r) => {
                            const on = p.result === r.value;
                            return (
                              <Pressable
                                key={r.value}
                                disabled={!editable}
                                onPress={() => setResult(p, r.value)}
                                style={[localStyles.resultBtn, on && { backgroundColor: r.bg, borderColor: r.color }]}
                              >
                                <Text style={[localStyles.resultText, on && { color: r.color, fontWeight: '700' }]}>{r.label}</Text>
                              </Pressable>
                            );
                          })}
                        </View>
                        {!!p.note && <Text style={localStyles.note}>{p.note}</Text>}
                        {p.photos.length > 0 && <Thumbs photos={p.photos} onPress={() => setPointId(p.id)} />}
                      </View>
                    ))}
                  </Card>
                ))}
              </View>
            ))}

            <Card title="整體備註與照片">
              <NoteEditor
                value={ins.general_note}
                editable={editable}
                placeholder="例如：整體狀況良好，屋主另提醒…"
                onSave={(text) => run(null, async () => setData(await api.updateInspectionNote(bookingId, text)))}
              />
              <Thumbs photos={ins.general_photos} onPress={() => setPointId(-1)} />
              {editable && <Button label="＋ 整體照片" variant="outline" onPress={() => setPointId(-1)} />}
            </Card>

            {ins.status === 'not_started' || ins.status === 'in_progress' ? (
              editable && (
                <Button
                  label={done ? '完成檢查，請屋主簽名' : `還有 ${ins.total - ins.checked} 個檢查點未填寫`}
                  disabled={!done}
                  onPress={() => router.push({ pathname: '/inspection/[bookingId]/sign', params: { bookingId: String(bookingId) } })}
                />
              )
            ) : (
              <Card title="屋主簽名">
                {ins.signature_url && <Image source={{ uri: ins.signature_url }} style={localStyles.signature} resizeMode="contain" />}
                <Text style={localStyles.meta}>
                  {ins.signer_name}　{ins.signed_at?.replace('T', ' ').slice(0, 16)}
                  {ins.inspector_name ? `｜驗屋人員 ${ins.inspector_name}` : ''}
                </Text>
              </Card>
            )}

            {(ins.status === 'signed' || ins.status === 'approved' || ins.status === 'sent') && (
              <Card title="報告">
                <Steps status={ins.status} />
                {ins.approved_at && (
                  <Text style={localStyles.meta}>
                    Review OK：{ins.approver_name ?? ''} {ins.approved_at.replace('T', ' ').slice(0, 16)}
                  </Text>
                )}
                {ins.sent_at && (
                  <Text style={localStyles.meta}>
                    已寄送：{ins.sent_at.replace('T', ' ').slice(0, 16)} → {ins.sent_to}
                  </Text>
                )}
                <View style={{ gap: 8, marginTop: 8 }}>
                  <Button label="預覽報告 PDF" variant="outline" onPress={previewReport} />
                  {ins.status === 'signed' && can('report.manage') && <Button label="Review OK（確認報告內容）" variant="secondary" onPress={approve} />}
                  {ins.status === 'approved' && can('report.manage') && (
                    <Button label="寄送報告給屋主" onPress={() => setAskEmail(true)} />
                  )}
                  {ins.status === 'sent' && can('report.manage') && (
                    <Button label="重新寄送報告" variant="outline" onPress={() => setAskEmail(true)} />
                  )}
                  {ins.status === 'approved' && can('report.manage') && (
                    <Text style={[localStyles.link, { textAlign: 'center' }]} onPress={unapprove}>取消確認</Text>
                  )}
                  {ins.status === 'signed' && can('inspection.edit') && (
                    <Text style={[localStyles.link, { textAlign: 'center' }]} onPress={reopen}>重新開啟（清除簽名後修改）</Text>
                  )}
                </View>
              </Card>
            )}
            <Card title="外部報告 PDF">
              {ins.external_report ? (
                <>
                  <Text style={localStyles.meta}>📄 {ins.external_report.filename}（{(ins.external_report.size / 1024 / 1024).toFixed(1)} MB）</Text>
                  <Text style={localStyles.meta}>
                    {ins.external_report.uploaded_at.replace('T', ' ').slice(0, 16)} 上傳{ins.external_report.uploaded_by ? `｜${ins.external_report.uploaded_by}` : ''}
                  </Text>
                  <View style={{ gap: 8, marginTop: 8 }}>
                    <Button label="開啟外部報告" variant="outline" onPress={() => Linking.openURL(ins.external_report!.url)} />
                    {can('report.manage') && ins.upload_enabled && <Button label="上傳新版本（取代）" onPress={uploadExternal} />}
                    {can('report.manage') && !ins.upload_enabled && (
                      <Text style={[localStyles.link, { textAlign: 'center' }]} onPress={allowReupload}>開啟上傳開關（允許重新上傳）</Text>
                    )}
                    {can('report.manage') && (
                      <Text style={[localStyles.link, { textAlign: 'center', color: colors.danger }]} onPress={deleteExternal}>刪除外部報告</Text>
                    )}
                  </View>
                </>
              ) : (
                <>
                  <Text style={localStyles.meta}>代驗屋公司或其他單位提供的報告（單一 PDF、30MB 以內）。上傳後會自動關閉此戶的上傳開關，寄送報告時一併附上。</Text>
                  {can('report.manage') && (
                    ins.upload_enabled
                      ? <View style={{ marginTop: 8 }}><Button label="上傳外部報告 PDF" variant="outline" onPress={uploadExternal} /></View>
                      : <Text style={[localStyles.link, { textAlign: 'center', marginTop: 8 }]} onPress={allowReupload}>上傳開關已關閉，點此開啟</Text>
                  )}
                </>
              )}
            </Card>
          </>
        )}
        <View style={{ height: 30 }} />
      </ScrollView>

      <PromptModal
        visible={askEmail}
        title={ins.status === 'sent' ? '重新寄送報告' : '寄送報告給屋主'}
        message="會寄出報告 PDF 與感謝信。收件人："
        initialValue={ins.sent_to ?? ins.default_email ?? ''}
        placeholder="owner@example.com"
        confirmText="寄送"
        onCancel={() => setAskEmail(false)}
        onConfirm={sendReport}
      />

      <PhotoNoteSheet
        visible={pointId !== null}
        title={pointId === -1 ? '整體照片' : point ? point.name : ''}
        point={pointId === -1 ? null : point ?? null}
        photos={pointId === -1 ? ins.general_photos : point?.photos ?? []}
        editable={editable}
        bookingId={bookingId}
        onClose={() => setPointId(null)}
        onPointChange={applyPoint}
        onPhotosChange={reload}
      />
    </View>
  );
}

function Steps({ status }: { status: string }) {
  const steps = [
    { label: '屋主簽名', done: true },
    { label: 'Review OK', done: status === 'approved' || status === 'sent' },
    { label: '寄送給屋主', done: status === 'sent' },
  ];
  return (
    <View style={localStyles.steps}>
      {steps.map((s, i) => (
        <View key={s.label} style={localStyles.step}>
          <View style={[localStyles.stepDot, s.done && localStyles.stepDotDone]}>
            <Text style={[localStyles.stepNum, s.done && { color: '#fff' }]}>{s.done ? '✓' : i + 1}</Text>
          </View>
          <Text style={[localStyles.stepLabel, s.done && { color: colors.green, fontWeight: '600' }]}>{s.label}</Text>
        </View>
      ))}
    </View>
  );
}

function Thumbs({ photos, onPress }: { photos: InspectionPhoto[]; onPress: () => void }) {
  if (!photos.length) return null;
  return (
    <Pressable onPress={onPress} style={localStyles.thumbs}>
      {photos.map((ph) => (
        <Image key={ph.id} source={{ uri: ph.url }} style={localStyles.thumb} />
      ))}
    </Pressable>
  );
}

function NoteEditor(props: { value: string | null; editable: boolean; placeholder?: string; onSave: (text: string | null) => void }) {
  const [text, setText] = useState(props.value ?? '');
  const dirty = text.trim() !== (props.value ?? '');
  return (
    <View style={{ gap: 6 }}>
      <TextInput
        style={localStyles.noteInput}
        value={text}
        onChangeText={setText}
        editable={props.editable}
        multiline
        placeholder={props.editable ? props.placeholder : '（無）'}
        placeholderTextColor="#9ca3af"
        onBlur={() => dirty && props.onSave(text.trim() || null)}
      />
      {props.editable && dirty && <Button label="儲存備註" variant="secondary" onPress={() => props.onSave(text.trim() || null)} />}
    </View>
  );
}

/** 單一檢查點的備註與照片（point 為 null 時是整體照片） */
function PhotoNoteSheet(props: {
  visible: boolean;
  title: string;
  point: InspectionPoint | null;
  photos: InspectionPhoto[];
  editable: boolean;
  bookingId: number;
  onClose: () => void;
  onPointChange: (p: InspectionPoint) => void;
  onPhotosChange: () => Promise<void>;
}) {
  const [uploading, setUploading] = useState(false);
  const [viewing, setViewing] = useState<InspectionPhoto | null>(null);
  const [menu, setMenu] = useState(false);
  // 錯誤要顯示在這個視窗裡；顯示在後面的頁面會被視窗擋住，看起來像沒反應
  const [sheetError, setSheetError] = useState<string | null>(null);
  const fail = (e: unknown) => setSheetError(errorText(e));

  async function add(source: 'camera' | 'library') {
    setSheetError(null);
    try {
      const file = await pickImage(source);
      if (!file) return;
      setUploading(true);
      await uploadFile(`/inspections/${props.bookingId}/photos`, file, props.point ? { check_point_id: String(props.point.id) } : {});
      await props.onPhotosChange();
    } catch (e) {
      fail(e);
    } finally {
      setUploading(false);
    }
  }

  async function remove(ph: InspectionPhoto) {
    if (!(await confirm('刪除照片', '確定要刪除這張照片？', '刪除', true))) return;
    try {
      await api.deletePhoto(ph.id);
      setViewing(null);
      await props.onPhotosChange();
    } catch (e) {
      setViewing(null);
      fail(e);
    }
  }

  return (
    <Modal visible={props.visible} animationType="slide" presentationStyle="pageSheet" onRequestClose={props.onClose}>
      <View style={localStyles.sheetHead}>
        <Text style={localStyles.sheetTitle}>{props.title}</Text>
        <Pressable onPress={props.onClose} hitSlop={12}>
          <Text style={[localStyles.link, { fontSize: 17, fontWeight: '600' }]}>完成</Text>
        </Pressable>
      </View>
      <ScrollView contentContainerStyle={[localStyles.content, { paddingBottom: 60 }]} keyboardShouldPersistTaps="handled">
        {sheetError && <Message kind="error" text={sheetError} />}
        {props.point && (
          <Card title="備註">
            <NoteEditor
              key={props.point.id}
              value={props.point.note}
              editable={props.editable}
              placeholder="例如：膠條脫落、窗框刮傷 3 公分"
              onSave={async (note) => {
                try {
                  props.onPointChange(await api.setResult(props.bookingId, props.point!.id, { note }));
                } catch (e) {
                  fail(e);
                }
              }}
            />
          </Card>
        )}
        <Card title={`照片（${props.photos.length}）`}>
          <View style={localStyles.grid}>
            {props.photos.map((ph) => (
              <Pressable key={ph.id} onPress={() => setViewing(ph)}>
                <Image source={{ uri: ph.url }} style={localStyles.gridPhoto} />
              </Pressable>
            ))}
          </View>
          {props.photos.length === 0 && <Text style={localStyles.meta}>尚無照片</Text>}
          {props.editable && <Button label={uploading ? '上傳中…' : '＋ 新增照片'} loading={uploading} onPress={() => setMenu(true)} />}
        </Card>
      </ScrollView>

      <ActionSheet
        visible={menu}
        title="新增照片"
        onClose={() => setMenu(false)}
        options={[
          { label: '拍照', onPress: () => void add('camera') },
          { label: '從相簿選擇', onPress: () => void add('library') },
        ]}
      />
      <Modal visible={!!viewing} transparent animationType="fade" onRequestClose={() => setViewing(null)}>
        <Pressable style={localStyles.viewer} onPress={() => setViewing(null)}>
          {viewing && <Image source={{ uri: viewing.url }} style={localStyles.viewerImage} resizeMode="contain" />}
          {viewing && props.editable && (
            <Pressable style={localStyles.viewerDelete} onPress={() => remove(viewing)}>
              <Text style={{ color: '#fff', fontSize: 16, fontWeight: '600' }}>刪除這張照片</Text>
            </Pressable>
          )}
        </Pressable>
      </Modal>
    </Modal>
  );
}

const localStyles = StyleSheet.create({
  content: { padding: 16, gap: 10, width: '100%', maxWidth: MAX_WIDTH, alignSelf: 'center' },
  headRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  headTitle: { flex: 1, fontSize: 18, fontWeight: '700', color: colors.text },
  badge: { fontSize: 12, fontWeight: '600', borderWidth: 1, borderRadius: 999, paddingHorizontal: 8, paddingVertical: 2 },
  meta: { fontSize: 14, color: colors.muted, marginTop: 2 },
  link: { color: colors.primary },
  checkedIn: { fontSize: 17, fontWeight: '700', color: colors.green },
  progressTrack: { height: 8, borderRadius: 4, backgroundColor: '#e5e7eb', marginTop: 10, overflow: 'hidden' },
  progressBar: { height: 8, backgroundColor: colors.green },
  category: { fontSize: 15, fontWeight: '700', color: colors.muted, marginTop: 8, marginLeft: 4 },
  itemHead: { flexDirection: 'row', alignItems: 'center', marginBottom: 4 },
  itemName: { flex: 1, fontSize: 17, fontWeight: '700', color: colors.text },
  point: { paddingVertical: 10, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border, gap: 8 },
  pointHead: { flexDirection: 'row', alignItems: 'center' },
  pointName: { flex: 1, fontSize: 16, color: colors.text },
  pointExtra: { fontSize: 13, color: colors.primary },
  results: { flexDirection: 'row', gap: 8 },
  resultBtn: { flex: 1, borderWidth: 1, borderColor: colors.border, borderRadius: 8, paddingVertical: 10, alignItems: 'center', backgroundColor: '#fff' },
  resultText: { fontSize: 15, color: colors.text },
  note: { fontSize: 14, color: '#374151', backgroundColor: '#f9fafb', borderRadius: 6, padding: 8 },
  thumbs: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  thumb: { width: 64, height: 64, borderRadius: 6, backgroundColor: '#e5e7eb' },
  noteInput: { borderWidth: 1, borderColor: colors.border, borderRadius: 8, padding: 10, minHeight: 70, fontSize: 15, color: colors.text, textAlignVertical: 'top' },
  signature: { width: '100%', height: 140, backgroundColor: '#fff' },
  steps: { flexDirection: 'row', justifyContent: 'space-between', marginVertical: 8 },
  step: { flex: 1, alignItems: 'center', gap: 4 },
  stepDot: { width: 28, height: 28, borderRadius: 14, borderWidth: 1, borderColor: colors.border, alignItems: 'center', justifyContent: 'center' },
  stepDotDone: { backgroundColor: colors.green, borderColor: colors.green },
  stepNum: { fontSize: 14, color: colors.muted, fontWeight: '700' },
  stepLabel: { fontSize: 13, color: colors.muted },
  sheetHead: { flexDirection: 'row', alignItems: 'center', padding: 16, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border, backgroundColor: '#fff' },
  sheetTitle: { flex: 1, fontSize: 18, fontWeight: '700', color: colors.text },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 8 },
  gridPhoto: { width: 104, height: 104, borderRadius: 8, backgroundColor: '#e5e7eb' },
  viewer: { flex: 1, backgroundColor: 'rgba(0,0,0,0.92)', justifyContent: 'center', alignItems: 'center' },
  viewerImage: { width: '100%', height: '80%' },
  viewerDelete: { position: 'absolute', bottom: 48, backgroundColor: colors.danger, borderRadius: 10, paddingHorizontal: 20, paddingVertical: 12 },
});
