# Mở rộng dữ liệu và giữ tin thỏa thuận — 07/11/2026

Đã thu thập thêm **607 ứng viên mới** từ ba website, đối chiếu với 218 tin lịch sử.
**Toàn bộ 825 tin được giữ trong bộ chính**, gồm **330 công khai (A), 6 ước tính
(B), 489 tin chưa đủ dữ liệu lương (C)**. Ban đầu 336 tin A/B được tách riêng;
theo yêu cầu giữ đầy đủ dữ liệu, các tin C đã được khôi phục vào CSV, PostgreSQL
và dashboard. Tin thiếu lương vẫn được dùng phân tích nhu cầu tuyển dụng/kỹ năng;
chỉ bị bỏ qua trong các phép tính số lương, không bị xóa bản ghi.

| Website | Tin mới | A · Công khai | B · Ước tính | C · Thiếu lương | Tổng giữ lại |
|---|---:|---:|---:|---:|---:|
| ITviec | 250 | 76 | 2 | 242 | 320 |
| TopDev | 57 | 24 | 1 | 82 | 107 |
| TopCV | 300 | 230 | 3 | 165 | 398 |
| **Tổng** | **607** | **330** | **6** | **489** | **825** |

## Thu thập và lựa chọn

- ITviec: đợt thu thập này có ưu tiên slider lương của trang tìm kiếm, đọc trang chi tiết và
  `JobPosting.baseSalary` công khai. 250 ứng viên mới đều có mô tả/yêu cầu.
  Đã sửa phân trang để giữ hai giá trị trùng tên `salary_ranges[]`; kết quả từ
  lượt thử trước được ghép lại theo job ID/URL, không tạo bản sao.
  Các lượt mới dùng danh sách IT tổng hợp và vẫn giữ tin chưa công khai lương.
- TopDev: duyệt hết các trang có thêm thẻ IT riêng biệt trong bộ lọc danh mục
  hiện dùng. Website trả về ít tin hơn giới hạn tối đa 250 nên không cố điền đủ
  số. Adapter giải mã tham chiếu JSON theo đường dẫn cho công ty và các bản ghi
  văn bản UTF-8 của yêu cầu/phúc lợi. Mức lương lấy từ `salary.value/min/max`,
  không dùng `min_estimate`, `max_estimate`, `min_filter` hay `max_filter`.
  Thông tin kinh nghiệm từ nhãn công khai được ghi rõ `Kinh nghiệm (website)`;
  yêu cầu số năm trong nội dung tin được ưu tiên hơn nhãn này khi đối chiếu.
- TopCV: tìm kiếm theo từ khóa IT, tối đa 300 ứng viên mới; ưu tiên tối đa 60
  trang chi tiết. Những tin còn lại giữ đúng dữ liệu đọc được từ thẻ, không tự
  tạo mô tả/kỹ năng/phúc lợi khi chưa lấy được.
- Mỗi nguồn có session riêng; nghỉ ít nhất 4 giây cho ITviec/TopDev, 12 giây
  cho TopCV. Kiểm tra robots.txt; không đăng nhập, không gọi API riêng tư,
  không vượt qua chặn truy cập. Lưu checkpoint trong lúc chạy.

Xuất đầy đủ A/B/C. Lương giờ/ngày chưa có thời lượng quy đổi và khoảng đảo ngược
được để NaN ở cột số tiền so sánh, vẫn giữ dữ liệu tin. Không tự bổ sung sàn cho
tin chỉ có trần hoặc ngược lại. Mẫu cho nhóm B phải đủ hai đầu công khai, cùng nhóm
vị trí/thành phố/kinh nghiệm, đủ tương đồng kỹ năng, ít nhất 3 tin / 2 công ty.
Không dùng các kết quả B làm mẫu và không giảm ngưỡng để tăng số lượng.

## Dữ liệu và kiểm tra

- `data/raw/jobs.csv`: 825 tin A/B/C dùng cho dashboard.
- `data/raw/jobs_archive.csv`: bản lưu trữ đầy đủ 825 tin để đối chiếu/khôi phục.
- `data/processed/jobs.csv`: 825 dòng sau ETL, 0 trùng, 0 bị từ chối.
- `data/processed/salary_collection_audit.csv`: cột số, lý do và nguồn đối chiếu.
- `data/processed/salary_collection_report.json`: thống kê chi tiết và kết quả ETL.
- PostgreSQL hiện có đủ 825 tin. Bước khôi phục bổ sung 362 tin C chưa được nạp
  trước đó; 489 tin C đều giữ NULL ở trường số lương. Dashboard mặc định hiển thị A/B/C.

Đã xác nhận CSV raw, processed và PostgreSQL cùng 825 tin, cùng phân nhóm A/B/C;
không trùng URL/job ID trong từng website. Các tin C giữ NaN, không điền 0.
Các giá trị ước tính tách khỏi `salary_min/max/text` gốc; giao diện và CSV xuất
ghi rõ nhóm, dấu `≈`, số mẫu, lý do và link từng tin đối chiếu.

Chạy lại quy trình:

```bash
python -m data_ana.collect_salary
python -m streamlit run src/data_ana/dashboard.py -- --data data/processed/jobs.csv
```

Lệnh crawl thông thường và scheduler giữ tin chưa có lương trong bộ chính;
lọc để phân tích lương không làm mất dữ liệu thị trường. Archive/audit/checkpoint là đầu ra cục bộ;
CSV bộ chính được commit lên GitHub để Streamlit Cloud đọc được dữ liệu mới.
