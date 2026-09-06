"""The textbook's worked examples, pinned as tests.

Every assertion here is a number printed in Bodie/Kane/Marcus 9CE, taken from
the summaries in `References/Stocks`. That is the point: the finance module is
only trustworthy if it reproduces the source, and a refactor that quietly
changes a formula should fail here rather than surface as a slightly wrong
forecast six months later.

Tolerances are loose (2-3 decimal places) because the textbook rounds its
intermediate steps and we do not.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from stocks.finance import index_model, portfolio, returns, risk


class TestChapter5Returns:
    def test_fisher_exact_matches_example_5_1(self):
        """Example 5.1: 8% nominal, 5% inflation -> 2.86% real."""
        assert returns.real_rate_exact(0.08, 0.05) == pytest.approx(0.0286, abs=1e-4)

    def test_fisher_approximation_overstates_by_the_documented_amount(self):
        """The chapter notes the approximation overstates by 14 basis points here."""
        exact = returns.real_rate_exact(0.08, 0.05)
        approx = returns.real_rate_approx(0.08, 0.05)
        assert approx == pytest.approx(0.03)
        assert approx - exact == pytest.approx(0.0014, abs=1e-4)

    def test_annualize_inverts_compounding(self):
        assert returns.annualize(0.2, 2.0) == pytest.approx(0.0954, abs=1e-4)

    def test_effective_annual_rate_converges_to_continuous(self):
        assert returns.effective_annual_rate(0.10, 1) == pytest.approx(0.10)
        assert returns.effective_annual_rate(0.10, 12) == pytest.approx(0.10471, abs=1e-5)
        # periods_per_year=0 is the continuous-compounding sentinel.
        assert returns.effective_annual_rate(0.10, 0) == pytest.approx(np.expm1(0.10))

    def test_geometric_mean_is_never_above_arithmetic(self):
        """Chapter 5, F4. The gap widens with volatility."""
        r = pd.Series([0.50, -0.30, 0.20, -0.10, 0.40])
        assert returns.geometric_mean_return(r) < returns.arithmetic_mean_return(r)

    def test_geometric_mean_of_constant_returns_is_that_return(self):
        r = pd.Series([0.07] * 10)
        assert returns.geometric_mean_return(r) == pytest.approx(0.07)

    def test_total_wipeout_gives_minus_one(self):
        assert returns.geometric_mean_return(pd.Series([0.1, -1.0, 0.5])) == -1.0

    def test_holding_period_return_includes_income(self):
        assert returns.holding_period_return(100, 110, 5) == pytest.approx(0.15)

    def test_forward_log_return_looks_forward_and_ends_in_nan(self):
        px = pd.Series([100.0, 110.0, 121.0, 133.1])
        fwd = returns.forward_log_return(px, 1)
        assert fwd.iloc[0] == pytest.approx(np.log(1.1))
        # The last h entries have no future and must be NaN, not filled.
        assert np.isnan(fwd.iloc[-1])


class TestChapter5Risk:
    def test_scenario_analysis_matches_f3(self):
        p = np.array([0.25, 0.50, 0.25])
        r = np.array([0.30, 0.10, -0.10])
        assert risk.scenario_expected_return(p, r) == pytest.approx(0.10)
        assert risk.scenario_variance(p, r) == pytest.approx(0.02)

    def test_scenario_probabilities_must_sum_to_one(self):
        with pytest.raises(ValueError, match="sum to 1"):
            risk.scenario_expected_return(np.array([0.3, 0.3]), np.array([0.1, 0.2]))

    def test_sharpe_ratio_matches_example_5_9(self):
        """Example 5.9: risk premium 5.76%, SD 19.49% -> Sharpe 0.30.

        Built as a synthetic series with exactly those moments, since the
        function consumes a series rather than the two summary statistics.
        """
        rng = np.random.default_rng(0)
        raw = rng.standard_normal(2520)
        excess = (raw - raw.mean()) / raw.std(ddof=1)
        # Annual premium 5.76% and SD 19.49%, expressed per trading day.
        daily = excess * (0.1949 / np.sqrt(252)) + 0.0576 / 252
        assert risk.sharpe_ratio(pd.Series(daily), 0.0) == pytest.approx(0.30, abs=0.02)

    def test_var_normal_uses_the_textbook_quantile(self):
        """Chapter 5, F6: VaR(1%) = mean - 2.33 * SD."""
        r = pd.Series(np.random.default_rng(1).standard_normal(1000))
        expected = r.mean() - 2.33 * r.std(ddof=1)
        assert risk.value_at_risk_normal(r) == pytest.approx(expected)

    def test_historical_var_is_worse_than_normal_var_on_fat_tails(self):
        """The whole reason the chapter recommends empirical VaR for equities."""
        rng = np.random.default_rng(2)
        # Student-t with 3 df: fat-tailed, like real daily equity returns.
        fat = pd.Series(rng.standard_t(3, 5000) / 100)
        assert risk.value_at_risk_historical(fat) < risk.value_at_risk_normal(fat)

    def test_expected_shortfall_is_worse_than_var(self):
        r = pd.Series(np.random.default_rng(3).standard_normal(2000))
        assert risk.expected_shortfall(r) < risk.value_at_risk_historical(r)

    def test_max_drawdown_finds_the_peak_to_trough(self):
        px = pd.Series([100.0, 120.0, 60.0, 90.0])
        assert risk.max_drawdown(px) == pytest.approx(-0.5)

    def test_annualized_vol_scales_by_root_time(self):
        r = pd.Series(np.random.default_rng(4).standard_normal(1000) * 0.01)
        assert risk.annualized_volatility(r) == pytest.approx(
            risk.volatility(r) * np.sqrt(252)
        )

    def test_normal_data_has_near_zero_skew_and_excess_kurtosis(self):
        r = pd.Series(np.random.default_rng(5).standard_normal(20_000))
        assert risk.skewness(r) == pytest.approx(0.0, abs=0.05)
        assert risk.excess_kurtosis(r) == pytest.approx(0.0, abs=0.10)


class TestChapter6Portfolio:
    def test_optimal_y_matches_example_6_4(self):
        """Example 6.4: r_f=7%, E(r_P)=15%, sigma_P=22%, A=4 -> y* = 0.41."""
        y = portfolio.optimal_risky_weight(0.15, 0.22, 0.07, 4.0)
        assert y == pytest.approx(0.4132, abs=1e-4)

    def test_complete_portfolio_matches_example_6_4(self):
        """E(r_C) = 10.28%, sigma_C = 9.02%, and Sharpe matches P's."""
        alloc = portfolio.capital_allocation_line(0.15, 0.22, 0.07, 4.0)
        assert alloc.expected_return == pytest.approx(0.1028, abs=1e-3)
        assert alloc.std_dev == pytest.approx(0.0902, abs=1e-3)
        # Every point on the CAL shares one Sharpe ratio: 8/22 = 0.3636.
        assert alloc.sharpe_ratio == pytest.approx(8 / 22, abs=1e-3)

    def test_risk_free_portfolio_scores_its_own_return(self):
        """Chapter 6, F1: zero variance means no risk penalty, for any A."""
        for a in (2.0, 3.5, 5.0):
            assert portfolio.utility_score(0.05, 0.0, a) == pytest.approx(0.05)

    def test_higher_risk_aversion_lowers_utility_of_a_risky_portfolio(self):
        scores = [portfolio.utility_score(0.15, 0.22, a) for a in (2.0, 3.5, 5.0)]
        assert scores == sorted(scores, reverse=True)

    def test_higher_risk_aversion_reduces_the_risky_allocation(self):
        weights = [portfolio.optimal_risky_weight(0.15, 0.22, 0.07, a) for a in (2.0, 4.0, 8.0)]
        assert weights == sorted(weights, reverse=True)

    def test_negative_risk_premium_implies_a_short(self):
        alloc = portfolio.capital_allocation_line(0.02, 0.22, 0.07, 4.0)
        assert alloc.is_short and alloc.y_star < 0

    def test_standard_deviation_is_never_negative(self):
        """The chapter writes sigma_C = y * sigma_P assuming y >= 0. This
        project reaches y < 0 whenever the forecast risk premium is negative,
        and taking the formula literally there yields a negative standard
        deviation -- not a quantity that exists."""
        assert portfolio.complete_portfolio_std(-0.5, 0.30) == pytest.approx(0.15)

        alloc = portfolio.capital_allocation_line(0.02, 0.22, 0.07, 4.0)
        assert alloc.is_short
        assert alloc.std_dev > 0

    def test_shorting_more_is_riskier_not_less(self):
        risks = [portfolio.complete_portfolio_std(y, 0.30) for y in (-0.2, -0.5, -1.0)]
        assert risks == sorted(risks)

    def test_symmetric_positions_carry_equal_risk(self):
        assert (portfolio.complete_portfolio_std(0.6, 0.25)
                == pytest.approx(portfolio.complete_portfolio_std(-0.6, 0.25)))


