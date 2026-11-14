# AQUAVERSE — bản public NoLogin (demo riêng từng trình duyệt)

## Những gì đã thay đổi
- Giữ layout React/Vite của bản NoLogin 14/11, chỉ cập nhật chữ “local” thành “demo công khai”.
- Frontend và API chạy chung host HTTPS trên một Docker web service.
- `POST /api/auth/demo-session` ở chế độ public tạo một **tài khoản khách độc lập** cho mỗi phiên trình duyệt, không dùng account local `demo@aquaverse.local`. API kiểm tra quyền sở hữu và CSRF như bản gốc.
- Phiên được bảo vệ bởi cookie `HttpOnly`, `Secure`, `SameSite=Lax`, chỉ hoạt động qua HTTPS.
- Tắt đăng ký/đăng nhập bằng mật khẩu và tải hồ sơ PDF/hình trong public demo. Không có OpenAI API key trong gói.
- Bật giới hạn thô tốc độ tạo phiên/yêu cầu POST; phải có thêm WAF/monitoring nếu phát hành lớn.

## Cách deploy trên Render (cần tài khoản GitHub và Render của bạn)
1. Giải nén ZIP này. Đưa **nội dung thư mục** lên GitHub repo mới (không đẩy dữ liệu thật, `.env`, hoặc `*.sqlite3`).
2. Vào https://dashboard.render.com/ > **New** > **Blueprint** và chọn repo GitHub trên.
3. Render sẽ đọc `render.yaml`, tạo Docker web service `aquaverse-public-demo` gói Free. Xem trước cài đặt rồi bấm Apply.
4. Sau khi deploy báo Live, mở `https://<tên-service>.onrender.com` do Render cung cấp. Truy cập `/api/health` để thấy `status: ok`.
5. Dùng máy khác hoặc cửa sổ private để xác nhận hai khách có dữ liệu tách biệt; tạo farm trong phiên A không xuất hiện ở phiên B.

### CỰC KỲ QUAN TRỌNG: dữ liệu là tạm thời
Free Render không giữ SQLite trên ổ đĩa khi sleep/restart/redeploy. Trình duyệt có thể mất phiên; dữ liệu demo bị xóa. **Không dùng để nhập dữ liệu nông hộ thực tế.** Nếu muốn lưu dữ liệu vĩnh viễn: cần thiết kế auth chuẩn, migrations, backup, abuse controls và persistent DB trước khi phát hành sản phẩm thật. Bản này chỉ để demo trải nghiệm công khai.

### Tính năng và giới hạn
- AquaFarm, AquaDecision, AquaMentor Evidence Finder, AquaConnect metadata, hồ sơ: giữ API và UI cốt lõi. Nguồn PDF đã có gói knowledge vẫn đọc được, nhưng **upload chứng từ tắt**.
- Các tính năng dùng LLM/OpenAI key chưa được bật; đừng quảng cáo là full AI.
- QR `/trace/<token>` dùng domain Render qua `RENDER_EXTERNAL_URL`.
- Khi app ngủ do không có truy cập, phiên mở đầu có thể chậm (giới hạn gói Free).

### Kiểm tra cục bộ
```bash
cd AQUAVERSE_Public_Demo_Deploy
python -m pip install -r backend/requirements.txt
export AQUAVERSE_DATABASE_URL=sqlite:////tmp/aquaverse_public_demo_test.sqlite3
export AQUAVERSE_PUBLIC_DEMO=1
export AQUAVERSE_SECURE_COOKIES=1
export AQUAVERSE_PUBLIC_ORIGIN=http://localhost:8000
cd backend
uvicorn app.main:app --reload --port 8000
```
Mở Terminal khác tại thư mục gốc `AQUAVERSE_Public_Demo_Deploy`, chạy `cd frontend && npm ci && VITE_PUBLIC_DEMO=1 npm run build`. Sau khi build, trình duyệt `http://localhost:8000` chạy frontend. Cookie Secure yêu cầu HTTPS nên nếu thử local HTTP bạn chỉ kiểm tra được API; muốn kiểm tra end-to-end đầy đủ, dùng HTTPS tunneling/domain dev và đặt `AQUAVERSE_PUBLIC_ORIGIN` đúng domain.

## Chưa xác minh trong môi trường tạo gói
Môi trường tạo gói không tải được Vite 8.3.6 từ npm registry, nên `npm run build` và Docker image end-to-end cần được xác nhận khi Render thực hiện npm ci. Không có lệnh deploy vào tài khoản Render của bạn, vì cần kết nối và quyền cấp phép.
