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

from stocks.finance import (
    capm,
    event_study,
    index_model,
    multifactor,
    portfolio,
    returns,
    risk,
    technical,
)


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


class TestChapter9CAPM:
    """Chapter 9 -- the CAPM and the security market line."""

    def test_sml_fair_return_matches_the_alpha_example(self):
        """Market 14%, T-bills 6%, beta 1.2 -> a fair return of 15.6%."""
        assert capm.sml_expected_return(1.2, 0.06, 0.08) == pytest.approx(0.156)

    def test_alpha_matches_the_alpha_example(self):
        """An analyst forecasting 17% against a 15.6% fair return -> alpha 1.4%."""
        assert capm.sml_alpha(0.17, 1.2, 0.06, 0.08) == pytest.approx(0.014, abs=1e-9)

    def test_example_9_1_utility_required_return(self):
        """Example 9.1: beta 0.6, T-bill 6%, MRP 8% -> 10.8%."""
        assert capm.required_return(0.6, 0.06, 0.08) == pytest.approx(0.108)

    def test_example_9_1_fair_profit(self):
        """Example 9.1: 10.8% on $100 million of invested capital -> $10.8 million."""
        assert capm.fair_profit(100e6, 0.6, 0.06, 0.08) == pytest.approx(10.8e6)

    def test_zero_beta_sml_is_flatter_than_the_simple_capm(self):
        """F2: with E(r_Z) > r_f, the zero-beta line is flatter.

        LO2's prediction, and the reason high-beta names have historically
        under-delivered against the simple model. Checked as a *property*
        rather than a number because the chapter gives no worked example.
        """
        rf, zero_beta, market = 0.03, 0.06, 0.11
        high = 1.8
        simple = capm.sml_expected_return(high, rf, market - rf)
        restricted = capm.zero_beta_expected_return(high, zero_beta, market)
        assert restricted < simple
        # Both lines pass through the market portfolio at beta = 1.
        assert capm.zero_beta_expected_return(1.0, zero_beta, market) == pytest.approx(market)

    def test_beta_zero_earns_only_the_risk_free_rate(self):
        assert capm.sml_expected_return(0.0, 0.04, 0.08) == pytest.approx(0.04)

    def test_total_volatility_does_not_enter_the_sml(self):
        """LO1's counter-intuitive claim, as an executable statement.

        A wildly volatile low-beta stock is entitled to *less* return than a
        placid high-beta one, because only systematic risk is compensated.
        """
        speculative = capm.sml_expected_return(0.4, 0.04, 0.08)   # 90% vol, say
        utility = capm.sml_expected_return(1.1, 0.04, 0.08)       # 25% vol, say
        assert speculative < utility

    def test_verdict_calls_small_alphas_fairly_priced(self):
        """Anything inside +/-1% is noise at this project's precision."""
        assert capm.evaluate_against_sml(0.101, 1.0, 0.02, 0.08).verdict == "fairly_priced"
        assert capm.evaluate_against_sml(0.15, 1.0, 0.02, 0.08).verdict == "underpriced"
        assert capm.evaluate_against_sml(0.05, 1.0, 0.02, 0.08).verdict == "overpriced"

    def test_mrp_shrinks_a_short_noisy_sample_toward_the_prior(self):
        """One year of returns is a hopeless estimator; the blend says so.

        A single year of index returns estimates the equity premium with a
        standard error several times the premium itself. At 252 observations
        the estimate must land far closer to the 8% prior than to whatever the
        sample happened to print.
        """
        # A mildly negative year: well inside what an index really does.
        soft = pd.Series([-0.0002] * 252)
        got = capm.realised_market_risk_premium(soft, 0.04)
        raw = capm.realised_market_risk_premium(soft, 0.04, shrink=False)
        assert raw == pytest.approx(-0.0904, abs=1e-3)
        # ~17% weight on the sample at n=252, so the blend stays near the prior.
        assert got == pytest.approx((252 / 1512) * raw + (1260 / 1512) * 0.08, abs=1e-6)
        assert 0.04 < got < 0.08

    def test_estimated_mrp_never_inverts_the_sml(self):
        """The failure the floor exists to prevent.

        A negative market risk premium is not a bear-market reading, it is the
        CAPM's premise inverted: the SML slopes downward and every high-beta
        name is scored as *entitled to less* than a low-beta one. The raw
        estimate goes negative routinely on a single bad year -- shrinkage
        narrows that but does not close it, which is why `MRP_FLOOR` exists.

        Swept across bad-year draws, including a 2008-scale collapse.
        """
        rng = np.random.default_rng(3)
        for drift in (-0.0008, -0.0016, -0.0025):
            for _ in range(15):
                sample = pd.Series(rng.normal(drift, 0.012, 252))
                mrp = capm.realised_market_risk_premium(sample, 0.04)
                assert mrp >= capm.MRP_FLOOR, (
                    "estimated MRP went below the floor; the SML would slope backwards"
                )

    def test_the_floor_is_a_floor_not_a_clamp_on_good_years(self):
        """A positive estimate must pass through untouched."""
        good = pd.Series([0.0006] * 252)
        assert capm.realised_market_risk_premium(good, 0.04) > capm.MRP_FLOOR

    def test_unshrunk_estimate_is_left_raw_and_can_go_negative(self):
        """`shrink=False` is for measuring the estimator's instability, so it
        must not be floored -- a floored 'raw' number would hide exactly the
        problem the caller is trying to observe."""
        awful = pd.Series([-0.002] * 252)
        assert capm.realised_market_risk_premium(awful, 0.04, shrink=False) < -0.5

    def test_mrp_gives_a_long_sample_real_weight(self):
        """Shrinkage must not be a constant. Ten years should move the estimate."""
        strong = pd.Series([0.0008] * 2520)          # ~20% annualised
        got = capm.realised_market_risk_premium(strong, 0.04)
        raw = capm.realised_market_risk_premium(strong, 0.04, shrink=False)
        assert got > 0.10, "a decade of evidence barely moved the estimate"
        assert got < raw, "shrinkage should still pull toward the prior"

    def test_mrp_is_nan_on_an_empty_series(self):
        assert np.isnan(capm.realised_market_risk_premium(pd.Series(dtype=float), 0.04))

    def test_beta_from_covariance_matches_the_regression_slope(self):
        """F1's definitional beta and Chapter 8's fitted beta are one number."""
        rng = np.random.default_rng(11)
        market = pd.Series(rng.normal(0.0004, 0.01, 800))
        stock = 1.3 * market + pd.Series(rng.normal(0, 0.008, 800))
        definitional = capm.beta_from_covariance(stock.cov(market), market.var())
        fitted = index_model.fit_scl(stock, market).beta
        assert definitional == pytest.approx(fitted, abs=1e-9)


