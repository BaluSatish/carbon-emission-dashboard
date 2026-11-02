"""
End-to-end pipeline: load CSV -> PostgreSQL -> clean -> analyse -> export CSVs -> charts.

Requires: PostgreSQL (psql CLI on PATH), Python 3.9+, pandas, matplotlib.
Connection uses the standard libpq env vars (PGHOST, PGPORT, PGUSER, PGDATABASE, PGPASSWORD).

    createdb emissions
    export PGDATABASE=emissions
    python data/generate_data.py
    python src/run_pipeline.py
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SQL = ROOT / "sql"
RESULTS = ROOT / "results"
RESULTS.mkdir(exist_ok=True)

EXPORTS = {
    "kpis": "v_kpis",
    "data_quality": "v_data_quality",
    "sector_share": "v_sector_share",
    "sector_trend": "v_sector_trend",
    "region_sector": "v_region_sector",
    "facility_pareto": "v_facility_pareto",
    "intensity": "v_intensity",
    "roadmap_summary": "v_roadmap_summary",
    "roadmap_facility": "v_roadmap_facility",
}


def psql(*args: str) -> None:
    cmd = ["psql", "-v", "ON_ERROR_STOP=1", "-q", *args]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        sys.exit(f"psql failed:\n{res.stderr}")


def main() -> None:
    psql("-f", str(SQL / "01_schema.sql"))
    psql("-c", f"\\copy emissions_raw FROM '{ROOT / 'data' / 'emissions_raw.csv'}' CSV HEADER")
    psql("-f", str(SQL / "02_clean.sql"))
    psql("-f", str(SQL / "03_analysis.sql"))
    for name, view in EXPORTS.items():
        psql("-c", f"\\copy (SELECT * FROM {view}) TO '{RESULTS / (name + '.csv')}' CSV HEADER")
        print(f"exported results/{name}.csv")
    # facility-year level clean data, handy for Power BI
    psql("-c", f"\\copy (SELECT * FROM emissions_clean ORDER BY facility_id, year) "
               f"TO '{RESULTS / 'emissions_clean.csv'}' CSV HEADER")
    print("exported results/emissions_clean.csv")
    print("Pipeline complete. Now run: python src/make_charts.py")


if __name__ == "__main__":
    main()
