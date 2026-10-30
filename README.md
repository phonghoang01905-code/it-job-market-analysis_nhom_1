# Phân tích thị trường tuyển dụng IT Việt Nam

Repo nay duoc tao cho de tai 1 trong file `Datana.docx`: thu thap va phan tich du lieu tuyen dung IT tu ITviec, TopDev va TopCV de tra loi cac cau hoi ve ky nang hot, muc luong, nha tuyen dung, mo hinh lam viec va ky nang niche.

## Muc tieu

- Xac dinh ky nang/cong nghe co nhieu tin tuyen dung nhat.
- So sanh muc luong theo vi tri, cap bac va dia diem.
- Thong ke nha tuyen dung co nhu cau cao va ty le Onsite/Hybrid/Remote.
- Tim nhom ky nang co muc luong cao nhung do canh tranh thap.
- Tao dau vao tham khao cho sinh vien IT, trung tam dao tao va HR/recruiter.

## Cau truc repo

```text
.
├── config/
│   └── sites.example.json
├── data/
│   ├── processed/
│   └── raw/
├── docs/
│   └── project-brief.md
├── notebooks/
│   └── README.md
├── outputs/
├── src/
│   └── data_ana/
│       ├── analyze.py
│       ├── crawl.py
│       ├── dashboard.py
│       ├── models.py
│       └── utils.py
├── tests/
│   └── test_utils.py
├── .gitignore
├── LICENSE
├── pyproject.toml
└── requirements.txt
```

## Cai dat

Yeu cau Python 3.10+.

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Tren macOS/Linux:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Quy trinh su dung

1. Sao chep file cau hinh:

```bash
copy config\sites.example.json config\sites.json
```

2. Thu thap du lieu mau:

```bash
python -m data_ana.crawl --config config\sites.json --out data\raw\jobs.csv
```

3. Chuan hoa va phan tich:

```bash
python -m data_ana.analyze --input data\raw\jobs.csv --out-dir outputs
```

### Thu thập TopCV, ITviec và TopDev

Cấu hình `config/sites.example.json` đã bật cả ba nguồn: ITviec tối đa 3 trang,
TopDev 4 trang, TopCV 1 trang; mục tiêu tối đa 50 tin riêng biệt mỗi nguồn/lần chạy.
Crawler kiểm tra `robots.txt`, khai báo User-Agent, nghỉ 4 giây giữa các request
ITviec/TopDev và 12 giây với TopCV,
retry lỗi tạm thời và lấy mô tả/ngày đăng từ trang chi tiết công khai.
Lỗi hoặc giới hạn truy cập ở một nguồn không ngăn việc thu thập nguồn tiếp theo.

Cài dự án để dùng các lệnh `python -m data_ana...` mà không cần thiết lập PYTHONPATH:

```cmd
python -m pip install -e .
python -m data_ana.crawl --sources itviec topdev --max-pages 1
```

Thu thập cả ba nguồn hoặc tăng giới hạn trang:

```cmd
python -m data_ana.crawl --max-pages 2
```

Nếu dùng cấu hình riêng, truyền `--config config/sites.json`.
Dữ liệu mới được gộp vào `data/raw/jobs.csv`, khử trùng theo website và link tin.
Các nguồn cũ được giữ lại; file tổng là tập tin đã thu thập, có thể chứa tin đã hết hạn.
Mỗi lần chạy tạo JSON riêng theo nguồn/ngày, ví dụ `data/raw/2026-10-28_itviec.json`,
và `data/raw/crawl_status.json` ghi tình trạng lần thu thập gần nhất của từng nguồn.
JSON mới lưu kỹ năng dạng mảng, CSV phân cách kỹ năng bằng dấu `;`.

TopDev hiện chuyển `/viec-lam-it` sang `/jobs/search` có cả ngành ngoài IT.
Adapter dùng bộ lọc IT trên trang tìm kiếm TopDev (`job_categories_ids`),
chỉ nhận tin có `job_category_id=1` trong metadata công khai và có thẻ tin
hiển thị trên trang. Nếu danh sách hiển thị lặp lại khi đổi trang, crawler dừng
khi không còn URL mới. Đây là mẫu tin công khai, không phải toàn bộ số kết quả tìm kiếm.
Lương yêu cầu đăng nhập không được suy đoán hay thu thập qua tài khoản.

Ngày 28/10/2026: bổ sung 20 tin ITviec và 7 tin TopDev, cả 27 tin đều có mô tả,
ngày đăng, công ty, địa điểm và link gốc; giữ nguyên 50 tin TopCV từ 19/10/2026.
Chi tiết: [docs/crawl-2026-10-28.md](docs/crawl-2026-10-28.md).

4. Chay dashboard:

```bash
python -m streamlit run src/data_ana/dashboard.py -- --data data/raw/jobs.csv
```

