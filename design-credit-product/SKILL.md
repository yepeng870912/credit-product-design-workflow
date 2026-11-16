---
name: design-credit-product
description: Design regional credit-product terms and build auditable single-loan and lifecycle pricing models. Use for loan input completion, product parameters, regional policy research, repayment and fee schedules, Vintage and prepayment modelling, borrower cost metrics, profitability, valuation, capital return, lifecycle value, scenarios, and formula-level validation. Do not treat demonstration assumptions as current policy or institution-approved parameters.
---

# Design Credit Product

Build a decision-ready parameter package and an auditable unit-economics model. Keep reusable methods separate from project configuration and evidence. Never silently invent a material policy, risk, cost, tax, or behavioral input.

## Route the request

- Read `references/input-contract.md` for JSON fields and curve conventions.
- Read `references/product-design.md` for stage gates and parameter checks.
- Read `references/financial-model.md` before calculating.
- Read `references/regional-compliance.md` whenever region, pricing compliance, tax, or benchmark discount rates matter. Retrieve current authoritative sources and cite them; do not rely on static memory.
- Start from `assets/input-template.json`. Create project inputs and outputs outside the skill directory.

## Execute

1. Identify the stage and ask the user to select the primary decision metrics and thresholds.
2. Capture country, province/state, city, lender/entity type, borrower type, product type, channel, and as-of date.
3. Retrieve current regional pricing, disclosure, fee, tax, benchmark-rate, data, and consumer-protection rules from primary official sources. Save each rule, URL, effective date, retrieval date, scope, and reviewer in the policy snapshot. If not verified, return a blocking compliance gap rather than presenting a definitive conclusion.
4. Build an input register with value, unit, basis, source, as-of date, owner, confidence, and status (`provided`, `derived`, `assumed`, `missing`). Ask only for items blocking the current stage.
5. Produce a parameter proposal with recommended value/range, rationale, constraint, downstream impact, owner, and open issue.
6. Keep the contractual receivable schedule separate from behavioral/risk adjustments. Accept `annuity`, `equal_principal`, `equal_principal_interest` (等本等息), or `bullet`.
7. Accept either an overall prepayment rate or an incremental monthly prepayment curve by original disbursement. Accept either uniform monthly risk or cumulative monthly 0+/30+/90+ Vintage curves by original disbursement. Require explicit Vintage 0+ to cover the contractual term plus the configured post-maturity observation period.
8. Save JSON and run:

   `python scripts/credit_model.py --input <input.json> --output <output.json> --cashflows <cashflows.csv>`

9. Review errors, warnings, regional policy status, decision thresholds, and every reconciliation. Do not call an output decision-ready while an error or unverified material policy remains.
10. Deliver single-loan monthly and cumulative income/cost/profit, lifecycle monthly cumulative LTV, scenario deltas, formula substitutions, and source lineage.

## Required output

1. Decision scope and user-selected primary metrics.
2. Input completeness and regional policy snapshot with citations.
3. Product parameter sheet.
4. Contractual receivable schedule and borrower cash flows.
5. Single-loan balance rollforward through the configured post-maturity observation period: cumulative/current prepayment principal, cumulative/new 0+ overdue principal, interest-bearing principal, actual normal principal, post-maturity recovery, actual ending principal, principal cash inflow, and income cash inflow; also output cumulative 0+/90+/prepayment curves.
6. Separate borrower IRR/APR for actual bundled-product purchasers and non-purchasers; do not purchase-rate-weight either borrower metric.
7. Company period cash receipts and payments using the standard core fields: disbursement, principal cash inflow, income cash inflow, acquisition-origination cost, credit inquiry cost, funding cost, collection-operating cost, payment cost, configured indirect tax, and net company cash flow. Preserve additional project-specific fields when needed. Output every item total and its ratio to original disbursement.
8. Lifecycle repeat-loan cycles, reduced repeat acquisition cost, monthly cumulative LTV, and scenario comparison.
9. Formula trace, validation, reconciliation, limitations, approvals, and next gate.

## Guardrails

- Treat economic capital as capital reserved for unexpected loss, not funding cost. Exclude it from gross profit and use average economic capital only as the RAROC denominator.
- Include only taxes explicitly configured and supported by the engine. The current engine supports configurable indirect tax on income or income less funding cost, with inclusive/exclusive pricing and negative-base settings. It does not calculate income tax.
- Solve borrower monthly IRR from dated cash flows and apply the configured annualization method. Calculate the configured management APR separately. Never present it as regulatory APR unless the applicable regional method has been verified and implemented. Output only actual purchaser and non-purchaser populations.
- Calculate period prepayment income loss as `period receivable income × cumulative prepayment rate`. Calculate funding cost on actual opening principal after prior normal and prepayment principal recovery. Set final-period principal recovery to the remaining actual balance.
- Do not double-count risk: use 0+ for income-collection loss, marginal 90+ with LGD for principal loss, and keep 30+ as a monitoring/collection signal unless the user supplies another mapping.
- Keep full precision in JSON/CSV; round only presentation values.
- Follow the selected and documented risk mapping profile in `references/financial-model.md`. The bundled `balance_vintage_v1` profile deducts cumulative 0+ overdue principal from interest-bearing principal and includes new 0+ overdue principal in the funding base.
- When gross profit is total company net cash flow, do not separately deduct expected principal loss: unrecovered principal already reduces principal cash inflow and remains in actual ending principal.
- Treat bundled-service purchase rate as expected participation, and clearly distinguish optional from mandatory charges for compliance.
- Require product, risk, finance, tax, legal, and compliance approval before launch.
