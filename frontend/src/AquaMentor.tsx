import { apiFetch } from './apiClient';
import { useEffect, useState, type FormEvent } from 'react';

const API_BASE = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '');
type MentorMode = 'rag_llm' | 'evidence_only' | 'general_ai' | 'farm_data';
type Source = { id: string; title: string; year: number; url: string; context: string; authors: string; species_id: string; source_type?: string; pages?: number | null };
type Evidence = { passage_id: string; source_id: string; title: string; year: number; url: string; scope: string; excerpt: string; score: number; page?: number | null; source_type?: string };
type FarmSnapshot = { source: string; tank_name: string; cycle_id: number; as_of_date: string; feed: {total_kg:number; recent_kg:number}; expenses: {total_vnd:number; recent_vnd:number}; water_latest: {date:string;ph:number|null;temperature_c:number|null;dissolved_oxygen_mg_l:number|null;ammonia_mg_l:number|null;ammonia_type:string|null}|null };
type Reply = { answer: string; mode: MentorMode; evidence: Evidence[]; species_id: string; warning: string; intent?: string; search_method?: string; farm_snapshot?:FarmSnapshot };
type Status = { status: string; mode: MentorMode; source_count: number; semantic_ready?: boolean; semantic_index_valid?: boolean; imported_document_count?: number; species_supported: string[]; knowledge_level: string };
type ChatMessage = { role: 'user' | 'assistant'; content: string; reply?: Reply };

const suggested = [
  'Những yếu tố nào liên quan đến lợi nhuận nuôi lươn bể không bùn?',
  'Thức ăn nào đã được nghiên cứu cho lươn giai đoạn ương?',
  'Có thể áp dụng chu kỳ sục khí RAS cho mọi bể không bùn không?',
  'Bể của tôi hôm nay đã ghi nhận bao nhiêu thức ăn và chi phí?',
];

function parseError(data: unknown, status: number): string {
  if (data && typeof data === 'object' && 'detail' in data && typeof data.detail === 'string') {
    return `${status}: ${data.detail}`;
  }
  return `Backend trả về lỗi ${status}.`;
}