Dashboard có tab Tổng quan và tab riêng TopCV / ITviec / TopDev, bộ lọc vị trí,
địa điểm, hình thức, lương công khai; biểu đồ thanh ngang có tooltip tên đầy đủ;
bảng tin có link gốc, phần đọc mô tả và nút tải CSV theo bộ lọc.
Thời điểm thu thập và mức độ đầy đủ được hiển thị riêng cho từng nguồn.

### Tải CV và gợi ý việc làm phù hợp

Dashboard có tab **CV → Việc làm phù hợp**, đối chiếu hồ sơ với tin đã thu thập
từ **TopCV, ITviec và TopDev**. Không cần API key, SMTP hay PostgreSQL để dùng
phần này; dashboard đọc file CSV đã có.

Cập nhật thư viện và mở dashboard tại thư mục dự án:

```cmd
python -m pip install -e .
python -m streamlit run src/data_ana/dashboard.py -- --data data/processed/jobs.csv
```

Nếu chưa có dữ liệu processed, thay đường dẫn cuối bằng `data/raw/jobs.csv`.
Mở địa chỉ do Streamlit hiển thị, thường là `http://localhost:8501`.

1. Chọn tab **CV → Việc làm phù hợp**. Có thể bấm **Dùng CV minh họa** để xem thử
   mà không cần CV thật.
2. Tải **PDF có văn bản, DOCX hoặc TXT**, hoặc chọn **Dán nội dung**, rồi bấm **Đọc CV**.
   Tệp tối đa 10 MB; PDF tối đa 20 trang; nội dung tối đa 100.000 ký tự.
   PDF scan/ảnh chưa có OCR: hãy dùng PDF có thể chọn chữ hoặc dán nội dung.
   TXT hỗ trợ UTF-8 và UTF-16 có BOM; DOCX đọc cả đoạn văn và ô bảng.
3. Kiểm tra/sửa kỹ năng chuyên môn, số năm kinh nghiệm liên quan, cấp bậc,
   ngoại ngữ và kỹ năng bổ trợ đã nhận diện. Điền điểm IELTS/TOEIC/TOEFL iBT
   hoặc mức CEFR nếu có. Giá trị chứng chỉ `0` nghĩa là chưa cung cấp.
   Số năm chỉ được tự nhận diện khi CV ghi rõ, ví dụ `2 năm kinh nghiệm`;
   không tự cộng các mốc thời gian học hoặc làm việc chồng lấn.
4. Dùng bộ lọc bên trái để chọn website, vị trí, địa điểm, hình thức hoặc lương mong muốn.
   Bấm **Xếp hạng việc làm phù hợp** để xem điểm `/100`, rating `/5`, ưu tiên
   **Cao / Vừa / Thấp**, công ty, website và link tin gốc.
5. Chọn một kết quả ở **Xem lý do rating của một công việc** để đọc kỹ năng khớp,
   kỹ năng chưa thấy trong CV, yêu cầu kinh nghiệm/ngoại ngữ cần đối chiếu và
   bảng điểm từng tiêu chí. Có thể tải bảng gợi ý CSV, rồi mở tin gốc để kiểm tra
   hạn tuyển dụng trước khi ứng tuyển.

Khi sửa hồ sơ đã xác nhận hoặc bộ lọc, kết quả được tính lại. Nếu thay nội dung
CV/tệp hoặc cách nhập, kết quả cũ bị ẩn cho tới khi bấm **Đọc CV** lại.

**Hiểu đúng rating:** đây là điểm khớp theo quy tắc, **không phải xác suất được
nhận việc**. Ví dụ `85/100` không có nghĩa là có 85% khả năng trúng tuyển.
Dự án chưa có dữ liệu ứng tuyển, phỏng vấn và kết quả nhận việc để tính xác suất đó.

| Tiêu chí | Trọng số gốc | Cách đối chiếu |
| --- | ---: | --- |
| Kỹ năng chuyên môn | 60% | Tỷ lệ kỹ năng/công nghệ trong tin xuất hiện trong hồ sơ đã xác nhận |
| Kinh nghiệm / cấp bậc | 15% | Số năm so với mức tối thiểu; dùng cấp bậc khi tin không nêu số năm rõ ràng, cảnh báo nếu hồ sơ tự xác nhận cấp bậc thấp hơn tin |
| Ngoại ngữ | 15% | Ngoại ngữ được nêu trong tin và hồ sơ; kiểm tra điểm chứng chỉ cùng loại nếu tin nêu rõ |
| Kỹ năng bổ trợ | 10% | Tỷ lệ kỹ năng bổ trợ trùng, như giao tiếp, làm việc nhóm, giải quyết vấn đề |

Chỉ tính những tiêu chí có dữ liệu trong tin rồi chuẩn hóa lại trọng số:
`điểm = tổng(trọng số × mức khớp) / tổng trọng số được dùng`.
Thiếu dữ liệu hồ sơ không tự được coi là đáp ứng. Tin thiếu yêu cầu chi tiết
chỉ được tối đa **60/100**; có yêu cầu quan trọng về kinh nghiệm/cấp bậc/ngoại ngữ
chưa đáp ứng hoặc chưa xác nhận chỉ được tối đa **65/100**.
Tin không có kỹ năng chuyên môn trùng không xuất hiện trong bảng gợi ý.

