---
name: design-credit-product
description: Design regional credit-product terms and build auditable single-loan and lifecycle pricing models. Use when Codex needs to complete loan inputs, define repayment/rate/fee/eligibility terms, retrieve location-specific pricing/tax/regulatory requirements, model delinquency Vintage and prepayment curves, calculate borrower IRR/APR, gross profit/NPV/RAROC/LTV, run scenarios, and preserve formulas, monthly cumulative components, validations, policy sources, and assumption lineage.
---

# Design Credit Product

Build a decision-ready parameter package and an auditable unit-economics model. Never silently invent a material policy, risk, cost, or behavioral input.

## Route the request

- Read `references/input-contract.md` for JSON fields and curve conventions.
- Read `references/product-design.md` for stage gates and parameter checks.
- Read `references/financial-model.md` before calculating.
- Read `references/regional-compliance.md` whenever region, pricing compliance, tax, or benchmark discount rates matter. Retrieve current authoritative sources and cite them; do not rely on static memory.
- Start from `assets/input-template.json`; use `assets/example-input.json` only as a labeled demonstration.

## Execute

1. Identify the stage and ask the user to select the primary decision metrics and thresholds.
2. Capture country, province/state, city, lender/entity type, borrower type, product type, channel, and as-of date.
3. Retrieve current regional pricing, disclosure, fee, tax, benchmark-rate, data, and consumer-protection rules from primary official sources. Save each rule, URL, effective date, retrieval date, scope, and reviewer in the policy snapshot. If not verified, return a blocking compliance gap rather than presenting a definitive conclusion.
4. Build an input register with value, unit, basis, source, as-of date, owner, confidence, and status (`provided`, `derived`, `assumed`, `missing`). Ask only for items blocking the current stage.
5. Produce a parameter proposal with recommended value/range, rationale, constraint, downstream impact, owner, and open issue.
6. Keep the contractual receivable schedule separate from behavioral/risk adjustments. Accept `annuity`, `equal_principal`, `equal_principal_interest` (等本等息), or `bullet`.
7. Accept either an overall prepayment rate or an incremental monthly prepayment curve by original disbursement. Accept either uniform monthly risk or cumulative monthly 0+/30+/90+ Vintage curves by original disbursement. Require explicit Vintage 0+ to extend three periods beyond the longest contractual term for post-maturity recoveries.
8. Save JSON and run:

   `python scripts/credit_model.py --input <input.json> --output <output.json> --cashflows <cashflows.csv>`

9. Review errors, warnings, regional policy status, decision thresholds, and every reconciliation. Do not call an output decision-ready while an error or unverified material policy remains.
10. Deliver single-loan monthly and cumulative income/cost/profit, lifecycle monthly cumulative LTV, scenario deltas, formula substitutions, and source lineage.

## Required output

1. Decision scope and user-selected primary metrics.
2. Input completeness and regional policy snapshot with citations.
3. Product parameter sheet.
4. Contractual receivable schedule and borrower cash flows.
5. Single-loan balance rollforward through three periods after maturity: cumulative/current prepayment principal, cumulative/new 0+ overdue principal, interest-bearing principal, actual normal principal, post-maturity recovery, actual ending principal, principal cash inflow, and income cash inflow; also output cumulative 0+/90+/prepayment curves.
6. Separate borrower IRR/APR for actual bundled-product purchasers and non-purchasers; do not purchase-rate-weight either borrower metric.
7. Company period cash receipts and payments with exactly ten value fields: disbursement, principal cash inflow, income cash inflow, acquisition-origination cost, credit inquiry cost, funding cost, collection-operating cost, payment cost, VAT, and net company cash flow. Output every item total and its ratio to original disbursement.
8. Lifecycle repeat-loan cycles, reduced repeat acquisition cost, monthly cumulative LTV, and scenario comparison.
9. Formula trace, validation, reconciliation, limitations, approvals, and next gate.

## Guardrails

- Treat economic capital as capital reserved for unexpected loss, not funding cost. Exclude it from gross profit and use average economic capital only as the RAROC denominator.
- Exclude income tax from period cash flow. Model VAT explicitly from the user-approved regional tax base and rate.
- Solve borrower monthly IRR from dated cash flows and annualize as `monthly IRR × 12` without compounding. Calculate APR separately as `(interest + credit-enhancement fee + actual bundled-product expenditure) / principal / term_months × 12`. Output only actual purchaser and non-purchaser populations.
- Calculate period prepayment income loss as `period receivable income × cumulative prepayment rate`. Calculate funding cost on actual opening principal after prior normal and prepayment principal recovery. Set final-period principal recovery to the remaining actual balance.
- Do not double-count risk: use 0+ for income-collection loss, marginal 90+ with LGD for principal loss, and keep 30+ as a monitoring/collection signal unless the user supplies another mapping.
- Keep full precision in JSON/CSV; round only presentation values.
- Follow the balance and cash-receipt formulas in `references/financial-model.md`; interest-bearing principal deducts cumulative 0+ overdue principal, while funding cost uses interest-bearing principal plus new 0+ overdue principal so prepayments stop accruing funding cost but delinquent principal remains funded.
- When gross profit is total company net cash flow, do not separately deduct expected principal loss: unrecovered principal already reduces principal cash inflow and remains in actual ending principal.
- Treat bundled-service purchase rate as expected participation, and clearly distinguish optional from mandatory charges for compliance.
- Require product, risk, finance, tax, legal, and compliance approval before launch.
