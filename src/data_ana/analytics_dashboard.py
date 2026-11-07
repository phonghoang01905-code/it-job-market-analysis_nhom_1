"""EDA pages shared with the report definitions."""
from __future__ import annotations

import altair as alt
import hashlib
import pandas as pd
import streamlit as st

from data_ana.analytics import prepare_jobs, summary, time_summary, skill_timeseries, skill_changes, cluster_jobs
from data_ana.salary_dashboard import show_salary_analysis

PAGES = ["Tổng quan & website", "Kỹ năng & xu hướng", "Lương", "Công ty & vị trí", "Phân cụm kỹ năng"]


def bar(table: pd.DataFrame, dimension: str, metric="job_count", title="Số tin"):
    if table.empty:
        st.info("Chưa đủ dữ liệu cho biểu đồ này.")
        return
    chart = alt.Chart(table.head(15)).mark_bar(cornerRadiusEnd=4, color="#6688f5").encode(
        y=alt.Y(f"{dimension}:N", sort="-x", title=None, axis=alt.Axis(labelLimit=240)),
        x=alt.X(f"{metric}:Q", title=title),
        tooltip=[alt.Tooltip(f"{dimension}:N", title="Tên đầy đủ"), alt.Tooltip(f"{metric}:Q", title=title, format=",.2f")])
    st.altair_chart(chart.properties(height=max(180, min(len(table), 15)*32)), use_container_width=True)


def download(table, key):
    st.dataframe(table, hide_index=True, use_container_width=True)
    st.download_button("Tải bảng CSV", table.to_csv(index=False).encode("utf-8-sig"), file_name=f"{key}.csv", mime="text/csv", key=f"eda_download_{key}")


def show_analysis_page(frame: pd.DataFrame, page: str):
    st.subheader(page)
    df = prepare_jobs(frame)
    if df.empty:
        st.info("Không có tin phù hợp với bộ lọc. Hãy nới bộ lọc bên trái.")
        return
    if page == "Kỹ năng & xu hướng":
        skills = summary(df, "skill")
        left, right = st.columns([1.3, 1])
        with left:
            bar(skills, "skill")
        with right:
            st.metric("Tin có ngày đăng chính xác", f"{df._date_posted.count()} / {len(df)}")
            st.caption("Mỗi kỹ năng tối đa một lượt/tin; một tin có thể nhắc nhiều kỹ năng. Tổng tỷ trọng kỹ năng có thể vượt 100%.")
            download(skills[["skill", "job_count", "share_pct"]], "skills")
        basis_label = st.radio("Mốc thời gian phân tích", ["Ngày đăng chính xác", "Ngày thu thập đã lưu"], horizontal=True, key="eda_basis")
        basis = "posted" if basis_label == "Ngày đăng chính xác" else "observed"
        frequency = st.radio("Gộp theo", ["Tuần", "Tháng"], horizontal=True, key="eda_frequency")
        freq = "week" if frequency == "Tuần" else "month"
        totals = time_summary(df, basis, freq)
        if totals.empty:
            st.info("Không có ngày hợp lệ cho mốc thời gian đã chọn; không tự thay bằng mốc khác.")
            return
        st.warning("Biểu đồ mô tả phân bố thời gian của mẫu đã thu thập. Tuần/tháng đầu hoặc cuối có thể chưa đầy đủ; số 0 có thể do thiếu quan sát. Chưa đủ lịch sử để kết luận tăng/giảm nhu cầu của thị trường.")
        chart = alt.Chart(totals).mark_line(point=True, color="#16a673").encode(
            x=alt.X("period:T", title="Đầu kỳ (tuần bắt đầu thứ Hai)"), y=alt.Y("job_count:Q", title="Số tin"),
            tooltip=[alt.Tooltip("period:T", title="Đầu kỳ", format="%d/%m/%Y"), alt.Tooltip("job_count:Q", title="Số tin")])
        st.altair_chart(chart, use_container_width=True)
        series = skill_timeseries(df, basis, freq)
        choices = sorted(series.skill.unique())
        default = [s for s in skills.skill.head(5) if s in choices]
        selected = st.multiselect("Kỹ năng xem xu hướng", choices, default=default, key="eda_trend_skills")
        data = series[series.skill.isin(selected)]
        if not data.empty:
            lines = alt.Chart(data).mark_line(point=True).encode(x=alt.X("period:T", title="Đầu kỳ"),
                y=alt.Y("share_pct:Q", title="Tỷ trọng tin có kỹ năng (%)"), color=alt.Color("skill:N", title="Kỹ năng"),
                tooltip=["skill:N", alt.Tooltip("period:T", format="%d/%m/%Y"), "job_count:Q", "period_jobs:Q", alt.Tooltip("share_pct:Q", format=".2f")])
            st.altair_chart(lines, use_container_width=True)
        st.markdown("**Thay đổi giữa hai tuần cuối có trong mẫu**")
        st.caption("share_change_pp: chênh lệch điểm phần trăm tỷ trọng. growth_pct trống khi số tin tuần trước bằng 0; không báo tăng vô hạn.")
        download(skill_changes(df, basis), "skill_changes")
    elif page == "Lương":
        show_salary_analysis(frame)
    elif page == "Công ty & vị trí":
        a, b = st.columns(2)
        with a:
            st.markdown("**Công ty có nhiều tin**")
            bar(summary(df, "company"), "company")
        with b:
            st.markdown("**Thành phố**")
            bar(summary(df, "city"), "city")
        st.caption("Tin nhiều thành phố được tính tại từng nơi nên tổng theo city có thể lớn hơn tổng tin. Một tin không mặc nhiên là một chỗ tuyển; không gộp trùng giữa các website.")
        st.markdown("**Vị trí nổi bật theo tiêu đề gốc**")
        download(summary(df, "title")[["title", "job_count", "salary_count", "median_salary"]], "positions")
    elif page == "Phân cụm kỹ năng":
        st.write("Gom các tin có bộ kỹ năng tương tự bằng KMeans. Nhãn cụm dùng các kỹ năng phổ biến để giải thích, không suy ra cấp bậc hay cơ hội trúng tuyển.")
        st.caption("Multi-hot → TF-IDF/L2 → KMeans; chọn k=2..6 theo silhouette cosine. random_state=42, n_init=20; tin không có kỹ năng không được ép vào cụm.")
        fingerprint = hashlib.sha256(df[["_key", "_skills", "salary_midpoint", "title", "company"]].to_json().encode()).hexdigest()
        if st.button("Phân cụm bộ dữ liệu đang lọc", key="eda_cluster_run"):
            assignments, groups, info = cluster_jobs(df)
            st.session_state["eda_cluster_result"] = (fingerprint, assignments, groups, info)
        saved = st.session_state.get("eda_cluster_result")
        if saved and saved[0] == fingerprint:
            _, assignments, groups, info = saved
            if info["status"] != "ok":
                st.info(info.get("reason", "Không đủ dữ liệu phân cụm."))
                return
            st.success(f"{info['k']} cụm · silhouette cosine {info['silhouette_cosine']:.3f} · {info['excluded']} tin chưa phân cụm")
            download(groups, "clusters")
            download(assignments.drop(columns="_key"), "cluster_jobs")
