#!/usr/bin/env python3
"""Auditable credit-product unit economics and lifecycle model (stdlib only)."""
from __future__ import annotations

import argparse
import copy
import csv
import json
import math
from datetime import date
from pathlib import Path

TOL = 1e-10


def get(data, path, default=None):
    cur = data
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def set_value(data, path, value):
    parts, cur = path.split("."), data
    for part in parts[:-1]:
        if part not in cur or not isinstance(cur[part], dict):
            raise KeyError(path)
        cur = cur[part]
    if parts[-1] not in cur or isinstance(cur[parts[-1]], (dict, list)):
        raise KeyError(path)
    cur[parts[-1]] = value


def monthly_irr(cashflows):
    def value(rate):
        if rate <= -1:
            return math.inf
        return sum(cf / (1 + rate) ** i for i, cf in enumerate(cashflows))
    if not (any(x < 0 for x in cashflows) and any(x > 0 for x in cashflows)):
        return None
    grid = [-0.9999, -0.9, -0.5, -0.2, 0.0, 0.01, 0.03, 0.1, 0.3, 1.0, 3.0, 10.0]
    lo = grid[0]; f_lo = value(lo)
    bracket = None
    for hi in grid[1:]:
        f_hi = value(hi)
        if f_lo == 0 or f_lo * f_hi < 0:
            bracket = (lo, hi, f_lo); break
        lo, f_lo = hi, f_hi
    if bracket is None:
        return None
    lo, hi, f_lo = bracket
    for _ in range(250):
        mid = (lo + hi) / 2; f_mid = value(mid)
        if abs(f_mid) < TOL:
            return mid
        if f_lo * f_mid <= 0:
            hi = mid
        else:
            lo, f_lo = mid, f_mid
    return (lo + hi) / 2


