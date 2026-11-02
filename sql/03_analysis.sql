-- 03_analysis.sql : analysis views (CTEs, window functions, subqueries)
-- Each view is exported to results/*.csv by src/run_pipeline.py

-- 1. Sector share of total emissions (all years, and latest year) --------------
CREATE OR REPLACE VIEW v_sector_share AS
WITH totals AS (
    SELECT sector,
           SUM(co2e_tonnes)                                  AS total_co2e,
           SUM(co2e_tonnes) FILTER (WHERE year = 2023)       AS co2e_2023
    FROM emissions_clean
    GROUP BY sector
)
SELECT sector,
       ROUND(total_co2e)                                              AS total_co2e_tonnes,
       ROUND(100.0 * total_co2e / SUM(total_co2e) OVER (), 2)         AS share_pct_all_years,
       ROUND(co2e_2023)                                               AS co2e_2023_tonnes,
       ROUND(100.0 * co2e_2023 / SUM(co2e_2023) OVER (), 2)           AS share_pct_2023,
       RANK() OVER (ORDER BY total_co2e DESC)                         AS rank_all_years
FROM totals
ORDER BY total_co2e DESC;

-- 2. Yearly trend per sector: YoY change (LAG) and 3-year rolling average ------
CREATE OR REPLACE VIEW v_sector_trend AS
WITH yearly AS (
    SELECT sector, year, SUM(co2e_tonnes) AS co2e
    FROM emissions_clean
    GROUP BY sector, year
)
SELECT sector, year,
       ROUND(co2e)                                                         AS co2e_tonnes,
       ROUND(100.0 * (co2e - LAG(co2e) OVER w) / NULLIF(LAG(co2e) OVER w, 0), 2) AS yoy_pct,
       ROUND(AVG(co2e) OVER (PARTITION BY sector ORDER BY year
                             ROWS BETWEEN 2 PRECEDING AND CURRENT ROW))    AS rolling_3yr_avg,
       ROUND(100.0 * (co2e - FIRST_VALUE(co2e) OVER w) / NULLIF(FIRST_VALUE(co2e) OVER w, 0), 2)
                                                                           AS pct_vs_2015
FROM yearly
WINDOW w AS (PARTITION BY sector ORDER BY year)
ORDER BY sector, year;

-- 3. Region x sector emissions, ranked within each sector ----------------------
CREATE OR REPLACE VIEW v_region_sector AS
WITH agg AS (
    SELECT region, sector, SUM(co2e_tonnes) AS co2e
    FROM emissions_clean
    WHERE year = 2023
    GROUP BY region, sector
)
SELECT region, sector,
       ROUND(co2e)                                                       AS co2e_2023_tonnes,
       ROUND(100.0 * co2e / SUM(co2e) OVER (PARTITION BY sector), 2)     AS pct_of_sector,
       DENSE_RANK() OVER (PARTITION BY sector ORDER BY co2e DESC)        AS region_rank_in_sector
FROM agg
ORDER BY sector, region_rank_in_sector;

-- 4. Facility concentration (Pareto) for 2023 ----------------------------------
CREATE OR REPLACE VIEW v_facility_pareto AS
WITH f AS (
    SELECT facility_id, sector, region, co2e_tonnes
    FROM emissions_clean
    WHERE year = 2023
)
SELECT facility_id, sector, region,
       ROUND(co2e_tonnes)                                             AS co2e_2023_tonnes,
       ROW_NUMBER() OVER (ORDER BY co2e_tonnes DESC)                  AS facility_rank,
       NTILE(10) OVER (ORDER BY co2e_tonnes DESC)                     AS decile,
       ROUND(100.0 * SUM(co2e_tonnes) OVER (ORDER BY co2e_tonnes DESC
                      ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
                    / SUM(co2e_tonnes) OVER (), 2)                    AS cumulative_share_pct
FROM f
ORDER BY facility_rank;

-- 5. Carbon intensity (tCO2e per $M revenue) by sector and year ----------------
CREATE OR REPLACE VIEW v_intensity AS
SELECT sector, year,
       ROUND(SUM(co2e_tonnes) / NULLIF(SUM(revenue_musd), 0), 1)       AS tco2e_per_musd,
       ROUND(AVG(renewable_pct), 1)                                    AS avg_renewable_pct
FROM emissions_clean
WHERE revenue_musd IS NOT NULL
GROUP BY sector, year
ORDER BY sector, year;

-- 6. Reduction roadmap (2023 baseline) -----------------------------------------
-- Assumptions live in one place so they are easy to change and to challenge.
DROP TABLE IF EXISTS roadmap_params;
CREATE TABLE roadmap_params (param TEXT PRIMARY KEY, value NUMERIC, note TEXT);
INSERT INTO roadmap_params VALUES
  ('gap_closure_share',    0.50, 'Lever A: facilities above their sector-median carbon intensity close this share of the gap to the median'),
  ('renewable_floor_pct',  25,   'Lever B: facilities below this renewable share are lifted to it'),
  ('energy_emissions_share', 0.50, 'Lever B: share of a facility''s emissions that scales with its non-renewable energy mix');

CREATE OR REPLACE VIEW v_roadmap_facility AS
WITH base AS (
    SELECT facility_id, sector, region, co2e_tonnes, revenue_musd, renewable_pct,
           co2e_tonnes / NULLIF(revenue_musd, 0) AS intensity
    FROM emissions_clean
    WHERE year = 2023
),
sector_med AS (
    SELECT sector,
           (percentile_cont(0.5) WITHIN GROUP (ORDER BY intensity))::NUMERIC AS med_intensity
    FROM base
    WHERE intensity IS NOT NULL
    GROUP BY sector
),
lever_a AS (
    SELECT b.*, m.med_intensity,
           CASE WHEN b.intensity > m.med_intensity
                THEN b.co2e_tonnes * (1 - m.med_intensity / b.intensity)
                     * (SELECT value FROM roadmap_params WHERE param = 'gap_closure_share')
                ELSE 0 END AS reduction_a
    FROM base b
    JOIN sector_med m USING (sector)
)
SELECT facility_id, sector, region, co2e_tonnes AS baseline_2023,
       reduction_a,
       GREATEST((SELECT value FROM roadmap_params WHERE param = 'renewable_floor_pct') - renewable_pct, 0)
         / 100.0
         * (SELECT value FROM roadmap_params WHERE param = 'energy_emissions_share')
         * (co2e_tonnes - reduction_a)                                   AS reduction_b
FROM lever_a;

CREATE OR REPLACE VIEW v_roadmap_summary AS
WITH s AS (
    SELECT sector,
           SUM(baseline_2023) AS baseline,
           SUM(reduction_a)   AS lever_a,
           SUM(reduction_b)   AS lever_b
    FROM v_roadmap_facility
    GROUP BY sector
)
SELECT sector,
       ROUND(baseline)                                   AS baseline_2023_tonnes,
       ROUND(lever_a)                                    AS lever_a_efficiency_tonnes,
       ROUND(lever_b)                                    AS lever_b_renewables_tonnes,
       ROUND(lever_a + lever_b)                          AS total_reduction_tonnes,
       ROUND(100.0 * (lever_a + lever_b) / baseline, 2)  AS reduction_pct_of_sector
FROM s
UNION ALL
SELECT 'ALL SECTORS',
       ROUND(SUM(baseline)), ROUND(SUM(lever_a)), ROUND(SUM(lever_b)),
       ROUND(SUM(lever_a + lever_b)),
       ROUND(100.0 * SUM(lever_a + lever_b) / SUM(baseline), 2)
FROM s
ORDER BY total_reduction_tonnes DESC;

-- 7. Headline KPIs ---------------------------------------------------------------
CREATE OR REPLACE VIEW v_kpis AS
SELECT
  (SELECT COUNT(*) FROM emissions_clean)                                         AS clean_records,
  (SELECT COUNT(DISTINCT facility_id) FROM emissions_clean)                      AS facilities,
  (SELECT ROUND(SUM(co2e_tonnes)) FROM emissions_clean WHERE year = 2015)        AS co2e_2015,
  (SELECT ROUND(SUM(co2e_tonnes)) FROM emissions_clean WHERE year = 2023)        AS co2e_2023,
  (SELECT ROUND(100.0 * (SUM(co2e_tonnes) FILTER (WHERE year = 2023)
                       - SUM(co2e_tonnes) FILTER (WHERE year = 2015))
                      / SUM(co2e_tonnes) FILTER (WHERE year = 2015), 2)
     FROM emissions_clean)                                                       AS change_pct_2015_2023;
