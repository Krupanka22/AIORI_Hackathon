"""
AIORI - Identity Resolution Service
Core module: resolves device identity across IPv6 address changes using behavioral similarity.
"""

from typing import Optional, Dict
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database.models import (
    DeviceProfile,
    AddressAssociation,
    TrafficStats,
    Device,
)


class IdentityResolver:
    """
    The central identity-resolution module.

    When a new IPv6 address appears on the network:
    1. Capture its traffic (via TrafficMonitor)
    2. Extract behavioral features (via FeatureExtractor)
    3. Generate its behavioral fingerprint (via FingerprintEngine)
    4. Compare it with all existing device profiles
    5. Calculate similarity scores
    6. If similarity exceeds threshold -> associate with existing profile
    7. Otherwise -> create new profile or mark as uncertain

    IMPORTANT: Does not use ground-truth device IDs in the resolution algorithm.
    Ground truth is stored only for evaluation purposes.
    """

    def __init__(self):
        self._similarity_threshold = settings.similarity_threshold
        self._uncertainty_threshold = 0.5  # Below this, identity is "uncertain"

    async def resolve(
        self,
        ipv6_address: str,
        db: AsyncSession,
        force: bool = False,
    ) -> Dict:
        """
        Attempt to resolve the identity of a device at the given IPv6 address.

        Returns a dict with resolution results.
        """
        from services.ai_fingerprint import fingerprint_engine
        from services.feature_extractor import feature_extractor

        # Check if this address is already associated
        if not force:
            existing = await db.execute(
                select(AddressAssociation).where(
                    AddressAssociation.ipv6_address == ipv6_address
                )
            )
            assoc = existing.scalar_one_or_none()
            if assoc:
                return {
                    "ipv6_address": ipv6_address,
                    "matched_profile_id": assoc.profile_id,
                    "similarity_score": assoc.similarity_score,
                    "confidence": assoc.confidence,
                    "is_new_profile": False,
                    "resolution_method": "cached",
                }

        # Get the latest feature vector for this address
        result = await db.execute(
            select(TrafficStats)
            .where(TrafficStats.ipv6_address == ipv6_address)
            .where(TrafficStats.feature_vector.isnot(None))
            .order_by(TrafficStats.window_end.desc())
            .limit(5)
        )
        stats_list = list(result.scalars().all())

        if not stats_list:
            return {
                "ipv6_address": ipv6_address,
                "matched_profile_id": None,
                "similarity_score": 0.0,
                "confidence": 0.0,
                "is_new_profile": False,
                "resolution_method": "insufficient_data",
            }

        # Average the feature vectors for more stable comparison
        import numpy as np

        vectors = [s.feature_vector for s in stats_list if s.feature_vector]
        if not vectors:
            return {
                "ipv6_address": ipv6_address,
                "matched_profile_id": None,
                "similarity_score": 0.0,
                "confidence": 0.0,
                "is_new_profile": False,
                "resolution_method": "no_features",
            }

        avg_vector = np.mean(vectors, axis=0).tolist()

        # Generate fingerprint for the new address
        new_fingerprint = fingerprint_engine.generate_fingerprint(avg_vector)

        # Compare with all existing profiles
        all_profiles_result = await db.execute(
            select(DeviceProfile).where(DeviceProfile.is_active == True)
        )
        all_profiles = list(all_profiles_result.scalars().all())

        best_match = None
        best_similarity = 0.0

        for profile in all_profiles:
            if not profile.fingerprint:
                continue

            profile_features = profile.fingerprint.get(
                "normalized_features",
                profile.fingerprint.get("raw_features", []),
            )
            if not profile_features or len(profile_features) != len(avg_vector):
                continue

            new_features = new_fingerprint.get(
                "normalized_features",
                new_fingerprint.get("raw_features", avg_vector),
            )

            similarity = fingerprint_engine.compute_similarity(
                new_features, profile_features
            )

            if similarity > best_similarity:
                best_similarity = similarity
                best_match = profile

        # Decision logic
        now = datetime.now(timezone.utc)

        if best_match and best_similarity >= self._similarity_threshold:
            # High confidence match
            confidence = best_similarity

            # Associate the address with the matching profile
            association = AddressAssociation(
                profile_id=best_match.id,
                ipv6_address=ipv6_address,
                similarity_score=best_similarity,
                confidence=confidence,
                resolution_method="behavioral_similarity",
            )

            # Try to find ground truth for evaluation
            device_result = await db.execute(
                select(Device).where(Device.current_ipv6 == ipv6_address)
            )
            device = device_result.scalar_one_or_none()
            if device:
                association.ground_truth_device_id = device.id

            db.add(association)

            # Update profile
            best_match.total_addresses += 1
            best_match.last_seen = now
            await fingerprint_engine.update_profile_fingerprint(
                best_match, avg_vector, db
            )

            await db.flush()

            from services.blockchain_service import blockchain_service
            await blockchain_service.record_identity_link(
                profile_id=best_match.id,
                ipv6_address=ipv6_address,
                fingerprint=best_match.fingerprint,
                db=db,
            )

            # Broadcast event
            from api.websocket import broadcast_identity_resolution
            await broadcast_identity_resolution({
                "ipv6_address": ipv6_address,
                "profile_id": best_match.id,
                "profile_label": best_match.label,
                "similarity": best_similarity,
                "confidence": confidence,
                "action": "matched",
            })

            logger.info(
                f"Identity resolved: {ipv6_address} -> {best_match.label} "
                f"(similarity={best_similarity:.3f})"
            )

            return {
                "ipv6_address": ipv6_address,
                "matched_profile_id": best_match.id,
                "similarity_score": round(best_similarity, 4),
                "confidence": round(confidence, 4),
                "is_new_profile": False,
                "resolution_method": "behavioral_similarity",
            }

        elif best_similarity >= self._uncertainty_threshold:
            # Uncertain match -- record but flag
            logger.warning(
                f"Uncertain identity for {ipv6_address}: "
                f"best similarity={best_similarity:.3f} (threshold={self._similarity_threshold})"
            )

            return {
                "ipv6_address": ipv6_address,
                "matched_profile_id": best_match.id if best_match else None,
                "similarity_score": round(best_similarity, 4),
                "confidence": round(best_similarity * 0.5, 4),
                "is_new_profile": False,
                "resolution_method": "uncertain",
            }

        else:
            # No match -- create new profile
            new_profile = DeviceProfile(
                label=f"Unknown-{ipv6_address[-8:]}",
                fingerprint=new_fingerprint,
                confidence=0.5,
                total_addresses=1,
            )
            db.add(new_profile)
            await db.flush()

            association = AddressAssociation(
                profile_id=new_profile.id,
                ipv6_address=ipv6_address,
                similarity_score=0.0,
                confidence=0.5,
                resolution_method="new_profile",
            )
            db.add(association)
            await db.flush()

            from services.blockchain_service import blockchain_service
            await blockchain_service.record_profile_created(
                profile_id=new_profile.id,
                fingerprint=new_profile.fingerprint,
                db=db,
            )

            logger.info(f"New profile created for {ipv6_address}: {new_profile.id}")

            from api.websocket import broadcast_identity_resolution
            await broadcast_identity_resolution({
                "ipv6_address": ipv6_address,
                "profile_id": new_profile.id,
                "profile_label": new_profile.label,
                "similarity": 0.0,
                "confidence": 0.5,
                "action": "new_profile",
            })

            return {
                "ipv6_address": ipv6_address,
                "matched_profile_id": new_profile.id,
                "similarity_score": 0.0,
                "confidence": 0.5,
                "is_new_profile": True,
                "resolution_method": "new_profile",
            }

    async def evaluate_accuracy(self, db: AsyncSession) -> Dict:
        """
        Evaluate identity resolution accuracy using ground truth.
        Only uses ground_truth_device_id from AddressAssociation records.
        """
        result = await db.execute(
            select(AddressAssociation).where(
                AddressAssociation.ground_truth_device_id.isnot(None)
            )
        )
        associations = list(result.scalars().all())

        if not associations:
            return {"error": "No ground-truth data available."}

        total = len(associations)
        correct = 0
        false_positives = 0
        false_negatives = 0

        for assoc in associations:
            # Get the device that actually owns this address
            dev_result = await db.execute(
                select(Device).where(Device.id == assoc.ground_truth_device_id)
            )
            actual_device = dev_result.scalar_one_or_none()
            if not actual_device or not actual_device.profile_id:
                continue

            if assoc.profile_id == actual_device.profile_id:
                correct += 1
            else:
                if assoc.resolution_method == "new_profile":
                    false_negatives += 1  # Failed to match existing
                else:
                    false_positives += 1  # Matched wrong profile

        accuracy = correct / total if total > 0 else 0.0
        fpr = false_positives / total if total > 0 else 0.0
        fnr = false_negatives / total if total > 0 else 0.0

        return {
            "total_associations": total,
            "correct": correct,
            "false_positives": false_positives,
            "false_negatives": false_negatives,
            "accuracy": round(accuracy, 4),
            "false_positive_rate": round(fpr, 4),
            "false_negative_rate": round(fnr, 4),
        }


# Singleton instance
identity_resolver = IdentityResolver()