class TestChapter10Multifactor:
    """Chapter 10 -- APT and multifactor models."""

    def test_example_10_3_multifactor_sml(self):
        """E(r1)=10%, E(r2)=12%, rf=4%, betas 0.5 and 0.75 -> 13%."""
        got = multifactor.multifactor_expected_return(
            {"f1": 0.5, "f2": 0.75}, {"f1": 0.06, "f2": 0.08}, 0.04)
        assert got == pytest.approx(0.13)

    def test_example_10_3_betas_below_one_can_still_be_aggressive(self):
        """The chapter's headline point: 9% risk premium from two sub-1 betas."""
        got = multifactor.multifactor_expected_return(
            {"f1": 0.5, "f2": 0.75}, {"f1": 0.06, "f2": 0.08}, 0.04)
        assert got - 0.04 == pytest.approx(0.09)

    def test_example_10_4_replicating_weights(self):
        """Q is 0.5 / 0.75 in the factor portfolios and -0.25 in T-bills."""
        w = multifactor.replicating_weights({"f1": 0.5, "f2": 0.75})
        assert w["f1"] == pytest.approx(0.5)
        assert w["f2"] == pytest.approx(0.75)
        # Negative: borrowing at the risk-free rate, not lending.
        assert w["risk_free"] == pytest.approx(-0.25)
        assert sum(w.values()) == pytest.approx(1.0)

    def test_example_10_4_arbitrage_profit(self):
        """A priced at 12% against a fair 13% -> $0.01 riskless per dollar."""
        assert multifactor.arbitrage_profit(0.13, 0.12) == pytest.approx(0.01)

    def test_no_arbitrage_profit_when_correctly_priced(self):
        assert multifactor.arbitrage_profit(0.13, 0.13) == pytest.approx(0.0)

    def test_joint_regression_recovers_known_loadings(self):
        """F3: a three-factor fit must recover the betas it was built from."""
        rng = np.random.default_rng(4)
        n = 1500
        market = pd.Series(rng.normal(0.0003, 0.010, n))
        smb = pd.Series(rng.normal(0.0001, 0.006, n))
        hml = pd.Series(rng.normal(0.0000, 0.005, n))
        stock = 1.15 * market + 0.60 * smb - 0.30 * hml + pd.Series(rng.normal(0, 0.004, n))

        fit = multifactor.fit_multifactor(stock, {"market": market, "smb": smb, "hml": hml})
        assert fit.betas["market"] == pytest.approx(1.15, abs=0.05)
        assert fit.betas["smb"] == pytest.approx(0.60, abs=0.06)
        assert fit.betas["hml"] == pytest.approx(-0.30, abs=0.07)
        assert fit.alpha == pytest.approx(0.0, abs=0.001)

    def test_omitting_a_correlated_factor_biases_the_remaining_loading(self):
        """Why the joint fit is not four univariate fits.

        This is the concrete reason `_multifactor_features` runs one regression
        instead of reusing the four separate `scl_*` fits: drop a correlated
        factor and the surviving loading absorbs it.
        """
        rng = np.random.default_rng(5)
        n = 2000
        market = pd.Series(rng.normal(0.0003, 0.010, n))
        # Deliberately correlated with the market, as ^RUT and ^GSPC are.
        smb = 0.7 * market + pd.Series(rng.normal(0, 0.004, n))
        stock = 1.0 * market + 0.8 * smb + pd.Series(rng.normal(0, 0.003, n))

        joint = multifactor.fit_multifactor(stock, {"market": market, "smb": smb})
        alone = multifactor.fit_multifactor(stock, {"market": market})

        assert joint.betas["market"] == pytest.approx(1.0, abs=0.05)
        # The univariate fit picks up the market beta plus 0.8 x 0.7 of SMB.
        assert alone.betas["market"] > 1.4

    def test_adjusted_r_squared_charges_for_every_added_factor(self):
        """Adding a column can only raise raw R-squared; adjusted pays for it.

        Stated as the identity rather than as "adjusted must fall on junk",
        which is *not* guaranteed -- adjusted R-squared only falls when the
        added factor's |t| < 1, so a lucky noise draw can raise it. The
        reliable property is that the penalty exists and grows with the factor
        count, and that is what makes the adjusted figure the one to read when
        comparing models of different width.
        """
        rng = np.random.default_rng(6)
        n = 300
        market = pd.Series(rng.normal(0.0003, 0.01, n))
        noise = pd.Series(rng.normal(0, 0.01, n))
        stock = 1.1 * market + pd.Series(rng.normal(0, 0.006, n))

        one = multifactor.fit_multifactor(stock, {"market": market})
        two = multifactor.fit_multifactor(stock, {"market": market, "junk": noise})

        # Raw R-squared never falls when a column is added.
        assert two.r_squared >= one.r_squared - 1e-12
        # Adjusted always sits below raw, and the shortfall is larger for the
        # wider model on the same rows.
        assert one.adj_r_squared < one.r_squared
        assert two.adj_r_squared < two.r_squared
        assert (two.r_squared - two.adj_r_squared) > (one.r_squared - one.adj_r_squared)

    def test_a_junk_factor_earns_an_insignificant_loading(self):
        """The honest test of a useless factor: its t-statistic, not R-squared.

        Chapter 10's closing caution is that empirically chosen factors can
        look explanatory in-sample. The defence is significance testing, which
        is why `MultiFactorResult` carries standard errors at all.
        """
        rng = np.random.default_rng(6)
        n = 300
        market = pd.Series(rng.normal(0.0003, 0.01, n))
        noise = pd.Series(rng.normal(0, 0.01, n))
        stock = 1.1 * market + pd.Series(rng.normal(0, 0.006, n))

        fit = multifactor.fit_multifactor(stock, {"market": market, "junk": noise})
        assert abs(fit.tstat("market")) > 10
        assert abs(fit.tstat("junk")) < 2

    def test_too_few_observations_for_the_factor_count_raises(self):
        with pytest.raises(ValueError, match="at least"):
            multifactor.fit_multifactor(
                pd.Series([0.1, 0.2, 0.3]),
                {"a": pd.Series([0.1, 0.2, 0.3]), "b": pd.Series([0.2, 0.1, 0.3])},
            )

    def test_smb_proxy_is_the_spread_not_the_level(self):
        small = pd.Series([0.02, -0.01, 0.03])
        big = pd.Series([0.01, -0.02, 0.01])
        assert list(multifactor.smb_proxy(small, big).round(10)) == [0.01, 0.01, 0.02]


