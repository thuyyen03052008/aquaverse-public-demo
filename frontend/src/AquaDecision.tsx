import { apiFetch } from './apiClient';
import { useEffect, useState, type FormEvent } from 'react';
import OutcomeReview from './OutcomeReview';

const API_BASE = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '');
const nf = new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 2 });
const vnd = (n: number) => `${nf.format(n)} đ`;

type Cycle = {
  id: number; species_id: string; stocked_count: number;
  stocked_avg_weight_g: number | null; start_date: string;
};
type Params = {
  starting_avg_weight_g: number; harvest_avg_weight_g: number;
  survival_percent: number; fcr_assumed: number;
  feed_price_vnd_per_kg: number; seed_price_vnd_per_animal: number;
  other_cost_vnd: number; quality_cost_vnd: number;
  selling_price_vnd_per_kg: number;
};
type Result = {
  engine_version: string; stocked_count: number; expected_surviving_animals: number;
  harvest_biomass_kg: number; survivor_biomass_gain_kg: number;
  estimated_feed_kg: number; feed_cost_vnd: number; seed_cost_vnd: number;
  operating_and_quality_cost_vnd: number; total_cost_vnd: number;
  estimated_revenue_vnd: number; estimated_balance_vnd: number;
  break_even_price_vnd_per_kg: number | null; assumptions_warning: string;
};
type Saved = { id: number; name: string; cycle_id: number; assumptions: Params; results: Result; engine_version: string; created_at: string };
type Choice = { id: number; scenario_id: number; cycle_id: number; notes: string; created_at: string };

type NumericKey = keyof Params;
const fields: { key: NumericKey; label: string; step: string; min: number; max?: number }[] = [
  { key: 'starting_avg_weight_g', label: 'Khối lượng đầu (g/con)', step: 'any', min: 0.01 },
  { key: 'harvest_avg_weight_g', label: 'Khối lượng thu hoạch giả định (g/con)', step: 'any', min: 0.01 },
  { key: 'survival_percent', label: 'Tỷ lệ sống giả định (%)', step: 'any', min: 0, max: 100 },
  { key: 'fcr_assumed', label: 'FCR giả định', step: 'any', min: 0.01 },
  { key: 'feed_price_vnd_per_kg', label: 'Giá thức ăn (đ/kg)', step: '1', min: 0 },
  { key: 'seed_price_vnd_per_animal', label: 'Giá giống (đ/con)', step: '1', min: 0 },
  { key: 'other_cost_vnd', label: 'Các chi phí khác (đ)', step: '1', min: 0 },
  { key: 'quality_cost_vnd', label: 'Chi phí kiểm nghiệm/chất lượng (đ)', step: '1', min: 0 },
  { key: 'selling_price_vnd_per_kg', label: 'Giá bán (đ/kg)', step: '1', min: 0 },
];

function initialParams(cycle: Cycle, isAlternative: boolean): Params {
  return {
    starting_avg_weight_g: cycle.stocked_avg_weight_g ?? 0,
    harvest_avg_weight_g: 200,
    survival_percent: isAlternative ? 70 : 80,
    fcr_assumed: isAlternative ? 1.9 : 1.6,
    feed_price_vnd_per_kg: 25000,
    seed_price_vnd_per_animal: 2500,
    other_cost_vnd: 500000,
    quality_cost_vnd: 0,
    selling_price_vnd_per_kg: 100000,
  };
}

async function api<T>(path: string, data?: unknown): Promise<T> {
  let response: Response;
  try {
    response = await apiFetch(`${API_BASE}${path}`, {
      method: data === undefined ? 'GET' : 'POST',
      headers: data === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: data === undefined ? undefined : JSON.stringify(data),
    });
  } catch {
    throw new Error('Không kết nối được backend (port 8000).');
  }
  const parsed: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = parsed && typeof parsed === 'object' && 'detail' in parsed ? parsed.detail : '';
    const reason = typeof detail === 'string' ? detail : Array.isArray(detail)
      ? detail.map((d: { loc?: string[]; msg?: string }) => `${d.loc?.join(' → ') ?? 'Input'}: ${d.msg ?? 'không hợp lệ'}`).join('; ')
      : 'Yêu cầu không hợp lệ';
    throw new Error(`${response.status} – ${reason}`);
  }
  return parsed as T;
}

