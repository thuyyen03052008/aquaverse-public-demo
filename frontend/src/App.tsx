import AuthGate from './AuthGate';
import AquaProfile from './AquaProfile';
import { apiFetch } from './apiClient';
import { useEffect, useState, type FormEvent } from 'react';
import './index.css';
import FarmJournal from './FarmJournal';
import AquaDecision from './AquaDecision';
import AquaMentor from './AquaMentor';
import AquaConnect, { PublicTrace } from './AquaConnect';
import './decision.css';
import './mentor.css';

const API_BASE = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '');

type Health = { status: string; service: string; version: string };
type Farm = { id: number; name: string; region: string | null; created_at: string };
type Tank = { id: number; farm_id: number; name: string; unit_type: string; culture_system_id: string; area_m2: number | null; volume_m3: number | null };
type Cycle = { id: number; unit_id: number; species_id: string; start_date: string; planned_end_date: string | null; stocked_count: number; stocked_avg_weight_g: number | null };
type Species = { id: string; scientific_name: string; common_name_vi: string; status: string };
type CultureSystem = { id: string; name_vi: string; description: string };

function humanError(detail: unknown): string {
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map((entry: { loc?: unknown; msg?: unknown }) => {
    const field = Array.isArray(entry.loc) ? entry.loc.join(' → ') : 'Dữ liệu';
    return `${field}: ${String(entry.msg ?? 'không hợp lệ')}`;
  }).join('; ');
  return 'Có lỗi xảy ra. Hãy kiểm tra dữ liệu và thử lại.';
}

async function request<T>(path: string, payload?: unknown): Promise<T> {
  let response: Response;
  try {
    response = await apiFetch(`${API_BASE}${path}`, {
      method: payload === undefined ? 'GET' : 'POST',
      headers: payload === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: payload === undefined ? undefined : JSON.stringify(payload),
    });
  } catch {
    throw new Error('Không kết nối được máy chủ AQUAVERSE. Vui lòng tải lại trang sau.');
  }
  const data: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = data !== null && typeof data === 'object' && 'detail' in data ? data.detail : null;
    throw new Error(`${response.status}: ${humanError(detail)}`);
  }
  return data as T;
}

const numberVN = new Intl.NumberFormat('vi-VN');
const nav = [
  { title: 'Tổng quan', code: 'overview', active: true },
  { title: 'AquaFarm', code: 'farm', active: true },
  { title: 'AquaDecision', code: 'decision', active: true },
  { title: 'AquaMentor', code: 'mentor', active: true },
  { title: 'AquaConnect', code: 'connect', active: true },
  { title: 'Hồ sơ cá nhân', code: 'profile', active: true },
] as const;
type ActivePage = 'overview' | 'farm' | 'decision' | 'mentor' | 'connect' | 'profile';

function TodayTag() {
  return <span className="meta-label">BẢN DEMO · DỮ LIỆU NHẬP THỦ CÔNG</span>;
}

function Empty({ title, subtitle }: { title: string; subtitle: string }) {
  return <div className="empty"><div className="empty-ring">◌</div><strong>{title}</strong><p>{subtitle}</p></div>;
}

