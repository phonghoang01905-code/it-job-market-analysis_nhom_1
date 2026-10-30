"""Streamlit CV workflow; no CV files, text, or results are persisted to disk."""
from __future__ import annotations

from dataclasses import asdict
import hashlib

import pandas as pd
import streamlit as st

from data_ana.cv_matching import Candidate, CEFR, LEVELS, MAX_CHARS, WEIGHTS, candidate_from_text, extract_cv_text, rank_jobs
from data_ana.etl import SKILL_ALIASES
from data_ana.job_profile import FOREIGN, SUPPLEMENTARY
from data_ana.languages import PATTERNS


DEMO_CV = """HỒ SƠ MINH HỌA — KHÔNG PHẢI CV THẬT
Junior Python Developer
Kinh nghiệm: 2 năm kinh nghiệm phát triển ứng dụng web.
Kỹ năng: Python, SQL, PostgreSQL, JavaScript, Docker, Git, AWS.
Dự án: xây dựng dịch vụ backend bằng Python và cơ sở dữ liệu PostgreSQL.
Ngoại ngữ: English, IELTS 6.5.
Kỹ năng bổ trợ: teamwork, communication skills, problem solving, self-learning.
"""


def clear_cv():
    generation = st.session_state.get("cv_generation", 0) + 1
    for key in list(st.session_state):
        if key.startswith("cv_"):
            del st.session_state[key]
    st.session_state["cv_generation"] = generation


