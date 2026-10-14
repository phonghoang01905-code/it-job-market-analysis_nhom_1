from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import streamlit as st


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("data/raw/jobs.csv"))
    return parser.parse_args()


def explode_skills(df: pd.DataFrame) -> pd.DataFrame:
    skills = df.assign(skill=df["skills"].fillna("").str.split(";")).explode("skill")
    skills["skill"] = skills["skill"].str.strip().str.lower()
    return skills[skills["skill"] != ""]


def main() -> None:
    args = parse_args()
    st.set_page_config(page_title="IT Job Market Analysis", layout="wide")
    st.title("Phan tich thi truong tuyen dung IT Viet Nam")

    if not args.data.exists():
        st.warning(f"Chua co file du lieu: {args.data}")
        return

    df = pd.read_csv(args.data)
    df["salary_midpoint"] = df[["salary_min", "salary_max"]].mean(axis=1, skipna=True)

    col1, col2, col3 = st.columns(3)
    col1.metric("So tin tuyen dung", len(df))
    col2.metric("So cong ty", df["company"].nunique())
    col3.metric("Luong TB", f"{df['salary_midpoint'].mean():,.0f} VND")

    st.subheader("Top ky nang")
    skill_counts = explode_skills(df)["skill"].value_counts().head(20)
    st.bar_chart(skill_counts)

    st.subheader("Mo hinh lam viec")
    st.bar_chart(df["work_model"].fillna("Unknown").value_counts())

    st.subheader("Bang du lieu")
    st.dataframe(df, use_container_width=True)


if __name__ == "__main__":
    main()

