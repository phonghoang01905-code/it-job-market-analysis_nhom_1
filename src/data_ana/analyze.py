from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns


def load_jobs(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    if "skills" in df.columns:
        df["skills"] = df["skills"].fillna("")
    return df


def explode_skills(df: pd.DataFrame) -> pd.DataFrame:
    skills = df.assign(skill=df["skills"].str.split(";")).explode("skill")
    skills["skill"] = skills["skill"].fillna("").str.strip().str.lower()
    return skills[skills["skill"] != ""]


def salary_midpoint(df: pd.DataFrame) -> pd.Series:
    return df[["salary_min", "salary_max"]].mean(axis=1, skipna=True)


def write_tables(df: pd.DataFrame, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    skill_df = explode_skills(df)
    skill_summary = skill_df.groupby("skill", as_index=False).agg(
        job_count=("title", "count"),
        avg_salary=("salary_midpoint", "mean"),
    )
    skill_summary.sort_values(["job_count", "avg_salary"], ascending=[False, False]).to_csv(
        out_dir / "skills_summary.csv", index=False, encoding="utf-8-sig"
    )

    df.groupby("company", as_index=False).size().sort_values("size", ascending=False).rename(
        columns={"size": "job_count"}
    ).to_csv(out_dir / "companies_summary.csv", index=False, encoding="utf-8-sig")

    df.groupby(["location", "level"], as_index=False).agg(
        job_count=("title", "count"),
        avg_salary=("salary_midpoint", "mean"),
        min_salary=("salary_min", "min"),
        max_salary=("salary_max", "max"),
    ).to_csv(out_dir / "salary_by_location_level.csv", index=False, encoding="utf-8-sig")

    df.groupby("work_model", as_index=False).size().rename(columns={"size": "job_count"}).to_csv(
        out_dir / "work_model_summary.csv", index=False, encoding="utf-8-sig"
    )


def write_charts(df: pd.DataFrame, out_dir: Path) -> None:
    sns.set_theme(style="whitegrid")
    skill_df = explode_skills(df)
    top_skills = skill_df["skill"].value_counts().head(15).sort_values()

    if not top_skills.empty:
        plt.figure(figsize=(10, 6))
        top_skills.plot(kind="barh", color="#2f80ed")
        plt.title("Top ky nang theo so luong tin tuyen dung")
        plt.xlabel("So tin tuyen dung")
        plt.ylabel("Ky nang")
        plt.tight_layout()
        plt.savefig(out_dir / "top_skills.png", dpi=160)
        plt.close()

    work_model = df["work_model"].fillna("Unknown").value_counts()
    if not work_model.empty:
        plt.figure(figsize=(7, 5))
        work_model.plot(kind="bar", color="#27ae60")
        plt.title("Phan bo mo hinh lam viec")
        plt.xlabel("Mo hinh")
        plt.ylabel("So tin")
        plt.tight_layout()
        plt.savefig(out_dir / "work_model.png", dpi=160)
        plt.close()


def analyze(input_path: Path, out_dir: Path) -> None:
    df = load_jobs(input_path)
    df["salary_midpoint"] = salary_midpoint(df)
    write_tables(df, out_dir)
    write_charts(df, out_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze IT job market data.")
    parser.add_argument("--input", type=Path, default=Path("data/raw/jobs.csv"))
    parser.add_argument("--out-dir", type=Path, default=Path("outputs"))
    args = parser.parse_args()

    analyze(args.input, args.out_dir)
    print(f"Analysis outputs saved to {args.out_dir}")


if __name__ == "__main__":
    main()

