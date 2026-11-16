# Input contract

Use JSON decimals (`0.18` means 18%). Monetary values use `metadata.currency`.

## Identity and region

Require `metadata.model_id`, `product_name`, `as_of_date`, `currency`, `stage`, and `region.country/province/city`. Add entity type, borrower type, and product type to the policy scope when collecting real inputs.

## Contract and revenue

- `contract.principal`, `term_months`, and `repayment_method`: `annuity`, `equal_principal`, `equal_principal_interest`, or `bullet`.
- `pricing.nominal_annual_rate`, upfront fee, and monthly fee.
- `pricing.credit_enhancement_fee`: `{rate, fixed, collection}` where collection is `upfront` or `installment`.
- `pricing.bundled_service`: `{rate, fixed, purchase_rate, collection}`. Expected bundled income equals fee × purchase rate.

## Delinquency and prepayment

- `risk.mode=uniform`: provide `cumulative_90_plus_rate`; the model creates an even monthly hazard and uses it for 0+/30+/90+.
- `risk.mode=vintage`: provide `30_plus` and `90_plus` arrays with exactly `term_months` values. Provide `0_plus` with exactly `term_months + observation.post_maturity_months` values: non-decreasing through maturity, optionally declining after maturity, and satisfying 0+ ≥ 30+ ≥ 90+ during the contractual term.
- `risk.mapping_profile` identifies the approved conversion from curves to balances and cash flow. The bundled engine supports `balance_vintage_v1`; do not silently substitute another risk interpretation.
- `risk.lgd`: loss share applied to the marginal 90+ balance by original disbursement.
- `prepayment.mode=overall`: provide total contractual-life `overall_rate`; the current transparent approximation spreads it evenly by month.
- `prepayment.mode=curve`: provide an incremental monthly curve by original disbursement; array sum must not exceed 1.

## Variable costs and tax

- Funding: annual rate on contractual opening balance.
- Acquisition and origination: merge into `costs.acquisition_origination_cost` at month 0; repeat acquisition-origination cost is reduced by the lifecycle multiplier.
- Operating: fixed monthly amount.
- Collection: monthly rate × 0+ overdue balance.
- Payment: rate × principal recovered.
- Credit inquiry: fixed + rate × original disbursement at month 0.
- Indirect tax: configure `tax.indirect_tax.enabled`, `type`, `rate`, `base_method`, `price_is_tax_inclusive`, and `allow_negative_base`. Supported base methods are `income` and `income_minus_funding_cost`.
- `tax.include_income_tax_in_period_cashflow` must remain false because the bundled engine does not implement income tax.

## Observation and borrower metrics

- `observation.post_maturity_months` controls the recovery tail and required 0+ curve length.
- `borrower_metrics.irr_annualization` is `simple_times_12` or `effective_compound`.
- `borrower_metrics.apr_method=simple_annualized_cost` calculates `(interest + credit-enhancement fee + actual bundled expenditure) / principal / term × 12`. Label it a management metric, not regulatory APR.

## Capital, value, lifecycle, and decisions

- `capital.economic_capital_rate`: economic capital / opening balance. It affects only RAROC denominator.
- `valuation.discount_annual_rate`: use a sourced regional benchmark compatible with term and currency; store benchmark name, URL, and effective date.
- `lifecycle.repeat_count`: additional repeat loans; `repeat_probability`: probability of reaching each next cycle; `repeat_acquisition_cost_multiplier`: repeat acquisition / first-loan acquisition.
- `decision.metrics`: user-selected `{name, operator, threshold}` entries. Supported values include `expected_gross_profit`, `npv`, `raroc`, `apr_without_bundled_product`, `apr_with_bundled_product`, and `ltv`.

## Source lineage

For every material input store `{path, source, as_of_date, owner, status, confidence, note}`. Save policy sources separately in `compliance.policy_snapshot`.
