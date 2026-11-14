import { useState, type FormEvent } from 'react';
import { apiFetch, apiBase } from './apiClient';

type Account = {id:number;email:string;display_name:string;experience_level:string;goal:string;preferred_species_id:string};

export default function AquaProfile({account}: {account:Account}) {
  const [name,setName] = useState(account.display_name);
  const [level,setLevel] = useState(account.experience_level);
  const [goal,setGoal] = useState(account.goal);
  const [message,setMessage] = useState('');
  const [busy,setBusy] = useState(false);
  async function save(e:FormEvent<HTMLFormElement>) {
    e.preventDefault();setBusy(true);setMessage('');
    try {
      const response = await apiFetch(`${apiBase}/api/auth/profile`, {
        method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({display_name:name,experience_level:level,goal,preferred_species_id:'monopterus_albus'})
      });
      if (!response.ok) throw new Error(`Không lưu được hồ sơ (${response.status})`);
      window.location.reload();
    } catch(err) {setMessage(err instanceof Error?err.message:'Có lỗi khi lưu hồ sơ')}
    finally {setBusy(false)}
  }
  return <section className="panel" style={{maxWidth:'720px',padding:'24px'}}>
    <div className="panel-head"><h2>Hồ sơ DEMO AQUAVERSE</h2><span className="panel-meta">Dữ liệu giả lập · lưu tạm</span></div>
    <p>Thông tin này dùng để cá nhân hóa giao diện; chưa tự tạo khuyến nghị kỹ thuật nuôi.</p>
    <form className="form-stack" onSubmit={save}>
      <label className="form-label" htmlFor="profile-email">Hồ sơ DEMO (không cần đăng nhập)</label>
      <input className="field readonly" id="profile-email" value={account.email} readOnly />
      <label className="form-label" htmlFor="profile-name">Tên hiển thị</label>
      <input className="field" id="profile-name" minLength={2} maxLength={120} required value={name} onChange={e=>setName(e.target.value)} />
      <label className="form-label" htmlFor="profile-level">Kinh nghiệm nuôi thủy sản</label>
      <select className="field" id="profile-level" value={level} onChange={e=>setLevel(e.target.value)}>
        <option value="beginner">Mới bắt đầu</option>
        <option value="intermediate">Đã có kinh nghiệm cơ bản</option>
        <option value="experienced">Đang vận hành trang trại thực</option>
      </select>
      <label className="form-label" htmlFor="profile-goal">Mục tiêu của bạn</label>
      <input className="field" id="profile-goal" value={goal} maxLength={200} minLength={2} required onChange={e=>setGoal(e.target.value)} />
      <p className="helper">Hồ sơ loài thí điểm: Lươn đồng (Monopterus albus). Các loài khác sẽ bổ sung sau khi kiểm chứng.</p>
      {message && <p role="alert">{message}</p>}
      <button className="button primary" type="submit" disabled={busy}>Lưu hồ sơ</button>
    </form>
  </section>;
}
