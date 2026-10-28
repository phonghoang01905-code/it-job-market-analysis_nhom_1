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

Cấu hình `config/sites.example.json` đã bật cả ba nguồn, mặc định một trang mỗi nguồn.
Crawler kiểm tra `robots.txt`, khai báo User-Agent, nghỉ 4 giây giữa các request,
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
Adapter chỉ nhận tin có `job_category_id=1` trong metadata công khai và có thẻ tin
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

Mặc định tối đa một trang danh sách/website. Dùng `--max-pages 2` để tăng giới hạn.
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
lương/mô tả khi tin nguồn thay đổi. Nó khác CSV raw, nơi một tin có thể được crawl lại.
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

