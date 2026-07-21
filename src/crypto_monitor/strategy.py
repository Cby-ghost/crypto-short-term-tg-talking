from __future__ import annotations

from collections import defaultdict

from .config import RiskConfig, StrategyConfig
from .models import (
    Direction,
    DivergenceKind,
    GateStatus,
    IndicatorVote,
    MarketSnapshot,
    Signal,
)


def _position_size(entry: float, stop: float, risk: RiskConfig) -> float | None:
    if risk.account_equity_usdt <= 0:
        return None
    distance = abs(entry - stop)
    if distance == 0:
        return None
    risk_budget = risk.account_equity_usdt * risk.risk_per_trade_pct / 100
    return risk_budget / distance


def _vote(name: str, score: int, reason: str, group: str) -> IndicatorVote:
    if score not in (-1, 0, 1):
        raise ValueError("普通訊號只能投 -1、0、+1")
    return IndicatorVote(name=name, score=score, reason=reason, group=group)


def build_votes(snapshot: MarketSnapshot, config: StrategyConfig) -> list[IndicatorVote]:
    votes: list[IndicatorVote] = []
    ema_gap_pct = abs(snapshot.ema_fast - snapshot.ema_slow) / snapshot.price * 100
    ema_score = 0
    ema_reason = f"EMA 快慢線差距 {ema_gap_pct:.3f}%，未達門檻"
    if ema_gap_pct >= config.ema_min_separation_pct:
        if snapshot.ema_fast > snapshot.ema_slow:
            ema_score, ema_reason = 1, "EMA 快線位於慢線上方，短線方向偏多"
        elif snapshot.ema_fast < snapshot.ema_slow:
            ema_score, ema_reason = -1, "EMA 快線位於慢線下方，短線方向偏空"
    votes.append(_vote("EMA 短線方向", ema_score, ema_reason, "trend"))

    histogram_rising = snapshot.macd_histogram > snapshot.previous_macd_histogram
    momentum_score = 0
    momentum_reason = "MACD 方向與柱體變化不一致或動能縮減"
    if snapshot.macd_histogram > 0 and histogram_rising:
        momentum_score, momentum_reason = 1, "MACD 柱為正且比上一根擴大"
    elif snapshot.macd_histogram < 0 and not histogram_rising:
        momentum_score, momentum_reason = -1, "MACD 柱為負且向下擴大"
    votes.append(_vote("MACD 動能", momentum_score, momentum_reason, "momentum"))

    divergence_score = snapshot.divergence.score if snapshot.divergence else 0
    divergence_reason = "沒有有效且已確認的標準 MACD 背離"
    if snapshot.divergence:
        item = snapshot.divergence
        if item.kind == DivergenceKind.BULLISH:
            divergence_reason = (
                "價格創更低低點，但 MACD 形成更高低點，出現底背離："
                f"價格 {item.first_price:.8g}→{item.second_price:.8g}，"
                f"MACD {item.first_macd:.6g}→{item.second_macd:.6g}，"
                f"柱體 {item.first_histogram:.6g}→{item.second_histogram:.6g}"
            )
        else:
            divergence_reason = (
                "價格創更高高點，但 MACD 形成更低高點，出現頂背離："
                f"價格 {item.first_price:.8g}→{item.second_price:.8g}，"
                f"MACD {item.first_macd:.6g}→{item.second_macd:.6g}，"
                f"柱體 {item.first_histogram:.6g}→{item.second_histogram:.6g}"
            )
    votes.append(_vote("MACD 價格背離", divergence_score, divergence_reason, "momentum"))

    threshold = config.minimum_cvd_ratio
    spot_score = (
        1
        if snapshot.flow.spot_cvd_ratio >= threshold
        else -1 if snapshot.flow.spot_cvd_ratio <= -threshold else 0
    )
    votes.append(
        _vote(
            "現貨 CVD",
            spot_score,
            f"現貨主動買賣差比率 {snapshot.flow.spot_cvd_ratio:+.2%}",
            "flow",
        )
    )
    swap_score = (
        1
        if snapshot.flow.swap_cvd_ratio >= threshold
        else -1 if snapshot.flow.swap_cvd_ratio <= -threshold else 0
    )
    votes.append(
        _vote(
            "合約 CVD",
            swap_score,
            f"合約主動買賣差比率 {snapshot.flow.swap_cvd_ratio:+.2%}",
            "flow",
        )
    )

    price_change = snapshot.price / snapshot.previous_close - 1
    cvd_divergence_score = 0
    cvd_divergence_reason = "現貨與合約 CVD 未形成有效分歧"
    if spot_score == 1 and swap_score == -1:
        if price_change >= 0:
            cvd_divergence_score = 1
            cvd_divergence_reason = "現貨 CVD 偏多、合約偏空且價格持平或上漲，可能出現現貨吸收"
        else:
            cvd_divergence_reason = "CVD 分歧但價格下跌，未確認現貨吸收"
    elif spot_score == -1 and swap_score == 1:
        if price_change <= 0:
            cvd_divergence_score = -1
            cvd_divergence_reason = "現貨 CVD 偏空、合約偏多且價格持平或下跌，可能出現現貨派發"
        else:
            cvd_divergence_reason = "CVD 分歧但價格上漲，未確認現貨派發"
    votes.append(_vote("CVD 分歧與價格反應", cvd_divergence_score, cvd_divergence_reason, "flow"))

    oi_score = 0
    if snapshot.oi_change_pct >= config.minimum_oi_change_pct:
        if price_change > 0:
            oi_score, oi_reason = 1, f"價格上漲且同一區間 OI 增加 {snapshot.oi_change_pct:.2f}%"
        elif price_change < 0:
            oi_score, oi_reason = -1, f"價格下跌且同一區間 OI 增加 {snapshot.oi_change_pct:.2f}%"
        else:
            oi_reason = f"OI 增加 {snapshot.oi_change_pct:.2f}%，但價格持平"
    elif snapshot.oi_change_pct <= -config.minimum_oi_change_pct:
        oi_reason = (
            f"價格上漲但 OI 下降 {abs(snapshot.oi_change_pct):.2f}%，可能是空單回補"
            if price_change > 0
            else (
                f"價格下跌但 OI 下降 {abs(snapshot.oi_change_pct):.2f}%，可能是多單平倉"
                if price_change < 0
                else f"OI 下降 {abs(snapshot.oi_change_pct):.2f}%"
            )
        )
    else:
        oi_reason = f"同一區間 OI 變化 {snapshot.oi_change_pct:+.2f}%，未達門檻"
    votes.append(_vote("價格 × OI", oi_score, oi_reason, "participation"))

    volume_score = 0
    volume_reason = f"相對成交量 {snapshot.volume_ratio:.2f} 倍，未達放量門檻"
    if snapshot.volume_ratio >= config.volume_spike_ratio:
        if price_change > 0:
            volume_score, volume_reason = 1, f"相對成交量 {snapshot.volume_ratio:.2f} 倍且價格上漲"
        elif price_change < 0:
            volume_score, volume_reason = -1, f"相對成交量 {snapshot.volume_ratio:.2f} 倍且價格下跌"
    votes.append(_vote("相對成交量", volume_score, volume_reason, "participation"))
    return votes


