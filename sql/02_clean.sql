-- 02_clean.sql : build emissions_clean from emissions_raw
-- Steps (each is a CTE below):
--   std        1. standardise sector labels (case, whitespace, abbreviations)
--   dedup      2. remove exact duplicate facility-years (ROW_NUMBER)
--   fac_median 3. robust per-facility median, used to detect/repair bad values
--   flagged    4. flag missing, negative and unit-error (kg reported as t) values
--   sector_ren 5. sector-year median renewable share for repairing bad values
DROP TABLE IF EXISTS emissions_clean CASCADE;

CREATE TABLE emissions_clean AS
WITH std AS (
    SELECT record_id, facility_id,
           CASE
               WHEN lower(trim(sector)) IN ('manufacturing', 'mfg')                      THEN 'Manufacturing'
               WHEN lower(trim(sector)) IN ('power & utilities', 'power and utilities')  THEN 'Power & Utilities'
               WHEN lower(trim(sector)) IN ('transportation', 'transport')               THEN 'Transportation'
               WHEN lower(trim(sector)) = 'mining'                                       THEN 'Mining'
               WHEN lower(trim(sector)) = 'construction'                                 THEN 'Construction'
               WHEN lower(trim(sector)) IN ('agriculture & food', 'agriculture and food') THEN 'Agriculture & Food'
               WHEN lower(trim(sector)) IN ('waste management', 'waste mgmt')            THEN 'Waste Management'
               WHEN lower(trim(sector)) IN ('commercial services', 'commercial svcs')   THEN 'Commercial Services'
               ELSE 'Unknown'
           END AS sector,
           region, country, year,
           co2e_tonnes, energy_mwh, revenue_musd, renewable_pct
    FROM emissions_raw
),
dedup AS (
    SELECT *,
           ROW_NUMBER() OVER (PARTITION BY facility_id, year ORDER BY record_id) AS rn
    FROM std
),
uniq AS (
    SELECT * FROM dedup WHERE rn = 1
),
fac_median AS (
    SELECT facility_id,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY co2e_tonnes) AS med_co2e
    FROM uniq
    WHERE co2e_tonnes > 0
    GROUP BY facility_id
),
flagged AS (
    SELECT u.*, m.med_co2e,
           CASE
               WHEN u.co2e_tonnes IS NULL              THEN 'missing_imputed'
               WHEN u.co2e_tonnes <= 0                 THEN 'negative_imputed'
               WHEN u.co2e_tonnes > 20 * m.med_co2e    THEN 'unit_error_fixed'
               ELSE 'ok'
           END AS co2e_flag
    FROM uniq u
    JOIN fac_median m USING (facility_id)
),
sector_ren AS (
    SELECT sector, year,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY renewable_pct) AS med_ren
    FROM uniq
    WHERE renewable_pct BETWEEN 0 AND 100
    GROUP BY sector, year
)
SELECT f.record_id, f.facility_id, f.sector, f.region, f.country, f.year,
       (CASE f.co2e_flag
            WHEN 'ok'               THEN f.co2e_tonnes
            WHEN 'unit_error_fixed' THEN f.co2e_tonnes / 1000
            ELSE f.med_co2e::NUMERIC             -- missing / negative -> facility median
        END)::NUMERIC(14,1)         AS co2e_tonnes,
       f.co2e_flag,
       f.energy_mwh,
       f.revenue_musd,
       COALESCE(CASE WHEN f.renewable_pct BETWEEN 0 AND 100 THEN f.renewable_pct END,
                s.med_ren::NUMERIC)::NUMERIC(5,1) AS renewable_pct
FROM flagged f
LEFT JOIN sector_ren s USING (sector, year);

ALTER TABLE emissions_clean ADD PRIMARY KEY (facility_id, year);
CREATE INDEX idx_clean_sector_year ON emissions_clean (sector, year);

-- data-quality audit view (exported to results/data_quality.csv)
CREATE OR REPLACE VIEW v_data_quality AS
SELECT 'raw rows loaded'                          AS check_name, COUNT(*)::BIGINT AS n FROM emissions_raw
UNION ALL SELECT 'duplicate rows removed',
       (SELECT COUNT(*) FROM emissions_raw) - (SELECT COUNT(*) FROM emissions_clean)
UNION ALL SELECT 'clean rows',                    COUNT(*) FROM emissions_clean
UNION ALL SELECT 'co2e missing -> imputed',       COUNT(*) FROM emissions_clean WHERE co2e_flag = 'missing_imputed'
UNION ALL SELECT 'co2e negative -> imputed',      COUNT(*) FROM emissions_clean WHERE co2e_flag = 'negative_imputed'
UNION ALL SELECT 'co2e unit error (kg) -> fixed', COUNT(*) FROM emissions_clean WHERE co2e_flag = 'unit_error_fixed'
UNION ALL SELECT 'unknown sector labels',         COUNT(*) FROM emissions_clean WHERE sector = 'Unknown';