export default function AquaMentor({cycleId, tankName}: {cycleId:number|null; tankName:string|null}) {
  const [question, setQuestion] = useState('');
  const [includeFarmContext, setIncludeFarmContext] = useState(false);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<Status | null>(null);
  const [sources, setSources] = useState<Source[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [error, setError] = useState('');

  useEffect(() => {
    let alive = true;
    Promise.all([
      apiFetch(`${API_BASE}/api/mentor/status`).then(r => { if (!r.ok) throw Error(`Status ${r.status}`); return r.json() as Promise<Status>; }),
      apiFetch(`${API_BASE}/api/mentor/sources`).then(r => { if (!r.ok) throw Error(`Sources ${r.status}`); return r.json() as Promise<Source[]>; }),
    ]).then(([health, list]) => {
      if (alive) { setStatus(health); setSources(list); }
    }).catch(() => {
      if (alive) setError('Không tải được tri thức. Hãy kiểm tra phiên đăng nhập và Backend.');
    });
    return () => { alive = false; };
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = question.trim();
    if (trimmed.length < 3 || trimmed.length > 600) {
      setError('Câu hỏi cần dài từ 3 đến 600 ký tự.');
      return;
    }
    // Previous local farm summaries are never sent back as chat history.
    const recent = messages.filter(m => m.role === 'user').slice(-6).map(({ role, content }) => ({ role, content: content.slice(0, 800) }));
    setLoading(true); setError(''); setQuestion('');
    try {
      const response = await apiFetch(`${API_BASE}/api/mentor/ask`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: trimmed, species_id: 'monopterus_albus', history: recent, cycle_id: includeFarmContext && cycleId !== null ? cycleId : undefined }),
      });
      const payload: unknown = await response.json().catch(() => null);
      if (!response.ok) throw new Error(parseError(payload, response.status));
      const reply = payload as Reply;
      setMessages(previous => [...previous, { role: 'user', content: trimmed }, { role: 'assistant', content: reply.answer, reply }]);
    } catch (cause: unknown) {
      setQuestion(trimmed);
      setError(cause instanceof Error ? cause.message : 'Không thể gửi câu hỏi.');
    } finally { setLoading(false); }
  }

  return <div className="mentor-page">
    <div className="mentor-hero">
      <div>
        <span className="mentor-kicker">AQUAMENTOR · PHASE 5M3</span>
        <h2>Trợ lý kiến thức thủy sản</h2>
        <p>Hỏi tình huống thực tế về lươn, tra cứu nguồn đã duyệt và hỏi tiếp. Có thể bật tìm kiếm ngữ nghĩa sau khi cấu hình dịch vụ embeddings.</p>
      </div>
      <div className="mentor-mode"><span className="mentor-status-dot" />
        {status?.mode === 'rag_llm' ? 'RAG + AI đã cấu hình' : 'Evidence Finder · chưa có AI tổng hợp'}
        <small>{status ? `${status.source_count} nguồn · ${status.imported_document_count ?? 0} PDF đã duyệt · ${status.semantic_ready ? 'Hybrid Search' : 'Tìm kiếm từ khóa'}` : 'Đang kiểm tra nguồn'}</small>
      </div>
    </div>
    <div className="mentor-layout">
      <section className="panel mentor-query" aria-labelledby="mentor-ask-title">
        <div className="panel-head"><h3 id="mentor-ask-title">Trò chuyện</h3><span className="panel-meta">Lươn đồng · phiên demo</span></div>
        <div className="mentor-thread" role="log" aria-live="polite" aria-label="Lịch sử hội thoại">
          {messages.length === 0 && <div className="mentor-placeholder">Hãy đặt câu hỏi. Bắt đầu bằng một chủ đề, sau đó bạn có thể hỏi “còn về giá bán thì sao?”.</div>}
          {messages.map((message, index) => <div className={`mentor-bubble ${message.role}`} key={index}>
            <strong>{message.role === 'user' ? 'Bạn' : 'AquaMentor'}</strong>
            <p>{message.content.replaceAll('**', '')}</p>
            {message.reply && <>
              <small>{message.reply.mode === 'rag_llm' ? 'AI tổng hợp từ nguồn' : message.reply.mode === 'general_ai' ? 'AI tổng quát · chưa có bằng chứng' : message.reply.mode === 'farm_data' ? 'Tổng hợp dữ liệu AquaFarm · không dùng AI' : 'Tra cứu bằng chứng từ tài liệu'}</small>
              {message.reply.warning && <div className="mentor-warning">{message.reply.warning}</div>}
              {message.reply.farm_snapshot && <details className="mentor-farm-snapshot">
                <summary>Dữ liệu bể riêng (chỉ đọc, do bạn nhập)</summary>
                <p>Bể {message.reply.farm_snapshot.tank_name} · vụ #{message.reply.farm_snapshot.cycle_id} · ngày {message.reply.farm_snapshot.as_of_date}</p>
                <p>Thức ăn đã ghi: {message.reply.farm_snapshot.feed.total_kg} kg (7 ngày: {message.reply.farm_snapshot.feed.recent_kg} kg). Chi phí đã ghi: {message.reply.farm_snapshot.expenses.total_vnd.toLocaleString('vi-VN')} VND.</p>
                <p>Đo nước gần nhất: {message.reply.farm_snapshot.water_latest ? `${message.reply.farm_snapshot.water_latest.date}; pH ${message.reply.farm_snapshot.water_latest.ph ?? 'chưa ghi'}, DO ${message.reply.farm_snapshot.water_latest.dissolved_oxygen_mg_l ?? 'chưa ghi'} mg/L` : 'Chưa có dữ liệu'}. Không tự kết luận an toàn.</p>
              </details>}
              {!!message.reply.evidence?.length && <details className="mentor-citations" open>
                <summary>Nguồn dẫn ({message.reply.evidence.length})</summary>
                {message.reply.evidence.map(e => <div key={e.passage_id} className="mentor-citation">
                  <a href={e.url} target="_blank" rel="noopener noreferrer">{e.title}{e.page ? ` · trang ${e.page}` : ''}</a>
                  <small>{e.scope}</small>
                  <p>{e.excerpt}</p>
                </div>)}
              </details>}
            </>}
          </div>)}
        </div>
        <div className="mentor-farm-scope">
          <label><input type="checkbox" checked={includeFarmContext} disabled={cycleId === null || loading}
            onChange={event => setIncludeFarmContext(event.target.checked)} />{' '}
            Dùng dữ liệu AquaFarm của vụ nuôi đang chọn (chỉ đọc)
          </label>
          <small>{cycleId !== null ? `Bể: ${tankName ?? 'chưa đặt tên'} · vụ #${cycleId}` : 'Chưa chọn vụ nuôi. Vào AquaFarm để chọn bể và vụ nuôi trước.'}</small>
          <small>Dữ liệu nhật ký không tự động được gửi sang mô hình AI bên ngoài. Nếu bật RAG + AI, nội dung câu hỏi bạn tự nhập vẫn có thể được gửi đến dịch vụ đã cấu hình.</small>
        </div>
        <form onSubmit={submit} className="mentor-form">
          <label className="form-label" htmlFor="mentor-input">Câu hỏi tiếp theo</label>
          <textarea id="mentor-input" className="field mentor-textarea" rows={3} maxLength={600}
            value={question} onChange={event => setQuestion(event.target.value)}
            placeholder="Ví dụ: Lươn vào mùa sinh sản nhưng không đẻ, cần kiểm tra gì?" />
          <div className="mentor-form-footer"><span>{question.length}/600</span>
            <button className="button primary" type="submit" disabled={loading || question.trim().length < 3}>
              {loading ? 'Đang tra cứu…' : 'Gửi câu hỏi →'}
            </button>
            <button type="button" className="button" disabled={loading || messages.length === 0} onClick={() => { setMessages([]); setError(''); }}>
              Xóa cuộc trò chuyện
            </button>
          </div>
        </form>
        {error && <div className="message error" role="alert">{error}</div>}
        <div className="mentor-questions"><strong>Gợi ý</strong>
          {suggested.map(item => <button key={item} className="mentor-suggestion" type="button" onClick={() => setQuestion(item)}>{item}</button>)}
        </div>
      </section>
      <section className="panel mentor-library" aria-labelledby="mentor-library-title">
        <div className="panel-head"><h3 id="mentor-library-title">Thư viện đã duyệt</h3><span className="panel-meta">Dẫn nguồn & phạm vi áp dụng</span></div>
        <div className="mentor-source-grid">{sources.map(item => <div className="mentor-source" key={item.id}>
          <strong>{item.title}</strong>
          <span>{item.authors} · {item.year}{item.pages ? ` · ${item.pages} trang` : ''}</span>
          <p>{item.context}{item.source_type === 'user_pdf' ? ' · PDF nhập từ máy, chưa thẩm định độc lập.' : ''}</p>
          <a href={item.url} target="_blank" rel="noopener noreferrer">Mở nguồn gốc ↗</a>
        </div>)}</div>
      </section>
    </div>
    <p className="mentor-disclaimer">Tra cứu tài liệu và tùy chọn tổng hợp chỉ đọc dữ liệu vụ nuôi theo quyền sở hữu. Không tự chẩn đoán, không tự gửi hồ sơ trang trại cho AI, không lưu lịch sử trò chuyện lên máy chủ. Chưa thay thế tư vấn chuyên gia hoặc kết quả kiểm nghiệm.</p>
  </div>;
}
