# Bổ sung kỹ năng, ngoại ngữ và phúc lợi — 30/10/2026

| Website | Tin đã lưu | Có kỹ năng bổ trợ | Có thông tin tiếng Anh | Có nội dung phúc lợi |
| --- | ---: | ---: | ---: | ---: |
| ITviec | 70 | 54 | 44 | 70 |
| TopDev | 50 | 37 | 27 | 49 |
| TopCV | 98 | 38 | 29 | 53 |
| Tổng | 218 | 129 | 100 | 172 |

“Có thông tin tiếng Anh” bao gồm yêu cầu rõ ràng, ưu tiên, chỉ nhắc đến và không bắt buộc;
không coi toàn bộ 100 tin là bắt buộc tiếng Anh. Không nêu rõ thông tin được giữ ở trạng thái unknown.

## Nguồn nội dung

- Phúc lợi từ trường JobPosting `jobBenefits` hoặc phần Quyền lợi/Benefits trong HTML công khai.
- Kỹ năng bổ trợ từ phần yêu cầu, tiêu đề, tag; chỉ dùng đoạn yêu cầu xác định được trong mô tả cũ.
- Ngoại ngữ tách khỏi ngôn ngữ lập trình; giữ trích dẫn có IELTS/TOEIC hoặc mức độ giao tiếp nếu tin có nêu.
- Không chuyển “đào tạo tiếng Anh” trong phúc lợi thành yêu cầu tiếng Anh; không gán bảo hiểm từ ngành kinh doanh bảo hiểm của công ty.
- Phân loại mức yêu cầu là heuristic; trích dẫn gốc luôn được giữ để kiểm tra.

## Độ đầy đủ

Đã đọc lại đủ 70 tin ITviec và 50 tin TopDev. Một tin TopDev không có nội dung phúc lợi đọc được.
TopCV đọc bổ sung được 27 tin chi tiết, sau đó trả HTTP 429. Lần tiếp tục sau thời gian nghỉ
vẫn gặp 429 tại cùng đường dẫn nên đã dừng; các trường chưa đọc đủ không được điền giả.
Kết hợp phần phúc lợi đã có trong mô tả lưu trước đó, tổng cộng có 53/98 tin TopCV có nội dung phúc lợi.
Report lần bổ sung gần nhất của TopCV nhắm tới 50 tin mới nhất; dữ liệu lịch sử vẫn có 98 tin.

## Lưu trữ và kiểm tra

- Danh sách vẫn có 218 tin, không tạo tin trùng. Raw, processed và PostgreSQL đã được đối chiếu.
- PostgreSQL bổ sung cột bằng migration không xóa bảng; cập nhật metadata trên tin đã tồn tại.
- Bằng chứng ngoại ngữ từ tag gốc được giữ nguyên qua ETL và PostgreSQL dù cột kỹ năng kỹ thuật không chứa English.
- Các file `data/raw/2026-10-30_*_profile.json` lưu snapshot bổ sung; `data/raw/enrichment_report.json` ghi kết quả và lỗi.
- Dashboard có cột, bộ lọc, thống kê và phần chi tiết cho kỹ năng bổ trợ/ngoại ngữ/phúc lợi. CSV tải xuống giữ nội dung đầy đủ.
- Kiểm tra tự động bao gồm phủ định/ưu tiên tiếng Anh, phúc lợi đào tạo ngoại ngữ, tránh nhầm ngành công ty thành phúc lợi, roundtrip CSV/ETL, nạp PostgreSQL, bộ lọc dashboard và trường hợp không có kết quả.