class TestChapter11EventStudy:
    """Chapter 11 -- the EMH, event studies, and anomalies."""

    def test_example_11_3_abnormal_return(self):
        """alpha 0.05%, beta 0.8, market +1%, stock +2% -> abnormal 1.15%."""
        assert event_study.abnormal_return(0.02, 0.01, 0.0005, 0.8) == pytest.approx(0.0115)

    def test_example_11_3_expected_return_step(self):
        """The intermediate step the chapter prints: 0.85%."""
        expected = 0.0005 + 0.8 * 0.01
        assert expected == pytest.approx(0.0085)

    def test_size_effect_spread_matches_f3(self):
        """F3: 7.65% per year, smallest NYSE decile over largest, 1926-2015."""
        assert event_study.SIZE_EFFECT_SPREAD == pytest.approx(0.0765)

    def test_car_sums_the_abnormal_returns(self):
        stock = pd.Series([0.02, 0.01, -0.005])
        market = pd.Series([0.01, 0.01, 0.00])
        window = event_study.cumulative_abnormal_return(stock, market, 0.0005, 0.8)
        # 0.0115 + 0.0015 - 0.0055
        assert window.car == pytest.approx(0.0075, abs=1e-9)
        assert window.n_days == 3

    def test_car_is_zero_when_the_stock_moves_exactly_as_predicted(self):
        """An efficient, uneventful stretch produces no abnormal return."""
        market = pd.Series([0.01, -0.005, 0.02, 0.0])
        stock = 0.0005 + 0.8 * market
        window = event_study.cumulative_abnormal_return(stock, market, 0.0005, 0.8)
        assert window.car == pytest.approx(0.0, abs=1e-12)

    def test_momentum_skips_the_most_recent_month(self):
        """The 12-1 specification must ignore the last 21 bars entirely.

        A price series that is flat for a year and then spikes in the final
        month has zero momentum by this measure -- that spike is the short-term
        reversal effect, which points the other way.
        """
        flat = [100.0] * 260
        spiked = flat[:-21] + [180.0] * 21
        assert event_study.momentum_12_1(pd.Series(spiked)) == pytest.approx(0.0, abs=1e-9)

    def test_momentum_reads_the_year_before_last_month(self):
        rising = [100.0 * (1.001 ** i) for i in range(300)]
        assert event_study.momentum_12_1(pd.Series(rising)) > 0

    def test_momentum_needs_a_full_year_plus_the_skip(self):
        assert np.isnan(event_study.momentum_12_1(pd.Series([100.0] * 100)))

    def test_reversal_sign_is_flipped_so_positive_predicts_a_rebound(self):
        """A stock that fell in years 2-3 back should score positive."""
        # Falls over the [-757, -253] span, then flat.
        falling = [100.0 * (0.999 ** i) for i in range(505)] + [60.0] * 300
        assert event_study.long_horizon_reversal(pd.Series(falling)) > 0

    def test_reversal_needs_three_years(self):
        assert np.isnan(event_study.long_horizon_reversal(pd.Series([100.0] * 500)))


