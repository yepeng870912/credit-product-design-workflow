#!/usr/bin/env python3
import copy, importlib.util, json, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("credit_model", HERE / "credit_model.py")
credit_model = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(credit_model)


class CreditModelBalanceCashflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with (HERE.parent / "assets" / "example-input.json").open(encoding="utf-8") as f: cls.example = json.load(f)

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
        self.assertEqual([round(x["requested_post_maturity_principal_recovery"], 8) for x in rows[-3:]], [200, 100, 100])
        self.assertEqual([round(x["post_maturity_principal_recovery"], 8) for x in rows[-3:]], [200, 100, 100])
        self.assertAlmostEqual(rows[11]["actual_ending_principal"], 6400.0, places=7)
        self.assertAlmostEqual(rows[-1]["actual_ending_principal"], 6000.0, places=7)

    def test_funding_vat_and_cost_bases(self):
        data = self.base()
        for row in self.loan()["cashflows"]:
            expected_funding_base = max(0, row["interest_bearing_principal"] + row["new_overdue_0_plus_principal"])
            self.assertAlmostEqual(row["funding_cost_base"], expected_funding_base)
            self.assertAlmostEqual(row["funding_cost"], expected_funding_base * data["costs"]["funding_annual_rate"] / 12)
            self.assertAlmostEqual(row["vat"], (row["income_cash_inflow"] - row["funding_cost"]) / 1.06 * data["tax"]["vat_rate"])
            self.assertAlmostEqual(row["collection_cost"], row["overdue_balance"] * data["costs"]["collection_monthly_rate_on_overdue_balance"])
            self.assertAlmostEqual(row["payment_cost"], row["principal_cash_inflow"] * data["costs"]["payment_rate_on_principal_recovered"])

    def test_company_cashflow_has_exact_ten_items(self):
        result = self.loan(); expected = {"month", "disbursement", "principal_cash_inflow", "income_cash_inflow",
            "acquisition_origination_cost", "credit_inquiry_cost", "funding_cost", "collection_operating_cost",
            "payment_cost", "vat", "net_company_cashflow"}
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
                - row["collection_operating_cost"] - row["payment_cost"] - row["vat"])
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


if __name__ == "__main__": unittest.main(verbosity=2)
