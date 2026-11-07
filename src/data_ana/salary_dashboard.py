"""Salary views with visible provenance for observed, estimated and NaN rows."""
from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from data_ana.analytics import prepare_jobs, summary, explode
from data_ana.salary import monthly_salary_label
from data_ana.salary_estimation import GROUP_LABELS, add_salary_estimates

COLORS = {"A": "#18b99a", "B": "#f0ad4e", "C": "#94a3b8"}


def show_salary_detail(row) -> None:
    st.markdown("**Mức lương & căn cứ đối chiếu**")
    group = row.get("salary_group", "C")
    st.markdown(f'<span style="display:inline-block;color:{COLORS[group]};border:1px solid {COLORS[group]};border-radius:20px;padding:4px 12px;font-size:13px">{GROUP_LABELS[group]}</span>', unsafe_allow_html=True)
    st.markdown(f"### {row.get('salary_display', 'NaN · Chưa đủ dữ liệu')}")
    st.caption(row.get("salary_estimate_reason", ""))
    if group == "A":
        st.write("VND/tháng: " + row.get("salary_vnd", ""))
        st.caption(row.get("salary_observed_evidence", ""))
    elif group == "B":
        st.caption(f"{row['salary_role']} · {row['salary_experience_band']} · {row.get('location', '')} · {row['salary_peer_count']} tin đối chiếu")
        peers = pd.DataFrame(row["salary_peers"])
        if peers.empty:
            return
        peers["Lương công khai / tháng"] = [monthly_salary_label(a, b) for a, b in zip(peers.salary_min, peers.salary_max)]
        peers["Thu thập"] = pd.to_datetime(peers.scraped_at, utc=True, errors="coerce").dt.strftime("%d/%m/%Y")
        table = peers.rename(columns={"title": "Vị trí", "company": "Công ty", "source": "Website", "similarity": "Tương đồng (%)", "url": "Tin gốc"})
        st.dataframe(table[["Vị trí", "Lương công khai / tháng", "Công ty", "Website", "Tương đồng (%)", "Thu thập", "Tin gốc"]], hide_index=True, use_container_width=True,
            column_config={"Tin gốc": st.column_config.LinkColumn(display_text="Mở tin"), "Vị trí": st.column_config.TextColumn(width="medium"), "Lương công khai / tháng": st.column_config.TextColumn(width="large")})
        values = [dict(label="≈ Ước tính cho tin này", low=row["salary_estimate_min"]/1e6, high=row["salary_estimate_max"]/1e6, kind="Ước tính")]
        values += [dict(label=f"{p['company']} · {p['title']}", low=p["salary_min"]/1e6, high=p["salary_max"]/1e6, kind="Công khai") for p in row["salary_peers"]]
        data = pd.DataFrame(values)
        chart = alt.Chart(data).mark_rule(strokeWidth=8, opacity=.85).encode(
            y=alt.Y("label:N", title=None, sort=data.label.tolist(), axis=alt.Axis(labelLimit=260)),
            x=alt.X("low:Q", title="Khoảng lương (triệu VND/tháng)", scale=alt.Scale(zero=True)), x2="high:Q",
            color=alt.Color("kind:N", title=None, scale=alt.Scale(domain=["Công khai", "Ước tính"], range=[COLORS["A"], COLORS["B"]])),
            tooltip=[alt.Tooltip("label:N", title="Tin"), alt.Tooltip("kind:N", title="Nguồn"), alt.Tooltip("low:Q", title="Từ (triệu)", format=".1f"), alt.Tooltip("high:Q", title="Đến (triệu)", format=".1f")])
        st.altair_chart(chart.properties(height=max(180, len(data)*38)), use_container_width=True)


