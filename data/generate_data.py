"""
Generate a SYNTHETIC multi-sector industrial emissions dataset.

IMPORTANT: this data is simulated, not real company data. It is built to
look like what a messy real-world facility-level emissions export looks like
(inconsistent labels, duplicates, missing values, unit errors) so the SQL
cleaning and analysis steps have real work to do.

Every figure reported in the README is computed from the output of this
script by the SQL in /sql. Nothing is hard-coded to hit a target number.

Usage:  python data/generate_data.py
Output: data/emissions_raw.csv
"""
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 42
rng = np.random.default_rng(SEED)

YEARS = list(range(2015, 2024))  # 2015-2023

# sector: (n_facilities, median annual tCO2e per facility, annual trend,
#          revenue $M per 1,000 tCO2e (lower => more carbon intensive),
#          typical renewable share %)
SECTORS = {
    "Manufacturing":        (380,  45_000, -0.006, 0.9, 18),
    "Power & Utilities":    (110, 130_000, -0.018, 0.5, 30),
    "Mining":               ( 90,  70_000, -0.002, 0.8, 12),
    "Transportation":       (200,  38_000,  0.003, 1.4, 6),
    "Construction":         (150,  16_000, -0.004, 3.0, 9),
    "Agriculture & Food":   (160,  22_000, -0.001, 2.2, 14),
    "Waste Management":     ( 90,  20_000, -0.008, 1.8, 11),
    "Commercial Services":  (220,   3_500, -0.010, 12.0, 35),
}

# region: (countries, emissions multiplier)
REGIONS = {
    "Asia-Pacific":  (["India", "China", "Japan", "Australia", "Indonesia"], 1.25),
    "Europe":        (["Germany", "France", "UK", "Poland", "Spain"], 0.85),
    "North America": (["USA", "Canada", "Mexico"], 1.05),
    "Middle East":   (["Saudi Arabia", "UAE", "Qatar"], 1.20),
    "Latin America": (["Brazil", "Argentina", "Chile"], 0.80),
    "Africa":        (["South Africa", "Nigeria", "Egypt"], 0.75),
}
REGION_WEIGHTS = [0.32, 0.22, 0.20, 0.08, 0.10, 0.08]


def build_facilities() -> pd.DataFrame:
    rows, fid = [], 1
    region_names = list(REGIONS)
    for sector, (n, median, _trend, _rev, _ren) in SECTORS.items():
        for _ in range(n):
            region = rng.choice(region_names, p=REGION_WEIGHTS)
            countries, mult = REGIONS[region]
            rows.append({
                "facility_id": f"F{fid:05d}",
                "sector": sector,
                "region": region,
                "country": rng.choice(countries),
                # facility-level scale: lognormal around the sector median
                "base_emissions": median * mult * rng.lognormal(0, 0.7),
                # facility-level efficiency (higher => more carbon per $ revenue)
                "intensity_factor": rng.lognormal(0, 0.35),
            })
            fid += 1
    return pd.DataFrame(rows)


def build_records(fac: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, f in fac.iterrows():
        n, median, trend, rev_per_k, ren = SECTORS[f.sector]
        for y in YEARS:
            t = y - YEARS[0]
            emissions = f.base_emissions * (1 + trend) ** t * rng.lognormal(0, 0.06)
            energy_mwh = emissions * rng.uniform(1.8, 2.6)
            revenue = (emissions / 1000) * rev_per_k / f.intensity_factor * rng.lognormal(0, 0.10)
            renewable = np.clip(rng.normal(ren + 1.2 * t, 6), 0, 100)
            rows.append({
                "facility_id": f.facility_id,
                "sector": f.sector,
                "region": f.region,
                "country": f.country,
                "year": y,
                "co2e_tonnes": round(emissions, 1),
                "energy_mwh": round(energy_mwh, 1),
                "revenue_musd": round(revenue, 2),
                "renewable_pct": round(renewable, 1),
            })
    return pd.DataFrame(rows)


def make_dirty(df: pd.DataFrame) -> pd.DataFrame:
    """Inject realistic data-quality problems for the SQL cleaning step."""
    df = df.copy()
    n = len(df)

    # 1) inconsistent sector labels (case / whitespace / abbreviations)
    idx = rng.choice(n, int(0.04 * n), replace=False)
    variants = {
        "Manufacturing": ["manufacturing", "MANUFACTURING", " Manufacturing ", "Mfg"],
        "Power & Utilities": ["power & utilities", "Power and Utilities", " Power & Utilities"],
        "Transportation": ["transportation", "Transport", "TRANSPORTATION "],
        "Mining": ["mining", "MINING"],
        "Construction": ["construction", "Construction "],
        "Agriculture & Food": ["agriculture & food", "Agriculture and Food"],
        "Waste Management": ["waste management", "Waste Mgmt"],
        "Commercial Services": ["commercial services", "Commercial Svcs"],
    }
    for i in idx:
        s = df.at[df.index[i], "sector"]
        df.at[df.index[i], "sector"] = rng.choice(variants[s])

    # 2) missing emissions / energy / revenue values
    for col, frac in [("co2e_tonnes", 0.020), ("energy_mwh", 0.010),
                      ("revenue_musd", 0.015), ("renewable_pct", 0.010)]:
        miss = rng.choice(n, int(frac * n), replace=False)
        df.loc[df.index[miss], col] = np.nan

    # 3) unit errors: some emissions reported in kg instead of tonnes (x1000)
    unit = rng.choice(n, int(0.004 * n), replace=False)
    df.loc[df.index[unit], "co2e_tonnes"] = df.loc[df.index[unit], "co2e_tonnes"] * 1000

    # 4) impossible negative values
    neg = rng.choice(n, int(0.002 * n), replace=False)
    df.loc[df.index[neg], "co2e_tonnes"] = -df.loc[df.index[neg], "co2e_tonnes"].abs()

    # 5) renewable share > 100
    over = rng.choice(n, int(0.002 * n), replace=False)
    df.loc[df.index[over], "renewable_pct"] = 100 + rng.uniform(1, 40, len(over))

    # 6) exact duplicate rows
    dup = df.sample(int(0.015 * n), random_state=SEED)
    df = pd.concat([df, dup], ignore_index=True)

    # shuffle and add a record id
    df = df.sample(frac=1, random_state=SEED).reset_index(drop=True)
    df.insert(0, "record_id", range(1, len(df) + 1))
    return df


if __name__ == "__main__":
    out = Path(__file__).parent / "emissions_raw.csv"
    fac = build_facilities()
    clean = build_records(fac)
    raw = make_dirty(clean)
    raw.to_csv(out, index=False)
    print(f"Wrote {len(raw):,} rows ({clean.shape[0]:,} true records + duplicates) to {out}")
    print(f"Facilities: {fac.shape[0]:,} | Years: {YEARS[0]}-{YEARS[-1]}")
