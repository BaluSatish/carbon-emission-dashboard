-- 01_schema.sql : raw landing table (loaded as-is from data/emissions_raw.csv)
DROP TABLE IF EXISTS emissions_raw CASCADE;

CREATE TABLE emissions_raw (
    record_id      INT,
    facility_id    TEXT,
    sector         TEXT,
    region         TEXT,
    country        TEXT,
    year           INT,
    co2e_tonnes    NUMERIC,   -- tonnes CO2-equivalent per facility-year
    energy_mwh     NUMERIC,
    revenue_musd   NUMERIC,   -- revenue in million USD
    renewable_pct  NUMERIC    -- share of energy from renewables (0-100)
);