class TestChapter7Portfolio:
    """Table 7.1: bond fund D (E=8%, sd=12%), stock fund E (E=13%, sd=20%),
    Cov=72 so rho=0.30, r_f=5%. All figures in percent, as the chapter has them."""

    SD_D, SD_E, RHO = 12.0, 20.0, 0.30

    def test_minimum_variance_weights_match_example_7_1(self):
        w_d, w_e = portfolio.minimum_variance_weights(self.SD_D, self.SD_E, self.RHO)
        assert w_d == pytest.approx(0.82, abs=0.01)
        assert w_e == pytest.approx(0.18, abs=0.01)

    def test_minimum_variance_sd_is_below_both_components(self):
        """11.45% -- lower than either 12% or 20%. Diversification in action."""
        w_d, _ = portfolio.minimum_variance_weights(self.SD_D, self.SD_E, self.RHO)
        sd = np.sqrt(portfolio.two_asset_variance(w_d, self.SD_D, self.SD_E, self.RHO))
        assert sd == pytest.approx(11.45, abs=0.05)
        assert sd < min(self.SD_D, self.SD_E)

    def test_optimal_risky_weights_match_example_7_2(self):
        """Excess returns: D = 8-5 = 3, E = 13-5 = 8. -> w_D = 0.40, w_E = 0.60."""
        w_d, w_e = portfolio.optimal_two_asset_weights(3.0, 8.0, self.SD_D, self.SD_E, self.RHO)
        assert w_d == pytest.approx(0.40, abs=0.01)
        assert w_e == pytest.approx(0.60, abs=0.01)

    def test_optimal_portfolio_moments_match_example_7_2(self):
        """E(r_P) = 11%, sigma_P = 14.2%, Sharpe = 0.42."""
        w_d = 0.40
        e_rp = portfolio.two_asset_return(w_d, 8.0, 13.0)
        sd_p = np.sqrt(portfolio.two_asset_variance(w_d, self.SD_D, self.SD_E, self.RHO))
        assert e_rp == pytest.approx(11.0, abs=0.01)
        assert sd_p == pytest.approx(14.2, abs=0.05)
        assert (e_rp - 5.0) / sd_p == pytest.approx(0.42, abs=0.01)

    def test_optimal_complete_portfolio_matches_example_7_3(self):
        """A=4 investor: y* = 0.7439, so 29.76% bonds and 44.63% stocks."""
        y = portfolio.optimal_risky_weight(11.0, 14.2, 5.0, 4.0) * 100
        assert y == pytest.approx(0.7439, abs=0.005)
        assert y * 0.40 == pytest.approx(0.2976, abs=0.005)
        assert y * 0.60 == pytest.approx(0.4463, abs=0.005)

    def test_perfect_negative_correlation_permits_zero_variance(self):
        """Chapter 7, LO2: at rho = -1 there are weights giving sigma = 0."""
        w_d, _ = portfolio.minimum_variance_weights(10.0, 20.0, -1.0)
        assert portfolio.two_asset_variance(w_d, 10.0, 20.0, -1.0) == pytest.approx(0.0, abs=1e-9)

    def test_lower_correlation_always_reduces_portfolio_risk(self):
        variances = [portfolio.two_asset_variance(0.5, 12.0, 20.0, rho)
                     for rho in (1.0, 0.5, 0.0, -0.5)]
        assert variances == sorted(variances, reverse=True)

    def test_correlation_outside_the_unit_interval_is_rejected(self):
        with pytest.raises(ValueError, match=r"\[-1, 1\]"):
            portfolio.two_asset_variance(0.5, 12.0, 20.0, 1.5)

    def test_markowitz_matches_the_two_asset_formula(self):
        """Chapter 7, F5 must reduce to F2 for n = 2."""
        w = np.array([0.4, 0.6])
        cov = self.RHO * self.SD_D * self.SD_E
        matrix = np.array([[self.SD_D**2, cov], [cov, self.SD_E**2]])
        assert portfolio.portfolio_variance(w, matrix) == pytest.approx(
            portfolio.two_asset_variance(0.4, self.SD_D, self.SD_E, self.RHO)
        )