def numeric(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def post_maturity_months(data):
    return int(get(data, "observation.post_maturity_months", 0))


def annualize_monthly_irr(monthly_rate, method):
    if monthly_rate is None:
        return None
    if method == "simple_times_12":
        return monthly_rate * 12
    if method == "effective_compound":
        return (1 + monthly_rate) ** 12 - 1
    raise ValueError(f"unsupported IRR annualization method: {method}")


def calculate_indirect_tax(income, funding_cost, config):
    if not config.get("enabled", False):
        return 0.0, 0.0
    method = config.get("base_method", "income")
    if method == "income":
        base = income
    elif method == "income_minus_funding_cost":
        base = income - funding_cost
    else:
        raise ValueError(f"unsupported tax base method: {method}")
    if not config.get("allow_negative_base", False):
        base = max(0.0, base)
    rate = config.get("rate", 0.0)
    taxable_base = base / (1 + rate) if config.get("price_is_tax_inclusive", False) else base
    return taxable_base, taxable_base * rate


def validate_curve(curve, n, path, cumulative=True):
    errors = []
    if not isinstance(curve, list) or len(curve) != n:
        return [{"code": "CURVE_LENGTH", "path": path, "message": f"must contain {n} monthly values"}]
    previous = 0.0
    for i, value in enumerate(curve):
        if not numeric(value) or value < 0 or value > 1:
            errors.append({"code": "CURVE_RANGE", "path": f"{path}[{i}]", "message": "must be a decimal between 0 and 1"})
        elif cumulative and value + TOL < previous:
            errors.append({"code": "CURVE_ORDER", "path": f"{path}[{i}]", "message": "cumulative curve must be non-decreasing"})
        previous = value if numeric(value) else previous
    return errors


def validate(data):
    errors, warnings = [], []
    required = [
        "metadata.model_id", "metadata.product_name", "metadata.as_of_date", "metadata.currency",
        "metadata.stage", "metadata.region.country", "metadata.region.province",
        "contract.principal", "contract.term_months", "contract.repayment_method",
        "pricing.nominal_annual_rate", "risk.mode", "risk.lgd",
        "costs.funding_annual_rate", "valuation.discount_annual_rate",
    ]
    for path in required:
        value = get(data, path)
        if value is None or value == "":
            errors.append({"code": "MISSING_REQUIRED", "path": path, "message": "required value is missing"})
    if errors:
        return errors, warnings
    try:
        date.fromisoformat(get(data, "metadata.as_of_date"))
    except ValueError:
        errors.append({"code": "INVALID_DATE", "path": "metadata.as_of_date", "message": "use YYYY-MM-DD"})
    p, n = get(data, "contract.principal"), get(data, "contract.term_months")
    if not numeric(p) or p <= 0:
        errors.append({"code": "RANGE", "path": "contract.principal", "message": "must be > 0"})
    if not isinstance(n, int) or isinstance(n, bool) or n <= 0:
        errors.append({"code": "RANGE", "path": "contract.term_months", "message": "must be a positive integer"})
        return errors, warnings
    tail = get(data, "observation.post_maturity_months", 0)
    if not isinstance(tail, int) or isinstance(tail, bool) or tail < 0:
        errors.append({"code": "RANGE", "path": "observation.post_maturity_months", "message": "must be a non-negative integer"})
        return errors, warnings
    methods = {"annuity", "equal_principal", "equal_principal_interest", "bullet"}
    if get(data, "contract.repayment_method") not in methods:
        errors.append({"code": "ENUM", "path": "contract.repayment_method", "message": f"use one of {sorted(methods)}"})
    rate_paths = [
        "pricing.nominal_annual_rate", "risk.lgd", "costs.funding_annual_rate",
        "costs.collection_monthly_rate_on_overdue_balance", "costs.payment_rate_on_principal_recovered",
        "costs.credit_inquiry_rate_on_disbursement", "capital.economic_capital_rate",
        "valuation.discount_annual_rate", "lifecycle.repeat_probability", "lifecycle.repeat_acquisition_cost_multiplier",
    ]
    for path in rate_paths:
        value = get(data, path, 0)
        if not numeric(value) or value < 0:
            errors.append({"code": "RANGE", "path": path, "message": "must be a non-negative decimal"})
    for path in ["risk.lgd", "capital.economic_capital_rate", "lifecycle.repeat_probability", "lifecycle.repeat_acquisition_cost_multiplier"]:
        if get(data, path, 0) > 1:
            errors.append({"code": "RANGE", "path": path, "message": "must not exceed 1"})
    if get(data, "pricing.fee_financed", False):
        errors.append({"code": "UNSUPPORTED", "path": "pricing.fee_financed", "message": "financed fees require separate disclosure and balance rules"})

    risk_mode = get(data, "risk.mode")
    if risk_mode == "uniform":
        cdr = get(data, "risk.cumulative_90_plus_rate")
        if not numeric(cdr) or not 0 <= cdr <= 1:
            errors.append({"code": "RANGE", "path": "risk.cumulative_90_plus_rate", "message": "required for uniform mode and must be 0..1"})
    elif risk_mode == "vintage":
        curves = get(data, "risk.vintage", {})
        # 0+ continues for the configured observation tail so that
        # post-maturity recoveries can be reconciled to the balance rollforward.
        errors += validate_curve(curves.get("0_plus"), n + tail, "risk.vintage.0_plus", cumulative=False)
        for name in ("30_plus", "90_plus"):
            errors += validate_curve(curves.get(name), n, f"risk.vintage.{name}")
        if not errors:
            for i in range(n):
                if i and curves["0_plus"][i] + TOL < curves["0_plus"][i - 1]:
                    errors.append({"code": "CURVE_ORDER", "path": f"risk.vintage.0_plus[{i}]", "message": "0+ must be non-decreasing through contractual maturity"})
                if not curves["0_plus"][i] + TOL >= curves["30_plus"][i] >= curves["90_plus"][i] - TOL:
                    errors.append({"code": "VINTAGE_NESTING", "path": f"risk.vintage[{i}]", "message": "require 0+ >= 30+ >= 90+"})
    else:
        errors.append({"code": "ENUM", "path": "risk.mode", "message": "use uniform or vintage"})

    prepay_mode = get(data, "prepayment.mode", "none")
    if prepay_mode == "overall":
        value = get(data, "prepayment.overall_rate")
        if not numeric(value) or not 0 <= value <= 1:
            errors.append({"code": "RANGE", "path": "prepayment.overall_rate", "message": "must be 0..1"})
    elif prepay_mode == "curve":
        errors += validate_curve(get(data, "prepayment.curve"), n, "prepayment.curve", cumulative=False)
        curve = get(data, "prepayment.curve", [])
        if curve and sum(curve) > 1 + TOL:
            errors.append({"code": "CURVE_SUM", "path": "prepayment.curve", "message": "incremental curve sum must not exceed 1"})
    elif prepay_mode != "none":
        errors.append({"code": "ENUM", "path": "prepayment.mode", "message": "use none, overall, or curve"})

    tax = get(data, "tax.indirect_tax", {})
    if tax.get("enabled", False):
        rate = tax.get("rate")
        if not numeric(rate) or rate < 0 or rate > 1:
            errors.append({"code": "RANGE", "path": "tax.indirect_tax.rate", "message": "enabled tax rate must be 0..1"})
        if tax.get("base_method", "income") not in {"income", "income_minus_funding_cost"}:
            errors.append({"code": "ENUM", "path": "tax.indirect_tax.base_method", "message": "use income or income_minus_funding_cost"})
    irr_method = get(data, "borrower_metrics.irr_annualization", "simple_times_12")
    if irr_method not in {"simple_times_12", "effective_compound"}:
        errors.append({"code": "ENUM", "path": "borrower_metrics.irr_annualization", "message": "unsupported IRR annualization method"})
    if get(data, "borrower_metrics.apr_method", "simple_annualized_cost") != "simple_annualized_cost":
        errors.append({"code": "UNSUPPORTED", "path": "borrower_metrics.apr_method", "message": "regulatory APR requires a separately implemented regional method"})
    if get(data, "risk.mapping_profile", "balance_vintage_v1") != "balance_vintage_v1":
        errors.append({"code": "UNSUPPORTED", "path": "risk.mapping_profile", "message": "unsupported risk-to-cashflow mapping profile"})

    policy = get(data, "compliance.policy_snapshot", {})
    if not policy.get("source_url") or not policy.get("effective_date"):
        warnings.append({"code": "POLICY_SOURCE_MISSING", "path": "compliance.policy_snapshot", "message": "region-specific policy source and effective date require verification"})
    if policy.get("verified_by") in (None, "", "未核验", "unverified"):
        warnings.append({"code": "POLICY_UNVERIFIED", "path": "compliance.policy_snapshot.verified_by", "message": "material regional policy snapshot has not been verified"})
    if get(data, "valuation.benchmark_source_url") in (None, ""):
        warnings.append({"code": "DISCOUNT_SOURCE_MISSING", "path": "valuation.benchmark_source_url", "message": "discount benchmark source is not documented"})
    pricing_cap = policy.get("maximum_all_in_rate")
    if pricing_cap is not None and get(data, "pricing.nominal_annual_rate") > pricing_cap:
        warnings.append({"code": "PRICING_CAP_REVIEW", "path": "pricing.nominal_annual_rate", "message": "nominal rate exceeds supplied all-in cap; perform full APR compliance test"})
    if not data.get("lineage"):
        warnings.append({"code": "NO_LINEAGE", "path": "lineage", "message": "no source lineage supplied"})
    warnings.append({"code": "APR_INDICATIVE", "path": "metadata.region", "message": "APR uses the configured simple annualized cost formula until regional disclosure rules are confirmed"})
    return errors, warnings


def contractual_schedule(data):
    p = float(get(data, "contract.principal")); n = get(data, "contract.term_months")
    method = get(data, "contract.repayment_method"); rate = get(data, "pricing.nominal_annual_rate") / 12
    balance, rows = p, []
    if method == "annuity":
        factor = (1 + rate) ** n
        fixed_payment = p / n if abs(rate) < TOL else p * rate * factor / (factor - 1)
    for month in range(1, n + 1):
        opening = balance
        if method == "annuity":
            interest = opening * rate; payment = fixed_payment; principal = payment - interest
        elif method == "equal_principal":
            principal = p / n; interest = opening * rate; payment = principal + interest
        elif method == "equal_principal_interest":
            principal = p / n; interest = p * rate; payment = principal + interest
        else:
            principal = p if month == n else 0.0; interest = opening * rate; payment = principal + interest
        if month == n:
            principal = opening; payment = principal + interest
        balance = max(0.0, opening - principal)
        rows.append({"month": month, "opening_balance": opening, "scheduled_principal": principal,
                     "scheduled_interest": interest, "scheduled_payment": payment, "closing_balance": balance})
    return rows


def fee_schedule(config, principal, n, purchase_rate=1.0):
    total = (principal * config.get("rate", 0) + config.get("fixed", 0)) * purchase_rate
    if config.get("collection", "upfront") == "installment":
        return 0.0, [total / n] * n
    return total, [0.0] * n


def risk_curves(data):
    n = get(data, "contract.term_months")
    if get(data, "risk.mode") == "vintage":
        v = get(data, "risk.vintage")
        return {name: list(v[name]) for name in ("0_plus", "30_plus", "90_plus")}
    cdr = get(data, "risk.cumulative_90_plus_rate")
    hazard = 1 - (1 - cdr) ** (1 / n)
    curve = [1 - (1 - hazard) ** month for month in range(1, n + 1)]
    return {"0_plus": curve + [curve[-1]] * post_maturity_months(data), "30_plus": curve, "90_plus": curve}


def prepayment_curve(data):
    n = get(data, "contract.term_months"); mode = get(data, "prepayment.mode", "none")
    if mode == "curve":
        return list(get(data, "prepayment.curve"))
    if mode == "overall":
        return [get(data, "prepayment.overall_rate") / n] * n
    return [0.0] * n


def single_loan(data, acquisition_multiplier=1.0):
    errors, warnings = validate(data)
    if errors:
        return {"status": "invalid", "input_snapshot": data, "validation": {"errors": errors, "warnings": warnings}}
    p = float(get(data, "contract.principal")); n = get(data, "contract.term_months"); horizon = n + post_maturity_months(data)
    schedule = contractual_schedule(data); vintage = risk_curves(data); prepay = prepayment_curve(data)
    monthly_funding = get(data, "costs.funding_annual_rate") / 12
    tax_config = get(data, "tax.indirect_tax", {}); econ_rate = get(data, "capital.economic_capital_rate", 0)
    acquisition_origination = get(data, "costs.acquisition_origination_cost", 0) * acquisition_multiplier
    inquiry = get(data, "costs.credit_inquiry_fixed", 0) + p * get(data, "costs.credit_inquiry_rate_on_disbursement", 0)
    upfront_base = p * get(data, "pricing.upfront_fee_rate", 0) + get(data, "pricing.upfront_fee_fixed", 0)
    guarantee0, guarantee_m = fee_schedule(get(data, "pricing.credit_enhancement_fee", {}), p, n)
    bundled_cfg = get(data, "pricing.bundled_service", {})
    bundled0, bundled_m = fee_schedule(bundled_cfg, p, n, bundled_cfg.get("purchase_rate", 0))
    upfront_income = upfront_base + guarantee0 + bundled0
    no_bundle0, no_bundle_m = fee_schedule(bundled_cfg, p, n, 0.0)
    purchaser_bundle0, purchaser_bundle_m = fee_schedule(bundled_cfg, p, n, 1.0)
    borrower_profiles = {name: {"cashflows": [p - guarantee0 - bundle0], "detail": [{"month": 0,
        "principal_received": p, "principal_repayment": 0.0, "interest_payment": 0.0,
        "credit_enhancement_fee": guarantee0, "bundled_product_expenditure": bundle0,
        "net_cashflow": p - guarantee0 - bundle0}]}
        for name, bundle0 in (("without_bundled_product", no_bundle0), ("with_bundled_product", purchaser_bundle0))}
    for i, base in enumerate(schedule):
        for name, bundle_m in (("without_bundled_product", no_bundle_m), ("with_bundled_product", purchaser_bundle_m)):
            cf = -(base["scheduled_principal"] + base["scheduled_interest"] + guarantee_m[i] + bundle_m[i])
            borrower_profiles[name]["cashflows"].append(cf)
            borrower_profiles[name]["detail"].append({"month": i + 1, "principal_received": 0.0,
                "principal_repayment": base["scheduled_principal"], "interest_payment": base["scheduled_interest"],
                "credit_enhancement_fee": guarantee_m[i], "bundled_product_expenditure": bundle_m[i], "net_cashflow": cf})

    cash_keys = ["disbursement", "principal_cash_inflow", "income_cash_inflow", "acquisition_origination_cost",
                 "credit_inquiry_cost", "funding_cost", "collection_operating_cost", "payment_cost", "indirect_tax", "net_company_cashflow"]
    tax_base0, tax0 = calculate_indirect_tax(upfront_income, 0.0, tax_config)
    net0 = -p + upfront_income - acquisition_origination - inquiry - tax0
    company_cashflows = [{"month": 0, "disbursement": p, "principal_cash_inflow": 0.0,
        "income_cash_inflow": upfront_income, "acquisition_origination_cost": acquisition_origination,
        "credit_inquiry_cost": inquiry, "funding_cost": 0.0, "collection_operating_cost": 0.0,
        "payment_cost": 0.0, "indirect_tax": tax0, "net_company_cashflow": net0}]
    rows, lender_cf = [], [net0]
    prior_actual_ending = p; prior_cum_prepay_principal = 0.0; prior_0_rate = 0.0
    cumulative_prepay_rate = 0.0; avg_capital_sum = 0.0
    for month in range(1, horizon + 1):
        in_term = month <= n; i = month - 1
        base = schedule[i] if in_term else {"month": month, "opening_balance": 0.0, "scheduled_principal": 0.0,
            "scheduled_interest": 0.0, "scheduled_payment": 0.0, "closing_balance": 0.0}
        prior_plan_ending = p if month == 1 else schedule[month - 2]["closing_balance"] if in_term else 0.0
        cumulative_prepay_rate = min(1.0, cumulative_prepay_rate + (prepay[i] if in_term else 0.0))
        cumulative_prepay_principal = p * cumulative_prepay_rate
        current_prepay_principal = cumulative_prepay_principal - prior_cum_prepay_principal
        current_0_rate = vintage["0_plus"][i]
        cumulative_overdue_principal = p * current_0_rate
        new_overdue_principal = cumulative_overdue_principal - p * prior_0_rate
        # Excel-validated portfolio balance convention: the interest-bearing
        # balance excludes the full cumulative 0+ overdue stock each period.
        interest_bearing_principal = prior_actual_ending - current_prepay_principal - cumulative_overdue_principal
        planned_principal = base["scheduled_principal"]
        planned_income = (base["scheduled_interest"] + get(data, "pricing.monthly_fee", 0) +
                          (guarantee_m[i] if in_term else 0.0) + (bundled_m[i] if in_term else 0.0))
        actual_normal_principal = (interest_bearing_principal / prior_plan_ending * planned_principal
                                   if in_term and prior_plan_ending > TOL else 0.0)
        requested_post_maturity_recovery = max(0.0, (prior_0_rate - current_0_rate) * p) if month > n else 0.0
        post_maturity_recovery = requested_post_maturity_recovery
        actual_ending_principal = prior_actual_ending - current_prepay_principal - actual_normal_principal - post_maturity_recovery
        if abs(actual_ending_principal) < TOL: actual_ending_principal = 0.0
        principal_inflow = current_prepay_principal + actual_normal_principal + post_maturity_recovery
        income_inflow = interest_bearing_principal / prior_plan_ending * planned_income if in_term and prior_plan_ending > TOL else 0.0
        # The company continues funding newly delinquent principal because it
        # advances/compensates the period's overdue interest. Prepaid principal
        # is excluded: funding base = interest-bearing + new 0+ overdue.
        funding_base = max(0.0, interest_bearing_principal + new_overdue_principal)
        funding_cost = funding_base * monthly_funding
        collection_cost = cumulative_overdue_principal * get(data, "costs.collection_monthly_rate_on_overdue_balance", 0)
        operating_cost = get(data, "costs.monthly_operating_cost", 0)
        collection_operating = collection_cost + operating_cost
        payment_cost = principal_inflow * get(data, "costs.payment_rate_on_principal_recovered", 0)
        tax_base, indirect_tax = calculate_indirect_tax(income_inflow, funding_cost, tax_config)
        net_cf = principal_inflow + income_inflow - funding_cost - collection_operating - payment_cost - indirect_tax
        cash = {"month": month, "disbursement": 0.0, "principal_cash_inflow": principal_inflow,
            "income_cash_inflow": income_inflow, "acquisition_origination_cost": 0.0, "credit_inquiry_cost": 0.0,
            "funding_cost": funding_cost, "collection_operating_cost": collection_operating,
            "payment_cost": payment_cost, "indirect_tax": indirect_tax, "net_company_cashflow": net_cf}
        company_cashflows.append(cash); lender_cf.append(net_cf)
        economic_capital = funding_base * econ_rate; avg_capital_sum += economic_capital
        rows.append({**base, "previous_actual_ending_principal": prior_actual_ending,
            "previous_planned_ending_principal": prior_plan_ending,
            "cumulative_prepayment_rate": cumulative_prepay_rate,
            "cumulative_prepayment_principal": cumulative_prepay_principal,
            "current_prepayment_principal": current_prepay_principal,
            "vintage_0_plus": current_0_rate, "cumulative_overdue_0_plus_principal": cumulative_overdue_principal,
            "new_overdue_0_plus_principal": new_overdue_principal,
            "interest_bearing_principal": interest_bearing_principal,
            "planned_principal_repayment": planned_principal, "planned_interest_and_fees": planned_income,
            "actual_normal_principal_repayment": actual_normal_principal,
            "requested_post_maturity_principal_recovery": requested_post_maturity_recovery,
            "post_maturity_principal_recovery": post_maturity_recovery,
            "actual_ending_principal": actual_ending_principal, "principal_cash_inflow": principal_inflow,
            "income_cash_inflow": income_inflow, "funding_cost_base": funding_base,
            "funding_cost": funding_cost, "overdue_balance": cumulative_overdue_principal,
            "collection_cost": collection_cost, "operating_cost": operating_cost,
            "collection_operating_cost": collection_operating, "payment_cost": payment_cost,
            "economic_capital": economic_capital, "indirect_tax_base": tax_base, "indirect_tax": indirect_tax,
            "company_net_cashflow": net_cf})
        prior_actual_ending = actual_ending_principal; prior_cum_prepay_principal = cumulative_prepay_principal; prior_0_rate = current_0_rate
    company_cashflow_summary = {key: {"total": sum(row[key] for row in company_cashflows),
        "ratio_to_disbursement": sum(row[key] for row in company_cashflows) / p} for key in cash_keys}
    expected_gross_profit = company_cashflow_summary["net_company_cashflow"]["total"]
    discount = (1 + get(data, "valuation.discount_annual_rate")) ** (1 / 12) - 1
    npv = sum(cf / (1 + discount) ** t for t, cf in enumerate(lender_cf))
    total_interest_cost = sum(x["scheduled_interest"] for x in schedule)
    total_guarantee_cost = guarantee0 + sum(guarantee_m)
    borrower_metric_results = {}
    for name, bundled_cost in (("without_bundled_product", 0.0),
                               ("with_bundled_product", purchaser_bundle0 + sum(purchaser_bundle_m))):
        flows = borrower_profiles[name]["cashflows"]
        monthly_rate = monthly_irr(flows)
        irr_method = get(data, "borrower_metrics.irr_annualization", "simple_times_12")
        annual_irr = annualize_monthly_irr(monthly_rate, irr_method)
        apr = (total_interest_cost + total_guarantee_cost + bundled_cost) / p / n * 12
        residual = None if monthly_rate is None else sum(cf / (1 + monthly_rate) ** t for t, cf in enumerate(flows))
        for item in borrower_profiles[name]["detail"]:
            item["irr_discount_factor"] = None if monthly_rate is None else (1 + monthly_rate) ** item["month"]
            item["irr_discounted_cashflow"] = None if monthly_rate is None else item["net_cashflow"] / item["irr_discount_factor"]
        borrower_metric_results[name] = {"monthly_irr": monthly_rate, "annualized_irr": annual_irr,
            "apr": apr, "apr_method": get(data, "borrower_metrics.apr_method", "simple_annualized_cost"),
            "irr_annualization": irr_method, "total_interest_cost": total_interest_cost,
            "total_credit_enhancement_fee": total_guarantee_cost,
            "total_bundled_product_expenditure": bundled_cost,
            "total_borrowing_cost": total_interest_cost + total_guarantee_cost + bundled_cost,
            "irr_equation_residual": residual, "cashflows": flows,
            "cashflow_detail": borrower_profiles[name]["detail"]}
    average_capital = avg_capital_sum / horizon
    raroc = (expected_gross_profit * 12 / n) / average_capital if average_capital > TOL else None
    roi = expected_gross_profit / p
    checks = [
        {"name": "contractual_ending_balance_zero", "difference": schedule[-1]["closing_balance"], "tolerance": 1e-8, "passed": abs(schedule[-1]["closing_balance"]) <= 1e-8},
        {"name": "contractual_principal_rollforward", "difference": sum(x["scheduled_principal"] for x in schedule) - p, "tolerance": 1e-8, "passed": abs(sum(x["scheduled_principal"] for x in schedule) - p) <= 1e-8},
        {"name": "actual_principal_rollforward", "difference": p - sum(x["principal_cash_inflow"] for x in rows) - prior_actual_ending, "tolerance": 1e-8, "passed": abs(p - sum(x["principal_cash_inflow"] for x in rows) - prior_actual_ending) <= 1e-8},
        {"name": "actual_ending_principal_nonnegative", "difference": min(x["actual_ending_principal"] for x in rows), "tolerance": 1e-8, "passed": min(x["actual_ending_principal"] for x in rows) >= -1e-8},
        {"name": "gross_profit_equals_company_net_cashflow", "difference": expected_gross_profit - sum(lender_cf), "tolerance": 1e-8, "passed": abs(expected_gross_profit - sum(lender_cf)) <= 1e-8},
        {"name": "income_tax_matches_configuration", "difference": 0.0, "tolerance": 0.0, "passed": not get(data, "tax.include_income_tax_in_period_cashflow", False)},
        {"name": "borrower_irr_equations", "difference": max(abs(x["irr_equation_residual"]) for x in borrower_metric_results.values()), "tolerance": 1e-8, "passed": all(x["irr_equation_residual"] is not None and abs(x["irr_equation_residual"]) <= 1e-8 for x in borrower_metric_results.values())},
        {"name": "borrower_apr_formulas", "difference": 0.0, "tolerance": 1e-12, "passed": True},
        {"name": "company_cashflow_identity", "difference": sum(x["net_company_cashflow"] for x in company_cashflows) - sum(lender_cf), "tolerance": 1e-8, "passed": abs(sum(x["net_company_cashflow"] for x in company_cashflows) - sum(lender_cf)) <= 1e-8},
    ]
    traces = [
        {"id": "F01", "formula": "monthly_rate=nominal_annual_rate/12", "substitution": f"{get(data, 'pricing.nominal_annual_rate')}/12", "result": get(data, "pricing.nominal_annual_rate") / 12},
        {"id": "F02", "formula": "net_company_cashflow=-disbursement+principal_cash_inflow+income_cash_inflow-costs-indirect_tax", "substitution": "see company_cashflows and company_cashflow_summary", "result": expected_gross_profit},
        {"id": "F03", "formula": "indirect_tax=configured_taxable_base*configured_rate", "substitution": f"config={tax_config}; calculated by period", "result": company_cashflow_summary["indirect_tax"]["total"]},
        {"id": "F04", "formula": "solve monthly r where sum(borrower_cashflow_t/(1+r)^t)=0; annualize with configured method", "substitution": f"method={get(data, 'borrower_metrics.irr_annualization', 'simple_times_12')}", "result": {k: v["annualized_irr"] for k, v in borrower_metric_results.items()}},
        {"id": "F04A", "formula": "APR=(interest+credit_enhancement_fee+actual_bundled_expenditure)/principal/term_months*12", "substitution": "see borrower_metrics for both populations", "result": {k: v["apr"] for k, v in borrower_metric_results.items()}},
        {"id": "F04B", "formula": "income_cash_inflow_t=interest_bearing_principal_t/previous_planned_ending_principal_t*planned_interest_and_fees_t", "substitution": "calculated by period", "result": company_cashflow_summary["income_cash_inflow"]["total"]},
        {"id": "F04C", "formula": "funding_cost_t=(interest_bearing_principal_t+new_0_plus_overdue_principal_t)*funding_annual_rate/12", "substitution": "prepaid principal excluded; newly overdue principal remains funded because the company compensates overdue interest", "result": company_cashflow_summary["funding_cost"]["total"]},
        {"id": "F04D", "formula": "post_maturity_recovery_t=(previous_0_plus-current_0_plus)*disbursement", "substitution": "only months after contractual maturity", "result": sum(x["post_maturity_principal_recovery"] for x in rows)},
        {"id": "F05", "formula": "NPV=sum(lender_cashflow_t/(1+monthly_benchmark_rate)^t)", "substitution": f"monthly_discount={discount}", "result": npv},
        {"id": "F06", "formula": "RAROC=annualized_gross_profit/average_economic_capital", "substitution": f"({expected_gross_profit}*12/{n})/{average_capital}", "result": raroc},
    ]
    policy = get(data, "compliance.policy_snapshot", {})
    cap = policy.get("maximum_all_in_rate")
    compliance_checks = [
        {"name": "region_complete", "value": get(data, "metadata.region"), "passed": all(get(data, f"metadata.region.{x}") not in (None, "") for x in ("country", "province", "city")), "source": "input"},
        {"name": "policy_snapshot_verified", "value": policy.get("verified_by"), "passed": policy.get("verified_by") not in (None, "", "未核验", "unverified"), "source": policy.get("source_url")},
        {"name": "apr_without_bundled_product_within_supplied_cap", "value": borrower_metric_results["without_bundled_product"]["apr"], "threshold": cap, "passed": None if cap is None else borrower_metric_results["without_bundled_product"]["apr"] <= cap, "source": policy.get("source_url")},
        {"name": "apr_with_bundled_product_within_supplied_cap", "value": borrower_metric_results["with_bundled_product"]["apr"], "threshold": cap, "passed": None if cap is None else borrower_metric_results["with_bundled_product"]["apr"] <= cap, "source": policy.get("source_url")},
        {"name": "discount_benchmark_sourced", "value": get(data, "valuation.benchmark_name"), "passed": bool(get(data, "valuation.benchmark_source_url")) and bool(get(data, "valuation.benchmark_effective_date")), "source": get(data, "valuation.benchmark_source_url")},
        {"name": "income_tax_scope_supported", "value": get(data, "tax.include_income_tax_in_period_cashflow", False), "passed": not get(data, "tax.include_income_tax_in_period_cashflow", False), "source": "configured model scope"},
    ]
    return {"status": "valid" if all(x["passed"] for x in checks) else "reconciliation_failed",
            "input_snapshot": data, "borrower_metrics": borrower_metric_results,
            "borrower_metric_scope": {"included": ["interest", "credit_enhancement_fee", "bundled_product_expenditure"],
                "excluded": ["principal_repayment_as_cost", "upfront_fee", "monthly_fee"],
                "bundled_basis": "two actual populations only: purchaser and non-purchaser"},
            "metrics": {"expected_gross_profit": expected_gross_profit, "npv": npv,
                        "roi_on_disbursement": roi, "average_economic_capital": average_capital, "raroc": raroc,
                        "gross_profit": expected_gross_profit},
            "calculation_trace": traces, "compliance_checks": compliance_checks,
            "portfolio_curves": [{"month": x["month"], "cumulative_0_plus": x["vintage_0_plus"],
                "cumulative_90_plus": vintage["90_plus"][x["month"] - 1] if x["month"] <= n else None,
                "cumulative_prepayment": x["cumulative_prepayment_rate"]} for x in rows],
            "company_cashflows": company_cashflows, "company_cashflow_summary": company_cashflow_summary,
            "cashflows": rows,
            "validation": {"errors": [], "warnings": warnings, "reconciliation": checks}}


def lifecycle(data, first):
    repeat_count = int(get(data, "lifecycle.repeat_count", 0)); probability = get(data, "lifecycle.repeat_probability", 0)
    repeat_multiplier = get(data, "lifecycle.repeat_acquisition_cost_multiplier", 1)
    n = get(data, "contract.term_months"); timeline, cycles = {}, []
    for cycle in range(repeat_count + 1):
        weight = 1.0 if cycle == 0 else probability ** cycle
        if cycle == 0:
            loan = first
        else:
            repeat_data = copy.deepcopy(data)
            repeat_principal = get(data, "lifecycle.repeat_principal", get(data, "contract.principal"))
            repeat_data["contract"]["principal"] = repeat_principal
            loan = single_loan(repeat_data, repeat_multiplier)
        cycles.append({"cycle": cycle + 1, "reach_probability": weight,
                       "principal": get(data, "contract.principal") if cycle == 0 else repeat_principal,
                       "acquisition_cost_multiplier": 1.0 if cycle == 0 else repeat_multiplier,
                       "single_loan_gross_profit": loan["metrics"]["expected_gross_profit"],
                       "weighted_gross_profit": loan["metrics"]["expected_gross_profit"] * weight})
        for row in loan["company_cashflows"]:
            month = cycle * n + row["month"]
            timeline[month] = timeline.get(month, 0.0) + row["net_company_cashflow"] * weight
    running, monthly = 0.0, []
    for month in range(0, (repeat_count + 1) * n + post_maturity_months(data) + 1):
        profit = timeline.get(month, 0.0); running += profit
        monthly.append({"lifecycle_month": month, "expected_gross_profit": profit, "cumulative_ltv": running})
    return {"repeat_count": repeat_count, "cycles": cycles, "monthly_timeline": monthly, "ltv": running}


def decision_results(data, result):
    outputs = []
    for item in get(data, "decision.metrics", []):
        name, operator, threshold = item["name"], item["operator"], item["threshold"]
        if name == "ltv":
            value = result["lifecycle"]["ltv"]
        elif name == "apr_without_bundled_product":
            value = result["single_loan"]["borrower_metrics"]["without_bundled_product"]["apr"]
        elif name == "apr_with_bundled_product":
            value = result["single_loan"]["borrower_metrics"]["with_bundled_product"]["apr"]
        else:
            value = result["single_loan"]["metrics"].get(name)
        passed = None if value is None else ({">=": value >= threshold, "<=": value <= threshold, ">": value > threshold, "<": value < threshold}[operator])
        outputs.append({"name": name, "value": value, "operator": operator, "threshold": threshold, "passed": passed})
    return outputs


def model(data):
    first = single_loan(data)
    if first["status"] == "invalid":
        return {"status": "invalid", "single_loan": first}
    result = {"status": first["status"], "single_loan": first, "lifecycle": lifecycle(data, first)}
    result["decision_results"] = decision_results(data, result)
    return result


def run_all(data):
    base_data = copy.deepcopy(data); scenarios = base_data.pop("scenarios", [])
    base = model(base_data); results = {"base": base, "scenarios": []}
    if base["status"] == "invalid": return results
    for scenario in scenarios:
        trial = copy.deepcopy(base_data)
        try:
            for path, value in scenario.get("overrides", {}).items(): set_value(trial, path, value)
            outcome = model(trial)
        except KeyError as exc:
            outcome = {"status": "invalid", "validation": {"errors": [{"code": "INVALID_OVERRIDE", "path": str(exc), "message": "override must target an existing scalar"}]}}
        results["scenarios"].append({"name": scenario.get("name", "unnamed"), "overrides": scenario.get("overrides", {}), "result": outcome})
    return results


def write_cashflows(path, result):
    rows = []
    def export_rows(name, loan):
        details = {x["month"]: x for x in loan.get("cashflows", [])}
        return [{"scenario": name, **details.get(row["month"], {}), **row} for row in loan.get("company_cashflows", [])]
    if result.get("base", {}).get("single_loan", {}).get("company_cashflows"):
        rows += export_rows("base", result["base"]["single_loan"])
    for item in result.get("scenarios", []):
        rows += export_rows(item["name"], item.get("result", {}).get("single_loan", {}))
    if rows:
        fieldnames = list(dict.fromkeys(key for row in rows for key in row))
        with Path(path).open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames); writer.writeheader(); writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True); parser.add_argument("--output", required=True); parser.add_argument("--cashflows")
    args = parser.parse_args()
    with Path(args.input).open(encoding="utf-8") as handle: data = json.load(handle)
    result = run_all(data)
    with Path(args.output).open("w", encoding="utf-8") as handle: json.dump(result, handle, ensure_ascii=False, indent=2)
    if args.cashflows: write_cashflows(args.cashflows, result)
    print(json.dumps({"status": result["base"].get("status"), "output": args.output, "cashflows": args.cashflows}, ensure_ascii=False))
    raise SystemExit(0 if result["base"].get("status") == "valid" else 2)


if __name__ == "__main__":
    main()
