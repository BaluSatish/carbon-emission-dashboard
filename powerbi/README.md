# Power BI dashboard - build guide

The `.pbix` file is not included: Power BI Desktop is Windows-only and has to be
authored by hand. `images/dashboard_preview.png` shows the intended layout.
This guide gets you from the exported CSVs to a working report in about 30 minutes.

## 1. Load data
Home > Get data > Text/CSV, then load from `results/`:
`emissions_clean.csv` (fact table), `sector_share.csv`, `sector_trend.csv`,
`roadmap_summary.csv`, `facility_pareto.csv`.
(If you prefer, connect Power BI straight to PostgreSQL and import the `emissions_clean`
table and the `v_*` views instead.)

## 2. DAX measures
Create these in a `_Measures` table:

```DAX
Total CO2e (t)      = SUM ( emissions_clean[co2e_tonnes] )
Total CO2e (Mt)     = DIVIDE ( [Total CO2e (t)], 1000000 )
Facilities          = DISTINCTCOUNT ( emissions_clean[facility_id] )

Sector Share %      =
DIVIDE ( [Total CO2e (t)],
         CALCULATE ( [Total CO2e (t)], ALL ( emissions_clean[sector] ) ) )

CO2e Prior Year     = CALCULATE ( [Total CO2e (t)], emissions_clean[year] = MAX ( emissions_clean[year] ) - 1 )
YoY %               = DIVIDE ( [Total CO2e (t)] - [CO2e Prior Year], [CO2e Prior Year] )

CO2e 2015           = CALCULATE ( [Total CO2e (t)], emissions_clean[year] = 2015 )
Change vs 2015 %    = DIVIDE ( [Total CO2e (t)] - [CO2e 2015], [CO2e 2015] )

Intensity (t/$M)    =
DIVIDE ( SUM ( emissions_clean[co2e_tonnes] ),
         SUM ( emissions_clean[revenue_musd] ) )
```

## 3. Page layout
| Visual | Fields |
|---|---|
| 4 KPI cards | Total CO2e (Mt), Facilities, Change vs 2015 %, Intensity |
| Bar chart | Axis `sector`, Values `Sector Share %` |
| Line chart | Axis `year`, Legend `sector`, Values `Total CO2e (Mt)` |
| Matrix / heatmap | Rows `region`, Columns `sector`, Values `Total CO2e (Mt)` (conditional formatting on) |
| Stacked bar | `roadmap_summary`: sector vs lever A / lever B |
| Slicers | `year`, `sector`, `region` (use *Sync slicers* across pages) |

## 4. Interactivity
- **Drill-down:** add `region` then `country` to the matrix rows (hierarchy), turn on drill mode.
- **Drill-through:** create a "Facility detail" page, drop `facility_id` in *Drill through*
  filters, then right-click any sector bar > Drill through.
- **Tooltip:** report-page tooltip with YoY % and intensity.

Export the finished report as a `.pbix` into this folder (and a PDF/screenshot into `images/`)
so recruiters can see the real thing.
