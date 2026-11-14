import { useEffect, useState, type ReactNode } from 'react';
import { apiBase, apiFetch, setCsrfToken } from './apiClient';
import './auth.css';

type Account = { id:number; email:string; display_name:string; experience_level:string; goal:string; preferred_species_id:string };
type SessionInfo = { user: Account; csrf_token: string };

// One in-flight bootstrap per page load: React StrictMode mounts effects twice in dev.
// Without deduplication, two POSTs could race to overwrite the session cookie.
let demoSessionPromise: Promise<SessionInfo> | null = null;
function ensureDemoSession(): Promise<SessionInfo> {
  if (!demoSessionPromise) {
    demoSessionPromise = (async () => {
      const existing = await apiFetch(`${apiBase}/api/auth/me`);
      if (existing.ok) return await existing.json() as SessionInfo;
      if (existing.status !== 401) {
        throw new Error(`Không thể kiểm tra trạng thái phiên DEMO (HTTP ${existing.status})`);
      }
      const response = await apiFetch(`${apiBase}/api/auth/demo-session`, { method: 'POST' });
      if (!response.ok) {
        const body = await response.json().catch(() => ({})) as {detail?:string};
        throw new Error(body.detail || `Không mở được phiên DEMO (HTTP ${response.status})`);
      }
      return await response.json() as SessionInfo;
    })();
  }
  return demoSessionPromise;
}

/** No-login demo session. Public visitors use separate server-side identities. */
export default function AuthGate({ children }: { children:(account:Account)=>ReactNode }) {
  const [account, setAccount] = useState<Account | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let alive = true;
    async function loadDemo() {
      try {
        const info = await ensureDemoSession();
        if (!info.user || !info.csrf_token) throw new Error('Backend trả dữ liệu phiên DEMO không hợp lệ');
        if (!alive) return;
        setCsrfToken(info.csrf_token);
        setAccount(info.user);
      } catch (err) {
        if (alive) setError(err instanceof Error ? err.message : 'Không kết nối được backend AQUAVERSE');
      } finally {
        if (alive) setLoading(false);
      }
    }
    void loadDemo();
    return () => { alive = false; };
  }, []);

  if (loading) return <main className="auth-shell"><section className="auth-card">Đang mở AQUAVERSE DEMO…</section></main>;
  if (account) return <>{children(account)}</>;
  return <main className="auth-shell"><section className="auth-card">
    <div className="auth-brand">≈ AQUAVERSE</div>
    <h1>Chưa mở được bản demo</h1>
    <p>Không cần tài khoản hay mật khẩu. Máy chủ đang tạm thời không khả dụng. Vui lòng tải lại trang.</p>
    {error && <p className="auth-error" role="alert">{error}</p>}
    <button type="button" onClick={() => window.location.reload()}>Thử kết nối lại</button>
    <small>Chỉ dành cho dữ liệu thử nghiệm. Không nhập dữ liệu nuôi thật hoặc thông tin cá nhân.</small>
  </section></main>;
}
