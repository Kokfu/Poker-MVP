"""Decision-time stress test of one action from a frozen river shadow trace."""

from research.holdem.reply_forecast import reply_geometry


REGRET_STRESS_BB = 2.0
MARGIN_CHANGE_BB = 1.0
CLOSING_ODDS_FACTOR = 2.0


def diagnose(estimate, scenarios, selected):
    """Compare the selected action with the best other action in each model."""
    alternatives = sorted(estimate.keys() - {selected})
    if not alternatives:
        return {"flagged": False, "reasons": [], "alternative_count": 0}

    def margin(values):
        return values[selected] - max(values[key] for key in alternatives)

    nominal = margin(estimate)
    margins = {name: margin(values) for name, values in scenarios.items()}
    reasons = [name for name, stressed in margins.items()
               if stressed <= -REGRET_STRESS_BB and nominal - stressed >= MARGIN_CHANGE_BB]
    return {
        "flagged": bool(reasons), "reasons": reasons, "alternative_count": len(alternatives),
        "nominal_advantage_bb": nominal, "scenario_advantage_bb": margins,
        "worst_stress_regret_bb": max(0., -min(margins.values(), default=nominal)),
        "stress_selected_status_change_fraction": (
            sum((gap < 0) != (nominal < 0) for gap in margins.values()) / len(margins) if margins else None),
    }


def evaluate(model, estimate, scenarios, reply_summary, closing_values, selected_index):
    labels = tuple(estimate)
    selected = labels[selected_index]
    result = diagnose(estimate, {**scenarios, **closing_values}, selected)
    action, _ = model.menu[selected_index]
    kind, target = model.root.actions[selected_index]
    child = model.root.children[selected_index]
    passive = [estimate[label] for label, (move, _) in zip(labels, model.root.actions, strict=True)
               if move in ("fold", "check", "call")]
    reply = reply_summary["coach"].get(child)
    if (kind in ("bet", "raise", "all_in") and passive and reply
            and "fold" in (reply["actions"] or {})):
        node = model.nodes[child]
        price = reply_geometry(node.state)
        # Villain folds immediately. Hero recovers any uncalled chips.
        fold_ev = (node.state.pot - (target - model.decision.hero_street_commitment)) / model.decision.big_blind
        fold_probability = reply["actions"]["fold"]
        if fold_probability < 1.:
            nonfold_ev = (estimate[selected] - fold_probability * fold_ev) / (1. - fold_probability)
            if nonfold_ev < max(passive) < fold_ev:
                threshold = (max(passive) - nonfold_ev) / (fold_ev - nonfold_ev)
                result["fold_break_even"] = {"forecast": fold_probability, "threshold": threshold,
                                             "margin": fold_probability - threshold,
                                             "collectible_cost_bb": price.cost / model.decision.big_blind}
    result.update(action=action, river_reply_observations=sum(model.counts))
    return result