Rating **5 sao từ 85**, **4 sao từ 70**, **3 sao từ 50**, **2 sao từ 30**,
**1 sao khi trên 0**. Ưu tiên **Cao** cần từ 75 điểm, có kỹ năng chuyên môn trùng
và không có cảnh báo về yêu cầu quan trọng; **Vừa** từ 45 điểm; còn lại là **Thấp**.
Địa điểm, lương và website được áp dụng qua bộ lọc, không tự cộng vào rating.

Các giới hạn cần hiểu: nhận diện dựa trên từ khóa theo từ điển, chưa hiểu đầy đủ
kỹ năng nào bắt buộc, ưu tiên hoặc thay thế nhau; kỹ năng chưa thấy không có nghĩa
ứng viên không biết. Viết CV bằng tiếng Anh không tự chứng minh trình độ tiếng Anh.
Không quy đổi điểm giữa TOEIC và IELTS; các chứng chỉ ngoài tiếng Anh cần đọc tin
gốc để tự đối chiếu. Dữ liệu thiếu và tin đã hết hạn có thể ảnh hưởng kết quả.
Hãy dùng bảng điểm và yêu cầu nguyên văn để quyết định, thay vì chỉ nhìn số sao.

**CV được xử lý trong bộ nhớ phiên Streamlit**, không tự ghi vào CSV/PostgreSQL/log
và không gửi tới API AI bên ngoài. Nút **Xóa CV và kết quả trong phiên** bỏ dữ liệu
CV khỏi phiên đang dùng. Bảng gợi ý chỉ được tải về khi bạn bấm nút tải CSV;
không chứa nguyên văn CV. Nếu chạy dashboard trên máy chủ, việc xử lý diễn ra
trên máy chủ đó. Tên, tuổi, giới tính, ảnh và thông tin liên hệ không được dùng làm
tiêu chí chấm điểm.

Mã xử lý: [cv_matching.py](src/data_ana/cv_matching.py);
giao diện: [cv_dashboard.py](src/data_ana/cv_dashboard.py).

### Mở rộng dữ liệu và ngôn ngữ lập trình (30/10/2026)

Thu thập tối đa 50 tin riêng biệt cho mỗi nguồn ITviec và TopDev:

```cmd
python -m data_ana.crawl --sources itviec topdev --max-jobs 50
python crawler.py --skip-crawl
```

Lệnh thứ nhất dùng tối đa 3 trang ITviec và 4 trang TopDev trong cấu hình.
Lệnh thứ hai làm sạch toàn bộ CSV đã lưu và nạp PostgreSQL, bao gồm làm giàu
các trường ngôn ngữ cho cả TopCV, ITviec và TopDev. Không xóa tin cũ để ép số lượng
về đúng 50; số tin tích lũy trên dashboard có thể lớn hơn 50 mỗi nguồn.
Nếu website bị giới hạn hoặc không đủ tin, crawler báo số thực tế, không thêm tin trùng.

Đợt 30/10/2026 đã lấy đủ 50 tin riêng biệt/website, cả 150 tin đều có mô tả.
Sau khi giữ lịch sử, CSV tổng có **218 tin: ITviec 70, TopDev 50, TopCV 98**.
Xem [báo cáo thu thập ngày 30/10](docs/crawl-2026-10-30.md) về độ đầy đủ và phương pháp.

TopDev dùng đường dẫn tìm kiếm công khai có bộ lọc IT và phân trang thực tế.
Chỉ tăng `page` trên trang tìm kiếm chung sẽ dễ lấy cả tin ngoài IT.
Không cần đăng nhập hay gọi API yêu cầu tài khoản để lấy dữ liệu này.

Các trường mới trong raw/processed và PostgreSQL:

| Trường | Nội dung |
| --- | --- |
| `requirements` | Phần yêu cầu ứng viên/công việc lấy từ tin gốc nếu có |
| `programming_languages` | Tên ngôn ngữ chuẩn hóa, ví dụ C++, C#, Python, Java, JavaScript, TypeScript, PHP, Go, SQL |
| `language_evidence` | Từng ngôn ngữ kèm nguồn và trích đoạn văn bản dùng để nhận diện |

ITviec/TopCV đọc phần yêu cầu trong HTML; TopDev đọc phần yêu cầu được nhúng
trong HTML công khai, kể cả khi văn bản được tham chiếu qua các bản ghi Next.js.
Nhận diện ưu tiên phần yêu cầu, rồi đến tiêu đề, mô tả và tag. Không suy ra
JavaScript chỉ vì tin nhắc React/NodeJS, không nhầm Java với JavaScript hay C với C++/C#.
Danh sách này phản ánh ngôn ngữ **được nhắc đến**, chưa kết luận tất cả đều bắt buộc:
tin có thể ghi “ưu tiên”, “hoặc”, hoặc một công nghệ dùng trong dự án.
SQL được tính là ngôn ngữ truy vấn; HTML/CSS và framework không nằm trong nhóm này.

