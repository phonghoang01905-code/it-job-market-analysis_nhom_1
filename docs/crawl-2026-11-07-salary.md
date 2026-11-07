# Mở rộng dữ liệu có lương — 07/11/2026

Đã thu thập thêm **607 ứng viên mới** từ ba website, đối chiếu với 218 tin lịch sử.
Sau phân loại, **245 tin mới đạt tiêu chí lương** được đưa vào bộ chính. Bộ chính
có **336 tin: 330 công khai (A), 6 ước tính (B), không có nhóm C**. Số tin có thể
dùng đối chiếu lương tăng từ 91 lên 336; đây là mẫu đã chọn theo độ đầy đủ lương,
không phải mẫu ngẫu nhiên đại diện thị trường.

| Website | Trang danh sách chính | Ứng viên mới | Tin mới đạt tiêu chí | A trong bộ chính | B trong bộ chính | Tổng bộ chính |
|---|---:|---:|---:|---:|---:|---:|
| ITviec | 16 | 250 | 62 | 76 | 2 | 78 |
| TopDev | 7 | 57 | 8 | 24 | 1 | 25 |
| TopCV | 8 | 300 | 175 | 230 | 3 | 233 |
| **Tổng** | **31** | **607** | **245** | **330** | **6** | **336** |

## Thu thập và lựa chọn

- ITviec: ưu tiên slider lương của trang tìm kiếm, đọc trang chi tiết và
  `JobPosting.baseSalary` công khai. 250 ứng viên mới đều có mô tả/yêu cầu.
  Đã sửa phân trang để giữ hai giá trị trùng tên `salary_ranges[]`; kết quả từ
  lượt thử trước được ghép lại theo job ID/URL, không tạo bản sao.
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

Chỉ xuất tin A/B có ít nhất một đầu lương VND/tháng hợp lệ. Lương giờ/ngày chưa
có thời lượng quy đổi và khoảng đảo ngược bị loại. Không tự bổ sung sàn cho tin
chỉ có trần hoặc ngược lại. Mẫu cho nhóm B phải đủ hai đầu công khai, cùng nhóm
vị trí/thành phố/kinh nghiệm, đủ tương đồng kỹ năng, ít nhất 3 tin / 2 công ty.
Không dùng các kết quả B làm mẫu và không giảm ngưỡng để tăng số lượng.

## Dữ liệu và kiểm tra

- `data/raw/jobs.csv`: 336 tin A/B dùng cho dashboard.
- `data/raw/jobs_archive.csv`: 825 ứng viên/lịch sử; gồm 489 tin C không đưa vào bộ chính.
- `data/processed/jobs.csv`: 336 dòng sau ETL, 0 trùng, 0 bị từ chối.
- `data/processed/salary_collection_audit.csv`: cột số, lý do và nguồn đối chiếu.
- `data/processed/salary_collection_report.json`: thống kê chi tiết và kết quả ETL.
- PostgreSQL thêm 245 tin, nhận diện 91 tin đã có. Database có 463 tin do giữ
  nguyên 127 dòng C lịch sử; dashboard mặc định A/B hiển thị đúng 336 tin.

Đã xác nhận CSV raw, processed và PostgreSQL cho cùng phân nhóm A/B của bộ chính;
không trùng URL/job ID trong từng website, mọi tin bộ chính có số tiền so sánh.
Các giá trị ước tính tách khỏi `salary_min/max/text` gốc; giao diện và CSV xuất
ghi rõ nhóm, dấu `≈`, số mẫu, lý do và link từng tin đối chiếu.

Chạy lại quy trình:

```bash
python -m data_ana.collect_salary
python -m streamlit run src/data_ana/dashboard.py -- --data data/processed/jobs.csv
```

Lệnh crawl thông thường và scheduler cũng áp dụng `salary_qualified_only=true`
trong cấu hình mặc định. Các tệp archive/audit/checkpoint là đầu ra cục bộ;
CSV bộ chính được commit lên GitHub để Streamlit Cloud đọc được dữ liệu mới.
