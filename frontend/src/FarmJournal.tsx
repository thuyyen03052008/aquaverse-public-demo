import { apiFetch } from './apiClient';
import { useEffect, useState, type FormEvent } from 'react';

const API_BASE = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '');
const numberVN = new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 2 });

type Category = 'feeding' | 'water' | 'growth' | 'expense' | 'care';
type Entry = { id: number; cycle_id: number; recorded_on: string; notes: string | null };
type Feeding = Entry & { feed_name: string; amount_kg: number };
type Water = Entry & { temperature_c: number | null; ph: number | null; dissolved_oxygen_mg_l: number | null; ammonia_mg_l: number | null; ammonia_type: 'TAN' | 'NH3' | null };
type Growth = Entry & { sample_count: number; avg_weight_g: number };
type Expense = Entry & { category: string; amount_vnd: number };
type Care = Entry & { activity_type: string; water_replaced_percent: number | null };
type Records = { feeding: Feeding[]; water: Water[]; growth: Growth[]; expense: Expense[]; care: Care[] };
type Summary = { cycle_id: number; feeding_entries: number; feed_total_kg: number; water_entries: number; growth_samples: number; care_entries: number; expense_entries: number; recorded_expenses_vnd: number };

const tabs: { id: Category; label: string; endpoint: string }[] = [
  { id: 'feeding', label: 'Thức ăn', endpoint: 'feeding-records' },
  { id: 'water', label: 'Chất lượng nước', endpoint: 'water-records' },
  { id: 'growth', label: 'Tăng trưởng', endpoint: 'growth-samples' },
  { id: 'expense', label: 'Chi phí', endpoint: 'expenses' },
  { id: 'care', label: 'Chăm sóc', endpoint: 'care-activities' },
];
const expenseLabels: Record<string, string> = {
  feed: 'Thức ăn', seed: 'Con giống', electricity: 'Điện', labor: 'Nhân công',
  equipment: 'Thiết bị', treatment: 'Xử lý', testing: 'Kiểm nghiệm', other: 'Khác',
};
const activityLabels: Record<string, string> = {
  water_change: 'Thay nước', cleaning: 'Vệ sinh', grading: 'Phân cỡ',
  inspection: 'Kiểm tra', other: 'Khác',
};

function detailMessage(payload: unknown): string {
  if (typeof payload !== 'object' || payload === null || !('detail' in payload)) return 'Yêu cầu không thành công.';
  const detail = payload.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map((item: { loc?: string[]; msg?: string }) => `${item.loc?.join(' → ') ?? 'Dữ liệu'}: ${item.msg ?? 'không hợp lệ'}`).join('; ');
  return 'Dữ liệu chưa hợp lệ.';
}

