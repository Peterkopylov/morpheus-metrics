# Dashboard Workflow Checklist

Use this checklist when the user asks to create or significantly change a dashboard.

1. Confirm dashboard purpose.
2. Confirm intended audience and access scope.
3. Confirm whether modeling should stay in `view`, move to `calculated`, or be investigated first.
4. Search for reusable views and scripts in `sql/`, `scripts/serving/`, `serving/dashboards/`, and `serving/dashboard_registry.csv`.
5. State the reuse findings before building new warehouse objects.
6. Implement only the minimal new layer needed:
   - existing view reuse
   - new or updated dashboard view
   - new or updated calculated metric
7. Update `serving/dashboard_registry.csv`.
8. Mention the final access decision, modeling decision, reuse findings, and registry update in the closeout.
