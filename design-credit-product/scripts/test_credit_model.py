#!/usr/bin/env python3
import copy, importlib.util, json, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("credit_model", HERE / "credit_model.py")
credit_model = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(credit_model)


class CreditModelBalanceCashflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with (HERE.parent / "assets" / "input-template.json").open(encoding="utf-8") as f: cls.example = json.load(f)
        cls.example.update({"metadata": {"model_id": "test", "product_name": "test", "as_of_date": "2026-01-01", "currency": "TST", "stage": "feasibility", "region": {"country": "XX", "province": "P", "city": "C"}},
            "contract": {"principal": 100000, "term_months": 12, "repayment_method": "equal_principal_interest"},
            "pricing": {"nominal_annual_rate": 0.18, "upfront_fee_rate": 0, "upfront_fee_fixed": 0, "monthly_fee": 0, "fee_financed": False, "credit_enhancement_fee": {"rate": 0.01, "fixed": 0, "collection": "installment"}, "bundled_service": {"rate": 0, "fixed": 1200, "purchase_rate": 0.25, "collection": "upfront"}},
            "risk": {"mode": "vintage", "mapping_profile": "balance_vintage_v1", "cumulative_90_plus_rate": 0.06, "lgd": 0.65, "vintage": {"0_plus": [0.01,0.02,0.03,0.04,0.05,0.055,0.06,0.065,0.07,0.07,0.07,0.07,0.062,0.061,0.06], "30_plus": [0.005,0.01,0.015,0.02,0.025,0.03,0.035,0.04,0.045,0.05,0.055,0.06], "90_plus": [0,0,0.005,0.01,0.015,0.02,0.025,0.03,0.035,0.04,0.05,0.06]}},
            "prepayment": {"mode": "curve", "overall_rate": 0, "curve": [0.005] * 12},
            "costs": {"funding_annual_rate": 0.08, "acquisition_origination_cost": 500, "monthly_operating_cost": 10, "collection_monthly_rate_on_overdue_balance": 0.005, "payment_rate_on_principal_recovered": 0.001, "credit_inquiry_fixed": 5, "credit_inquiry_rate_on_disbursement": 0.0001},
            "tax": {"indirect_tax": {"enabled": True, "type": "configured_indirect_tax", "rate": 0.06, "base_method": "income_minus_funding_cost", "price_is_tax_inclusive": True, "allow_negative_base": True}, "include_income_tax_in_period_cashflow": False},
            "capital": {"economic_capital_rate": 0.08}, "valuation": {"discount_annual_rate": 0.04, "benchmark_name": "test", "benchmark_source_url": "https://example.invalid", "benchmark_effective_date": "2026-01-01"},
            "observation": {"post_maturity_months": 3}, "borrower_metrics": {"irr_annualization": "simple_times_12", "apr_method": "simple_annualized_cost"},
            "lifecycle": {"repeat_count": 2, "repeat_probability": 0.5, "repeat_acquisition_cost_multiplier": 0.5}, "decision": {"metrics": [{"name": "npv", "operator": ">=", "threshold": -100000}]},
            "compliance": {"policy_snapshot": {"maximum_all_in_rate": 1, "source_url": "https://example.invalid", "effective_date": "2026-01-01", "verified_by": "test"}}, "lineage": [{"path": "test", "source": "test"}], "scenarios": []})

    def base(self):
        data = copy.deepcopy(self.example); data.pop("scenarios", None); return data

    def loan(self, data=None): return credit_model.model(data or self.base())["single_loan"]

    def test_four_repayment_methods_reconcile(self):
        for method in ("annuity", "equal_principal", "equal_principal_interest", "bullet"):
            data = self.base(); data["contract"]["repayment_method"] = method
            result = self.loan(data)
            self.assertEqual(result["status"], "valid")
            self.assertTrue(all(x["passed"] for x in result["validation"]["reconciliation"]))

    def test_equal_principal_interest_and_final_principal(self):
        rows = self.loan()["cashflows"][:12]
        self.assertAlmostEqual(max(x["scheduled_payment"] for x in rows), min(x["scheduled_payment"] for x in rows), places=8)
        self.assertAlmostEqual(rows[-1]["scheduled_principal"], rows[-1]["opening_balance"])

    def test_zero_plus_extends_three_months(self):
        result = self.loan(); curves = result["portfolio_curves"]
        self.assertEqual(len(curves), 15)
        self.assertEqual([x["cumulative_0_plus"] for x in curves[-3:]], [0.062, 0.061, 0.060])
        self.assertTrue(all(x["cumulative_90_plus"] is None for x in curves[-3:]))

    def test_balance_intermediate_formulas(self):
        p = self.base()["contract"]["principal"]
        for row in self.loan()["cashflows"]:
            self.assertAlmostEqual(row["cumulative_prepayment_principal"], p * row["cumulative_prepayment_rate"])
            self.assertAlmostEqual(row["cumulative_overdue_0_plus_principal"], p * row["vintage_0_plus"])
            self.assertAlmostEqual(row["interest_bearing_principal"], row["previous_actual_ending_principal"] - row["current_prepayment_principal"] - row["cumulative_overdue_0_plus_principal"])
            self.assertAlmostEqual(row["actual_ending_principal"], row["previous_actual_ending_principal"] - row["current_prepayment_principal"] - row["actual_normal_principal_repayment"] - row["post_maturity_principal_recovery"])
            self.assertAlmostEqual(row["principal_cash_inflow"], row["current_prepayment_principal"] + row["actual_normal_principal_repayment"] + row["post_maturity_principal_recovery"])

    def test_normal_principal_and_income_scale_by_balance(self):
        for row in self.loan()["cashflows"][:12]:
            ratio = row["interest_bearing_principal"] / row["previous_planned_ending_principal"]
            self.assertAlmostEqual(row["actual_normal_principal_repayment"], ratio * row["planned_principal_repayment"])
            self.assertAlmostEqual(row["income_cash_inflow"], ratio * row["planned_interest_and_fees"])

    def test_post_maturity_recovery(self):
        rows = self.loan()["cashflows"]
        self.assertEqual([round(x["requested_post_maturity_principal_recovery"], 8) for x in rows[-3:]], [800, 100, 100])
        self.assertEqual([round(x["post_maturity_principal_recovery"], 8) for x in rows[-3:]], [800, 100, 100])
        self.assertAlmostEqual(rows[11]["actual_ending_principal"], 7000.0, places=7)
        self.assertAlmostEqual(rows[-1]["actual_ending_principal"], 6000.0, places=7)

    def test_funding_tax_and_cost_bases(self):
        data = self.base()
        for row in self.loan()["cashflows"]:
            expected_funding_base = max(0, row["interest_bearing_principal"] + row["new_overdue_0_plus_principal"])
            self.assertAlmostEqual(row["funding_cost_base"], expected_funding_base)
            self.assertAlmostEqual(row["funding_cost"], expected_funding_base * data["costs"]["funding_annual_rate"] / 12)
            self.assertAlmostEqual(row["indirect_tax"], (row["income_cash_inflow"] - row["funding_cost"]) / 1.06 * data["tax"]["indirect_tax"]["rate"])
            self.assertAlmostEqual(row["collection_cost"], row["overdue_balance"] * data["costs"]["collection_monthly_rate_on_overdue_balance"])
            self.assertAlmostEqual(row["payment_cost"], row["principal_cash_inflow"] * data["costs"]["payment_rate_on_principal_recovered"])

    def test_company_cashflow_has_exact_ten_items(self):
        result = self.loan(); expected = {"month", "disbursement", "principal_cash_inflow", "income_cash_inflow",
            "acquisition_origination_cost", "credit_inquiry_cost", "funding_cost", "collection_operating_cost",
            "payment_cost", "indirect_tax", "net_company_cashflow"}
        self.assertEqual(len(result["company_cashflows"]), 16)
        self.assertTrue(all(set(row) == expected for row in result["company_cashflows"]))

    def test_company_cashflow_identity_summary_and_ratios(self):
        result = self.loan(); p = self.base()["contract"]["principal"]
        for key, summary in result["company_cashflow_summary"].items():
            self.assertAlmostEqual(summary["total"], sum(x[key] for x in result["company_cashflows"]))
            self.assertAlmostEqual(summary["ratio_to_disbursement"], summary["total"] / p)
        for row in result["company_cashflows"]:
            expected = (-row["disbursement"] + row["principal_cash_inflow"] + row["income_cash_inflow"]
                - row["acquisition_origination_cost"] - row["credit_inquiry_cost"] - row["funding_cost"]
                - row["collection_operating_cost"] - row["payment_cost"] - row["indirect_tax"])
            self.assertAlmostEqual(row["net_company_cashflow"], expected)
        self.assertAlmostEqual(result["metrics"]["expected_gross_profit"], result["company_cashflow_summary"]["net_company_cashflow"]["total"])

    def test_borrower_metrics_two_actual_populations(self):
        result = self.loan(); self.assertEqual(set(result["borrower_metrics"]), {"without_bundled_product", "with_bundled_product"})
        for population in result["borrower_metrics"].values():
            self.assertAlmostEqual(population["annualized_irr"], population["monthly_irr"] * 12)
            self.assertAlmostEqual(population["irr_equation_residual"], 0, places=7)
        self.assertGreater(result["borrower_metrics"]["with_bundled_product"]["apr"], result["borrower_metrics"]["without_bundled_product"]["apr"])

    def test_capital_only_affects_raroc(self):
        data = self.base(); base = self.loan(data); data["capital"]["economic_capital_rate"] = 0.16; changed = self.loan(data)
        self.assertAlmostEqual(base["metrics"]["expected_gross_profit"], changed["metrics"]["expected_gross_profit"])
        self.assertNotEqual(base["metrics"]["raroc"], changed["metrics"]["raroc"])

    def test_lifecycle_and_decisions(self):
        result = credit_model.model(self.base())
        self.assertEqual(len(result["lifecycle"]["cycles"]), 3)
        self.assertAlmostEqual(result["lifecycle"]["monthly_timeline"][-1]["cumulative_ltv"], result["lifecycle"]["ltv"])
        self.assertTrue(all(x["passed"] is not None for x in result["decision_results"]))

    def test_repeat_principal_is_used(self):
        data = self.base(); data["lifecycle"]["repeat_principal"] = 50000
        result = credit_model.model(data)
        self.assertEqual(result["lifecycle"]["cycles"][1]["principal"], 50000)

    def test_invalid_zero_plus_length_is_blocked(self):
        data = self.base(); data["risk"]["vintage"]["0_plus"].pop()
        result = self.loan(data)
        self.assertEqual(result["status"], "invalid")
        self.assertIn("CURVE_LENGTH", {x["code"] for x in result["validation"]["errors"]})

    def test_observation_horizon_is_configurable(self):
        data = self.base(); data["observation"]["post_maturity_months"] = 1
        data["risk"]["vintage"]["0_plus"] = data["risk"]["vintage"]["0_plus"][:13]
        self.assertEqual(len(self.loan(data)["cashflows"]), 13)

    def test_tax_and_irr_methods_are_configurable(self):
        data = self.base(); data["tax"]["indirect_tax"]["price_is_tax_inclusive"] = False
        data["borrower_metrics"]["irr_annualization"] = "effective_compound"
        result = self.loan(data)
        first = result["cashflows"][0]
        self.assertAlmostEqual(first["indirect_tax"], first["indirect_tax_base"] * data["tax"]["indirect_tax"]["rate"])
        metric = result["borrower_metrics"]["without_bundled_product"]
        self.assertAlmostEqual(metric["annualized_irr"], (1 + metric["monthly_irr"]) ** 12 - 1)


if __name__ == "__main__": unittest.main(verbosity=2)
