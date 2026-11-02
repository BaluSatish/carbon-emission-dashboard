"""Re-run the roadmap under different assumptions to see how sensitive the % reduction is.
Resets roadmap_params to defaults when done. Same psql env vars as run_pipeline.py."""
import subprocess

def q(sql):
    r = subprocess.run(["psql", "-At", "-v", "ON_ERROR_STOP=1", "-c", sql], capture_output=True, text=True)
    if r.returncode: raise SystemExit(r.stderr)
    return r.stdout.strip().splitlines()[-1]

DEFAULTS = (0.50, 25)
rows = ["gap_closure,renewable_floor_pct,total_reduction_pct"]
for gap in (0.25, 0.50, 0.75, 1.00):
    for floor in (25, 40, 60):
        q(f"UPDATE roadmap_params SET value={gap} WHERE param='gap_closure_share'")
        q(f"UPDATE roadmap_params SET value={floor} WHERE param='renewable_floor_pct'")
        pct = q("SELECT reduction_pct_of_sector FROM v_roadmap_summary WHERE sector='ALL SECTORS'")
        rows.append(f"{gap},{floor},{pct}")
q(f"UPDATE roadmap_params SET value={DEFAULTS[0]} WHERE param='gap_closure_share'")
q(f"UPDATE roadmap_params SET value={DEFAULTS[1]} WHERE param='renewable_floor_pct'")
open("results/roadmap_sensitivity.csv", "w").write("\n".join(rows) + "\n")
print("\n".join(rows))