function App({account}: {account: {id:number;display_name:string;email:string;experience_level:string;goal:string;preferred_species_id:string}}) {
  const [page, setPage] = useState<ActivePage>('farm');
  const [health, setHealth] = useState<Health | null>(null);
  const [farms, setFarms] = useState<Farm[]>([]);
  const [species, setSpecies] = useState<Species[]>([]);
  const [systems, setSystems] = useState<CultureSystem[]>([]);
  const [farmId, setFarmId] = useState<number | null>(null);
  const [tanks, setTanks] = useState<Tank[]>([]);
  const [tankId, setTankId] = useState<number | null>(null);
  const [cycles, setCycles] = useState<Cycle[]>([]);
  const [cycleId, setCycleId] = useState<number | null>(null);
  const [initialLoading, setInitialLoading] = useState(true);
  const [tankLoading, setTankLoading] = useState(false);
  const [cycleLoading, setCycleLoading] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [newFarmName, setNewFarmName] = useState('');
  const [newFarmRegion, setNewFarmRegion] = useState('');
  const [newTankName, setNewTankName] = useState('');
  const [newTankArea, setNewTankArea] = useState('');
  const [newCycleDate, setNewCycleDate] = useState(new Date().toISOString().slice(0, 10));
  const [newCycleCount, setNewCycleCount] = useState('');
  const [newCycleWeight, setNewCycleWeight] = useState('');

  const selectedFarm = farms.find((farm) => farm.id === farmId);
  const selectedTank = tanks.find((tank) => tank.id === tankId);
  const pilot = species.find((item) => item.status === 'pilot');
  const mudfree = systems.find((system) => system.id === 'mudfree_tank');

  useEffect(() => {
    let alive = true;
    Promise.all([
      request<Health>('/api/health'),
      request<Farm[]>('/api/farms'),
      request<Species[]>('/api/species'),
      request<CultureSystem[]>('/api/culture-systems'),
    ]).then(([h, f, s, c]) => {
      if (!alive) return;
      setHealth(h); setFarms(f); setSpecies(s); setSystems(c);
      setFarmId((current) => current !== null && f.some((x) => x.id === current) ? current : (f[0]?.id ?? null));
    }).catch((reason: unknown) => {
      if (alive) setError(reason instanceof Error ? reason.message : 'Không tải được dữ liệu.');
    }).finally(() => { if (alive) setInitialLoading(false); });
    return () => { alive = false; };
  }, []);

  useEffect(() => {
    let alive = true;
    if (farmId === null) { setTanks([]); setTankId(null); return; }
    setTankLoading(true);
    request<Tank[]>(`/api/farms/${farmId}/tanks`).then((rows) => {
      if (!alive) return;
      setTanks(rows);
      setTankId((current) => current !== null && rows.some((x) => x.id === current) ? current : (rows[0]?.id ?? null));
    }).catch((reason: unknown) => { if (alive) setError(reason instanceof Error ? reason.message : 'Không tải được bể.'); })
      .finally(() => { if (alive) setTankLoading(false); });
    return () => { alive = false; };
  }, [farmId]);

  useEffect(() => {
    let alive = true;
    if (tankId === null) { setCycles([]); setCycleId(null); return; }
    setCycles([]); setCycleId(null);
    setCycleLoading(true);
    request<Cycle[]>(`/api/tanks/${tankId}/cycles`).then((rows) => {
      if (alive) { setCycles(rows); setCycleId((current) => current !== null && rows.some((x) => x.id === current) ? current : (rows[rows.length-1]?.id ?? null)); }
    }).catch((reason: unknown) => { if (alive) setError(reason instanceof Error ? reason.message : 'Không tải được vụ nuôi.'); })
      .finally(() => { if (alive) setCycleLoading(false); });
    return () => { alive = false; };
  }, [tankId]);

  async function createFarm(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(''); setNotice(''); setPending(true);
    try {
      const created = await request<Farm>('/api/farms', { name: newFarmName.trim(), region: newFarmRegion.trim() || null });
      setFarms((old) => [...old, created]);
      setFarmId(created.id);
      setNewFarmName(''); setNewFarmRegion('');
      setNotice(`Đã tạo trang trại “${created.name}”.`);
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Không tạo được trang trại.'); }
    finally { setPending(false); }
  }

  async function createTank(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (farmId === null) return;
    setError(''); setNotice(''); setPending(true);
    try {
      const created = await request<Tank>(`/api/farms/${farmId}/tanks`, {
        name: newTankName.trim(), unit_type: 'tank', culture_system_id: 'mudfree_tank',
        area_m2: newTankArea.trim() ? Number(newTankArea) : null,
      });
      setTanks((old) => [...old, created]); setTankId(created.id);
      setNewTankName(''); setNewTankArea('');
      setNotice(`Đã tạo bể “${created.name}”.`);
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Không tạo được bể.'); }
    finally { setPending(false); }
  }

  async function createCycle(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (tankId === null || !pilot) return;
    setError(''); setNotice(''); setPending(true);
    try {
      const created = await request<Cycle>(`/api/tanks/${tankId}/cycles`, {
        species_id: pilot.id, start_date: newCycleDate,
        stocked_count: Number(newCycleCount),
        stocked_avg_weight_g: newCycleWeight.trim() ? Number(newCycleWeight) : null,
      });
      setCycles((old) => [...old, created]); setCycleId(created.id);
      setNewCycleCount(''); setNewCycleWeight('');
      setNotice(`Đã tạo vụ nuôi #${created.id}.`);
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Không tạo được vụ nuôi.'); }
    finally { setPending(false); }
  }

  async function reload() {
    setError(''); setNotice(''); setInitialLoading(true);
    try {
      const [newFarms, newSpecies, newSystems, h] = await Promise.all([
        request<Farm[]>('/api/farms'), request<Species[]>('/api/species'),
        request<CultureSystem[]>('/api/culture-systems'), request<Health>('/api/health'),
      ]);
      setHealth(h); setFarms(newFarms); setSpecies(newSpecies); setSystems(newSystems);
      setFarmId((current) => current !== null && newFarms.some((x) => x.id === current) ? current : (newFarms[0]?.id ?? null));
      if (farmId !== null && newFarms.some((x) => x.id === farmId)) {
        const newTanks = await request<Tank[]>(`/api/farms/${farmId}/tanks`);
        setTanks(newTanks);
        const preferred = tankId !== null && newTanks.some((x) => x.id === tankId) ? tankId : (newTanks[0]?.id ?? null);
        setTankId(preferred);
        const refreshedCycles = preferred === null ? [] : await request<Cycle[]>(`/api/tanks/${preferred}/cycles`);
        setCycles(refreshedCycles);
        setCycleId((current) => current !== null && refreshedCycles.some((x) => x.id === current) ? current : (refreshedCycles[refreshedCycles.length-1]?.id ?? null));
      }
      setNotice('Đã tải lại dữ liệu từ Backend.');
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Không thể tải lại.'); }
    finally { setInitialLoading(false); }
  }

  const totalCycles = cycles.length;
  const totalStocked = cycles.reduce((sum, cycle) => sum + cycle.stocked_count, 0);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="wordmark"><span className="logo-mark">≈</span><span>AQUAVERSE<small>SMART AQUACULTURE</small></span></div>
        <div className="nav-group"><span className="nav-caption">KHÔNG GIAN LÀM VIỆC</span>
          {nav.map((item) => <button key={item.code} type="button" className={`nav-link ${page === item.code ? 'selected' : ''}`} disabled={!item.active} title={!item.active ? 'Đang trong lộ trình phát triển' : undefined} onClick={() => { if (item.active) setPage(item.code as ActivePage); }}>
            <span className="nav-dot" />{item.title}{!item.active && <span className="nav-soon">Sắp có</span>}
          </button>)}
        </div>
        <div className="sidebar-bottom"><span className="pilot-dot" />Lươn đồng · Eel-first MVP<small>Kiến trúc sẵn sàng cho nhiều loài</small></div>
      </aside>
      <div className="main-layout">
        <header className="topbar"><div><span className="breadcrumb">Workspace / {page === 'farm' ? 'AquaFarm' : page === 'decision' ? 'AquaDecision' : page === 'mentor' ? 'AquaMentor' : page === 'connect' ? 'AquaConnect' : page === 'profile' ? 'Hồ sơ cá nhân' : 'Overview'}</span><strong>{page === 'farm' ? 'Quản lý trang trại' : page === 'decision' ? 'Phòng mô phỏng' : page === 'mentor' ? 'Trợ lý kiến thức' : page === 'connect' ? 'Chất lượng và thương mại' : page === 'profile' ? 'Hồ sơ của tôi' : 'Tổng quan hệ thống'}</strong></div><div className="top-actions"><span className={`connection ${health?.status === 'ok' ? 'connected' : 'disconnected'}`}><span className="connection-dot" />{health?.status === 'ok' ? `API ${health.version} connected` : 'API offline'}</span><button type="button" className="button subtle" onClick={reload} disabled={initialLoading}>↻ Tải lại</button><span className="scope-pill">{account.display_name}</span><span className="scope-pill" title="Không cần đăng nhập; mỗi trình duyệt có dữ liệu demo riêng">DEMO CÔNG KHAI</span></div></header>
        <main className="main-content">
          <TodayTag />
          <div className="page-head"><div><h1>{page === 'farm' ? 'AquaFarm' : page === 'decision' ? 'AquaDecision' : page === 'mentor' ? 'AquaMentor' : page === 'connect' ? 'AquaConnect' : page === 'profile' ? 'Hồ sơ cá nhân' : 'Tổng quan trang trại'}</h1><p>Dữ liệu thử nghiệm được lưu tạm trên máy chủ; không nhập thông tin cá nhân hay dữ liệu nuôi thật.</p></div><span className="scope-pill">Phase 4 · Public demo</span></div>
          {error && <div className="message error" role="alert"><strong>Có lỗi:</strong> {error}<button type="button" onClick={() => setError('')} aria-label="Đóng thông báo">×</button></div>}
          {notice && <div className="message success" role="status">✓ {notice}<button type="button" onClick={() => setNotice('')} aria-label="Đóng thông báo">×</button></div>}
          {page === 'profile' ? <AquaProfile account={account} /> : page === 'mentor' ? <AquaMentor cycleId={cycleId} tankName={selectedTank?.name ?? null} /> : page === 'connect' ? <><button className="button subtle" type="button" onClick={() => setPage('farm')}>← Chọn vụ nuôi trong AquaFarm</button><AquaConnect key={cycleId ?? 'none'} cycle={cycles.find(c => c.id === cycleId) ?? null} /></> : page === 'decision' ? <><button className="button subtle" type="button" onClick={() => setPage('farm')}>← Chọn vụ nuôi trong AquaFarm</button><AquaDecision key={cycleId ?? 'none'} cycle={cycles.find(c => c.id === cycleId) ?? null} /></> : <>
          <section className="stats" aria-label="Thống kê trang trại">
            <div className="stat"><span>Trang trại đã lưu</span><strong>{numberVN.format(farms.length)}</strong><small>Chỉ của phiên demo này</small></div>
            <div className="stat"><span>Bể trong trang trại đang chọn</span><strong>{tankLoading ? '…' : numberVN.format(tanks.length)}</strong><small>{selectedFarm?.name ?? 'Chưa chọn trang trại'}</small></div>
            <div className="stat"><span>Vụ nuôi trong bể đang chọn</span><strong>{cycleLoading ? '…' : numberVN.format(totalCycles)}</strong><small>{selectedTank?.name ?? 'Chưa chọn bể'}</small></div>
            <div className="stat highlight"><span>Số con thả đã khai báo</span><strong>{cycleLoading ? '…' : numberVN.format(totalStocked)}</strong><small>Trong bể đang chọn · dữ liệu nhập</small></div>
          </section>
          {page === 'overview' && <div className="intro-panel"><div><span className="intro-eyebrow">MVP FIRST · MULTI-SPECIES READY</span><h2>Một nền tảng chung, bắt đầu với lươn không bùn</h2><p>Hiện tại bạn đã có thể xem và tạo trang trại, bể nuôi và vụ nuôi qua giao diện. AquaDecision hỗ trợ so sánh kịch bản; AquaMentor tra cứu nguồn nghiên cứu về lươn. AquaConnect đã có quản lý lô hàng, hồ sơ và QR nội bộ.</p></div><button className="button primary" onClick={() => setPage('farm')}>Mở AquaFarm →</button></div>}
          <div className="section-label"><h2>Dữ liệu AquaFarm</h2><span>Thao tác theo thứ tự: Trang trại → Bể nuôi → Vụ nuôi</span></div>
          <div className="workspace-grid">
            <section className="panel" aria-labelledby="farm-heading">
              <div className="panel-head"><div><span className="step">01</span><h3 id="farm-heading">Trang trại</h3></div><span className="panel-meta">{farms.length} bản ghi</span></div>
              <label className="form-label" htmlFor="farm-selector">Trang trại hiện tại</label>
              <select id="farm-selector" className="field" value={farmId ?? ''} onChange={(e) => { setError(''); setNotice(''); setFarmId(e.target.value ? Number(e.target.value) : null); }} disabled={initialLoading || farms.length === 0}>
                {farms.length === 0 && <option value="">Chưa có trang trại</option>}
                {farms.map((farm) => <option key={farm.id} value={farm.id}>{farm.name} · #{farm.id}</option>)}
              </select>
              {selectedFarm && <div className="record-detail"><span>ID #{selectedFarm.id}</span><strong>{selectedFarm.name}</strong><p>{selectedFarm.region || 'Chưa khai báo khu vực'}</p></div>}
              <form className="form-stack" onSubmit={createFarm}><h4>+ Thêm trang trại</h4><label className="form-label" htmlFor="farm-name">Tên trang trại</label><input id="farm-name" className="field" required minLength={2} maxLength={120} placeholder="Ví dụ: Trại lươn An Bình" value={newFarmName} onChange={(e) => setNewFarmName(e.target.value)} /><label className="form-label" htmlFor="farm-region">Khu vực (không bắt buộc)</label><input id="farm-region" className="field" maxLength={120} placeholder="Ví dụ: Đồng Tháp" value={newFarmRegion} onChange={(e) => setNewFarmRegion(e.target.value)} /><button className="button primary" type="submit" disabled={pending}>Tạo trang trại</button></form>
            </section>
            <section className="panel" aria-labelledby="tank-heading">
              <div className="panel-head"><div><span className="step">02</span><h3 id="tank-heading">Bể nuôi</h3></div><span className="panel-meta">{tanks.length} bản ghi</span></div>
              {farmId === null ? <Empty title="Chưa chọn trang trại" subtitle="Tạo hoặc chọn trang trại ở cột bên trái." /> : <>
                <label className="form-label" htmlFor="tank-selector">Bể đang xem</label><select id="tank-selector" className="field" value={tankId ?? ''} onChange={(e) => { setError(''); setNotice(''); setTankId(e.target.value ? Number(e.target.value) : null); }} disabled={tankLoading || tanks.length === 0}>
                  {tanks.length === 0 && <option value="">Chưa có bể nuôi</option>}
                  {tanks.map((tank) => <option key={tank.id} value={tank.id}>{tank.name} · #{tank.id}</option>)}
                </select>
                {selectedTank && <div className="record-detail"><span>ID #{selectedTank.id}</span><strong>{selectedTank.name}</strong><p>{mudfree?.name_vi ?? selectedTank.culture_system_id}{selectedTank.area_m2 !== null ? ` · ${numberVN.format(selectedTank.area_m2)} m²` : ''}</p></div>}
                <form className="form-stack" onSubmit={createTank}><h4>+ Thêm bể nuôi</h4><label className="form-label" htmlFor="tank-name">Tên bể</label><input id="tank-name" className="field" required maxLength={120} placeholder="Ví dụ: Bể lươn số 02" value={newTankName} onChange={(e) => setNewTankName(e.target.value)} /><label className="form-label" htmlFor="tank-area">Diện tích mặt bể (m²)</label><input id="tank-area" className="field" type="number" inputMode="decimal" min="0.01" step="any" placeholder="Ví dụ: 12" value={newTankArea} onChange={(e) => setNewTankArea(e.target.value)} /><p className="helper">Hệ thống nuôi: {mudfree?.name_vi ?? 'Bể không bùn'}</p><button className="button primary" type="submit" disabled={pending || !mudfree}>Tạo bể nuôi</button></form>
              </>}
            </section>
            <section className="panel" aria-labelledby="cycle-heading">
              <div className="panel-head"><div><span className="step">03</span><h3 id="cycle-heading">Vụ nuôi</h3></div><span className="panel-meta">{cycles.length} bản ghi</span></div>
              {tankId === null ? <Empty title="Chưa có bể đang chọn" subtitle="Tạo hoặc chọn bể nuôi để xem các vụ nuôi." /> : <>
                <label className="form-label" htmlFor="journal-cycle">Vụ nuôi đang ghi nhật ký</label><select id="journal-cycle" className="field" value={cycleId ?? ''} disabled={cycleLoading || cycles.length === 0} onChange={(event) => setCycleId(event.target.value ? Number(event.target.value) : null)}>{cycles.length === 0 && <option value="">Chưa có vụ nuôi</option>}{cycles.map((cycle) => <option key={cycle.id} value={cycle.id}>Vụ #{cycle.id} · {cycle.start_date}</option>)}</select><div className="cycle-list">{cycleLoading ? <p className="helper">Đang tải vụ nuôi…</p> : cycles.length === 0 ? <Empty title="Chưa có vụ nuôi" subtitle="Tạo vụ nuôi đầu tiên ngay bên dưới." /> : cycles.map((cycle) => <article className="cycle-row" key={cycle.id}><div><strong>Vụ nuôi #{cycle.id}</strong><span>{species.find((s) => s.id === cycle.species_id)?.common_name_vi ?? cycle.species_id} · {cycle.start_date}</span></div><div className="count"><strong>{numberVN.format(cycle.stocked_count)}</strong><small>con thả</small></div></article>)}</div>
                <form className="form-stack" onSubmit={createCycle}><h4>+ Thêm vụ nuôi</h4><label className="form-label" htmlFor="cycle-species">Loài nuôi (MVP)</label><input id="cycle-species" className="field readonly" readOnly value={pilot ? `${pilot.common_name_vi} · ${pilot.scientific_name}` : 'Chưa có loài thí điểm'} /><label className="form-label" htmlFor="cycle-date">Ngày bắt đầu</label><input id="cycle-date" className="field" type="date" required value={newCycleDate} onChange={(e) => setNewCycleDate(e.target.value)} /><div className="form-inline"><div><label className="form-label" htmlFor="cycle-count">Số lượng thả (con)</label><input id="cycle-count" className="field" type="number" min="1" step="1" required placeholder="500" value={newCycleCount} onChange={(e) => setNewCycleCount(e.target.value)} /></div><div><label className="form-label" htmlFor="cycle-weight">Khối lượng đầu (g/con)</label><input id="cycle-weight" className="field" type="number" min="0" step="any" placeholder="15" value={newCycleWeight} onChange={(e) => setNewCycleWeight(e.target.value)} /></div></div><button className="button primary" type="submit" disabled={pending || !pilot}>Tạo vụ nuôi</button><p className="helper">Giá trị nhập để kiểm thử không phải khuyến nghị mật độ hoặc kỹ thuật nuôi.</p></form>
              </>}
            </section>
          </div>
          <FarmJournal key={`${tankId ?? "none"}-${cycleId ?? "none"}`} cycleId={cycleId} /><div className="next-panel"><div><strong>AquaDecision đã sẵn sàng</strong><p>Chọn vụ nuôi phía trên, sau đó nhấn AquaDecision ở menu bên trái để so sánh hai phương án kinh tế giả định.</p></div><button className="button primary" type="button" onClick={() => setPage('decision')}>Mở AquaDecision →</button></div>
          </>}
        </main>
        <footer className="footer">AQUAVERSE · Multi-species architecture · Eel-first validation · Public prototype · Anonymous isolated demo · Synthetic data only</footer>
      </div>
    </div>
  );
}

export default function Root() {
  const match = window.location.pathname.match(/^\/trace\/([A-Za-z0-9_-]+)\/?$/);
  return match ? <PublicTrace token={match[1]} /> : <AuthGate>{(account)=><App key={account.id} account={account}/>}</AuthGate>;
}