def show_cv_matcher(df: pd.DataFrame) -> None:
    st.subheader("Tìm việc phù hợp với CV")
    st.info("Rating là mức khớp giữa hồ sơ bạn xác nhận và thông tin tin tuyển dụng, không phải xác suất được nhận hay cam kết từ nhà tuyển dụng.")
    st.caption("CV được xử lý trong bộ nhớ phiên Streamlit; không ghi vào CSV, PostgreSQL hoặc log và không gửi sang dịch vụ AI/API bên ngoài.")
    action, clear = st.columns(2)
    if action.button("Dùng CV minh họa", key="cv_demo"):
        clear_cv()
        st.session_state["cv_mode"] = "Dán nội dung"
        generation = st.session_state["cv_generation"]
        st.session_state[f"cv_paste_{generation}"] = DEMO_CV
        st.rerun()
    if clear.button("Xóa CV và kết quả trong phiên", key="cv_clear"):
        clear_cv()
        st.rerun()
    generation = st.session_state.get("cv_generation", 0)
    mode = st.radio("Cách nhập CV", ["Tải tệp", "Dán nội dung"], horizontal=True, key="cv_mode")
    data, filename, pasted = None, "", ""
    if mode == "Tải tệp":
        uploaded = st.file_uploader("Chọn CV PDF, DOCX hoặc TXT", type=["pdf", "docx", "txt"], key=f"cv_file_{generation}", help="Tối đa 10 MB; PDF tối đa 20 trang. CV scan/ảnh cần chuyển thành văn bản hoặc dán nội dung.")
        if uploaded is not None:
            data, filename = uploaded.getvalue(), uploaded.name
    else:
        pasted = st.text_area("Nội dung CV", height=200, max_chars=MAX_CHARS, key=f"cv_paste_{generation}", placeholder="Dán kinh nghiệm, kỹ năng, dự án và ngoại ngữ…")
    digest = hashlib.sha256((data or pasted.encode("utf-8")) + mode.encode()).hexdigest()
    if st.button("Đọc CV", key="cv_parse", type="primary"):
        try:
            if mode == "Tải tệp":
                if data is None:
                    raise ValueError("Hãy chọn một tệp CV trước.")
                text = extract_cv_text(data, filename)
            else:
                if len(pasted.strip()) < 30:
                    raise ValueError("Hãy dán ít nhất 30 ký tự nội dung CV.")
                text = pasted.strip()
            detected = candidate_from_text(text)
        except ValueError as exc:
            st.error(str(exc))
            return
        st.session_state["cv_detected"] = asdict(detected)
        st.session_state["cv_text"] = text
        st.session_state["cv_hash"] = digest
        st.session_state["cv_version"] = st.session_state.get("cv_version", 0) + 1
    if "cv_detected" not in st.session_state:
        st.caption("Tải CV → Đọc CV → kiểm tra hồ sơ → xếp hạng việc làm.")
        return
    if digest != st.session_state.get("cv_hash"):
        st.warning("Nội dung CV đã thay đổi. Bấm Đọc CV để dùng hồ sơ mới; kết quả cũ đã được ẩn.")
        return
    version = st.session_state["cv_version"]
    detected = st.session_state["cv_detected"]
    st.markdown("**Kiểm tra hồ sơ trước khi đối chiếu**")
    st.caption("Bạn có thể sửa các thông tin nhận diện. Viết CV bằng tiếng Anh không tự chứng minh trình độ tiếng Anh; số năm chỉ lấy từ câu nêu kinh nghiệm rõ ràng, không cộng thời gian học/dự án.")
    tech_options = sorted(set(SKILL_ALIASES) | set(PATTERNS) | set(detected["skills"]))
    skills = st.multiselect("Kỹ năng chuyên môn trong hồ sơ", tech_options, default=detected["skills"], key=f"cv_skills_{version}")
    left, right = st.columns(2)
    with left:
        known_years = st.checkbox("Tôi xác nhận số năm kinh nghiệm", value=detected["years"] is not None, key=f"cv_years_known_{version}")
        years = st.number_input("Số năm kinh nghiệm liên quan", min_value=0.0, max_value=60.0, value=float(detected["years"] or 0), step=0.5, disabled=not known_years, key=f"cv_years_{version}")
        default_level = detected["level"] if detected["level"] in LEVELS else "Unknown"
        level = st.selectbox("Cấp bậc bạn xác nhận", LEVELS, index=LEVELS.index(default_level), format_func=lambda value: "Chưa xác định" if value == "Unknown" else value, key=f"cv_level_{version}")
    with right:
        foreign = st.multiselect("Ngoại ngữ trong hồ sơ", sorted(FOREIGN), default=detected["foreign_languages"], key=f"cv_foreign_{version}")
        supplementary = st.multiselect("Kỹ năng bổ trợ trong hồ sơ", sorted(SUPPLEMENTARY), default=detected["supplementary_skills"], key=f"cv_supp_{version}")
    with st.expander("Điểm chứng chỉ tiếng Anh đã có"):
        st.caption("Chỉ đối chiếu cùng loại chứng chỉ; không quy đổi TOEIC thành IELTS. Giá trị 0 nghĩa là chưa có/không dùng.")
        a, b, c = st.columns(3)
        certs = {
            "IELTS": a.number_input("IELTS", 0.0, 9.0, float(detected["certificates"].get("IELTS", 0)), step=0.5, key=f"cv_ielts_{version}"),
            "TOEIC": b.number_input("TOEIC", 0, 990, int(detected["certificates"].get("TOEIC", 0)), step=5, key=f"cv_toeic_{version}"),
            "TOEFL iBT": c.number_input("TOEFL iBT", 0, 120, int(detected["certificates"].get("TOEFL iBT", 0)), step=1, key=f"cv_toefl_{version}"),
        }
        cefr = st.selectbox("Mức tiếng Anh theo CEFR đã xác nhận", ["Chưa xác định"] + CEFR, index=int(detected["certificates"].get("CEFR", 0)), key=f"cv_cefr_{version}")
        if cefr in CEFR:
            certs["CEFR"] = CEFR.index(cefr)+1
    with st.expander("Xem văn bản CV đã đọc"):
        st.text(st.session_state["cv_text"])
    st.caption(f"Đối chiếu trong {len(df)} tin theo bộ lọc bên trái. Tin lưu trước đây có thể đã hết hạn; mở link gốc để kiểm tra trước khi ứng tuyển.")
    if st.button("Xếp hạng việc làm phù hợp", key=f"cv_rank_{version}", type="primary"):
        st.session_state[f"cv_show_{version}"] = True
    if not st.session_state.get(f"cv_show_{version}"):
        return
    if not skills:
        st.warning("Chưa có kỹ năng chuyên môn để đối chiếu. Hãy kiểm tra hoặc bổ sung kỹ năng trong hồ sơ phía trên.")
        return
    if df.empty:
        st.info("Không còn tin trong bộ lọc. Hãy nới bộ lọc bên trái.")
        return
    candidate = Candidate(skills=skills, foreign_languages=foreign, supplementary_skills=supplementary,
        years=years if known_years else None, level=level, certificates={k: float(v) for k, v in certs.items() if v > 0})
    results = rank_jobs(candidate, df.to_dict("records"))
    results = [r for r in results if r["matched_skills"]]
    if not results:
        st.info("Chưa tìm thấy tin có kỹ năng chuyên môn trùng với hồ sơ. Hãy kiểm tra kỹ năng đã nhận diện hoặc cập nhật thêm tin tuyển dụng.")
        return
    st.markdown("**Công việc nên ưu tiên đối chiếu và ứng tuyển**")
    count, priority_count, sources = st.columns(3)
    count.metric("Tin có kỹ năng trùng", len(results))
    priority_count.metric("Ưu tiên cao", sum(r["priority"] == "Cao" for r in results))
    sources.metric("Website có gợi ý", len({r["job"].get("source", "") for r in results}))
    n = st.slider("Số kết quả hiển thị", 5, 50, 15, step=5, key=f"cv_limit_{version}")
    selected_results = results[:n]
    table = pd.DataFrame([{
        "Ưu tiên": r["priority"], "Điểm khớp /100": r["score"], "Rating /5": r["stars"],
        "Vị trí": r["job"].get("title", ""), "Công ty": r["job"].get("company", ""),
        "Website": r["job"].get("website", r["job"].get("source", "")),
        "Địa điểm": r["job"].get("location", ""), "Lương": r["job"].get("salary_text", ""),
        "Kỹ năng trùng": "; ".join(r["matched_skills"]), "Chưa thấy trong CV": "; ".join(r["missing_skills"]),
        "Cần đối chiếu": "; ".join(r["blockers"] + r["foreign_gaps"]),
        "Tin gốc": r["job"].get("url", ""),
    } for r in selected_results])
    st.dataframe(table, hide_index=True, use_container_width=True, column_config={"Tin gốc": st.column_config.LinkColumn(display_text="Xem tin"), "Điểm khớp /100": st.column_config.ProgressColumn(min_value=0,max_value=100,format="%.1f")})
    st.download_button("Tải bảng gợi ý CSV", table.to_csv(index=False).encode("utf-8-sig"), file_name="cong_viec_phu_hop_cv.csv", mime="text/csv", key=f"cv_download_{version}")
    index = st.selectbox("Xem lý do rating của một công việc", list(range(len(selected_results))), format_func=lambda i: f"{selected_results[i]['score']:.1f}/100 · {selected_results[i]['job'].get('title', '')} · {selected_results[i]['job'].get('company', '')}", key=f"cv_result_{version}")
    chosen = selected_results[index]
    st.markdown(f"**{'★'*chosen['stars']}{'☆'*(5-chosen['stars'])} · {chosen['score']:.1f}/100 · Ưu tiên ứng tuyển: {chosen['priority']}**")
    st.write("Kỹ năng trùng: " + ", ".join(chosen["matched_skills"]))
    st.write("Công nghệ/kỹ năng trong tin chưa thấy trong CV: " + (", ".join(chosen["missing_skills"]) or "Không có trong các mục đã nhận diện"))
    st.caption("Các mục chưa thấy trong CV không mặc nhiên là điều kiện bắt buộc; tin có thể nêu ưu tiên hoặc các công nghệ thay thế nhau.")
    for note in chosen["blockers"] + chosen["foreign_gaps"] + chosen["notes"]:
        st.write("• " + note)
    component_table = pd.DataFrame(chosen["components"]).rename(columns={"criterion":"Tiêu chí", "weight":"Trọng số", "match":"Mức khớp /100", "detail":"Giải thích"})
    st.dataframe(component_table,hide_index=True,use_container_width=True)
    with st.expander("Yêu cầu tuyển dụng dùng để đối chiếu"):
        st.write(chosen["job"].get("requirements") or "Chưa có phần yêu cầu riêng; đang dùng tiêu đề/tag/mô tả với giới hạn điểm.")
        st.write("Kinh nghiệm: " + chosen["experience_excerpt"])
        st.write(chosen["job"].get("english_requirement") or "Chưa có câu yêu cầu tiếng Anh riêng")
    if str(chosen["job"].get("url", "")).startswith("https://"):
        st.link_button("Mở tin gốc để kiểm tra và ứng tuyển", chosen["job"]["url"])
    with st.expander("Cách tính rating"):
        st.write("Trọng số gốc: " + ", ".join(f"{name} {weight}%" for name,weight in WEIGHTS.items()) + ".")
        st.write("Chỉ dùng tiêu chí có dữ liệu trong tin, rồi chuẩn hóa trọng số. Thiếu dữ liệu từ hồ sơ không được coi là đáp ứng. Tin thiếu yêu cầu chi tiết tối đa 60 điểm; có yêu cầu quan trọng chưa đáp ứng/xác nhận tối đa 65 điểm. Rating 5 sao từ 85 điểm, 4 sao từ 70, 3 sao từ 50, 2 sao từ 30, 1 sao khi trên 0.")
        st.write("Ưu tiên Cao: từ 75 điểm, có kỹ năng chuyên môn trùng và không có yêu cầu quan trọng còn thiếu/xác nhận; Vừa: từ 45 điểm; còn lại: Thấp. Bộ lọc bên trái quyết định website, vị trí, địa điểm và mức lương muốn tìm; các mục này không tự cộng vào điểm.")
        st.caption("Đối chiếu theo từ khóa, chưa phân biệt đầy đủ công nghệ bắt buộc, ưu tiên hoặc thay thế nhau. Điểm giữa các tin có thể dựa trên các tiêu chí khác nhau do mức độ đầy đủ của dữ liệu.")
        st.write("Chưa có dữ liệu ứng tuyển/phỏng vấn/kết quả nhận việc để hiệu chỉnh thành xác suất. Không chấm theo tên, giới tính, tuổi, ảnh hoặc thông tin liên hệ.")