class TestChapter8IndexModel:
    @staticmethod
    def _synthetic_scl(alpha: float, beta: float, resid_sd: float, n: int = 600, seed: int = 7):
        rng = np.random.default_rng(seed)
        market = pd.Series(rng.standard_normal(n) * 0.01)
        stock = alpha + beta * market + pd.Series(rng.standard_normal(n) * resid_sd)
        return stock, market

    def test_recovers_known_alpha_and_beta(self):
        stock, market = self._synthetic_scl(0.0016, 1.1048, 0.008)
        scl = index_model.fit_scl(stock, market)
        assert scl.alpha == pytest.approx(0.0016, abs=5e-4)
        assert scl.beta == pytest.approx(1.1048, abs=0.05)

    def test_r_squared_matches_the_f4_identity(self):
        """Chapter 8, F4: R^2 = 1 - sigma^2(e)/sigma^2(i)."""
        stock, market = self._synthetic_scl(0.001, 1.2, 0.01)
        scl = index_model.fit_scl(stock, market)
        implied = 1.0 - scl.residual_std**2 / stock.var(ddof=1)
        assert scl.r_squared == pytest.approx(implied, abs=0.02)

    def test_variance_shares_sum_to_one(self):
        """Chapter 8, F1: total risk splits into systematic + firm-specific."""
        stock, market = self._synthetic_scl(0.0, 1.0, 0.01)
        scl = index_model.fit_scl(stock, market)
        assert scl.systematic_variance_share + scl.firm_specific_variance_share == pytest.approx(1.0)

    def test_higher_residual_noise_lowers_r_squared(self):
        r2s = [index_model.fit_scl(*self._synthetic_scl(0.0, 1.0, sd)).r_squared
               for sd in (0.002, 0.01, 0.05)]
        assert r2s == sorted(r2s, reverse=True)

    def test_information_ratio_is_alpha_over_residual_std(self):
        stock, market = self._synthetic_scl(0.002, 1.0, 0.01)
        scl = index_model.fit_scl(stock, market)
        assert scl.information_ratio == pytest.approx(scl.alpha / scl.residual_std)

    def test_residual_series_is_uncorrelated_with_the_market(self):
        """The defining property of an OLS residual, and the reason
        `residual_series` is a useful alternative target."""
        stock, market = self._synthetic_scl(0.001, 1.3, 0.01)
        resid = index_model.residual_series(stock, market)
        assert resid.corr(market) == pytest.approx(0.0, abs=1e-9)

    def test_combined_sharpe_never_falls_below_the_index(self):
        """Chapter 8, F5: security analysis can only help, if done optimally."""
        assert index_model.combined_sharpe_squared(0.4, 0.15) > 0.4**2
        assert index_model.combined_sharpe_squared(0.4, 0.0) == pytest.approx(0.16)

    def test_treynor_black_weights_sum_to_one_and_short_negative_alpha(self):
        """Chapter 8, F6."""
        alphas = pd.Series({"A": 0.02, "B": 0.01, "C": -0.015})
        resid_var = pd.Series({"A": 0.04, "B": 0.02, "C": 0.03})
        w = index_model.treynor_black_weights(alphas, resid_var)
        assert w.sum() == pytest.approx(1.0)
        assert w["C"] < 0

    def test_misaligned_series_are_joined_not_silently_offset(self):
        """A stock that did not trade on a day the index did must be dropped,
        never shifted -- an off-by-one alignment manufactures fake alpha."""
        stock, market = self._synthetic_scl(0.0, 1.0, 0.005, n=100)
        stock.index = pd.date_range("2024-01-01", periods=100, freq="D")
        market.index = pd.date_range("2024-01-01", periods=100, freq="D")
        scl = index_model.fit_scl(stock.drop(stock.index[10:20]), market)
        assert scl.n_obs == 90

    def test_too_few_observations_raises(self):
        with pytest.raises(ValueError, match="at least 3"):
            index_model.fit_scl(pd.Series([0.1, 0.2]), pd.Series([0.1, 0.2]))
