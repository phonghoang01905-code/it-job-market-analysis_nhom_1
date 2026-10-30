from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st
from data_ana.languages import ALIASES, extract_languages
from data_ana.job_profile import ENGLISH_STATUS_LABELS, extract_profile
from data_ana.cv_dashboard import show_cv_matcher


SOURCES = {
    "topcv": {"name": "TopCV", "color": "#16a673", "url": "https://www.topcv.vn"},
    "itviec": {"name": "ITviec", "color": "#ed5264", "url": "https://itviec.com"},
    "topdev": {"name": "TopDev", "color": "#6688f5", "url": "https://topdev.vn"},
}
MODEL_NAMES = {"Onsite": "Tại văn phòng", "Hybrid": "Kết hợp", "Remote": "Từ xa", "Unknown": "Chưa xác định"}
SKILL_NAMES = {
    "node.js": "NodeJS", "nodejs": "NodeJS", "reactjs": "React", "react": "React",
    "vuejs": "Vue", "vue": "Vue", "js": "JavaScript", "javascript": "JavaScript",
    "typescript": "TypeScript", "python": "Python", "java": "Java", "c#": "C#",
    "c++": "C++", ".net": ".NET", "sql": "SQL", "mysql": "MySQL", "aws": "AWS",
    "qa": "QA", "qa/qc": "QA/QC", "ai": "AI", "php": "PHP", "gcp": "GCP",
    "postgresql": "PostgreSQL", "mongodb": "MongoDB", "devops": "DevOps",
}
SKILL_NAMES.update({name.casefold(): name for name in ALIASES})
SKILL_NAMES.update({alias.casefold(): name for name, aliases in ALIASES.items() for alias in aliases})
SKILL_NAMES.update({"c": "C", "go": "Go"})


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("data/raw/jobs.csv"))
    return parser.parse_args()


