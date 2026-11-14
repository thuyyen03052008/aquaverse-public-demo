import { apiFetch } from './apiClient';
import { useEffect, useMemo, useState, type FormEvent } from 'react';

const API_BASE = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '');
const vi = new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 2 });
const money = (v: number) => `${vi.format(v)} đ`;

interface Cycle { id: number; start_date: string; stocked_count: number }
interface Choice { id: number; scenario_id: number; cycle_id: number; created_at: string }
interface Scenario { id: number; name: string; results: {
  harvest_biomass_kg: number; estimated_feed_kg: number; total_cost_vnd: number;
  estimated_revenue_vnd: number; estimated_balance_vnd: number;
} }
interface Comparison {
  scenario_name: string;
  planned_harvest_biomass_kg: number; reported_harvest_biomass_kg: number; delta_harvest_biomass_kg: number;
  planned_revenue_vnd: number; reported_revenue_vnd: number; delta_revenue_vnd: number;
  planned_cost_vnd: number; reported_cost_vnd: number; delta_cost_vnd: number;
  planned_balance_vnd: number; reported_balance_vnd: number; delta_balance_vnd: number;
  planned_feed_kg: number; reported_feed_kg: number | null; delta_feed_kg: number | null;
  explanation: string;
}
interface Outcome {
  id: number; cycle_id: number; choice_id: number; recorded_on: string;
  source_kind: 'user_reported' | 'synthetic_demo';
  harvested_count: number; harvest_biomass_kg: number; actual_feed_kg: number | null;
  total_cost_vnd: number; revenue_vnd: number; notes: string;
  comparison: Comparison;
}
interface Draft {
  recorded_on: string; source_kind: 'user_reported' | 'synthetic_demo';
  harvested_count: string; harvest_biomass_kg: string; actual_feed_kg: string;
  total_cost_vnd: string; revenue_vnd: string; notes: string;
}

function localToday(): string {
  const now = new Date();
  const adjusted = new Date(now.getTime() - now.getTimezoneOffset() * 60000);
  return adjusted.toISOString().slice(0, 10);
}
function emptyDraft(): Draft {
  return { recorded_on: localToday(), source_kind: 'user_reported', harvested_count: '',
    harvest_biomass_kg: '', actual_feed_kg: '', total_cost_vnd: '', revenue_vnd: '', notes: '' };
}
async function request<T>(path: string, data?: unknown): Promise<T> {
  let response: Response;
  try {
    response = await apiFetch(`${API_BASE}${path}`, {
      method: data === undefined ? 'GET' : 'POST',
      headers: data === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: data === undefined ? undefined : JSON.stringify(data),
    });
  } catch { throw new Error('Không kết nối được backend trên port 8000.'); }
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    let detail = 'Không thể xử lý dữ liệu.';
    if (body && typeof body === 'object' && 'detail' in body) {
      const raw = body.detail;
      detail = typeof raw === 'string' ? raw : Array.isArray(raw)
        ? raw.map((entry: { msg?: string; loc?: string[] }) => `${entry.loc?.join(' → ') ?? ''} ${entry.msg ?? ''}`).join('; ')
        : detail;
    }
    throw new Error(`${response.status} – ${detail}`);
  }
  return body as T;
}

function DeltaLine({ name, estimated, reported, delta, unit }: {
  name: string; estimated: number; reported: number; delta: number; unit: 'kg' | 'vnd'
}) {
  const fmt = (n: number) => unit === 'vnd' ? money(n) : `${vi.format(n)} kg`;
  return <div className="outcome-metric">
    <span>{name}</span><span>{fmt(estimated)}</span><strong>{fmt(reported)}</strong>
    <strong className={delta === 0 ? '' : 'outcome-difference'}>{delta > 0 ? '+' : ''}{fmt(delta)}</strong>
  </div>;
}

