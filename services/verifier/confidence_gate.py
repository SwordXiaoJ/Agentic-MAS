# Copyright AGNTCY Contributors
# SPDX-License-Identifier: Apache-2.0

import logging
from shared.schemas import (
    ClassificationResult,
    VerificationTest,
    VerificationTestResult,
    VerificationRecommendation
)

logger = logging.getLogger(__name__)


class ConfidenceGate:
    """Confidence-based verification mechanism"""

    def __init__(self, pass_threshold: float = 0.75, uncertain_threshold: float = 0.6):
        self.pass_threshold = pass_threshold
        self.uncertain_threshold = uncertain_threshold

    def verify(self, result: ClassificationResult) -> VerificationTest:
        """
        Verify classification result based on confidence threshold.

        Returns:
            VerificationTest with pass/fail status and recommendation
        """
        confidence = result.confidence

        if confidence >= self.pass_threshold:
            return VerificationTest(
                test_name="confidence_threshold",
                result=VerificationTestResult.PASS,
                details={
                    "threshold": self.pass_threshold,
                    "actual": confidence,
                    "recommendation": VerificationRecommendation.ACCEPT
                }
            )

        elif confidence >= self.uncertain_threshold:
            return VerificationTest(
                test_name="confidence_threshold",
                result=VerificationTestResult.FAIL,
                details={
                    "threshold": self.pass_threshold,
                    "actual": confidence,
                    "recommendation": VerificationRecommendation.REPLAN_ENSEMBLE,
                    "reason": f"Confidence {confidence:.3f} below threshold {self.pass_threshold}. Suggest ensemble."
                }
            )

        else:
            return VerificationTest(
                test_name="confidence_threshold",
                result=VerificationTestResult.FAIL,
                details={
                    "threshold": self.pass_threshold,
                    "actual": confidence,
                    "recommendation": VerificationRecommendation.HUMAN_REVIEW,
                    "reason": f"Very low confidence {confidence:.3f}. Manual review required."
                }
            )