def score_groups(votes: list[IndicatorVote]) -> dict[str, int]:
    scores: dict[str, int] = defaultdict(int)
    for vote in votes:
        scores[vote.group] += vote.score
    scores["momentum"] = max(-1, min(1, scores["momentum"]))
    scores["flow"] = max(-2, min(2, scores["flow"]))
    return dict(scores)


def _cost_adjusted_rr(entry: float, distance: float, reward: float, risk: RiskConfig) -> float:
    round_trip_cost = entry * 2 * (risk.fee_rate_pct + risk.slippage_pct) / 100
    net_reward = max(0.0, reward - round_trip_cost)
    net_risk = distance + round_trip_cost
    return net_reward / net_risk if net_risk else 0.0


def evaluate_signal(
    snapshot: MarketSnapshot, config: StrategyConfig, risk: RiskConfig
) -> Signal:
    votes = build_votes(snapshot, config)
    groups = score_groups(votes)
    base_score = sum(groups.values())
    funding_adjustment = 0
    funding_warning = ""
    if base_score > 0 and snapshot.funding_rate >= config.max_abs_funding_rate:
        funding_adjustment = -1
        funding_warning = f"正資金費率 {snapshot.funding_rate:+.4%} 偏高，多方擁擠，總分扣 1"
    elif base_score < 0 and snapshot.funding_rate <= -config.max_abs_funding_rate:
        funding_adjustment = 1
        funding_warning = f"負資金費率 {snapshot.funding_rate:+.4%} 偏低，空方擁擠，總分向 0 調整 1"
    score = base_score + funding_adjustment

    if score >= config.signal_threshold:
        direction = Direction.LONG
    elif score <= -config.signal_threshold:
        direction = Direction.SHORT
    else:
        direction = Direction.NEUTRAL
    sign = 1 if score > 0 else -1 if score < 0 else 0

    ema_vote = next(vote for vote in votes if vote.name == "EMA 短線方向")
    divergence_vote = next(vote for vote in votes if vote.name == "MACD 價格背離")
    direction_confirmed = sign != 0 and (
        ema_vote.score == sign or divergence_vote.score == sign
    )
    fund_names = {"現貨 CVD", "合約 CVD", "CVD 分歧與價格反應", "價格 × OI"}
    funds_confirmed = sign != 0 and any(
        vote.name in fund_names and vote.score == sign for vote in votes
    )
    support_groups = tuple(
        group for group in ("trend", "momentum", "flow", "participation")
        if groups.get(group, 0) * sign > 0
    ) if sign else ()
    gates = GateStatus(
        direction_confirmed=direction_confirmed,
        funds_confirmed=funds_confirmed,
        independent_groups_confirmed=len(support_groups) >= 3,
        data_quality_confirmed=snapshot.data_quality.passed,
        supporting_groups=support_groups,
    )

    risk_sign = sign or 1
    distance = snapshot.atr * config.atr_stop_multiple
    if snapshot.divergence and snapshot.divergence.score == risk_sign:
        if risk_sign > 0:
            divergence_stop = snapshot.divergence.second_price - snapshot.atr * config.divergence_stop_atr_buffer
            distance = max(distance, snapshot.price - divergence_stop)
        else:
            divergence_stop = snapshot.divergence.second_price + snapshot.atr * config.divergence_stop_atr_buffer
            distance = max(distance, divergence_stop - snapshot.price)
    stop = snapshot.price - distance if risk_sign > 0 else snapshot.price + distance
    reward = distance * config.risk_reward_ratio
    take_profit = snapshot.price + reward if risk_sign > 0 else snapshot.price - reward
    cost_adjusted_rr = _cost_adjusted_rr(snapshot.price, distance, reward, risk)

    blocked: list[str] = []
    stop_distance_pct = distance / snapshot.price * 100 if snapshot.price else float("inf")
    if distance <= 0 or stop_distance_pct > risk.max_stop_distance_pct:
        blocked.append(f"停損距離 {stop_distance_pct:.2f}% 異常")
    if cost_adjusted_rr < risk.minimum_cost_adjusted_rr:
        blocked.append(f"扣除成本後盈虧比 {cost_adjusted_rr:.2f} 低於最低要求")
    if not snapshot.data_quality.passed:
        blocked.extend(snapshot.data_quality.issues or ("必要資料品質未通過",))

    aligned_reasons = tuple(vote.reason for vote in votes if sign and vote.score == sign)
    warnings = [vote.reason for vote in votes if sign and vote.score == -sign]
    warnings.extend(
        vote.reason
        for vote in votes
        if vote.score == 0 and ("回補" in vote.reason or "平倉" in vote.reason or "分歧但" in vote.reason)
    )
    if funding_warning:
        warnings.append(funding_warning)
    if snapshot.divergence:
        warnings.append("MACD 背離只表示原趨勢動能減弱，不保證立即反轉")

    invalidation = (
        "價格觸及停損，或現貨 CVD 轉為明顯負值且總分跌回門檻內。"
        if risk_sign > 0
        else "價格觸及停損，或現貨 CVD 轉為明顯正值且總分升回門檻內。"
    )
    return Signal(
        symbol=snapshot.symbol,
        direction=direction,
        score=score,
        base_score=base_score,
        funding_adjustment=funding_adjustment,
        threshold=config.signal_threshold,
        strong_threshold=config.strong_signal_threshold,
        entry=snapshot.price,
        stop_loss=stop,
        take_profit=take_profit,
        price_rr=config.risk_reward_ratio,
        cost_adjusted_rr=cost_adjusted_rr,
        reasons=aligned_reasons,
        warnings=tuple(dict.fromkeys(warnings)),
        votes=tuple(votes),
        group_scores=tuple(sorted(groups.items())),
        gates=gates,
        invalidation=invalidation,
        blocked_reasons=tuple(dict.fromkeys(blocked)),
        position_size_base=_position_size(snapshot.price, stop, risk),
    )
