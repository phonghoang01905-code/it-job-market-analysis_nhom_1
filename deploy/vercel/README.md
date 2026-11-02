# Cấu hình Vercel riêng cho dashboard

Bản local và Streamlit Community Cloud tiếp tục dùng Streamlit 1.39 trong
`requirements.txt` gốc. Cấu hình Vercel dùng **Streamlit 1.60 + st.App (ASGI)**,
không chạy một tiến trình `streamlit run` bên trong request serverless.
Vercel hiện hỗ trợ WebSocket cho Python Functions, nhưng cần kiểm thử bản đã
deploy trước khi khẳng định mọi chức năng hoạt động trên production.

## Chuẩn bị và xuất bản

Tại thư mục gốc dự án, dùng terminal PowerShell:

```powershell
python scripts/prepare_vercel.py
vercel.cmd login
vercel.cmd --cwd .tools/vercel-stage --prod --yes
```

`vercel.cmd` tránh lỗi PowerShell chặn chạy file `vercel.ps1`, không cần đổi
Execution Policy của máy. Chờ CLI báo đăng nhập thành công trước khi deploy.
Không gửi mật khẩu/token lên chat hay commit vào Git.

Script chuẩn bị chỉ chép mã Python/SQL và `data/raw/jobs.csv` công khai vào
`.tools/vercel-stage`; không chép `.env`, database local, profile trình duyệt,
log hoặc CV người dùng. Thư mục staging được Git bỏ qua. Không deploy cả thư mục
dự án kèm `.tools` vì chứa runtime local và thông tin phiên làm việc.

Vercel dùng Python 3.12. Gói có yêu cầu tối thiểu cho dashboard; không cần
matplotlib, seaborn hay pytest trên hosting. Cấu hình loại tests thư viện,
Jupyter extension và JavaScript source maps khỏi function bundle để giảm dung lượng.
Các chức năng thống kê, KMeans và CV matching vẫn dùng cùng mã trong `src/data_ana`.

## Kiểm tra sau deploy

- `/_stcore/health` trả về `ok`.
- Trang tổng quan hiển thị số tin của snapshot đã commit, mở được ba tab website.
- Bộ lọc, biểu đồ, trang lương và xu hướng có dữ liệu.
- Tải CV TXT/PDF/DOCX hoặc dùng CV minh họa rồi đọc và xếp hạng được.
- Tải bảng CSV được, không có lỗi WebSocket trong trình duyệt.

CSV là snapshot trên hosting; không tự đồng bộ PostgreSQL trên máy cá nhân.
Muốn đọc DB trực tiếp, cần PostgreSQL online và cấu hình `DATABASE_URL` trong
environment variables của Vercel. Không dùng URL `127.0.0.1:55432` của máy local.

Functions có giới hạn thời gian chạy và có thể khởi tạo lại; trạng thái CV trong
bộ nhớ phiên không phải dữ liệu lưu bền vững. Kết nối WebSocket mới không được
đảm bảo quay về cùng instance. Cần kiểm tra việc tải file và vòng đời phiên
thực tế trên Vercel; kiểm thử local không thay thế kiểm thử production.

Tài liệu: [Vercel Python](https://vercel.com/docs/functions/runtimes/python),
[WebSocket Python](https://vercel.com/changelog/websocket-support-is-now-available-for-python-functions),
[Streamlit st.App](https://docs.streamlit.io/1.60.0/develop/api-reference/server/st.app).
