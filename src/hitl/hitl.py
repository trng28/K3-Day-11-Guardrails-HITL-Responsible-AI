"""
Lab 11 — Part 4: Human-in-the-Loop Design
  TODO 11: Confidence Router
  TODO 12: Design 3 HITL decision points
"""
import math
from dataclasses import dataclass


# ============================================================
# TODO 11: Implement ConfidenceRouter
#
# Route agent responses based on confidence scores:
#   - HIGH (>= 0.9): Auto-send to user
#   - MEDIUM (0.7 - 0.9): Queue for human review
#   - LOW (< 0.7): Escalate to human immediately
#
# Special case: if the action is HIGH_RISK (e.g., money transfer,
# account deletion), ALWAYS escalate regardless of confidence.
#
# Implement the route() method.
# ============================================================

HIGH_RISK_ACTIONS = [
    "transfer_money",
    "close_account",
    "change_password",
    "delete_data",
    "update_personal_info",
    "change_beneficiary",
    "add_beneficiary",
]


@dataclass
class RoutingDecision:
    """Result of the confidence router."""
    action: str          # "auto_send", "queue_review", "escalate"
    confidence: float
    reason: str
    priority: str        # "low", "normal", "high"
    requires_human: bool


class ConfidenceRouter:
    """Route agent responses based on confidence and risk level.

    Thresholds:
        HIGH:   confidence >= 0.9 -> auto-send
        MEDIUM: 0.7 <= confidence < 0.9 -> queue for review
        LOW:    confidence < 0.7 -> escalate to human

    High-risk actions always escalate regardless of confidence.
    """

    HIGH_THRESHOLD = 0.9
    MEDIUM_THRESHOLD = 0.7

    def route(self, response: str, confidence: float,
              action_type: str = "general") -> RoutingDecision:
        """Route a response based on confidence score and action type.

        Args:
            response: The agent's response text
            confidence: Confidence score between 0.0 and 1.0
            action_type: Type of action (e.g., "general", "transfer_money")

        Returns:
            RoutingDecision with routing action and metadata
        """
        # TODO 11: Implement routing logic
        #
        # 1. Check if action_type is in HIGH_RISK_ACTIONS
        #    -> If yes: always escalate (action="escalate", priority="high",
        #       requires_human=True, reason="High-risk action: {action_type}")
        #
        # 2. Check confidence thresholds:
        #    - confidence >= 0.9:
        #      action="auto_send", priority="low",
        #      requires_human=False, reason="High confidence"
        #
        #    - 0.7 <= confidence < 0.9:
        #      action="queue_review", priority="normal",
        #      requires_human=True, reason="Medium confidence — needs review"
        #
        #    - confidence < 0.7:
        #      action="escalate", priority="high",
        #      requires_human=True, reason="Low confidence — escalating"

        normalized_action = (
            action_type.strip().casefold() if isinstance(action_type, str) else ""
        )
        try:
            normalized_confidence = float(confidence)
        except (TypeError, ValueError):
            normalized_confidence = float("nan")

        if normalized_action in HIGH_RISK_ACTIONS:
            return RoutingDecision(
                action="escalate", confidence=normalized_confidence,
                reason=f"High-risk action requires human approval: {normalized_action}",
                priority="high", requires_human=True,
            )
        if not math.isfinite(normalized_confidence) or not (
            0.0 <= normalized_confidence <= 1.0
        ):
            return RoutingDecision(
                action="escalate", confidence=normalized_confidence,
                reason="Invalid confidence score — escalating for human review",
                priority="high", requires_human=True,
            )
        if normalized_confidence >= self.HIGH_THRESHOLD:
            return RoutingDecision(
                action="auto_send", confidence=normalized_confidence,
                reason="High confidence for a non-high-risk action",
                priority="low", requires_human=False,
            )
        if normalized_confidence >= self.MEDIUM_THRESHOLD:
            return RoutingDecision(
                action="queue_review", confidence=normalized_confidence,
                reason="Medium confidence — queued for human review",
                priority="normal", requires_human=True,
            )
        return RoutingDecision(
            action="escalate", confidence=normalized_confidence,
            reason="Low confidence — escalating to a human reviewer",
            priority="high", requires_human=True,
        )


# ============================================================
# TODO 12: Design 3 HITL decision points + a review lifecycle
#
# For each decision point, define:
# - trigger: What condition activates this HITL check?
# - hitl_model: Which model? (human-in-the-loop, human-on-the-loop,
#   human-as-tiebreaker)
# - context_needed: What info does the human reviewer need?
# - example: A concrete scenario
# - approval_path: What approve/reject/timeout decision is recorded?
# - audit_fields: Which correlation ID, intent and proposed action/diff are logged?
#
# Think about real banking scenarios where human judgment is critical.
# ============================================================