Dashboard có bộ lọc nhiều ngôn ngữ, biểu đồ thanh ngang, bảng so sánh giữa ba
website và cột ngôn ngữ trong từng tin. Khi chọn nhiều ngôn ngữ, tin khớp ít nhất
một ngôn ngữ sẽ được giữ lại. Mở “Đọc mô tả đầy đủ của một tin” để xem trích dẫn
và phần yêu cầu gốc. “Chưa thấy nêu” có thể do tin không nêu hoặc dữ liệu chưa đủ.

Lệnh dashboard cũ vẫn dùng được với `data/raw/jobs.csv`; cũng có thể dùng
`data/processed/jobs.csv` sau ETL. Các file CSV cũ chưa có trường ngôn ngữ vẫn đọc
được; dashboard tự nhận diện từ nội dung hiện có.

### Kỹ năng bổ trợ, ngoại ngữ và phúc lợi trên dashboard

Đã bổ sung cho cả TopCV, ITviec và TopDev:

| Trường | Ý nghĩa |
| --- | --- |
| `supplementary_skills` | Kỹ năng mềm và công cụ bổ trợ: giao tiếp, làm việc nhóm, giải quyết vấn đề, tự học, Excel, Jira… |
| `foreign_languages` | Ngoại ngữ được nhắc đến trong yêu cầu, tiêu đề hoặc tag, ví dụ tiếng Anh/Nhật/Hàn |
| `english_requirement` | Trích đoạn nêu tiếng Anh, giữ nguyên thông tin IELTS/TOEIC hoặc trình độ nếu có |
| `english_status` | Phân loại sơ bộ: yêu cầu rõ ràng, ưu tiên, có nhắc nhưng chưa rõ bắt buộc, không bắt buộc, chưa có thông tin |
| `benefits` | Nội dung phúc lợi gốc: bảo hiểm, thưởng, nghỉ phép, đào tạo, phụ cấp… |
| `benefit_tags` | Nhóm phúc lợi chuẩn hóa để thống kê/lọc |
| `profile_evidence` | Nguồn và trích dẫn dùng để nhận diện các nhóm trên |

Phúc lợi lấy từ `jobBenefits` công khai hoặc mục Quyền lợi/Benefits trên trang chi tiết.
Chỉ nhận diện nhóm phúc lợi trong phần phúc lợi, không suy từ ngành công ty;
ví dụ công ty làm phần mềm bảo hiểm không tự động được gán phúc lợi bảo hiểm.
Lớp học tiếng Anh do công ty hỗ trợ là phúc lợi, không tự biến thành yêu cầu tiếng Anh.
Việc phân loại theo từ khóa là sơ bộ; đọc trích dẫn và yêu cầu nguyên văn để xác định
mức độ bắt buộc/ưu tiên trong từng trường hợp. Không thấy dữ liệu không có nghĩa
tin không yêu cầu ngoại ngữ hoặc không có phúc lợi.

Crawler tự lấy các phần này khi đọc chi tiết tin. Để bổ sung cho dữ liệu cũ:

```cmd
python -m data_ana.enrich_existing --sources topcv itviec topdev
python crawler.py --skip-crawl
```

Lệnh bổ sung giữ nguyên danh sách tin và lưu HTML công khai tại `outputs/detail_cache`
để tránh tải lại cùng trang khi tiếp tục một lần chạy bị gián đoạn. `--refresh` để
đọc lại website thay vì dùng HTML đã lưu; `--limit 50` để giới hạn 50 tin mới nhất mỗi nguồn.
Nếu gặp HTTP 403/429 sau retry, chương trình dừng nguồn đó và ghi kết quả chưa đầy đủ.
`data/raw/enrichment_report.json` ghi số tin đọc được, tin chưa xử lý và lỗi theo nguồn.
Log bổ sung nằm trong `logs/enrichment/`. Không dùng cache để khẳng định tin vẫn còn hạn.

ETL lưu các trường mới vào CSV/JSON sạch và PostgreSQL. Tin đã tồn tại được làm giàu
metadata, không tạo bản sao. Phúc lợi đã lưu không bị xóa khi nhập lại snapshot cũ thiếu trường này.
Dashboard có bộ lọc và thống kê riêng cho kỹ năng bổ trợ, ngoại ngữ, tiếng Anh, phúc lợi;
bảng tin và CSV tải về chứa các trường mới. Trong chi tiết tin có nội dung phúc lợi đầy đủ
và trích dẫn kỹ năng/ngoại ngữ.