class TestChapter12Technical:
    """Chapter 12 -- behavioural finance and technical analysis."""

    def test_royal_dutch_shell_fair_ratio(self):
        """A 60/40 profit split implies a fair price ratio of exactly 1.5."""
        assert technical.parity_ratio(60, 40) == pytest.approx(1.5)

    def test_royal_dutch_shell_february_1993_premium(self):
        """Royal Dutch traded about 10% above parity in February 1993."""
        assert technical.parity_premium(1.65, 1.5) == pytest.approx(0.10, abs=1e-9)

    def test_royal_dutch_shell_premium_widened_to_seventeen_percent(self):
        """The premium widened before it reversed -- fundamental risk, made
        concrete. An arbitrageur right in 1993 lost money until 1999."""
        assert technical.parity_premium(1.755, 1.5) == pytest.approx(0.17, abs=1e-9)

    def test_moving_average_matches_f2(self):
        prices = pd.Series([10.0, 12.0, 14.0, 16.0, 18.0])
        assert technical.moving_average(prices, 3).iloc[-1] == pytest.approx(16.0)

    def test_moving_average_is_trailing_never_centred(self):
        """A centred average would see the future. The first n-1 values must be NaN."""
        ma = technical.moving_average(pd.Series(range(10), dtype=float), 4)
        assert ma.iloc[:3].isna().all()
        assert ma.iloc[3] == pytest.approx(1.5)

    def test_crossover_state_reads_the_chapter_example(self):
        """A falling stock whose price then jumps above its average -> +1."""
        falling = pd.Series([100.0 - i for i in range(60)])
        assert technical.ma_crossover_state(falling, 50) == -1.0
        recovered = pd.concat([falling, pd.Series([200.0])], ignore_index=True)
        assert technical.ma_crossover_state(recovered, 50) == 1.0

    def test_crossover_age_counts_days_since_the_cross(self):
        falling = pd.Series([100.0 - i for i in range(60)])
        # Three bars above the average after a long stretch below it.
        series = pd.concat([falling, pd.Series([200.0, 201.0, 202.0])], ignore_index=True)
        assert technical.ma_crossover_age(series, 50) == pytest.approx(3.0)

    def test_crossover_age_saturates_rather_than_returning_nan(self):
        """No cross in a year is a real observation about a persistent trend,
        not missing data -- imputing it would replace an extreme with a median."""
        rising = pd.Series([100.0 * (1.002 ** i) for i in range(400)])
        assert technical.ma_crossover_age(rising, 50, max_lookback=252) == 252.0

    def test_relative_strength_is_the_return_difference(self):
        stock = pd.Series([100.0 * (1.002 ** i) for i in range(100)])
        bench = pd.Series([100.0 * (1.001 ** i) for i in range(100)])
        rs = technical.relative_strength(stock, bench, 63)
        assert rs == pytest.approx(63 * (np.log(1.002) - np.log(1.001)), abs=1e-9)

    def test_relative_strength_is_zero_against_itself(self):
        prices = pd.Series([100.0 * (1.003 ** i) for i in range(100)])
        assert technical.relative_strength(prices, prices, 63) == pytest.approx(0.0, abs=1e-12)

    def test_trin_above_one_is_bearish(self):
        """F3: heavier volume in declining issues than advancing ones."""
        assert technical.trin(1_000_000, 100, 3_000_000, 100) == pytest.approx(3.0)
        assert technical.trin(3_000_000, 100, 1_000_000, 100) == pytest.approx(1 / 3)

    def test_trin_is_nan_rather_than_dividing_by_zero(self):
        assert np.isnan(technical.trin(0, 100, 1_000_000, 100))