def show_salary_analysis(frame: pd.DataFrame) -> None:
    if "salary_group" not in frame:
        frame = add_salary_estimates(frame)
    st.write("So sánh lương với nguồn dữ liệu rõ ràng")
    cards = st.columns(3)
    subtitles = {"A": "Giữ mức lương nhà tuyển dụng công khai.", "B": "≈ Từ ít nhất 3 tin tương tự / 2 công ty.", "C": "NaN · Không tự gán khi thiếu căn cứ."}
    for card, group in zip(cards, GROUP_LABELS):
        with card, st.container(border=True):
            st.markdown(f'<span style="color:{COLORS[group]};font-weight:600">{GROUP_LABELS[group]}</span>', unsafe_allow_html=True)
            st.metric("Số tin", int(frame.salary_group.eq(group).sum()), label_visibility="collapsed")
            st.caption(subtitles[group])
    mode = st.radio("Dữ liệu dùng để so sánh lương", ["Công khai + ước tính", "Chỉ lương công khai"], horizontal=True, key="salary_comparison_mode")
    compare = frame.copy()
    compare["salary_min"] = compare.salary_comparison_min
    compare["salary_max"] = compare.salary_comparison_max
    if mode == "Chỉ lương công khai":
        compare.loc[compare.salary_group.ne("A"), ["salary_min", "salary_max"]] = float("nan")
    df = prepare_jobs(compare)
    st.caption("Các trường lương gốc được giữ nguyên. Ước tính B dùng lại mẫu công khai A, nên A+B không phải số quan sát lương độc lập. Nhóm C và tin chỉ có trần/sàn không dùng tính midpoint.")
    a, b = st.columns(2)
    median = df.salary_midpoint.median()
    a.metric("Trung vị midpoint · " + ("A+B" if mode.startswith("Công khai +") else "A"), f"{median/1e6:.1f} triệu/tháng" if pd.notna(median) else "NaN")
    b.metric("Tin đủ khoảng lương để so sánh", f"{df.salary_midpoint.count()} / {len(df)}")
    dimension = st.selectbox("Phân nhóm lương", ["skill", "level", "city"], format_func=lambda v: {"skill": "Kỹ năng", "level": "Cấp bậc", "city": "Thành phố"}[v], key="eda_salary_dimension")
    minimum = st.number_input("Số tin có lương tối thiểu trong nhóm", 1, 100, 1, key="eda_salary_minimum")
    data = explode(df, dimension)
    included = data.loc[data.salary_midpoint.notna()].copy()
    included["Loại lương"] = included.salary_group.map(GROUP_LABELS)
    chart_data = included.groupby([dimension, "Loại lương"], as_index=False).agg(median_salary=("salary_midpoint", "median"), count=("_key", "nunique"))
    chart_data = chart_data.loc[chart_data["count"].ge(minimum)].copy()
    chart_data["million"] = chart_data.median_salary/1e6
    if chart_data.empty:
        st.info("Chưa có nhóm đủ số mẫu đã chọn. Hãy giảm ngưỡng hoặc bổ sung thêm tin có lương công khai.")
    else:
        top = chart_data.groupby(dimension).million.max().nlargest(15).index
        chart_data = chart_data.loc[chart_data[dimension].isin(top)]
        chart = alt.Chart(chart_data).mark_bar(cornerRadiusEnd=4).encode(
            y=alt.Y(f"{dimension}:N", title=None, sort="-x", axis=alt.Axis(labelLimit=240)),
            yOffset=alt.YOffset("Loại lương:N"), x=alt.X("million:Q", title="Trung vị midpoint (triệu VND/tháng)"),
            color=alt.Color("Loại lương:N", scale=alt.Scale(domain=[GROUP_LABELS["A"], GROUP_LABELS["B"]], range=[COLORS["A"], COLORS["B"]]), title=None),
            tooltip=[alt.Tooltip(f"{dimension}:N", title="Nhóm"), "Loại lương:N", alt.Tooltip("million:Q", title="Triệu/tháng", format=".1f"), alt.Tooltip("count:Q", title="Số tin")])
        st.altair_chart(chart.properties(height=max(220, len(top)*52)), use_container_width=True)
    table = summary(df, dimension)
    counts = included.groupby([dimension, "salary_group"])._key.nunique().unstack(fill_value=0).reindex(columns=["A", "B"], fill_value=0).rename(columns={"A": "observed_count", "B": "estimated_count"}).reset_index()
    table = table.merge(counts, on=dimension, how="left")
    table[["observed_count", "estimated_count"]] = table[["observed_count", "estimated_count"]].fillna(0).astype(int)
    display = table.copy()
    pay_columns = {"median_salary": "Trung vị (triệu)", "avg_salary": "Trung bình (triệu)", "p25_salary": "P25 (triệu)", "p75_salary": "P75 (triệu)"}
    for column in pay_columns:
        display[column] = (display[column]/1e6).round(1)
    display = display.rename(columns={dimension: {"skill": "Kỹ năng", "level": "Cấp bậc", "city": "Thành phố"}[dimension],
        "job_count": "Tổng tin", "salary_count": "Tin có lương", "observed_count": "A · Công khai", "estimated_count": "B · Ước tính", "share_pct": "Tỷ trọng (%)", **pay_columns})
    st.dataframe(display, hide_index=True, use_container_width=True)
    st.caption("Số mẫu được hiển thị trong tooltip và bảng. Nhóm ít mẫu chỉ có giá trị tham khảo; lương B là kết quả suy từ mẫu A.")
    st.download_button("Tải bảng so sánh lương", table.to_csv(index=False).encode("utf-8-sig"), file_name=f"salary_{dimension}.csv", mime="text/csv", key="salary_summary_download")
    st.markdown("**Kiểm tra mức lương của từng tin**")
    choices = frame.index.tolist()
    selected = st.selectbox("Chọn tin để xem căn cứ lương", choices, format_func=lambda i: f"{frame.loc[i, 'title']} · {frame.loc[i, 'company']}", key="salary_inspect")
    if selected is not None:
        with st.container(border=True):
            show_salary_detail(frame.loc[selected])
    with st.expander("Phương pháp ước tính & điều kiện giữ NaN"):
        st.write("Đối chiếu trong toàn bộ dữ liệu trước khi lọc dashboard: cùng nhóm vị trí, cùng thành phố cụ thể, cùng nhóm kinh nghiệm; chênh lệch tối đa 2 năm nếu cả hai tin nêu số năm. Kỹ năng giao nhau theo Jaccard tối thiểu 0,2.")
        st.write("Chọn tối đa 7 tin gần nhất theo kỹ năng (80%) và từ trong tiêu đề (20%). Cần ít nhất 3 tin / 2 công ty, tối đa 2 tin mỗi công ty; gộp tin trùng cùng công ty/tiêu đề/địa điểm/cấp bậc. Chỉ dùng khoảng lương công khai đầy đủ, thu thập trong 180 ngày; không lấy tin đã ước tính làm mẫu.")
        st.write("Ước tính bằng trung vị từng đầu khoảng lương. Giữ NaN nếu thiếu thông tin, ít tin so sánh hoặc lương nhóm quá phân tán (IQR midpoint/trung vị > 0,6 hoặc midpoint cao nhất/thấp nhất > 3). Khoảng này mô tả nhóm đối chiếu, không phải khoảng tin cậy hay cam kết của nhà tuyển dụng.")
