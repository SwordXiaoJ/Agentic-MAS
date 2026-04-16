# Copyright AGNTCY Contributors
# SPDX-License-Identifier: Apache-2.0

import logging
from typing import List, Dict
from shared.schemas import (
    ClassificationResult,
    VerificationTest,
    VerificationTestResult,
    VerificationRecommendation,
    DisagreementAnalysis
)

logger = logging.getLogger(__name__)


class EnsembleVoter:
    """Ensemble voting verification mechanism"""

    def __init__(self, agreement_threshold: float = 0.67):
        self.agreement_threshold = agreement_threshold

    def verify(self, results: List[ClassificationResult]) -> tuple[VerificationTest, DisagreementAnalysis]:
        """
        Verify ensemble of classification results.

        Args:
            results: List of classification results from multiple agents

        Returns:
            Tuple of (VerificationTest, DisagreementAnalysis)
        """
        if len(results) < 2:
            return VerificationTest(
                test_name="ensemble_voting",
                result=VerificationTestResult.SKIP,
                details={"reason": "Less than 2 results, ensemble not applicable"}
            ), None

        # Count votes for each label
        label_votes: Dict[str, int] = {}
        label_confidences: Dict[str, List[float]] = {}

        for result in results:
            label = result.label
            label_votes[label] = label_votes.get(label, 0) + 1
            if label not in label_confidences:
                label_confidences[label] = []
            label_confidences[label].append(result.confidence)

        total_votes = len(results)
        max_votes = max(label_votes.values())
        agreement_rate = max_votes / total_votes

        # Get majority label
        majority_label = max(label_votes, key=label_votes.get)

        # Create disagreement analysis
        disagreement = DisagreementAnalysis(
            agreement_rate=agreement_rate,
            conflicting_labels=list(label_votes.keys()),
            vote_distribution=label_votes
        )

        # Check if agreement meets threshold
        if agreement_rate >= self.agreement_threshold:
            # Calculate confidence-weighted average for majority label
            avg_confidence = sum(label_confidences[majority_label]) / len(label_confidences[majority_label])

            return VerificationTest(
                test_name="ensemble_voting",
                result=VerificationTestResult.PASS,
                details={
                    "agreement_rate": agreement_rate,
                    "agreement_threshold": self.agreement_threshold,
                    "majority_label": majority_label,
                    "votes": f"{max_votes}/{total_votes}",
                    "avg_confidence": avg_confidence,
                    "recommendation": VerificationRecommendation.ACCEPT,
                    "note": f"{max_votes}/{total_votes} agents agreed on '{majority_label}'"
                }
            ), disagreement

        else:
            return VerificationTest(
                test_name="ensemble_voting",
                result=VerificationTestResult.FAIL,
                details={
                    "agreement_rate": agreement_rate,
                    "agreement_threshold": self.agreement_threshold,
                    "vote_distribution": label_votes,
                    "recommendation": VerificationRecommendation.HUMAN_REVIEW,
                    "reason": f"No majority. Disagreement: {label_votes}"
                }
            ), disagreement

    def get_ensemble_result(self, results: List[ClassificationResult]) -> ClassificationResult:
        """
        Get final result from ensemble (majority vote with averaged confidence).

        Args:
            results: List of classification results

        Returns:
            Combined classification result
        """
        # Count votes
        label_votes: Dict[str, int] = {}
        label_confidences: Dict[str, List[float]] = {}

        for result in results:
            label = result.label
            label_votes[label] = label_votes.get(label, 0) + 1
            if label not in label_confidences:
                label_confidences[label] = []
            label_confidences[label].append(result.confidence)

        # Get majority label
        majority_label = max(label_votes, key=label_votes.get)
        avg_confidence = sum(label_confidences[majority_label]) / len(label_confidences[majority_label])

        # Use first result as template and update label/confidence
        ensemble_result = results[0].model_copy(deep=True)
        ensemble_result.label = majority_label
        ensemble_result.confidence = avg_confidence
        ensemble_result.agent_id = "ensemble"

        return ensemble_result
