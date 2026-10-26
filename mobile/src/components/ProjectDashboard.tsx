/** 建案儀表板：點進建案時最先顯示的綜合狀態，並可匯出主管會議用的報表 */
import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { ChartCard, chartColors, DataTable, HBars, pct, Segment, StackedColumns, StackedRows, StatTile } from './charts';
import { Message, colors } from './ui';
import { api, Dashboard, StageKey } from '@/lib/api';
import { errorText } from '@/lib/dialogs';
import { openLink } from '@/lib/download';

const STAGES: StageKey[] = ['completed', 'booked', 'invited', 'not_invited'];
const SERVICES = [
  { key: 'visit', label: '參觀' },
  { key: 'inspection', label: '驗屋' },
  { key: 'health_check', label: '健檢' },
] as const;

export function ProjectDashboard({ data, projectId }: { data: Dashboard; projectId: number }) {
  const [notice, setNotice] = useState<{ ok: boolean; text: string } | null>(null);
  const total = data.units.total;

  async function exportReport(format: 'html' | 'xlsx') {
    setNotice(null);
    try {
      let filename = '';
      await openLink(async () => {
        const link = await api.reportExportLink(projectId, format);
        filename = link.filename;
        return link.url;
      });
      setNotice({ ok: true, text: `已在瀏覽器開啟「${filename}」，可儲存或分享（連結 5 分鐘內有效）` });
    } catch (e) {
      setNotice({ ok: false, text: errorText(e) });
    }
  }

  const stageLegend: Segment[] = STAGES.map((k) => ({ key: k, label: data.stage_labels[k], value: 0, color: chartColors.stage[k] }));
  const serviceLegend: Segment[] = SERVICES.map((s) => ({ key: s.key, label: s.label, value: 0, color: chartColors.service[s.key] }));

  return (
    <View style={{ gap: 10 }}>
      <View style={localStyles.head}>
        <Text style={localStyles.title}>儀表板</Text>
        <Text style={localStyles.time}>資料時間 {data.generated_at.replace('T', ' ')}</Text>
      </View>

      <View style={localStyles.tiles}>
        <StatTile label="住戶" value={total} sub={data.units.without_email ? `${data.units.without_email} 戶缺 Email` : 'Email 皆已登錄'} />
        {data.phases.map((p) => (
          <StatTile
            key={p.service}
            label={`${p.label}完成`}
            value={`${p.stages.completed} / ${total}`}
            meter={{ value: p.stages.completed, total }}
            sub={p.has_reports ? `已預約 ${p.bookings}・報告已寄 ${p.reports_sent}` : `已預約 ${p.bookings}`}
          />
        ))}
        <StatTile
          label="逾期未完成報告"
          value={data.overdue_reports}
          status={data.overdue_reports ? 'critical' : 'good'}
          sub="預約日後超過 7 天"
          wide
        />
      </View>

      <ChartCard
        title="各階段進度"
        subtitle={`共 ${total} 戶，依住戶目前進度分段`}
        legend={stageLegend}
        table={
          <DataTable
            headers={['階段', ...STAGES.map((k) => data.stage_labels[k]), '完成率']}
            rows={data.phases.map((p) => [p.label, ...STAGES.map((k) => p.stages[k]), pct(p.stages.completed, total)])}
            emphasizeLast
          />
        }
      >
        <StackedRows
          rows={data.phases.map((p) => ({
            key: p.service,
            label: p.label,
            total,
            note: `完成 ${pct(p.stages.completed, total)}`,
            segments: STAGES.map((k) => ({ key: k, label: data.stage_labels[k], value: p.stages[k], color: chartColors.stage[k] })),
          }))}
        />
      </ChartCard>

      {data.daily.length > 0 && (
        <ChartCard
          title="每日預約數"
          subtitle="參觀／驗屋／健檢分色堆疊"
          legend={serviceLegend}
          table={
            <DataTable
              headers={['日期', ...SERVICES.map((s) => s.label), '合計']}
              rows={data.daily.map((d) => [d.date.slice(5), ...SERVICES.map((s) => d[s.key]), SERVICES.reduce((n, s) => n + d[s.key], 0)])}
            />
          }
        >
          <StackedColumns
            columns={data.daily.map((d) => ({
              key: d.date,
              label: d.date.slice(5).replace('-', '/'),
              segments: SERVICES.map((s) => ({ key: s.key, label: s.label, value: d[s.key], color: chartColors.service[s.key] })),
            }))}
          />
        </ChartCard>
      )}

      {data.top_fails.length > 0 && (
        <ChartCard
          title="最常見的不合格項目"
          subtitle="Top 10，作為改善優先順序參考"
          table={<DataTable headers={['項目', '次數']} rows={data.top_fails.map((f) => [`${f.service_label}｜${f.label}`, f.count])} />}
        >
          <HBars rows={data.top_fails.map((f, i) => ({ key: String(i), label: f.label, tag: f.service_label, value: f.count }))} />
        </ChartCard>
      )}

      <View style={localStyles.exportCard}>
        <Text style={localStyles.exportTitle}>匯出報表</Text>
        <View style={localStyles.exportGroup}>
          <ExportButton icon="🌐" label="互動網頁" onPress={() => exportReport('html')} />
          <View style={localStyles.exportDivider} />
          <ExportButton icon="📊" label="Excel 圖表" onPress={() => exportReport('xlsx')} />
        </View>
      </View>
      {notice && <Message kind={notice.ok ? 'ok' : 'error'} text={notice.text} />}
    </View>
  );
}

function ExportButton({ icon, label, onPress }: { icon: string; label: string; onPress: () => void }) {
  return (
    <Pressable onPress={onPress} style={({ pressed }) => [localStyles.exportButton, pressed && { backgroundColor: colors.subtle }]}>
      <Text style={localStyles.exportIcon}>{icon}</Text>
      <Text style={localStyles.exportText}>{label}</Text>
    </Pressable>
  );
}

const localStyles = StyleSheet.create({
  head: { flexDirection: 'row', alignItems: 'baseline', justifyContent: 'space-between', marginTop: 4 },
  title: { fontSize: 18, fontWeight: '700', color: colors.text },
  time: { fontSize: 12, color: colors.muted },
  tiles: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  exportCard: { backgroundColor: colors.card, borderRadius: 12, padding: 16, gap: 12 },
  exportTitle: { fontSize: 16, fontWeight: '700', color: colors.text },
  // 兩個匯出按鈕合成一組，中間細線分隔
  exportGroup: { flexDirection: 'row', borderWidth: 1, borderColor: colors.primary, borderRadius: 10, overflow: 'hidden' },
  exportButton: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingVertical: 12 },
  exportDivider: { width: 1, backgroundColor: colors.primary },
  exportIcon: { fontSize: 16 },
  exportText: { color: colors.primary, fontSize: 15, fontWeight: '600' },
});