async function api<T>(path: string, body?: unknown): Promise<T> {
  let response: Response;
  try {
    response = await apiFetch(`${API_BASE}${path}`, {
      method: body === undefined ? 'GET' : 'POST',
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new Error('Không kết nối được Backend. Kiểm tra Terminal FastAPI (port 8000).');
  }
  const parsed: unknown = await response.json().catch(() => null);
  if (!response.ok) throw new Error(`${response.status}: ${detailMessage(parsed)}`);
  return parsed as T;
}

function optionalNumber(form: FormData, name: string): number | null {
  const raw = String(form.get(name) ?? '').trim();
  return raw === '' ? null : Number(raw);
}
function optionalText(form: FormData, name: string): string | null {
  return String(form.get(name) ?? '').trim() || null;
}
function formatRow(tab: Category, item: Entry): string {
  switch (tab) {
    case 'feeding': {
      const row = item as Feeding;
      return `${row.feed_name} · ${numberVN.format(row.amount_kg)} kg`;
    }
    case 'water': {
      const row = item as Water;
      return [
        row.temperature_c === null ? null : `${numberVN.format(row.temperature_c)} °C`,
        row.ph === null ? null : `pH ${numberVN.format(row.ph)}`,
        row.dissolved_oxygen_mg_l === null ? null : `DO ${numberVN.format(row.dissolved_oxygen_mg_l)} mg/L`,
        row.ammonia_mg_l === null ? null : `${row.ammonia_type} ${numberVN.format(row.ammonia_mg_l)} mg/L`,
      ].filter(Boolean).join(' · ');
    }
    case 'growth': {
      const row = item as Growth;
      return `${numberVN.format(row.sample_count)} con lấy mẫu · ${numberVN.format(row.avg_weight_g)} g/con`;
    }
    case 'expense': {
      const row = item as Expense;
      return `${expenseLabels[row.category] ?? row.category} · ${numberVN.format(row.amount_vnd)} ₫`;
    }
    case 'care': {
      const row = item as Care;
      const suffix = row.water_replaced_percent === null ? '' : ` · ${numberVN.format(row.water_replaced_percent)}% nước`;
      return `${activityLabels[row.activity_type] ?? row.activity_type}${suffix}`;
    }
  }
}

function Field({ label, name, type = 'text', required = false, min, max, step, placeholder }: {
  label: string; name: string; type?: string; required?: boolean; min?: string; max?: string; step?: string; placeholder?: string;
}) {
  return <label className="journal-field"><span>{label}</span><input name={name} type={type} required={required} min={min} max={max} step={step} placeholder={placeholder} defaultValue={type === 'date' ? new Date().toLocaleDateString('sv-SE') : undefined} /></label>;
}

export default function FarmJournal({ cycleId }: { cycleId: number | null }) {
  const [tab, setTab] = useState<Category>('feeding');
  const [records, setRecords] = useState<Records>({ feeding: [], water: [], growth: [], expense: [], care: [] });
  const [summary, setSummary] = useState<Summary | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  useEffect(() => {
    if (cycleId === null) return;
    let active = true;
    setLoading(true); setError('');
    Promise.all([
      ...tabs.map((entry) => api<Entry[]>(`/api/cycles/${cycleId}/${entry.endpoint}`)),
      api<Summary>(`/api/cycles/${cycleId}/summary`),
    ]).then((results) => {
      if (!active) return;
      setRecords({
        feeding: results[0] as Feeding[], water: results[1] as Water[], growth: results[2] as Growth[],
        expense: results[3] as Expense[], care: results[4] as Care[],
      });
      setSummary(results[5] as Summary);
    }).catch((reason: unknown) => { if (active) setError(reason instanceof Error ? reason.message : 'Không tải được nhật ký.'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [cycleId]);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (cycleId === null || saving) return;
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const notes = optionalText(form, 'notes');
    const data: Record<string, unknown> = { recorded_on: String(form.get('recorded_on')), notes };
    if (tab === 'feeding') {
      data.feed_name = String(form.get('feed_name') ?? '').trim();
      data.amount_kg = optionalNumber(form, 'amount_kg');
    } else if (tab === 'water') {
      data.temperature_c = optionalNumber(form, 'temperature_c');
      data.ph = optionalNumber(form, 'ph');
      data.dissolved_oxygen_mg_l = optionalNumber(form, 'dissolved_oxygen_mg_l');
      data.ammonia_mg_l = optionalNumber(form, 'ammonia_mg_l');
      data.ammonia_type = data.ammonia_mg_l === null ? null : String(form.get('ammonia_type') ?? 'TAN');
    } else if (tab === 'growth') {
      data.sample_count = optionalNumber(form, 'sample_count');
      data.avg_weight_g = optionalNumber(form, 'avg_weight_g');
    } else if (tab === 'expense') {
      data.category = String(form.get('category') ?? 'other');
      data.amount_vnd = optionalNumber(form, 'amount_vnd');
    } else {
      data.activity_type = String(form.get('activity_type') ?? 'other');
      data.water_replaced_percent = optionalNumber(form, 'water_replaced_percent');
    }
    const endpoint = tabs.find((entry) => entry.id === tab)?.endpoint;
    if (!endpoint) return;
    setError(''); setNotice(''); setSaving(true);
    try {
      await api<Entry>(`/api/cycles/${cycleId}/${endpoint}`, data);
      const [entries, updated] = await Promise.all([
        api<Entry[]>(`/api/cycles/${cycleId}/${endpoint}`),
        api<Summary>(`/api/cycles/${cycleId}/summary`),
      ]);
      setRecords((old) => ({ ...old, [tab]: entries }));
      setSummary(updated);
      formElement.reset();
      setNotice('Đã lưu bản ghi vào database.');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Lưu nhật ký thất bại.');
    } finally { setSaving(false); }
  }

  const activeRows = records[tab] as Entry[];
  return <section className="journal-section" aria-labelledby="journal-title">
    <div className="journal-head"><div><span className="intro-eyebrow">PHASE 1C · NHẬT KÝ THỰC</span><h2 id="journal-title">Nhật ký AquaFarm</h2><p>Ghi nhận theo vụ nuôi. Chỉ số không đồng nghĩa với kết luận an toàn sinh học.</p></div>{cycleId !== null && <span className="scope-pill">Vụ nuôi #{cycleId}</span>}</div>
    {cycleId === null ? <div className="panel"><p className="helper">Hãy tạo hoặc chọn một vụ nuôi ở phần trên để bắt đầu ghi nhật ký.</p></div> : <>
      <div className="journal-metrics" aria-label="Tổng hợp nhật ký">
        <div><span>Tổng thức ăn đã ghi</span><strong>{summary ? `${numberVN.format(summary.feed_total_kg)} kg` : '…'}</strong></div>
        <div><span>Chi phí đã nhập</span><strong>{summary ? `${numberVN.format(summary.recorded_expenses_vnd)} ₫` : '…'}</strong></div>
        <div><span>Lần đo nước</span><strong>{summary ? numberVN.format(summary.water_entries) : '…'}</strong></div>
        <div><span>Lần lấy mẫu</span><strong>{summary ? numberVN.format(summary.growth_samples) : '…'}</strong></div>
      </div>
      <p className="journal-caveat">Chi phí chỉ bao gồm các khoản bạn nhập; thức ăn ghi theo khối lượng không tự tạo chi phí để tránh cộng hai lần.</p>
      <div className="journal-tabs" role="tablist" aria-label="Loại nhật ký">
        {tabs.map((entry) => <button key={entry.id} type="button" role="tab" aria-selected={tab === entry.id} className={tab === entry.id ? 'active' : ''} onClick={() => { setTab(entry.id); setError(''); setNotice(''); }}>{entry.label}</button>)}
      </div>
      {error && <div className="message error" role="alert">{error}</div>}
      {notice && <div className="message success" role="status">✓ {notice}</div>}
      <div className="journal-grid">
        <form key={`${cycleId}-${tab}`} className="panel journal-form" onSubmit={save}>
          <h3>+ Thêm {tabs.find((x) => x.id === tab)?.label.toLowerCase()}</h3>
          <Field label="Ngày ghi nhận" name="recorded_on" type="date" required />
          {tab === 'feeding' && <><Field label="Tên thức ăn" name="feed_name" required placeholder="Ví dụ: Thức ăn viên" /><Field label="Khối lượng (kg)" name="amount_kg" type="number" min="0.001" step="any" required /></>}
          {tab === 'water' && <><div className="journal-two"><Field label="Nhiệt độ (°C)" name="temperature_c" type="number" min="0" max="50" step="any" /><Field label="pH" name="ph" type="number" min="0" max="14" step="any" /></div><div className="journal-two"><Field label="DO (mg/L)" name="dissolved_oxygen_mg_l" type="number" min="0" step="any" /><Field label="Ammonia (mg/L)" name="ammonia_mg_l" type="number" min="0" step="any" /></div><label className="journal-field"><span>Loại phép đo ammonia</span><select name="ammonia_type" defaultValue="TAN"><option value="TAN">TAN (tổng ammonia)</option><option value="NH3">NH₃ (không ion hóa)</option></select></label><p className="helper">Nhập ít nhất một chỉ số. Không thay thế TAN và NH₃ cho nhau; giữ nguyên đơn vị và cách báo cáo trên thiết bị/phiếu đo.</p></>}
          {tab === 'growth' && <div className="journal-two"><Field label="Số con lấy mẫu" name="sample_count" type="number" min="1" step="1" required /><Field label="Khối lượng TB (g/con)" name="avg_weight_g" type="number" min="0.001" step="any" required /></div>}
          {tab === 'expense' && <><label className="journal-field"><span>Danh mục chi phí</span><select name="category">{Object.entries(expenseLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><Field label="Số tiền (VND)" name="amount_vnd" type="number" min="1" step="1" required /></>}
          {tab === 'care' && <><label className="journal-field"><span>Hoạt động chăm sóc</span><select name="activity_type">{Object.entries(activityLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><Field label="Tỷ lệ nước thay (%) – chỉ dùng khi chọn Thay nước" name="water_replaced_percent" type="number" min="0" max="100" step="any" /></>}
          <label className="journal-field"><span>Ghi chú {tab === 'care' ? '(bắt buộc)' : '(không bắt buộc)'}</span><textarea name="notes" rows={3} maxLength={1000} required={tab === 'care'} placeholder="Quan sát hoặc nguồn dữ liệu…" /></label>
          <button className="button primary" type="submit" disabled={saving}>{saving ? 'Đang lưu…' : 'Lưu nhật ký'}</button>
        </form>
        <div className="panel journal-history"><div className="journal-history-head"><h3>Lịch sử ghi nhận</h3><span>{loading ? 'Đang tải…' : `${activeRows.length} bản ghi`}</span></div>
          {!loading && activeRows.length === 0 ? <p className="helper">Chưa có dữ liệu cho mục này.</p> : <div className="journal-list">{activeRows.map((entry) => <article key={entry.id} className="journal-record"><div className="journal-record-top"><time dateTime={entry.recorded_on}>{entry.recorded_on}</time><span>#{entry.id}</span></div><strong>{formatRow(tab, entry)}</strong>{entry.notes && <p>{entry.notes}</p>}</article>)}</div>}
        </div>
      </div>
    </>}
  </section>;
}
