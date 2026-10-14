# Phan tich thi truong tuyen dung IT Viet Nam

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

4. Chay dashboard:

```bash
streamlit run src\data_ana\dashboard.py -- --data data\raw\jobs.csv
```

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