export default function OutcomeReview({ cycle, scenarios, choices }: {
  cycle: Cycle; scenarios: Scenario[]; choices: Choice[];
}) {
  const [selectedChoiceId, setSelectedChoiceId] = useState<number | null>(null);
  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const [outcomes, setOutcomes] = useState<Outcome[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const path = `/api/cycles/${cycle.id}/decision/outcomes`;

  useEffect(() => {
    setSelectedChoiceId(current => current !== null && choices.some(c => c.id === current)
      ? current : (choices[0]?.id ?? null));
  }, [choices]);
  useEffect(() => {
    let active = true;
    request<Outcome[]>(path).then(records => { if (active) setOutcomes(records); })
      .catch(e => { if (active) setError(e instanceof Error ? e.message : 'Không tải được kết quả.'); });
    return () => { active = false; };
  }, [path]);

  const selectedChoice = choices.find(c => c.id === selectedChoiceId);
  const selectedScenario = scenarios.find(s => s.id === selectedChoice?.scenario_id);
  const selectedOutcome = useMemo(() => outcomes.find(o => o.choice_id === selectedChoiceId), [outcomes, selectedChoiceId]);

  const set = (field: keyof Draft, value: string) => setDraft(old => ({ ...old, [field]: value }));

  function fillSynthetic() {
    if (!selectedScenario) return;
    const r = selectedScenario.results;
    setDraft({
      recorded_on: localToday() < cycle.start_date ? cycle.start_date : localToday(),
      source_kind: 'synthetic_demo',
      harvested_count: String(Math.min(cycle.stocked_count, Math.round(cycle.stocked_count * 0.75))),
      harvest_biomass_kg: String(Number((r.harvest_biomass_kg * 0.91).toFixed(3))),
      actual_feed_kg: String(Number((r.estimated_feed_kg * 1.08).toFixed(3))),
      total_cost_vnd: String(Math.round(r.total_cost_vnd * 1.06)),
      revenue_vnd: String(Math.round(r.estimated_revenue_vnd * 0.93)),
      notes: 'SỐ LIỆU GIẢ LẬP – tạo để thử tính năng; không phải dữ liệu trại thực tế.',
    });
    setNotice('Đã nạp dữ liệu GIẢ LẬP để thử giao diện, không dùng làm kết quả nghiên cứu.');
  }

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (selectedChoiceId === null) return;
    setBusy(true); setError(''); setNotice('');
    try {
      const data = {
        choice_id: selectedChoiceId,
        recorded_on: draft.recorded_on,
        source_kind: draft.source_kind,
        harvested_count: Number(draft.harvested_count),
        harvest_biomass_kg: Number(draft.harvest_biomass_kg),
        actual_feed_kg: draft.actual_feed_kg.trim() === '' ? null : Number(draft.actual_feed_kg),
        total_cost_vnd: Number(draft.total_cost_vnd),
        revenue_vnd: Number(draft.revenue_vnd), notes: draft.notes,
      };
      const result = await request<Outcome>(path, data);
      setOutcomes(old => [result, ...old]);
      setDraft(emptyDraft());
      setNotice(`Đã lưu kết quả #${result.id}. Đối chiếu với kịch bản đã chọn được hiển thị bên dưới.`);
    } catch (e) { setError(e instanceof Error ? e.message : 'Không lưu được kết quả.'); }
    finally { setBusy(false); }
  }

  return <section className="panel outcome-section" aria-label="Đối chiếu sau vụ nuôi">
    <div className="panel-head"><div><span className="step">✓</span><h3>Đối chiếu kế hoạch với kết quả sau vụ nuôi</h3></div><span className="panel-meta">Phase 2B</span></div>
    <p className="decision-caution"><strong>Lưu ý về nguồn dữ liệu:</strong> "Người dùng khai báo" chưa được kiểm toán;
      "Dữ liệu giả lập" chỉ để kiểm thử. Phần chênh lệch thể hiện sự khác nhau giữa số nhập và <strong>giả định đã lưu</strong>,
      không chứng minh độ chính xác dự báo sinh học. Chỉ nhập kết quả tổng kết của <strong>toàn vụ nuôi</strong>, không phải một đợt thu hoạch riêng lẻ.</p>
    {choices.length === 0 ? <p className="helper">Bạn cần lưu một kịch bản và nhấn “Chọn phương án” ở phía trên trước khi ghi kết quả.</p> : <>
      <label className="journal-field outcome-selector">Quyết định muốn đối chiếu
        <select value={selectedChoiceId ?? ''} onChange={e => { setSelectedChoiceId(Number(e.target.value)); setError(''); setNotice(''); }}>
          {choices.map(choice => <option value={choice.id} key={choice.id}>Quyết định #{choice.id} · {scenarios.find(s => s.id === choice.scenario_id)?.name ?? 'Kịch bản'} (#{choice.scenario_id})</option>)}
        </select>
      </label>
      {selectedOutcome ? <>
        <p className="message success">Đã ghi nhận kết quả #{selectedOutcome.id} · {selectedOutcome.source_kind === 'synthetic_demo' ? 'DỮ LIỆU GIẢ LẬP' : 'Người dùng khai báo, chưa xác minh'} · {selectedOutcome.recorded_on}</p>
        <div className="outcome-results">
          <div className="outcome-metric outcome-header"><strong>Chỉ số</strong><strong>Kịch bản</strong><strong>Đã nhập</strong><strong>Chênh lệch</strong></div>
          <DeltaLine name="Khối lượng thu hoạch" estimated={selectedOutcome.comparison.planned_harvest_biomass_kg} reported={selectedOutcome.comparison.reported_harvest_biomass_kg} delta={selectedOutcome.comparison.delta_harvest_biomass_kg} unit="kg" />
          <DeltaLine name="Doanh thu" estimated={selectedOutcome.comparison.planned_revenue_vnd} reported={selectedOutcome.comparison.reported_revenue_vnd} delta={selectedOutcome.comparison.delta_revenue_vnd} unit="vnd" />
          <DeltaLine name="Tổng chi phí" estimated={selectedOutcome.comparison.planned_cost_vnd} reported={selectedOutcome.comparison.reported_cost_vnd} delta={selectedOutcome.comparison.delta_cost_vnd} unit="vnd" />
          <DeltaLine name="Chênh lệch thu – chi" estimated={selectedOutcome.comparison.planned_balance_vnd} reported={selectedOutcome.comparison.reported_balance_vnd} delta={selectedOutcome.comparison.delta_balance_vnd} unit="vnd" />
          {selectedOutcome.comparison.reported_feed_kg !== null && <DeltaLine name="Lượng thức ăn" estimated={selectedOutcome.comparison.planned_feed_kg} reported={selectedOutcome.comparison.reported_feed_kg} delta={selectedOutcome.comparison.delta_feed_kg ?? 0} unit="kg" />}
        </div>
        <p className="helper">{selectedOutcome.comparison.explanation}</p>
        {selectedOutcome.notes && <p className="helper">Ghi chú: {selectedOutcome.notes}</p>}
        <p className="helper">MVP chỉ lưu một bản kết quả cho mỗi quyết định để giữ lịch sử không bị sửa âm thầm.</p>
      </> : <form className="outcome-form" onSubmit={submit}>
        {selectedScenario && <p className="helper">Đang đối chiếu với kịch bản đã lưu “{selectedScenario.name}” – không dùng các con số A/B chưa lưu ở phía trên.</p>}
        <div className="outcome-form-grid">
          <label className="journal-field">Ngày tổng kết vụ<input type="date" min={cycle.start_date} value={draft.recorded_on} required onChange={e => set('recorded_on', e.target.value)} /></label>
          <label className="journal-field">Loại dữ liệu<select value={draft.source_kind} onChange={e => set('source_kind', e.target.value)}>
            <option value="user_reported">Người dùng khai báo (chưa xác minh)</option><option value="synthetic_demo">Dữ liệu giả lập để demo</option>
          </select></label>
          <label className="journal-field">Số con thu hoạch<input type="number" min="0" max={cycle.stocked_count} step="1" required value={draft.harvested_count} onChange={e => set('harvested_count', e.target.value)} /></label>
          <label className="journal-field">Tổng khối lượng thu hoạch (kg)<input type="number" min="0" step="any" required value={draft.harvest_biomass_kg} onChange={e => set('harvest_biomass_kg', e.target.value)} /></label>
          <label className="journal-field">Lượng thức ăn đã dùng (kg, tùy chọn)<input type="number" min="0" step="any" value={draft.actual_feed_kg} onChange={e => set('actual_feed_kg', e.target.value)} /></label>
          <label className="journal-field">Tổng chi phí đã ghi nhận (đ)<input type="number" min="0" step="1" required value={draft.total_cost_vnd} onChange={e => set('total_cost_vnd', e.target.value)} /></label>
          <label className="journal-field">Tổng doanh thu đã ghi nhận (đ)<input type="number" min="0" step="1" required value={draft.revenue_vnd} onChange={e => set('revenue_vnd', e.target.value)} /></label>
          <label className="journal-field outcome-notes">Ghi chú<input maxLength={600} value={draft.notes} onChange={e => set('notes', e.target.value)} placeholder="Nguồn số liệu hoặc thông tin cần lưu ý" /></label>
        </div>
        <div className="outcome-actions"><button type="button" className="button subtle" disabled={!selectedScenario || busy} onClick={fillSynthetic}>Nạp dữ liệu GIẢ LẬP</button>
          <button type="submit" className="button primary" disabled={busy || !selectedScenario}>{busy ? 'Đang lưu...' : 'Lưu kết quả và đối chiếu'}</button></div>
      </form>}
      {error && <p role="alert" className="message error">{error}</p>}
      {notice && <p role="status" className="message success">{notice}</p>}
    </>}
  </section>;
}