function InputPanel({ title, values, update }: { title: string; values: Params; update: (key: NumericKey, value: number) => void }) {
  return <section className="panel decision-panel">
    <h3>{title}</h3>
    <div className="decision-form-grid">
      {fields.map((f) => <label className="journal-field" key={f.key}>
        {f.label}
        <input type="number" inputMode="decimal" step={f.step} min={f.min} max={f.max}
          value={values[f.key]} onChange={(e) => update(f.key, e.target.value === '' ? NaN : Number(e.target.value))} />
      </label>)}
    </div>
  </section>;
}

function ResultCard({ label, result }: { label: string; result: Result }) {
  return <section className="decision-result" aria-label={`Kết quả ${label}`}>
    <h3>{label}</h3>
    <div className="decision-result-grid">
      <div><span>Thu hoạch giả định</span><strong>{nf.format(result.harvest_biomass_kg)} kg</strong></div>
      <div><span>Thức ăn tính theo giả định</span><strong>{nf.format(result.estimated_feed_kg)} kg</strong></div>
      <div><span>Doanh thu giả định</span><strong>{vnd(result.estimated_revenue_vnd)}</strong></div>
      <div><span>Tổng chi phí đã nhập</span><strong>{vnd(result.total_cost_vnd)}</strong></div>
      <div className="decision-important"><span>Chênh lệch thu – chi giả định</span><strong className={result.estimated_balance_vnd < 0 ? 'decision-negative' : ''}>{vnd(result.estimated_balance_vnd)}</strong></div>
      <div><span>Giá hòa vốn trên kg</span><strong>{result.break_even_price_vnd_per_kg === null ? 'Không xác định' : vnd(result.break_even_price_vnd_per_kg)}</strong></div>
    </div>
  </section>;
}

