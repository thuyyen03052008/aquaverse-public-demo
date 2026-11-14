import { apiFetch } from './apiClient';
import { useEffect, useState, type FormEvent } from 'react';
import './connect.css';

const API = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '');
const PUBLIC_DEMO = import.meta.env.VITE_PUBLIC_DEMO === '1';
const money = (value: number) => new Intl.NumberFormat('vi-VN').format(value) + ' đ';
const number = (value: number) => new Intl.NumberFormat('vi-VN', {maximumFractionDigits: 2}).format(value);
const today = () => new Date().toLocaleDateString('en-CA');

type Cycle = { id: number; species_id: string; start_date: string };
type Batch = { id: number; cycle_id: number; batch_code: string; harvest_date: string; quantity_kg: number; source_kind: string; notes: string; public_label: string; public_token: string; is_published: boolean };
type Document = { id: number; title: string; kind: string; issuer: string; original_filename: string; verification_status: string; size_bytes: number };
type Ready = { standard_reference: string; standard_url: string; template_version: string; nature: string; complete_count: number; total_count: number; items: {key: string; title: string; available: boolean; reason: string}[] };
type Commercial = { quantity_kg: number; baseline_revenue_vnd: number; proposed_revenue_vnd: number; additional_cost_vnd: number; net_difference_vnd: number; minimum_premium_vnd_per_kg: number; warning: string };
type Trace = {batch_code: string; species_name: string; scientific_name: string; harvest_date: string; quantity_kg: number; source_kind: string; public_label: string; verification: string};

async function req<T>(path: string, payload?: unknown, multipart?: FormData): Promise<T> {
  const response = await apiFetch(`${API}${path}`, multipart ? {method: 'POST', body: multipart} : {
    method: payload === undefined ? 'GET' : 'POST',
    headers: payload === undefined ? undefined : {'Content-Type': 'application/json'},
    body: payload === undefined ? undefined : JSON.stringify(payload),
  });
  const json: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = json && typeof json === 'object' && 'detail' in json ? json.detail : null;
    throw new Error(`${response.status}: ${typeof detail === 'string' ? detail : 'Không thể xử lý yêu cầu'}`);
  }
  return json as T;
}

export function PublicTrace({token}: {token: string}) {
  const [data, setData] = useState<Trace | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    req<Trace>(`/api/public/trace/${encodeURIComponent(token)}`)
      .then(result => { if (active) setData(result); })
      .catch(() => { if (active) setError('Không tìm thấy lô hàng được công khai. Có thể mã không hợp lệ hoặc người nuôi đã tắt chia sẻ.'); });
    return () => {active = false;};
  }, [token]);
  return <main className="trace-public">
    <div className="trace-card"><div className="trace-logo">≈ AQUAVERSE <small>TRACEABILITY</small></div>
      <h1>Thông tin lô thủy sản</h1>
      {error && <p className="connect-alert" role="alert">{error}</p>}
      {!data && !error && <p>Đang tải dữ liệu…</p>}
      {data && <><h2>{data.batch_code}</h2><dl>
        <dt>Loài</dt><dd>{data.species_name} ({data.scientific_name})</dd>
        <dt>Ngày thu hoạch khai báo</dt><dd>{data.harvest_date}</dd>
        <dt>Sản lượng khai báo</dt><dd>{number(data.quantity_kg)} kg</dd>
        <dt>Tên cơ sở tự công bố</dt><dd>{data.public_label || 'Không công bố'}</dd>
        <dt>Loại dữ liệu</dt><dd>{data.source_kind === 'synthetic_demo' ? 'DỮ LIỆU GIẢ LẬP' : 'Do người dùng khai báo'}</dd>
      </dl><p className="connect-alert">{data.verification}. Mã QR không phải chứng nhận chất lượng hoặc xác nhận nguồn gốc độc lập.</p></>}
      <a href="/">Mở AQUAVERSE</a>
    </div>
  </main>;
}

