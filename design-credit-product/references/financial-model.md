# Financial model

## Contract and observation horizons

- Origination is month 0. The contractual schedule runs for `n` months.
- The actual company balance and cash-flow schedule runs through `n + observation.post_maturity_months` so post-maturity collections are visible.
- Supported repayment methods are annuity, equal principal, equal principal and interest (等本等息), and bullet. In every method, contractual final principal equals the remaining contractual balance.

## Balance rollforward

All behavioral curves are by original disbursement `P`. For month `t`:

- cumulative prepayment principal = `P * cumulative prepayment rate_t`
- current prepayment principal = `cumulative prepayment principal_t - cumulative prepayment principal_(t-1)`
- cumulative 0+ overdue principal = `P * cumulative 0+ rate_t`
- new 0+ overdue principal = `cumulative 0+ overdue principal_t - cumulative 0+ overdue principal_(t-1)`
- interest-bearing principal = `previous actual ending principal - current prepayment principal - cumulative 0+ overdue principal`
- actual normal principal = `interest-bearing principal / previous planned ending principal * planned principal`, during the contractual term only
- requested post-maturity recovery = `(previous cumulative 0+ rate - current cumulative 0+ rate) * P`, after maturity only
- actual post-maturity recovery equals the curve-implied recovery; the reconciliation verifies that actual ending principal remains non-negative
- actual ending principal = `previous actual ending principal - current prepayment principal - actual normal principal - actual post-maturity recovery`
- principal cash inflow = `current prepayment principal + actual normal principal + actual post-maturity recovery`
- income cash inflow = `interest-bearing principal / previous planned ending principal * planned interest and fees`, during the contractual term only

The 0+ curve must cover the complete configured horizon. The first `n` observations are non-decreasing; tail observations can decline to represent post-maturity recovery. Uniform-risk mode carries the terminal 0+ value through the configured tail and therefore assumes no post-maturity recovery unless an explicit Vintage curve is supplied.

## Costs, tax, and company cash flow

- funding cost = `(interest-bearing principal + new 0+ overdue principal) * annual funding rate / 12`. Prepaid principal is excluded; newly overdue principal remains funded because the company compensates its overdue interest.
- collection cost = `cumulative 0+ overdue principal * monthly collection rate`
- collection-operating cost = collection cost + monthly operating cost
- payment cost = `principal cash inflow * payment cost rate`
- indirect tax = the configured taxable base, inclusive/exclusive treatment, rate, and negative-base rule
- company net cash flow = `-disbursement + principal cash inflow + income cash inflow - acquisition-origination cost - credit inquiry cost - funding cost - collection-operating cost - payment cost - indirect tax`

Month 0 contains disbursement, upfront income, acquisition-origination cost, credit inquiry cost, and any configured indirect tax. The core report contains the ten standard company cash fields above, plus month, and may preserve additional project-specific fields. For every value field output the lifecycle total and total/original-disbursement ratio.

Single-loan gross profit is total company net cash flow through the configured observation horizon. Do not deduct expected principal loss again: non-recovered principal is already absent from principal cash inflow. Economic capital is excluded from gross profit and used only in the RAROC denominator. Income tax is outside the bundled engine's scope.

## Borrower metrics

- Build borrower cash flows from principal received at month 0 and scheduled principal, interest, credit-enhancement fees, and actual bundled-product expenditure paid in each period.
- Solve monthly IRR and annualize with the configured method: `simple_times_12` or `effective_compound`.
- The bundled `simple_annualized_cost` APR method is `(interest + credit-enhancement fee + actual bundled-product expenditure) / principal / term months * 12`; it is not a substitute for a region-specific regulatory APR.
- Output only actual bundled-product purchasers and non-purchasers. Purchase rate is used only for company expected income.

## Valuation and lifecycle

- NPV discounts company net cash flow at the sourced local benchmark rate.
- RAROC = annualized gross profit / average economic capital.
- Repeat-loan LTV probability-weights each cycle and applies the configured lower acquisition cost to repeats. Cash-flow tails may overlap later cycles.

## Required reconciliations

- Contractual ending balance is zero and contractual principal sums to disbursement.
- Original disbursement equals cumulative principal cash inflow plus actual ending principal.
- Actual ending principal is never negative.
- Gross profit equals total company net cash flow.
- Borrower IRR equations have zero residual; APR uses its separate simple formula.
- Income tax in period cash flow is zero.

This is a transparent feasibility model, not an IFRS 9/CECL, regulatory-capital, tax-filing, regulatory-APR, or production behavioral model. Every project must record its selected observation, tax, borrower-metric, and risk-mapping configuration.