def normalize(value: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", value.lower()) if unicodedata.category(c) != "Mn").replace("đ", "d")


def city_label(value: str) -> str:
    normalized = normalize(value)
    matches = [label for label, names in {
        "Hồ Chí Minh": ["ho chi minh", "hcm", "sai gon"],
        "Hà Nội": ["ha noi", "hanoi"], "Đà Nẵng": ["da nang", "danang"],
    }.items() if any(name in normalized for name in names)]
    if len(matches) > 1:
        return "Nhiều địa điểm"
    return matches[0] if matches else (value.strip() or "Chưa xác định")


def profile_for_row(row: dict) -> dict:
    profile = extract_profile(row["title"], row["description"], row["requirements"], row["skills"], row["benefits"])
    try:
        evidence = json.loads(row.get("profile_evidence") or "{}")
    except (ValueError, TypeError):
        return profile
    groups = ("supplementary_skills", "foreign_languages", "benefits")
    if not isinstance(evidence, dict) or not all(isinstance(evidence.get(key), dict) for key in groups):
        return profile
    if not all(isinstance(item, dict) and "source" in item and "excerpt" in item for key in groups for item in evidence[key].values()):
        return profile
    # Processed skills contain technical skills only. Preserve original spoken
    # language evidence instead of trying to reconstruct it from that column.
    profile.update(supplementary_skills=sorted(evidence["supplementary_skills"]), foreign_languages=sorted(evidence["foreign_languages"]), benefit_tags=sorted(evidence["benefits"]), profile_evidence=evidence)
    english = evidence["foreign_languages"].get("Tiếng Anh", {})
    profile["english_requirement"] = english.get("excerpt", "")
    status = english.get("status", "unknown")
    profile["english_status"] = status if status in ENGLISH_STATUS_LABELS else "unknown"
    return profile


def load_jobs(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, keep_default_na=False)
    for column in ["source", "title", "company", "location", "level", "work_model", "salary_text", "skills", "description", "requirements", "benefits", "posted_date", "url", "scraped_at"]:
        if column not in df:
            df[column] = ""
        df[column] = df[column].fillna("").astype(str)
    for column in ["salary_min", "salary_max"]:
        if column not in df:
            df[column] = float("nan")
        df[column] = pd.to_numeric(df[column], errors="coerce").where(lambda s: s > 0)
    df["source"] = df["source"].str.strip().str.lower()
    if "posted_date_text" in df:
        df["posted_date"] = df["posted_date"].where(df["posted_date"].ne(""), df["posted_date_text"])
    df["_job_key"] = df["url"].str.replace(r"[?#].*$", "", regex=True)
    df["_job_key"] = df["_job_key"].where(df["_job_key"].ne(""), df["title"] + "|" + df["company"])
    df = df.drop_duplicates(["source", "_job_key"], keep="last").copy()
    extracted = [extract_languages(row.title, row.description, row.skills, row.requirements) for row in df.itertuples()]
    df["_language_list"] = pd.Series([value[0] for value in extracted], index=df.index, dtype=object)
    df["_language_evidence"] = pd.Series([value[1] for value in extracted], index=df.index, dtype=object)
    df["programming_languages"] = df["_language_list"].apply(lambda values: "; ".join(values))
    profiles = [profile_for_row(row) for row in df.to_dict("records")]
    for field, internal in [("supplementary_skills", "_supplementary_list"), ("foreign_languages", "_foreign_list"), ("benefit_tags", "_benefit_list")]:
        df[internal] = pd.Series([p[field] for p in profiles], index=df.index, dtype=object)
        df[field] = df[internal].apply(lambda values: "; ".join(values))
    for field in ("english_requirement", "english_status", "benefits"):
        df[field] = pd.Series([p[field] for p in profiles], index=df.index, dtype=object)
    df["_profile_evidence"] = pd.Series([p["profile_evidence"] for p in profiles], index=df.index, dtype=object)
    df["salary_midpoint"] = df[["salary_min", "salary_max"]].mean(axis=1, skipna=True)
    df["city"] = df["location"].apply(city_label)
    df["work_model"] = df["work_model"].where(df["work_model"].isin(MODEL_NAMES), "Unknown")
    df["website"] = df["source"].map(lambda s: SOURCES.get(s, {}).get("name", s))
    return df


def explode_skills(df: pd.DataFrame) -> pd.DataFrame:
    def clean_skills(value: str) -> list[str]:
        result = set()
        for skill in value.split(";"):
            skill = skill.strip()
            # Old TopCV data has shortened experience tags, not usable skill names.
            if len(skill) < 2 or "..." in skill or "…" in skill:
                continue
            if re.search(r"kinh nghiem|yeu cau|\d+\s*nam", normalize(skill)):
                continue
            result.add(SKILL_NAMES.get(skill.lower(), skill))
        return sorted(result)

    skills = df.assign(skill=df["skills"].apply(clean_skills)).explode("skill")
    return skills[skills["skill"].notna() & skills["skill"].ne("")]


def horizontal_bar_chart(
    values: pd.Series, *, value_label: str = "Số tin tuyển dụng",
    colors: dict[str, str] | None = None, color: str = "#6688f5",
    label_title: str = "Tên đầy đủ",
) -> None:
    values = values.sort_values(ascending=False, kind="stable")
    if values.empty:
        st.info("Chưa có dữ liệu phù hợp để vẽ biểu đồ.")
        return
    data = pd.DataFrame({"label": values.index.astype(str), "value": values.to_numpy()})
    order = data["label"].tolist()
    tooltip = [alt.Tooltip("label:N", title=label_title), alt.Tooltip("value:Q", title=value_label, format="d")]
    base = alt.Chart(data).encode(
        x=alt.X("value:Q", title=value_label, scale=alt.Scale(domain=[0, max(float(values.max()), 1) * 1.2]), axis=alt.Axis(tickMinStep=1, gridDash=[3, 4])),
        y=alt.Y("label:N", sort=order, title=None, axis=alt.Axis(labelLimit=230, labelFontSize=12, labelPadding=10, ticks=False, domain=False)),
        tooltip=tooltip,
    )
    color_encoding = alt.Color("label:N", scale=alt.Scale(domain=order, range=[colors.get(label, color) for label in order]), legend=None) if colors else alt.value(color)
    bars = base.mark_bar(cornerRadiusEnd=5, height=19).encode(color=color_encoding)
    labels = base.mark_text(align="left", dx=8, fontSize=12).encode(text=alt.Text("value:Q", format="d"))
    st.altair_chart((bars + labels).properties(height=max(140, 33 * len(data))).configure_view(strokeWidth=0), use_container_width=True)


def show_metrics(df: pd.DataFrame) -> None:
    total, companies, disclosed, descriptions = st.columns(4)
    total.metric("Tin tuyển dụng", f"{len(df):,}")
    companies.metric("Nhà tuyển dụng", f"{df.loc[df['company'].ne(''), 'company'].nunique():,}")
    disclosed.metric("Có thông tin lương", f"{df['salary_midpoint'].notna().sum():,} / {len(df):,}")
    descriptions.metric("Có mô tả chi tiết", f"{df['description'].str.strip().ne('').sum():,} / {len(df):,}")


def show_jobs(df: pd.DataFrame, key: str) -> None:
    st.subheader("Danh sách tuyển dụng")
    if df.empty:
        st.info("Không có tin phù hợp với bộ lọc đang chọn.")
        return
    columns = ["website", "title", "company", "location", "salary_text", "programming_languages", "supplementary_skills", "foreign_languages", "english_requirement", "english_status", "benefits", "benefit_tags", "requirements", "work_model", "skills", "posted_date", "scraped_at", "url"]
    table = df[columns].copy()
    table["salary_text"] = table["salary_text"].replace("", "Chưa công khai")
    table["work_model"] = table["work_model"].map(MODEL_NAMES)
    table["scraped_at"] = pd.to_datetime(table["scraped_at"], utc=True, errors="coerce").dt.tz_convert("Asia/Ho_Chi_Minh").dt.strftime("%d/%m/%Y %H:%M")
    table["programming_languages"] = table["programming_languages"].replace("", "Chưa thấy nêu trong dữ liệu")
    table["english_status"] = table["english_status"].map(ENGLISH_STATUS_LABELS)
    for field in ("supplementary_skills", "foreign_languages", "english_requirement", "benefits", "benefit_tags"):
        table[field] = table[field].replace("", "Chưa có thông tin trong dữ liệu")
    names = {"website": "Website", "title": "Vị trí", "company": "Công ty", "location": "Địa điểm", "salary_text": "Lương công khai", "programming_languages": "Ngôn ngữ lập trình", "requirements": "Yêu cầu ứng viên", "work_model": "Hình thức", "skills": "Kỹ năng", "posted_date": "Ngày đăng / thời gian gốc", "scraped_at": "Thu thập (giờ VN)", "url": "Tin gốc"}
    names.update(supplementary_skills="Kỹ năng bổ trợ", foreign_languages="Ngoại ngữ", english_requirement="Tiếng Anh — trích dẫn", english_status="Mức yêu cầu tiếng Anh", benefits="Phúc lợi — nội dung gốc", benefit_tags="Nhóm phúc lợi")
    st.dataframe(table.rename(columns=names), hide_index=True, use_container_width=True, column_config={"Tin gốc": st.column_config.LinkColumn("Tin gốc", display_text="Mở tin"), "Vị trí": st.column_config.TextColumn(width="large"), "Kỹ năng": st.column_config.TextColumn(width="large")})
    st.download_button("Tải CSV đang xem", table.rename(columns=names).to_csv(index=False).encode("utf-8-sig"), file_name=f"viec_lam_{key}.csv", mime="text/csv", key=f"download_{key}")
    with st.expander("Đọc mô tả đầy đủ của một tin"):
        selected = st.selectbox("Chọn tin tuyển dụng", df.index.tolist(), format_func=lambda i: f"{df.loc[i, 'title']} · {df.loc[i, 'company']}", key=f"detail_{key}")
        if selected is not None:
            row = df.loc[selected]
            st.markdown("**Kỹ năng bổ trợ và ngoại ngữ**")
            st.write("Kỹ năng bổ trợ: " + (row["supplementary_skills"] or "Chưa có thông tin"))
            st.write("Ngoại ngữ: " + (row["foreign_languages"] or "Chưa có thông tin"))
            st.write("Tiếng Anh: " + ENGLISH_STATUS_LABELS.get(row["english_status"], "Chưa có thông tin"))
            for group in ("supplementary_skills", "foreign_languages"):
                for label, item in row["_profile_evidence"][group].items():
                    st.markdown(f"**{label}** · {item['source']}")
                    st.write(item["excerpt"])
            st.markdown("**Phúc lợi / Lợi ích từ tin gốc**")
            if row["benefits"]:
                for paragraph in row["benefits"].splitlines():
                    st.write(paragraph)
            else:
                st.info("Chưa thu thập được phần phúc lợi của tin này; không đồng nghĩa công ty không có phúc lợi.")
            st.markdown("**Ngôn ngữ lập trình và trích dẫn từ tin**")
            if row["_language_evidence"]:
                for language, item in row["_language_evidence"].items():
                    st.markdown(f"**{language}** · {item['source']}")
                    st.write(item["excerpt"])
            else:
                st.info("Chưa thấy nêu ngôn ngữ lập trình trong dữ liệu đã thu được. Điều này không có nghĩa tin không yêu cầu ngôn ngữ.")
            if row["requirements"]:
                st.markdown("**Yêu cầu ứng viên từ tin gốc**")
                st.write(row["requirements"])
            st.markdown("**Mô tả chi tiết**")
            st.write(row["description"] or "Tin này chưa thu thập được mô tả chi tiết.")
            if row["url"].startswith("https://"):
                st.link_button("Xem trên website tuyển dụng", row["url"])


def show_languages(df: pd.DataFrame, color: str) -> None:
    st.subheader("Ngôn ngữ lập trình trong tin tuyển dụng")
    st.caption("Nhận diện từ yêu cầu ứng viên, tiêu đề, tag và mô tả; mỗi ngôn ngữ tính một lần/tin. Một ngôn ngữ được nhắc đến có thể là yêu cầu bắt buộc hoặc ưu tiên. SQL được tính là ngôn ngữ truy vấn; framework nằm ở biểu đồ kỹ năng bên dưới.")
    languages = df.explode("_language_list").dropna(subset=["_language_list"])
    left, right = st.columns([2, 1], gap="large")
    with left:
        horizontal_bar_chart(languages["_language_list"].value_counts(), color=color, label_title="Ngôn ngữ")
    with right:
        st.metric("Tin có nhắc ngôn ngữ", f"{df['_language_list'].apply(bool).sum()} / {len(df)}")
        st.metric("Có phần yêu cầu riêng", f"{df['requirements'].str.strip().ne('').sum()} / {len(df)}")
        st.caption("Chưa thấy nêu ngôn ngữ có thể do tin không nêu, hoặc mô tả chưa thu thập đủ. Mở một tin bên dưới để xem đoạn văn làm căn cứ.")


def show_profile_summary(df: pd.DataFrame, color: str) -> None:
    st.subheader("Kỹ năng bổ trợ, ngoại ngữ và phúc lợi")
    skill, english, benefit = st.columns(3)
    skill.metric("Có kỹ năng bổ trợ", f"{df['_supplementary_list'].apply(bool).sum()} / {len(df)}")
    english.metric("Có thông tin tiếng Anh", f"{df['english_status'].ne('unknown').sum()} / {len(df)}")
    benefit.metric("Có nội dung phúc lợi", f"{df['benefits'].str.strip().ne('').sum()} / {len(df)}")
    st.caption("Phân biệt yêu cầu ngoại ngữ với lớp học ngoại ngữ do công ty hỗ trợ. Nhóm phúc lợi phản ánh nội dung tin đăng; mở chi tiết để xem nguyên văn.")
    with st.expander("Xem thống kê kỹ năng bổ trợ, ngoại ngữ và phúc lợi", expanded=True):
        left, right = st.columns(2, gap="large")
        with left:
            st.markdown("**Kỹ năng bổ trợ được nhắc đến**")
            counts = df.explode("_supplementary_list")["_supplementary_list"].dropna().value_counts().head(8)
            horizontal_bar_chart(counts, color=color, label_title="Kỹ năng bổ trợ")
            st.markdown("**Ngoại ngữ trong tin**")
            counts = df.explode("_foreign_list")["_foreign_list"].dropna().value_counts()
            horizontal_bar_chart(counts, color=color, label_title="Ngoại ngữ")
        with right:
            st.markdown("**Nhóm phúc lợi**")
            counts = df.explode("_benefit_list")["_benefit_list"].dropna().value_counts()
            horizontal_bar_chart(counts, color="#16a673", label_title="Phúc lợi")


def show_charts(df: pd.DataFrame, color: str) -> None:
    show_profile_summary(df, color)
    show_languages(df, color)
    left, right = st.columns([1.35, 1], gap="large")
    with left:
        st.subheader("Kỹ năng được nhắc đến nhiều nhất")
        st.caption("Mỗi kỹ năng được tính tối đa một lần trong một tin. Rê chuột vào thanh để đọc tên đầy đủ.")
        horizontal_bar_chart(explode_skills(df)["skill"].value_counts().head(12), color=color, label_title="Kỹ năng")
    with right:
        st.subheader("Hình thức làm việc")
        horizontal_bar_chart(df["work_model"].map(MODEL_NAMES).value_counts(), colors={"Tại văn phòng": "#6688f5", "Kết hợp": "#f3b458", "Từ xa": "#16a673", "Chưa xác định": "#8c97ab"}, label_title="Hình thức")
        st.caption("Chưa xác định: tin gốc chưa nêu rõ hình thức làm việc.")
        st.subheader("Địa điểm tuyển dụng")
        horizontal_bar_chart(df["city"].value_counts().head(6), color=color, label_title="Địa điểm")


def read_status(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}


def show_source(df: pd.DataFrame, all_df: pd.DataFrame, source: str, status: dict) -> None:
    info = SOURCES[source]
    full = all_df[all_df["source"].eq(source)]
    filtered = df[df["source"].eq(source)]
    heading, link = st.columns([5, 1])
    heading.subheader(info["name"])
    link.link_button("Mở website ↗", info["url"], use_container_width=True)
    dates = pd.to_datetime(full["scraped_at"], utc=True, errors="coerce").dropna()
    if not dates.empty:
        st.caption(f"Thu thập gần nhất: {dates.max().tz_convert('Asia/Ho_Chi_Minh'):%d/%m/%Y %H:%M} (giờ Việt Nam) · Đang hiển thị {len(filtered)} / {len(full)} tin đã lưu.")
    attempt = status.get(source, {})
    profile_status = attempt.get("profile_enrichment", {})
    if profile_status.get("status") == "partial":
        st.warning("Đợt bổ sung kỹ năng/phúc lợi chưa đọc được hết các tin do website giới hạn hoặc tin không còn truy cập được. Các mục chưa có thông tin vẫn được giữ để đối chiếu.")
    if attempt.get("status") in {"partial", "error", "empty", "blocked"}:
        st.warning("Lần thu thập gần nhất chưa đầy đủ. Dữ liệu đã lưu vẫn được hiển thị; một số tin có thể thiếu mô tả.")
        with st.expander("Chi tiết lần thu thập gần nhất"):
            st.write(attempt.get("message") or "Chưa thu thập đủ dữ liệu.")
            st.caption(f"Số tin thu được: {attempt.get('collected', 0)} · Có mô tả: {attempt.get('with_description', 0)}")
    if full.empty:
        st.info(f"Chưa có dữ liệu {info['name']}. Chạy crawler cho nguồn này để bổ sung.")
        return
    if filtered.empty:
        st.info("Không có tin phù hợp. Hãy thay đổi bộ lọc bên trái.")
        return
    with st.container(border=True):
        show_metrics(filtered)
    show_charts(filtered, info["color"])
    show_jobs(filtered, source)


def main() -> None:
    args = parse_args()
    st.set_page_config(page_title="IT Job Market · Việt Nam", page_icon="📊", layout="wide")
    st.markdown("<style>[data-testid='stMetricValue']{font-size:1.8rem} .block-container{padding-top:2rem} [data-baseweb='tab']{font-size:1rem;padding:12px 22px} [data-testid='stCaptionContainer']{line-height:1.6}</style>", unsafe_allow_html=True)
    st.caption("IT JOB MARKET / VIỆT NAM")
    st.title("Thị trường tuyển dụng IT")
    st.write("Theo dõi nhu cầu tuyển dụng từ TopCV, ITviec và TopDev trong cùng một không gian.")
    if not args.data.exists():
        st.warning(f"Chưa có file dữ liệu: {args.data}")
        return
    all_df = load_jobs(args.data)
    status_path = args.data.parent / "crawl_status.json"
    if not status_path.exists() and args.data.parent.name == "processed":
        status_path = args.data.parent.parent / "raw/crawl_status.json"
    statuses = read_status(status_path)
    with st.sidebar:
        st.header("Bộ lọc tuyển dụng")
        st.caption("Áp dụng đồng thời cho tất cả các tab.")
        keyword = st.text_input("Vị trí, công ty hoặc kỹ năng", placeholder="Python, Data Analyst…")
        city = st.selectbox("Địa điểm", ["Tất cả"] + sorted(all_df["city"].unique().tolist()))
        model = st.selectbox("Hình thức làm việc", ["Tất cả"] + list(MODEL_NAMES.values()))
        available_languages = sorted({language for items in all_df["_language_list"] for language in items})
        selected_languages = st.multiselect("Ngôn ngữ lập trình", available_languages, placeholder="C++, Python, Java…")
        st.caption("Chọn nhiều ngôn ngữ: hiển thị tin khớp ít nhất một ngôn ngữ.")
        selected_supplementary = st.multiselect("Kỹ năng bổ trợ", sorted({s for items in all_df["_supplementary_list"] for s in items}))
        selected_foreign = st.multiselect("Ngoại ngữ giao tiếp", sorted({s for items in all_df["_foreign_list"] for s in items}))
        english_filter = st.selectbox("Thông tin tiếng Anh", ["Tất cả"] + list(ENGLISH_STATUS_LABELS.values()))
        selected_benefits = st.multiselect("Phúc lợi mong muốn", sorted({s for items in all_df["_benefit_list"] for s in items}))
        benefits_only = st.checkbox("Chỉ tin đã có nội dung phúc lợi")
        st.caption("Trong mỗi nhóm lọc, tin khớp ít nhất một lựa chọn; giữa các nhóm, tin phải khớp đồng thời.")
        disclosed_only = st.checkbox("Chỉ tin có lương công khai")
        st.divider()
        st.caption("Lương cần đăng nhập hoặc thương lượng được để trống khi tính thống kê. Các nguồn có thể được thu thập vào các ngày khác nhau.")
    df = all_df.copy()
    if keyword.strip():
        text = df[["title", "company", "skills", "requirements", "supplementary_skills", "foreign_languages", "english_requirement", "benefits"]].agg(" ".join, axis=1)
        df = df[text.str.contains(keyword.strip(), case=False, regex=False)]
    if city != "Tất cả":
        df = df[df["city"].eq(city)]
    if model != "Tất cả":
        df = df[df["work_model"].map(MODEL_NAMES).eq(model)]
    if selected_languages:
        mask = df["_language_list"].apply(lambda values: bool(set(values) & set(selected_languages))).astype(bool)
        df = df.loc[mask]
    for selected, field in [(selected_supplementary, "_supplementary_list"), (selected_foreign, "_foreign_list"), (selected_benefits, "_benefit_list")]:
        if selected:
            df = df.loc[df[field].apply(lambda values: bool(set(values) & set(selected))).astype(bool)]
    if english_filter != "Tất cả":
        df = df.loc[df["english_status"].map(ENGLISH_STATUS_LABELS).eq(english_filter)]
    if benefits_only:
        df = df.loc[df["benefits"].str.strip().ne("")]
    if disclosed_only:
        df = df[df["salary_midpoint"].notna()]
    overview, *source_tabs, cv_tab = st.tabs(["Tổng quan", "TopCV", "ITviec", "TopDev", "CV → Việc làm phù hợp"])
    with overview:
        with st.container(border=True):
            show_metrics(df)
        st.subheader("Dữ liệu theo website")
        cards = st.columns(3)
        for card, (source, info) in zip(cards, SOURCES.items()):
            data = df[df["source"].eq(source)]
            with card, st.container(border=True):
                st.markdown(f"### {info['name']}")
                st.metric("Tin trong bộ lọc", len(data))
                st.caption(f"{data.loc[data['company'].ne(''), 'company'].nunique()} công ty · {data['description'].str.strip().ne('').sum()} tin có mô tả")
        st.caption("Số lượng phản ánh mẫu đã thu thập, không đại diện toàn bộ thị trường hoặc toàn bộ tin trên mỗi website.")
        with st.expander("So sánh số tin nhắc đến từng ngôn ngữ giữa ba website"):
            language_data = df.explode("_language_list").dropna(subset=["_language_list"])
            if not language_data.empty:
                comparison = pd.crosstab(language_data["_language_list"], language_data["website"])
                comparison = comparison.reindex(columns=[s["name"] for s in SOURCES.values()], fill_value=0)
                st.dataframe(comparison.rename_axis("Ngôn ngữ"), use_container_width=True)
            else:
                st.info("Chưa có ngôn ngữ phù hợp với bộ lọc.")
        show_charts(df, "#6688f5")
        show_jobs(df, "all")
    for tab, source in zip(source_tabs, SOURCES):
        with tab:
            show_source(df, all_df, source, statuses)
    with cv_tab:
        show_cv_matcher(df)


if __name__ == "__main__":
    main()