export default function AquaConnect({cycle}: {cycle: Cycle | null}) {
  const [batches, setBatches] = useState<Batch[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [readiness, setReadiness] = useState<Ready | null>(null);
  const [comparison, setComparison] = useState<Commercial | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [code, setCode] = useState('LUON-' + Date.now().toString().slice(-6));
  const [harvestDate, setHarvestDate] = useState(today());
  const [quantity, setQuantity] = useState('25');
  const [source, setSource] = useState<'synthetic_demo' | 'user_reported'>('synthetic_demo');
  const [publicLabel, setPublicLabel] = useState('');
  const [docKind, setDocKind] = useState('lab_report');
  const [docTitle, setDocTitle] = useState('');
  const [docIssuer, setDocIssuer] = useState('');
  const [docFile, setDocFile] = useState<File | null>(null);
  const [basePrice, setBasePrice] = useState('100000');
  const [proposedPrice, setProposedPrice] = useState('110000');
  const [testCost, setTestCost] = useState('200000');
  const [certificateCost, setCertificateCost] = useState('500000');
  const [logisticsCost, setLogisticsCost] = useState('100000');
  const selected = batches.find(row => row.id === selectedId) ?? null;

  useEffect(() => {
    setBatches([]); setSelectedId(null); setError(''); setReadiness(null); setComparison(null);
    if (!cycle) return;
    let active = true;
    req<Batch[]>(`/api/cycles/${cycle.id}/batches`).then(rows => {
      if (active) { setBatches(rows); setSelectedId(rows[0]?.id ?? null); }
    }).catch(err => {if (active) setError(err instanceof Error ? err.message : 'Không tải được lô hàng');});
    return () => {active = false;};
  }, [cycle?.id]);

  useEffect(() => {
    setDocuments([]); setReadiness(null); setComparison(null);
    if (!selectedId) return;
    let active = true;
    Promise.all([req<Document[]>(`/api/batches/${selectedId}/documents`), req<Ready>(`/api/batches/${selectedId}/readiness`)]).then(([docs, ready]) => {
      if (active) {setDocuments(docs); setReadiness(ready);}
    }).catch(err => {if (active) setError(err instanceof Error ? err.message : 'Lỗi tải tài liệu');});
    return () => {active = false;};
  }, [selectedId]);

  async function createBatch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!cycle) return;
    setError(''); setNotice(''); setBusy(true);
    try {
      const newBatch = await req<Batch>(`/api/cycles/${cycle.id}/batches`, {
        batch_code: code.trim(), harvest_date: harvestDate, quantity_kg: Number(quantity),
        source_kind: source, public_label: publicLabel.trim(), notes: '',
      });
      setBatches(old => [newBatch, ...old]); setSelectedId(newBatch.id); setCode('LUON-' + Date.now().toString().slice(-6));
      setNotice('Đã tạo lô thu hoạch. Chưa công khai và chưa kiểm định.');
    } catch (err) {setError(err instanceof Error ? err.message : 'Không tạo được lô');}
    finally {setBusy(false);}
  }

  async function uploadDocument(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!selected || !docFile) return;
    setError(''); setNotice(''); setBusy(true);
    try {
      const form = new FormData();
      form.append('kind', docKind); form.append('title', docTitle); form.append('issuer', docIssuer); form.append('file', docFile);
      const newDoc = await req<Document>(`/api/batches/${selected.id}/documents`, undefined, form);
      setDocuments(old => [newDoc, ...old]); setDocFile(null); setDocTitle(''); setDocIssuer('');
      const fresh = await req<Ready>(`/api/batches/${selected.id}/readiness`);
      setReadiness(fresh); setNotice('Đã lưu tệp trên máy. Tệp CHƯA được xác minh bởi đơn vị độc lập.');
    } catch (err) {setError(err instanceof Error ? err.message : 'Không tải lên được tài liệu');}
    finally {setBusy(false);}
  }

  async function togglePublished() {
    if (!selected) return;
    setError(''); setNotice(''); setBusy(true);
    try {
      const updated = await req<Batch>(`/api/batches/${selected.id}/publish`, {published: !selected.is_published});
      setBatches(rows => rows.map(row => row.id === selected.id ? updated : row));
      setNotice(updated.is_published ? 'Đã cho phép truy xuất một số thông tin công khai (KHÔNG có hồ sơ kiểm nghiệm).' : 'Đã tắt chia sẻ lô hàng.');
    } catch (err) {setError(err instanceof Error ? err.message : 'Không đổi được trạng thái');}
    finally {setBusy(false);}
  }

  async function compareMarket(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!selected) return;
    setError(''); setBusy(true);
    try {
      const result = await req<Commercial>(`/api/batches/${selected.id}/market-comparison`, {
        baseline_price_vnd_per_kg: Number(basePrice), proposed_price_vnd_per_kg: Number(proposedPrice),
        testing_cost_vnd: Number(testCost), certification_cost_vnd: Number(certificateCost),
        additional_logistics_vnd: Number(logisticsCost),
      });
      setComparison(result);
    } catch (err) {setError(err instanceof Error ? err.message : 'Không tính được kịch bản');}
    finally {setBusy(false);}
  }

  if (!cycle) return <div className="panel connect-empty"><h2>AquaConnect</h2><p>Chọn trang trại → bể → vụ nuôi trong AquaFarm trước khi tạo lô hàng.</p></div>;
  return <div className="connect-page">
    <div className="connect-hero"><div><span className="intro-eyebrow">AQUACONNECT · QUALITY & MARKET ACCESS</span><h2>Từ nhật ký nuôi đến hồ sơ lô hàng</h2>
      <p>Gắn lô thu hoạch với vụ nuôi #{cycle.id}, tập hợp minh chứng, tạo truy xuất nội bộ và so sánh chi phí thương mại theo giả định.</p></div><span className="connect-status">PUBLIC DEMO · KHÔNG CHỨNG NHẬN</span></div>
    {error && <div className="message error" role="alert">{error}<button onClick={() => setError('')}>×</button></div>}
    {notice && <div className="message success" role="status">{notice}<button onClick={() => setNotice('')}>×</button></div>}
    <div className="connect-grid">
      <section className="panel"><h3>1. Hồ sơ lô thu hoạch</h3><p className="helper">Lô hàng liên kết vụ nuôi, không tự xác minh số liệu.</p>
        <form className="connect-form" onSubmit={createBatch}>
          <label>Mã lô <input required minLength={3} maxLength={48} pattern="[A-Za-z0-9][A-Za-z0-9._-]+" value={code} onChange={e => setCode(e.target.value)} /></label>
          <label>Ngày thu hoạch <input required type="date" value={harvestDate} onChange={e => setHarvestDate(e.target.value)} /></label>
          <label>Khối lượng khai báo (kg) <input required type="number" min="0.01" step="any" value={quantity} onChange={e => setQuantity(e.target.value)} /></label>
          <label>Loại dữ liệu<select value={source} onChange={e => setSource(e.target.value as typeof source)}><option value="synthetic_demo">Dữ liệu giả lập (demo)</option>{!PUBLIC_DEMO && <option value="user_reported">Do người dùng khai báo</option>}</select></label>
          <label>Tên cơ sở cho phép công khai (tùy chọn)<input maxLength={100} placeholder="Để trống nếu cần ẩn" value={publicLabel} onChange={e => setPublicLabel(e.target.value)} /></label>
          <button className="button primary" disabled={busy}>+ Tạo lô thu hoạch</button>
        </form>
        <label className="connect-selector">Lô đang xem<select value={selectedId ?? ''} onChange={e => setSelectedId(e.target.value ? Number(e.target.value) : null)}><option value="">Chọn lô hàng</option>{batches.map(b => <option key={b.id} value={b.id}>{b.batch_code} · {number(b.quantity_kg)} kg</option>)}</select></label>
      </section>
      <section className="panel"><h3>2. Hồ sơ chất lượng</h3>
        {!selected ? <p className="helper">Tạo lô hàng trước khi đính kèm minh chứng.</p> : <>
          {PUBLIC_DEMO ? <p className="helper">Bản demo công khai không cho tải lên chứng từ thật nhằm bảo vệ dữ liệu cá nhân.</p> : <form className="connect-form" onSubmit={uploadDocument}>
            <label>Loại giấy tờ<select value={docKind} onChange={e => setDocKind(e.target.value)}><option value="lab_report">Phiếu kiểm nghiệm</option><option value="supplier_record">Hồ sơ nhà cung cấp</option><option value="certificate">Chứng nhận có sẵn</option><option value="other">Giấy tờ khác</option></select></label>
            <label>Tiêu đề<input required minLength={3} maxLength={140} value={docTitle} onChange={e => setDocTitle(e.target.value)} placeholder="Ví dụ: Phiếu xét nghiệm lô 01" /></label>
            <label>Đơn vị phát hành (theo giấy tờ)<input maxLength={140} value={docIssuer} onChange={e => setDocIssuer(e.target.value)} /></label>
            <label>Tệp PDF/PNG/JPG (≤5 MB)<input required type="file" accept=".pdf,.png,.jpg,.jpeg" onChange={e => setDocFile(e.target.files?.[0] ?? null)} /></label>
            <button className="button primary" disabled={busy || !docFile}>Lưu giấy tờ (riêng tư)</button>
          </form>}
          <ul className="connect-docs">{documents.map(d => <li key={d.id}><strong>{d.title}</strong><small>{d.original_filename} · Chưa xác minh độc lập</small></li>)}{documents.length===0 && <li>Chưa có giấy tờ.</li>}</ul>
        </>}
      </section>
      <section className="panel"><h3>3. Sự hiện diện của hồ sơ</h3>
        {readiness ? <><p className="connect-note"><strong>{readiness.complete_count}/{readiness.total_count}</strong> nhóm hồ sơ có dữ liệu</p>
          <p className="helper">{readiness.nature}</p>
          <ul className="connect-checks">{readiness.items.map(item => <li key={item.key}><span>{item.available ? '✓' : '○'}</span><div><strong>{item.title}</strong><small>{item.reason}</small></div></li>)}</ul>
          <a href={readiness.standard_url} target="_blank" rel="noreferrer">Tham khảo phạm vi TCVN 13528-1:2022 ↗</a>
        </> : <p className="helper">Chọn lô để kiểm tra sự đầy đủ của các loại hồ sơ đã nhập.</p>}
      </section>
      <section className="panel"><h3>4. Truy xuất nguồn gốc bằng QR</h3>
        {!selected ? <p className="helper">Chọn một lô hàng.</p> : <>
          <p className="helper">QR chỉ hiển thị mã lô, loài, ngày thu hoạch, khối lượng khai báo và tên cơ sở nếu bạn chủ động công bố. Không hiển thị giấy tờ riêng tư.</p>
          <button type="button" className="button primary" disabled={busy} onClick={togglePublished}>{selected.is_published ? 'Tắt công khai thông tin lô' : 'Cho phép truy xuất công khai'}</button>
          {selected.is_published && <div className="connect-qr"><img src={`${API}/api/batches/${selected.id}/qr.svg`} alt="Mã QR dẫn tới trang truy xuất của lô hàng" />
            <a target="_blank" rel="noreferrer" href={`/trace/${selected.public_token}`}>Xem trang truy xuất ↗</a><small>QR dẫn đến trang truy xuất công khai của bản demo. Dữ liệu sẽ mất khi dịch vụ khởi động lại.</small></div>}
        </>}
      </section>
      <section className="panel connect-wide"><h3>5. Phân tích chi phí – cơ hội thương mại</h3>
        <p className="helper">Giá bán cao hơn nếu đáp ứng tiêu chuẩn chỉ là giả định. Không mặc định có doanh nghiệp cam kết thu mua.</p>
        {!selected ? <p>Vui lòng chọn lô.</p> : <><form className="connect-market-form" onSubmit={compareMarket}>
          {[
            ['Giá bán cơ sở (đ/kg)', basePrice, setBasePrice],['Giá bán giả định mới (đ/kg)', proposedPrice, setProposedPrice],
            ['Chi phí kiểm nghiệm (đ)', testCost, setTestCost],['Chi phí chứng nhận (đ)',certificateCost,setCertificateCost],['Chi phí logistics bổ sung (đ)',logisticsCost,setLogisticsCost]
          ].map(([label, value, update]) => <label key={label as string}>{label as string}<input type="number" min="0" step="1" required value={value as string} onChange={e => (update as (value:string)=>void)(e.target.value)}/></label>)}
          <button className="button primary" disabled={busy}>So sánh chi phí giả định</button>
        </form>
        {comparison && <div className="connect-financials"><div><span>Doanh thu cơ sở</span><strong>{money(comparison.baseline_revenue_vnd)}</strong></div><div><span>Doanh thu kịch bản</span><strong>{money(comparison.proposed_revenue_vnd)}</strong></div><div><span>Chi phí bổ sung</span><strong>{money(comparison.additional_cost_vnd)}</strong></div><div><span>Chênh lệch sau chi phí</span><strong>{money(comparison.net_difference_vnd)}</strong></div><p>Để bù chi phí bổ sung, mức tăng giá tối thiểu khoảng <strong>{money(comparison.minimum_premium_vnd_per_kg)}/kg</strong>.</p><small>{comparison.warning}</small></div>}
        </>}
      </section>
    </div>
    <div className="connect-warning"><strong>Giới hạn an toàn:</strong> Đây là bản demo công khai không cần đăng nhập, mỗi trình duyệt có dữ liệu riêng. Dữ liệu chỉ lưu tạm và có thể bị xóa bất kỳ lúc nào. Không nhập dữ liệu thật; không phải dịch vụ kiểm định/chứng nhận.</div>
  </div>;
}