Kết quả bổ sung ngày 30/10: 172/218 tin có nội dung phúc lợi, 129 tin có kỹ năng bổ trợ,
100 tin có thông tin tiếng Anh (bao gồm cả ưu tiên/không bắt buộc). TopCV bị giới hạn HTTP 429,
nên một phần tin chưa đọc bổ sung được; dashboard có thông báo và giữ trường chưa biết.
Xem [báo cáo bổ sung](docs/profile-enrichment-2026-10-30.md).

## Tuần 3 — Tự động hóa

Đã có `crawler.py` làm điểm chạy chung, scheduler chạy mỗi ngày, workflow GitHub
Actions, log ra file và cảnh báo lỗi qua Telegram/email.

### Hiểu luồng chạy

```mermaid
flowchart LR
    A[Scheduler hoặc GitHub Actions] --> B[crawler.py]
    B --> C[Crawl TopCV / ITviec / TopDev]
    C --> D[JSON theo ngày + CSV raw]
    D --> E[ETL làm sạch]
    E --> F[PostgreSQL: chỉ thêm tin mới]
    B --> G[Log + báo cáo lần chạy]
    G --> H[Cảnh báo nếu lỗi hoặc thiếu dữ liệu]
```

`python crawler.py` chạy **một lần rồi kết thúc**. Scheduler hoặc GitHub Actions
là phần quyết định **khi nào** chạy lại lệnh này; crawler tự nó không chạy mãi.

Trước hết mở CMD tại `D:\Data_Ana` và cập nhật thư viện:

```cmd
python -m pip install -e .
```

Các lệnh thường dùng:

| Lệnh | Khi nào dùng |
| --- | --- |
| `python crawler.py` | Crawl cả ba nguồn → làm sạch → nạp PostgreSQL |
| `python crawler.py --sources itviec topdev` | Chỉ crawl hai nguồn này, vẫn giữ dữ liệu các nguồn khác |
| `python crawler.py --skip-crawl` | Dùng dữ liệu raw đã có để chạy ETL + nạp PostgreSQL, không gọi website |
| `python crawler.py --skip-db` | Crawl và làm sạch, chưa nạp database |
| `python crawler.py --skip-crawl --skip-db` | Chỉ làm sạch dữ liệu đã có, không cần website hay database |

Mặc định dùng giới hạn trang và 50 tin trong cấu hình từng website. Dùng
`--max-pages` để thay giới hạn trang, `--max-jobs` để thay số tin tối đa mỗi nguồn.
Pipeline có khóa chống hai tiến trình chạy đồng thời trên cùng thư mục log.

### Cách 1: chạy scheduler trên máy

```cmd
python -m data_ana.scheduler --at 07:15
```

Scheduler chờ **07:15 mỗi ngày, múi giờ Asia/Ho_Chi_Minh**, rồi chạy pipeline.
Giữ terminal mở và máy đang bật. `Ctrl+C` để dừng. Nếu mở scheduler sau 07:15,
nó chờ 07:15 ngày tiếp theo; không tự chạy bù những ngày máy tắt.
Đổi giờ bằng `--at HH:MM`. Thử chạy ngay một lần bằng:

```cmd
python -m data_ana.scheduler --once --skip-crawl
```

Nếu dùng cron trên một máy Linux có múi giờ **UTC**, ví dụ:

```cron
15 0 * * * cd /path/to/Data_Ana && /path/to/venv/bin/python crawler.py
```

`15 0 * * *` nghĩa là 00:15 UTC hằng ngày, tương đương 07:15 Việt Nam.
CMD trên Windows không có cron; dùng scheduler Python hoặc GitHub Actions bên dưới.

### Cách 2: GitHub Actions, không cần giữ máy cá nhân bật

