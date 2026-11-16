# Regional policy workflow

## Retrieval sequence

1. Identify country, province/state, city, lender/entity type, borrower type, product type, channel, currency, and model date.
2. Search current primary sources: central bank, financial regulator, legislature/gazette, tax authority, local regulator, and official benchmark publisher.
3. Capture rule title, clause/summary, URL, issuing body, publication date, effective date, geographic scope, entity/product scope, retrieval date, and reviewer.
4. Check pricing caps and all-in cost, fee and bundled-sale restrictions, APR/disclosure method, VAT/tax base and rate, overdue-interest tax timing, data/consent, marketing, prepayment, collections, and consumer-protection requirements.
5. Select a benchmark discount rate matching currency and product term. Do not automatically equate LPR or another policy rate with the institution's hurdle rate; record the user's approved basis.
6. Mark every conclusion `verified`, `assumed`, `not applicable`, or `missing`. A missing material rule blocks approval-stage conclusions.

## Compliance output

Return `check | applicable rule | model value | result | source | effective date | scope | owner | action`.

## Tax caution

Do not generalize any indirect-tax base, rate, inclusive/exclusive treatment, or deductibility rule. Configure only a method supported by current authoritative guidance and record the source. If the required regional method is unsupported, calculate it outside the engine with a documented formula or block the approval-stage conclusion.

## Freshness

Regulation, tax, pricing limits, and benchmark rates are time-sensitive. Retrieve them for every real project and cite official sources near each claim. Never reuse the demonstration snapshot as current policy.