hitl_decision_points = [
    {
        "id": 1,
        "name": "Transfer or beneficiary change approval",
        "trigger": (
            "Agent proposes transfer_money, add_beneficiary, or change_beneficiary; "
            "also trigger on beneficiary mismatch or fraud/anomaly signals."
        ),
        "hitl_model": "human-in-the-loop — execution is blocked pending a reviewer",
        "context_needed": (
            "Proposed action and intent; old/new beneficiary names and account IDs; "
            "amount, currency, source account, customer confirmation, anomaly signals, "
            "destination, and a field-level diff."
        ),
        "example": (
            "Change beneficiary from Nguyen A to Nguyen B and send VND 50,000,000 "
            "after an unusual-device alert."
        ),
        "approval_path": (
            "Approve creates a scoped single-use approval for only the shown diff; "
            "reject cancels it; timeout holds the request and sends no transfer. Any "
            "changed amount or beneficiary requires a new review."
        ),
        "audit_fields": (
            "request_id, action/intent, proposed_action, old_value, new_value, amount, "
            "risk_signals, reviewer_id, reviewer_decision, reviewer_reason, timestamp, "
            "timeout_status, approval_id, layer=hitl_transfer_review"
        ),
    },
    {
        "id": 2,
        "name": "Account closure or data deletion",
        "trigger": "Agent proposes close_account or delete_data at any confidence.",
        "hitl_model": "human-in-the-loop — destructive actions cannot auto-execute",
        "context_needed": (
            "Customer identity and consent evidence, exact account/action, balance, "
            "pending payments, holds, linked products, retention duties, impact, and diff."
        ),
        "example": (
            "Close an account that still has a positive balance and pending card settlement."
        ),
        "approval_path": (
            "Approve schedules only the reviewed closure/deletion; reject leaves all "
            "accounts and data unchanged; timeout rejects safely and requires the "
            "customer to restart verification."
        ),
        "audit_fields": (
            "request_id, action/intent, proposed_action, account_id, impact/diff, "
            "consent_evidence, reviewer_id, reviewer_decision, reviewer_reason, "
            "timestamp, timeout_status, approval_id, layer=hitl_destructive_review"
        ),
    },
    {
        "id": 3,
        "name": "Credential or personal-information change",
        "trigger": (
            "Agent proposes change_password or update_personal_info, or identity/risk "
            "signals conflict with the request."
        ),
        "hitl_model": "human-in-the-loop with an identity/fraud operations reviewer",
        "context_needed": (
            "Verified identity, proposed action, masked old/new values, authentication "
            "method, recent device/account activity, risk signals, and exact field diff; "
            "never expose a raw password."
        ),
        "example": (
            "A new device changes the phone number immediately before a password reset "
            "and high-value transfer."
        ),
        "approval_path": (
            "Approve applies only reviewed fields with a scoped approval; reject keeps "
            "old values and may open a fraud case; timeout holds/rejects the change and "
            "does not update credentials or personal data."
        ),
        "audit_fields": (
            "request_id, action/intent, proposed_action, masked_diff, auth_evidence, "
            "risk_signals, reviewer_id, reviewer_decision, reviewer_reason, timestamp, "
            "timeout_status, approval_id, layer=hitl_identity_review"
        ),
    },
]


# ============================================================
# Quick tests
# ============================================================

def test_confidence_router():
    """Test ConfidenceRouter with sample scenarios."""
    router = ConfidenceRouter()

    test_cases = [
        ("Balance inquiry", 0.95, "general"),
        ("Interest rate question", 0.82, "general"),
        ("Ambiguous request", 0.55, "general"),
        ("Transfer $50,000", 0.98, "transfer_money"),
        ("Close my account", 0.91, "close_account"),
    ]

    print("Testing ConfidenceRouter:")
    print("=" * 80)
    print(f"{'Scenario':<25} {'Conf':<6} {'Action Type':<18} {'Decision':<15} {'Priority':<10} {'Human?'}")
    print("-" * 80)

    for scenario, conf, action_type in test_cases:
        decision = router.route(scenario, conf, action_type)
        print(
            f"{scenario:<25} {conf:<6.2f} {action_type:<18} "
            f"{decision.action:<15} {decision.priority:<10} "
            f"{'Yes' if decision.requires_human else 'No'}"
        )

    print("=" * 80)


def test_hitl_points():
    """Display HITL decision points."""
    print("\nHITL Decision Points:")
    print("=" * 60)
    for point in hitl_decision_points:
        print(f"\n  Decision Point #{point['id']}: {point['name']}")
        print(f"    Trigger:  {point['trigger']}")
        print(f"    Model:    {point['hitl_model']}")
        print(f"    Context:  {point['context_needed']}")
        print(f"    Example:  {point['example']}")
    print("\n" + "=" * 60)


if __name__ == "__main__":
    test_confidence_router()
    test_hitl_points()