export default function AquaDecision({ cycle }: { cycle: Cycle | null }) {
  const [base, setBase] = useState<Params | null>(cycle ? initialParams(cycle, false) : null);
  const [alternative, setAlternative] = useState<Params | null>(cycle ? initialParams(cycle, true) : null);
  const [baseResult, setBaseResult] = useState<Result | null>(null);
  const [altResult, setAltResult] = useState<Result | null>(null);
  const [saved, setSaved] = useState<Saved[]>([]);
  const [choices, setChoices] = useState<Choice[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const path = cycle ? `/api/cycles/${cycle.id}/decision` : '';

  useEffect(() => {
    let mounted = true;
    if (!cycle) return;
    Promise.all([api<Saved[]>(`${path}/scenarios`), api<Choice[]>(`${path}/choices`)])
      .then(([a, b]) => { if (mounted) { setSaved(a); setChoices(b); } })
      .catch(e => { if (mounted) setError(e instanceof Error ? e.message : 'Không thể tải lịch sử.'); });
    return () => { mounted = false; };
  }, [cycle, path]);

  function update(index: 0 | 1, key: NumericKey, value: number) {
    if (index === 0) setBase(old => old ? { ...old, [key]: value } : old);
    else setAlternative(old => old ? { ...old, [key]: value } : old);
    setBaseResult(null); setAltResult(null); setNotice('');
  }

  async function compare(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!base || !alternative) return;
    setBusy(true); setError(''); setNotice(''); setBaseResult(null); setAltResult(null);
    try {
      const [first, second] = await Promise.all([
        api<Result>(`${path}/preview`, { assumptions: base }),
        api<Result>(`${path}/preview`, { assumptions: alternative }),
      ]);
      setBaseResult(first); setAltResult(second);
      setNotice('Đã tính lại cả hai phương án bằng Python backend.');
    } catch (e) { setError(e instanceof Error ? e.message : 'Không thể tính kịch bản.'); }
    finally { setBusy(false); }
  }

  async function save(index: 0 | 1) {
    const p = index === 0 ? base : alternative;
    if (!p || !(index === 0 ? baseResult : altResult)) return;
    setBusy(true); setError(''); setNotice('');
    try {
      const row = await api<Saved>(`${path}/scenarios`, { name: index === 0 ? 'Phương án A' : 'Phương án B', assumptions: p });
      setSaved(old => [row, ...old]);
      setNotice(`Đã lưu ${row.name} #${row.id} vào cơ sở dữ liệu.`);
    } catch (e) { setError(e instanceof Error ? e.message : 'Lưu thất bại.'); }
    finally { setBusy(false); }
  }

  async function choose(row: Saved) {
    setBusy(true); setError(''); setNotice('');
    try {
      const item = await api<Choice>(`${path}/choices`, { scenario_id: row.id, notes: 'Đã chọn trong giao diện demo' });
      setChoices(old => [item, ...old]);
      setNotice(`Đã ghi nhận quyết định chọn “${row.name}” (#${row.id}).`);
    } catch (e) { setError(e instanceof Error ? e.message : 'Không lưu được quyết định.'); }
    finally { setBusy(false); }
  }

  if (!cycle) return <div className="panel decision-empty"><h2>Chưa chọn vụ nuôi</h2><p>Vào AquaFarm, chọn trang trại → bể → vụ nuôi trước khi tạo kịch bản.</p></div>;
  if (!base || !alternative) return null;

  return <section className="decision-section">
    <div className="decision-banner">
      <div><span className="intro-eyebrow">AQUADECISION · PHASE 2B</span><h2>So sánh phương án trước khi quyết định</h2>
        <p>Vụ #{cycle.id} · Lươn đồng · {nf.format(cycle.stocked_count)} con thả. Tất cả giá trị dưới đây là <strong>giả định minh họa</strong>, không phải hướng dẫn nuôi.</p></div>
      <span className="scope-pill">Scenario finance v1</span>
    </div>
    <p className="decision-caution"><strong>Chưa phải dự báo sinh học.</strong> Ứng dụng chỉ tính kết quả nếu các giả định bạn nhập xảy ra. FCR áp dụng cho mức tăng sinh khối của nhóm sống tới thu hoạch; chưa tính riêng thức ăn tiêu thụ bởi những con chết. Chi phí trong AquaFarm không tự nhập vào phép tính để tránh cộng trùng.</p>
    {cycle.stocked_avg_weight_g === null && <p className="message error">Vụ nuôi chưa có khối lượng đầu kỳ. Hãy điền chính xác trường “Khối lượng đầu (g/con)” cho cả hai kịch bản.</p>}
    {error && <p className="message error" role="alert">{error}</p>}
    {notice && <p className="message success" role="status">{notice}</p>}
    <form onSubmit={compare}>
      <div className="decision-columns">
        <InputPanel title="Phương án A – Cơ sở" values={base} update={(k,v)=>update(0,k,v)} />
        <InputPanel title="Phương án B – Thay thế" values={alternative} update={(k,v)=>update(1,k,v)} />
      </div>
      <button className="button primary decision-compare" type="submit" disabled={busy}>Tính và so sánh hai phương án →</button>
    </form>
    {baseResult && altResult && <div className="decision-comparison">
      <div className="decision-columns">
        <ResultCard label="Kết quả phương án A" result={baseResult} />
        <ResultCard label="Kết quả phương án B" result={altResult} />
      </div>
      <div className="decision-difference panel">
        <h3>Chênh lệch nếu chọn phương án B thay A</h3>
        <strong className={(altResult.estimated_balance_vnd-baseResult.estimated_balance_vnd)<0?'decision-negative':''}>{vnd(altResult.estimated_balance_vnd-baseResult.estimated_balance_vnd)}</strong>
        <p>Đây là độ nhạy theo giả định, không phải lợi nhuận thực tế được bảo đảm. Mọi chi phí chưa nhập sẽ làm sai lệch kết quả.</p>
        <div className="decision-save-row"><button className="button subtle" type="button" disabled={busy} onClick={()=>save(0)}>Lưu phương án A</button><button className="button subtle" type="button" disabled={busy} onClick={()=>save(1)}>Lưu phương án B</button></div>
      </div>
    </div>}
    <section className="panel decision-history">
      <div className="panel-head"><div><span className="step">↺</span><h3>Kịch bản và quyết định đã lưu</h3></div><span className="panel-meta">{saved.length} kịch bản</span></div>
      {saved.length === 0 ? <p className="helper">Chưa có kịch bản lưu. Hãy tính xong, bấm Lưu phương án A hoặc B.</p> :
        <div className="decision-saved-list">{saved.map(row => <div className="decision-saved-item" key={row.id}>
          <div><strong>#{row.id} · {row.name}</strong><small>{nf.format(row.results.harvest_biomass_kg)} kg · Chênh lệch thu–chi {vnd(row.results.estimated_balance_vnd)} · {row.engine_version}</small>
            {choices.some(c=>c.scenario_id===row.id) && <span className="decision-chosen">Đã chọn làm quyết định</span>}
          </div>
          <button type="button" className="button subtle" onClick={()=>choose(row)} disabled={busy}>Chọn phương án</button>
        </div>)}</div>}
      <p className="helper">Kết quả trong mỗi kịch bản được lưu cố định tại thời điểm tạo. Dữ liệu thu hoạch thực tế được nhập riêng bên dưới.</p>
    </section>
    <OutcomeReview cycle={cycle} scenarios={saved} choices={choices} />
  </section>;
}
