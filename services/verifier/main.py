# Copyright AGNTCY Contributors
# SPDX-License-Identifier: Apache-2.0

import logging
from typing import List, Optional
from shared.schemas import (
    ClassificationResult,
    ClassificationRequest,
    VerificationReport,
    VerificationConfig,
    VerificationStatus,
    VerificationTest,
    VerificationRecommendation,
    VerificationTestResult
)
from .confidence_gate import ConfidenceGate
from .ensemble_vote import EnsembleVoter
from .augmentation_test import AugmentationStabilityTester

logger = logging.getLogger(__name__)


class Verifier:
    """
    Main verifier combining all verification mechanisms.
    """

    def __init__(self, config: Optional[VerificationConfig] = None):
        self.config = config or VerificationConfig()

        # Initialize verification mechanisms
        self.confidence_gate = ConfidenceGate(
            pass_threshold=self.config.confidence_threshold
        )
        self.ensemble_voter = EnsembleVoter(
            agreement_threshold=self.config.ensemble_agreement_threshold
        )
        self.augmentation_tester = AugmentationStabilityTester(
            stability_threshold=self.config.augmentation_stability_threshold
        )

    async def verify(
        self,
        results: List[ClassificationResult],
        request: ClassificationRequest,
        agent_url: Optional[str] = None,
        slim_client: Optional[any] = None
    ) -> VerificationReport:
        """
        Verify classification results using configured mechanisms.

        Args:
            results: List of classification results (1+ agents)
            request: Original classification request
            agent_url: Agent URL for augmentation testing
            slim_client: SLIM client for augmentation testing

        Returns:
            VerificationReport with pass/fail status and recommendation
        """
        tests_performed: List[VerificationTest] = []
        primary_result = results[0] if results else None

        if not primary_result:
            return VerificationReport(
                request_id=request.request_id,
                status=VerificationStatus.FAIL,
                tests_performed=[],
                recommendation=VerificationRecommendation.ABORT,
                notes="No results to verify"
            )

        # Test 1: Confidence gating (always run)
        conf_test = self.confidence_gate.verify(primary_result)
        tests_performed.append(conf_test)

        # Test 2: Ensemble voting (if multiple results)
        disagreement_analysis = None
        if len(results) > 1 and self.config.enable_ensemble_voting:
            ensemble_test, disagreement_analysis = self.ensemble_voter.verify(results)
            tests_performed.append(ensemble_test)

        # Test 3: Augmentation stability (if enabled)
        if self.config.enable_augmentation_test and agent_url and slim_client:
            aug_test = await self.augmentation_tester.verify(
                primary_result,
                agent_url,
                request.image.presigned_url,
                slim_client
            )
            tests_performed.append(aug_test)

        # Determine overall status and recommendation
        status, recommendation, notes = self._aggregate_results(tests_performed)

        return VerificationReport(
            request_id=request.request_id,
            status=status,
            tests_performed=tests_performed,
            primary_result=primary_result.model_dump(),
            ensemble_results=[r.model_dump() for r in results] if len(results) > 1 else None,
            disagreement_analysis=disagreement_analysis,
            recommendation=recommendation,
            notes=notes
        )

    def _aggregate_results(
        self,
        tests: List[VerificationTest]
    ) -> tuple[VerificationStatus, VerificationRecommendation, str]:
        """
        Aggregate test results into overall status and recommendation.

        Returns:
            Tuple of (status, recommendation, notes)
        """
        # Check if all tests passed
        failed_tests = [t for t in tests if t.result == VerificationTestResult.FAIL]
        passed_tests = [t for t in tests if t.result == VerificationTestResult.PASS]

        if not failed_tests:
            return (
                VerificationStatus.PASS,
                VerificationRecommendation.ACCEPT,
                f"All {len(passed_tests)} verification tests passed."
            )

        # Determine recommendation based on which tests failed
        recommendations = []
        for test in failed_tests:
            rec = test.details.get("recommendation")
            if rec:
                recommendations.append(rec)

        # Priority order for recommendations
        if VerificationRecommendation.HUMAN_REVIEW in recommendations:
            final_recommendation = VerificationRecommendation.HUMAN_REVIEW
        elif VerificationRecommendation.REPLAN_ENSEMBLE in recommendations:
            final_recommendation = VerificationRecommendation.REPLAN_ENSEMBLE
        elif VerificationRecommendation.REPLAN_DIFFERENT_AGENTS in recommendations:
            final_recommendation = VerificationRecommendation.REPLAN_DIFFERENT_AGENTS
        else:
            final_recommendation = VerificationRecommendation.ABORT

        notes = f"{len(failed_tests)} test(s) failed: {[t.test_name for t in failed_tests]}"

        return (VerificationStatus.FAIL, final_recommendation, notes)

    def get_ensemble_result(self, results: List[ClassificationResult]) -> ClassificationResult:
        """Get combined result from ensemble"""
        return self.ensemble_voter.get_ensemble_result(results)