File đã tạo: [daily-crawl.yml](.github/workflows/daily-crawl.yml).
Workflow chạy hằng ngày lúc **07:15 giờ Việt Nam**, hoặc chạy thủ công bằng nút
**Run workflow**. GitHub có thể chạy trễ so với lịch; lịch dùng nhánh mặc định của repo.
Xem [tài liệu lịch chạy GitHub Actions](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

Để kích hoạt trên repo của bạn:

1. Commit và push các file mới lên nhánh mặc định, thường là `main`.
2. Vào repo → **Settings → Secrets and variables → Actions**.
3. Thêm Repository secret `DATABASE_URL` trỏ tới PostgreSQL mà GitHub runner truy cập được.
4. Nếu muốn cảnh báo, thêm các secrets/variables tương ứng ở phần tiếp theo.
5. Vào **Actions → Daily crawl and ETL → Run workflow** để chạy thử.
6. Mở lần chạy để xem log. Phần **Artifacts** có file `job-data-...`, gồm raw,
   processed và log; workflow đặt thời hạn lưu artifact là 90 ngày.

**Địa chỉ `127.0.0.1:55432` trên máy bạn không dùng được từ GitHub runner.**
Khi chạy GitHub Actions, dùng URL của một PostgreSQL server mà runner có thể kết nối,
ví dụ `postgresql://USER:PASSWORD@HOST:5432/DB?sslmode=require`.
Database đó phải tồn tại trước; code tự tạo bốn bảng bên trong database.
Không dùng PostgreSQL service tạm của một workflow để tích lũy dữ liệu qua nhiều ngày.

Workflow không tự commit dữ liệu vào Git. Database giữ lịch sử tích lũy;
artifact giữ snapshot mỗi lần chạy. CSV trên runner chỉ gồm dữ liệu có trong checkout
và tin vừa crawl, không tự tải toàn bộ lịch sử từ database về CSV.
**Hiện workflow mới được tạo trong workspace; cần push lên GitHub và điền secrets
thì lịch trên GitHub mới hoạt động.**

### Logging và cảnh báo lỗi

| File | Nội dung |
| --- | --- |
| `logs/pipeline.log` | Các bước crawl/ETL, số tin, lỗi và traceback; giờ UTC |
| `logs/latest_run.json` | Kết quả lần chạy gần nhất, trạng thái từng nguồn, số tin thêm/bỏ qua |
| `data/raw/crawl_status.json` | Tình trạng crawl gần nhất của từng website, dùng cho dashboard |
| `data/processed/etl_report.json` | Số dòng đọc, làm sạch, loại bỏ, trùng và kết quả nạp DB |

Log tự xoay mỗi ngày, giữ tối đa 30 bản lưu cũ. Mật khẩu DB, bot token và mật khẩu
SMTP được che khi ghi log. Không đẩy `.env`, log hay thư mục dữ liệu PostgreSQL lên Git.

Nếu một website lỗi hoặc thiếu mô tả, pipeline vẫn xử lý các nguồn khác và dữ liệu
hợp lệ, nhưng trả mã thoát **1** và gửi cảnh báo khi đã cấu hình. Lần chạy đầy đủ
trả **0**. Nếu đã có pipeline khác chạy, lần chạy trùng trả **2**.
Cảnh báo ở đây áp dụng khi chương trình Python đã khởi chạy; lỗi cài thư viện hoặc
runner chưa chạy cần xem trực tiếp trong GitHub Actions.

**Telegram:** tạo bot qua BotFather, lấy token, mở chat với bot và nhấn Start,
lấy `chat_id` của chat nhận cảnh báo. Điền trong `.env`:

```dotenv
ALERT_CHANNEL=telegram
TELEGRAM_BOT_TOKEN=TOKEN_CUA_BAN
TELEGRAM_CHAT_ID=CHAT_ID_CUA_BAN
```

Bot gọi [Telegram sendMessage](https://core.telegram.org/bots/api#sendmessage).
Không cần điền token vào source code. Để lấy chat ID, có thể xem `message.chat.id`
trong phản hồi `getUpdates` sau khi gửi một tin cho bot; giữ token trong môi trường riêng.

**Email:** dùng tài khoản SMTP của bạn; điền host, thông tin đăng nhập và người nhận:

```dotenv
ALERT_CHANNEL=email
SMTP_HOST=SMTP_HOST_CUA_BAN
SMTP_PORT=587
SMTP_SECURITY=starttls
SMTP_USERNAME=TAI_KHOAN_SMTP
SMTP_PASSWORD=MAT_KHAU_SMTP
ALERT_FROM=sender@example.com
ALERT_TO=receiver@example.com
```

Dùng `SMTP_SECURITY=ssl`, cổng `465` nếu nhà cung cấp yêu cầu SSL trực tiếp.
`ALERT_CHANNEL=both` để dùng cả hai; `none` để chỉ ghi log.
Đối với GitHub Actions, đặt `ALERT_CHANNEL`, `SMTP_PORT`, `SMTP_SECURITY`,
`USD_VND_RATE` trong **Variables**; các token, mật khẩu, địa chỉ email và thông tin SMTP
đặt trong **Secrets** theo đúng tên ở `.env.example`.

Chưa có token/tài khoản nhận cảnh báo trong phiên làm việc này, nên `.env` đang để
`ALERT_CHANNEL=none`: phần gửi thông báo đã có code nhưng **chưa bật gửi thật**.

## Tuần 4 — ETL và PostgreSQL

ETL là ba bước: **Extract** đọc dữ liệu raw, **Transform** làm sạch/chuẩn hóa,
**Load** nạp vào PostgreSQL. `src/data_ana/etl.py` thực hiện ba bước đó.

### Chuẩn bị PostgreSQL và .env

Trên máy hiện tại đã tạo cluster **riêng cho dự án** tại `data/postgres`,
cổng `55432`, database `it_job_market`, user `data_ana`.
Mật khẩu ngẫu nhiên và `DATABASE_URL` được lưu trong `.env` ở thư mục gốc.
Sau khi khởi động lại máy, bật database trước:

```cmd
python -m data_ana.local_postgres start
python crawler.py --skip-crawl
```

Các lệnh quản lý khác:

```cmd
python -m data_ana.local_postgres status
python -m data_ana.local_postgres stop
```

Helper này sử dụng bộ binary PostgreSQL có sẵn trên Windows. Để khởi tạo trên một
máy Windows khác có binary PostgreSQL và **chưa cấu hình DATABASE_URL**, dùng:

```cmd
python -m data_ana.local_postgres init
```

Có thể chỉ định `POSTGRES_BIN` nếu helper không tìm được thư mục binary.
Helper không cài Windows service; khi tắt/reboot máy cần chạy `start` lại.

Nếu dùng PostgreSQL riêng hoặc trên server khác, tạo database trước, sao chép
`.env.example` thành `.env` **chỉ khi chưa có `.env`**, rồi sửa `DATABASE_URL`.
Biến môi trường của terminal được ưu tiên hơn giá trị trong `.env`.

Nếu chọn Docker thay cho cluster trên, dừng cluster trước để giải phóng cổng 55432,
điền `POSTGRES_PASSWORD` và `DATABASE_URL` khớp nhau trong `.env`, sau đó chạy:

```cmd
docker compose up -d db
python crawler.py --skip-crawl
```

Docker lưu dữ liệu trong volume `postgres_data`; `docker compose down` dừng container
và vẫn giữ volume. Chỉ chọn một cách chạy PostgreSQL trên cùng cổng 55432.

### ETL làm sạch những gì?

| Dữ liệu | Cách xử lý |
| --- | --- |
| Tiêu đề, công ty, mô tả | Bỏ khoảng trắng thừa; loại HTML trong mô tả |
| Link | Bỏ query tracking và fragment để nhận diện tin trùng |
| Lương | Đọc lại `salary_text`, giữ tiền tệ/số gốc; quy đổi VND/tháng |
| Kỹ năng | Regex theo danh sách tên/alias trong `etl.py`, đọc cả tiêu đề, mô tả và tag |
| Địa điểm | Chuẩn hóa các cách viết phổ biến của Hà Nội, Hồ Chí Minh, Đà Nẵng; vẫn giữ địa điểm gốc |
| Ngày đăng | Đổi ISO/ngày-tháng-năm sang DATE; chuỗi như “1 tuần trước” giữ ở `posted_date_text`, không tự đoán ngày chính xác |
| Thời gian thu thập | Bắt buộc có múi giờ, chuẩn hóa UTC |
| Tin thiếu source/title/ID hoặc link | Loại khỏi dữ liệu sạch, ghi lý do trong `rejected.json` |

Ví dụ lương với giả định `USD_VND_RATE=25000`:

| Chuỗi gốc | salary_min / salary_max (VND/tháng) |
| --- | --- |
| `20 - 35 triệu` | 20.000.000 / 35.000.000 |
| `$1,000 - $2,000` | 25.000.000 / 50.000.000 |
| `Tới 25 triệu` | NULL / 25.000.000 |
| `Từ 20 triệu` | 20.000.000 / NULL |
| `Thoả thuận`, `Login to view salary` | NULL / NULL |

Tỷ giá trên là **tham số giả định của dự án, không phải tỷ giá được cập nhật trực tiếp**.
Đổi `USD_VND_RATE` trong `.env` hoặc dùng `--usd-vnd` khi chạy ETL.
Mỗi tin lưu cả `salary_currency`, `salary_period`, `salary_min_original`,
`salary_max_original` và `usd_vnd_rate` để có thể kiểm tra phép đổi.
Không nêu kỳ trả lương thì giả định theo tháng; lương theo năm chia 12.
Lương theo giờ/ngày giữ số gốc, để NULL ở cột VND/tháng vì chưa biết số giờ/ngày làm việc.
Lương không có đơn vị tiền tệ hoặc cấu trúc không rõ cũng không được suy đoán.

Các alias kỹ năng như `ReactJS`/`React` và `Node.js`/`NodeJS` được gộp về một tên.
Các tag bị cắt “...” và tag kinh nghiệm không dùng làm tên kỹ năng.
Đây là regex theo từ điển, không phải mô hình NLP hiểu ngữ cảnh: mô tả nhắc một công
nghệ chưa chắc công nghệ đó là yêu cầu bắt buộc. Muốn bổ sung công nghệ, sửa
`SKILL_ALIASES` trong `src/data_ana/etl.py`.

### Bốn bảng trong PostgreSQL

Schema: [schema.sql](src/data_ana/schema.sql).

```mermaid
erDiagram
    companies ||--o{ jobs : "tuyển dụng"
    jobs ||--o{ job_skills : "có kỹ năng"
    skills ||--o{ job_skills : "được nhắc đến"
```

| Bảng | Vai trò |
| --- | --- |
| `companies` | Mỗi tên công ty chuẩn hóa một dòng, gộp khác biệt hoa/thường/khoảng trắng |
| `jobs` | Tin tuyển dụng, liên kết công ty; giữ nguồn, job ID/link, lương, địa điểm, mô tả, ngày |
| `skills` | Mỗi tên kỹ năng chuẩn hóa một dòng |
| `job_skills` | Bảng nối nhiều-nhiều: một tin có nhiều kỹ năng, một kỹ năng xuất hiện trong nhiều tin |

Việc gộp công ty dựa trên tên là một giả định, chưa phải đối chiếu pháp nhân/mã số thuế.
`jobs` có ràng buộc UNIQUE cho `(source, source_job_id)` và `(source, url)`;
`job_skills` có khóa chính `(job_id, skill_id)`.

### Incremental: vì sao chạy lại không bị trùng?

Mỗi dòng được kiểm tra theo **website + job ID hoặc website + link chuẩn hóa**.
Nếu đã có, loader bỏ qua. Nếu chưa có, loader thêm công ty/kỹ năng liên quan,
thêm tin rồi tạo các liên kết trong `job_skills`.
`ON CONFLICT DO NOTHING` là lớp bảo vệ thêm ở database.
Toàn bộ lần nạp dùng một transaction: nếu lỗi thì rollback để không ghi dở bốn bảng.
Xem [PostgreSQL INSERT / ON CONFLICT](https://www.postgresql.org/docs/current/sql-insert.html).

Đây là chế độ **chỉ thêm tin mới**: tin cũ trong PostgreSQL không được cập nhật lại
lương/mô tả khi tin nguồn thay đổi. Các trường bổ sung `requirements`,
`programming_languages`, `language_evidence`, kỹ năng bổ trợ, ngoại ngữ và phúc lợi được làm giàu cho cả tin cũ khi chạy ETL,
để dữ liệu lịch sử cũng dùng được bộ lọc ngôn ngữ. Nó khác CSV raw, nơi một tin có thể được crawl lại.
Không tự xóa tin hết hạn. Hai website đăng cùng một vị trí vẫn là hai tin theo hai nguồn.

Chạy ETL riêng:

```cmd
python -m data_ana.etl --input data/raw/jobs.csv
python -m data_ana.etl --input data/raw/2026-10-28_itviec.json
```

Hai lệnh trên **đều nạp PostgreSQL**. Nếu chỉ muốn xem dữ liệu sạch:

```cmd
python -m data_ana.etl --input data/raw/jobs.csv --no-db
```

File đầu ra nằm trong `data/processed`: `jobs.csv`, `jobs.json`, `rejected.json`,
`etl_report.json`. ETL đọc được cả JSON cũ có `skills` dạng chuỗi và JSON mới có mảng.

Xem dashboard bằng dữ liệu đã làm sạch:

```cmd
python -m streamlit run src/data_ana/dashboard.py -- --data data/processed/jobs.csv
```

Dashboard hiện đọc CSV, chưa truy vấn PostgreSQL trực tiếp. Mở file
[sql/examples.sql](sql/examples.sql) trong công cụ quản lý PostgreSQL để thống kê
tin theo website, kỹ năng, công ty và lương trực tiếp từ bốn bảng.

### Kết quả đã chạy và cách tự kiểm tra

Ngày 28/10/2026 đã chạy ETL trên 77 tin đang có: 50 TopCV, 20 ITviec, 7 TopDev.
Lần nạp đầu thêm 77 tin; chạy lại thêm 0, bỏ qua 77; không có dòng bị loại.
Đã kiểm tra trên PostgreSQL thật việc chống trùng theo ID/link và rollback khi lỗi.
Các test database dùng schema tạm riêng, không sửa bảng dữ liệu chính.

```cmd
python -m pytest -q
```

Lệnh trên chạy test tự động; test kết nối PostgreSQL chỉ chạy khi có biến
`TEST_DATABASE_URL`, nếu không sẽ báo skipped. Không cần cấu hình Telegram/email
để chạy test vì phần gửi thông báo được giả lập.

## Luu y ve thu thap du lieu

- Kiem tra `robots.txt` va dieu khoan su dung cua tung website truoc khi crawl.
- Dung `User-Agent` ro rang va delay giua cac request.
- Khong thu thap du lieu ca nhan nhay cam.
- Neu website thay doi cau truc HTML/API, cap nhat selector trong `config/sites.json`.

## Dinh dang du lieu dau ra

File CSV gom cac cot chinh:

| Cot | Mo ta |
| --- | --- |
| `source` | Website nguon |
| `title` | Tieu de viec lam |
| `company` | Ten cong ty |
| `location` | Dia diem |
| `level` | Cap bac: Intern, Fresher, Junior, Middle, Senior |
| `work_model` | Onsite, Hybrid, Remote hoac Unknown |
| `salary_min` | Luong toi thieu, don vi VND/thang neu tach duoc |
| `salary_max` | Luong toi da, don vi VND/thang neu tach duoc |
| `skills` | Danh sach ky nang, ngan cach bang dau `;` |
| `url` | Link tin tuyen dung |
| `scraped_at` | Thoi diem thu thap |

## Thanh vien

- Hoang Cao Phong
- Vu Thi Dieu Linh

