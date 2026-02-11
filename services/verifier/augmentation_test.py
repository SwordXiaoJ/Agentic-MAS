# Copyright AGNTCY Contributors
# SPDX-License-Identifier: Apache-2.0

import logging
from typing import List, Optional
from shared.schemas import (
    ClassificationResult,
    VerificationTest,
    VerificationTestResult,
    VerificationRecommendation
)
from shared.utils.image_transforms import ImageTransformer, apply_transforms_to_url

logger = logging.getLogger(__name__)


class AugmentationStabilityTester:
    """Augmentation stability verification mechanism"""

    def __init__(self, stability_threshold: float = 0.67):
        self.stability_threshold = stability_threshold
        self.transformer = ImageTransformer()

    async def verify(
        self,
        result: ClassificationResult,
        agent_url: str,
        image_presigned_url: str,
        slim_client: Optional[any] = None
    ) -> VerificationTest:
        """
        Test if classification is stable under augmentations.

        Args:
            result: Original classification result
            agent_url: Agent URL for re-classification
            image_presigned_url: Presigned URL of original image
            slim_client: SLIM client for sending tasks

        Returns:
            VerificationTest with stability results
        """
        # For MVP, we'll implement a simplified version
        # In production, this would:
        # 1. Download image from presigned URL
        # 2. Apply transforms
        # 3. Re-upload transformed images
        # 4. Send to agent for re-classification
        # 5. Compare results

        # Simplified implementation: Skip if no SLIM client
        if slim_client is None:
            return VerificationTest(
                test_name="augmentation_stability",
                result=VerificationTestResult.SKIP,
                details={
                    "reason": "Augmentation test not configured (requires SLIM client)",
                    "recommendation": VerificationRecommendation.ACCEPT
                }
            )

        try:
            # Get standard augmentations
            transform_names = self.transformer.get_standard_augmentations()

            # Apply transforms to image
            transformed_images = await apply_transforms_to_url(
                image_presigned_url,
                transform_names
            )

            # Re-classify each transformed image
            stable_count = 0
            results = []

            for b64_image, transform_name in transformed_images:
                # Send to agent
                task = {
                    "request_id": f"{result.request_id}-aug-{transform_name}",
                    "image": {
                        "bytes": b64_image,
                        "format": "jpeg"
                    },
                    "prompt": "Classify image",
                    "constraints": {
                        "timeout_ms": 5000,
                        "return_top_k": 1
                    }
                }

                try:
                    aug_result = await slim_client.send_task(agent_url, task)
                    results.append({
                        "transform": transform_name,
                        "label": aug_result.get("label"),
                        "confidence": aug_result.get("confidence")
                    })

                    if aug_result.get("label") == result.label:
                        stable_count += 1

                except Exception as e:
                    logger.warning(f"Failed to re-classify with {transform_name}: {e}")

            # Calculate stability rate
            stability_rate = stable_count / len(transform_names) if transform_names else 0.0

            if stability_rate >= self.stability_threshold:
                return VerificationTest(
                    test_name="augmentation_stability",
                    result=VerificationTestResult.PASS,
                    details={
                        "stability_rate": stability_rate,
                        "stability_threshold": self.stability_threshold,
                        "stable_count": f"{stable_count}/{len(transform_names)}",
                        "transforms_applied": transform_names,
                        "results": results,
                        "recommendation": VerificationRecommendation.ACCEPT,
                        "note": f"Label '{result.label}' stable under {stable_count}/{len(transform_names)} transforms"
                    }
                )
            else:
                return VerificationTest(
                    test_name="augmentation_stability",
                    result=VerificationTestResult.FAIL,
                    details={
                        "stability_rate": stability_rate,
                        "stability_threshold": self.stability_threshold,
                        "stable_count": f"{stable_count}/{len(transform_names)}",
                        "results": results,
                        "recommendation": VerificationRecommendation.REPLAN_DIFFERENT_AGENTS,
                        "reason": f"Unstable predictions. Only {stable_count}/{len(transform_names)} preserved label."
                    }
                )

        except Exception as e:
            logger.error(f"Error in augmentation stability test: {e}")
            return VerificationTest(
                test_name="augmentation_stability",
                result=VerificationTestResult.FAIL,
                details={
                    "error": str(e),
                    "recommendation": VerificationRecommendation.ACCEPT
                }
            )
