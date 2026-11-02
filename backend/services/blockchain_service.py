"""
AIORI - Blockchain Service
Interface to Hyperledger Fabric for tamper-evident identity audit records.

NOTE: The actual Hyperledger Fabric network is deployed separately (Phase 8).
This service provides the integration layer and falls back to local SHA-256
hashed records when the blockchain network is unavailable.
"""

import hashlib
import json
from typing import Optional, Dict
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database.models import BlockchainRecord, DeviceProfile, AddressAssociation


class BlockchainService:
    """
    Manages blockchain audit records for device identity events.

    When Hyperledger Fabric is enabled, records are submitted to the ledger.
    When disabled, records are stored locally with SHA-256 integrity hashes
    that can later be migrated to the blockchain.

    Stored data (privacy-aware):
    - Pseudonymous profile ID (not device name or real identity)
    - IPv6 address association record
    - Timestamp
    - Fingerprint digest (hash of behavioral fingerprint, not raw features)
    - Event type (identity_linked, profile_created, anomaly_detected, etc.)
    """

    def __init__(self):
        self._enabled = settings.blockchain_enabled

    def _compute_fingerprint_digest(self, fingerprint: Optional[dict]) -> str:
        """Compute SHA-256 digest of a behavioral fingerprint."""
        if not fingerprint:
            return "none"
        raw = json.dumps(fingerprint, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()

    def _compute_record_hash(self, data: dict) -> str:
        """Compute an integrity hash for a record."""
        canonical = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode()).hexdigest()

    async def record_identity_link(
        self,
        profile_id: str,
        ipv6_address: str,
        fingerprint: Optional[dict],
        db: AsyncSession,
    ) -> BlockchainRecord:
        """Record an identity-address association event."""
        fingerprint_digest = self._compute_fingerprint_digest(fingerprint)

        recorded_at = datetime.now(timezone.utc)
        record_data = {
            "profile_id": profile_id,
            "ipv6_address": ipv6_address,
            "event_type": "identity_linked",
            "fingerprint_digest": fingerprint_digest,
            "timestamp": recorded_at.isoformat(),
        }

        tx_hash = self._compute_record_hash(record_data)

        if self._enabled:
            # Submit to Hyperledger Fabric
            tx_hash = await self._submit_to_fabric(record_data)

        record = BlockchainRecord(
            profile_id=profile_id,
            ipv6_address=ipv6_address,
            event_type="identity_linked",
            fingerprint_digest=fingerprint_digest,
            transaction_hash=tx_hash,
            is_verified=not self._enabled,  # Local records auto-verified
            recorded_at=recorded_at,
            raw_data=record_data,
        )
        db.add(record)
        await db.flush()

        logger.info(
            f"Blockchain record: identity_linked "
            f"profile={profile_id} addr={ipv6_address}"
        )
        return record

    async def record_profile_created(
        self,
        profile_id: str,
        fingerprint: Optional[dict],
        db: AsyncSession,
    ) -> BlockchainRecord:
        """Record a new profile creation event."""
        fingerprint_digest = self._compute_fingerprint_digest(fingerprint)

        recorded_at = datetime.now(timezone.utc)
        record_data = {
            "profile_id": profile_id,
            "event_type": "profile_created",
            "fingerprint_digest": fingerprint_digest,
            "timestamp": recorded_at.isoformat(),
        }
        tx_hash = self._compute_record_hash(record_data)

        if self._enabled:
            tx_hash = await self._submit_to_fabric(record_data)

        record = BlockchainRecord(
            profile_id=profile_id,
            event_type="profile_created",
            fingerprint_digest=fingerprint_digest,
            transaction_hash=tx_hash,
            is_verified=not self._enabled,
            recorded_at=recorded_at,
            raw_data=record_data,
        )
        db.add(record)
        await db.flush()

        return record

    async def record_anomaly_detected(
        self,
        profile_id: str,
        ipv6_address: Optional[str],
        anomaly_summary: str,
        db: AsyncSession,
    ) -> BlockchainRecord:
        """Record an anomaly detection event."""
        recorded_at = datetime.now(timezone.utc)
        fingerprint_digest = hashlib.sha256(anomaly_summary.encode()).hexdigest()
        record_data = {
            "profile_id": profile_id,
            "ipv6_address": ipv6_address or "",
            "event_type": "anomaly_detected",
            "fingerprint_digest": fingerprint_digest,
            "timestamp": recorded_at.isoformat(),
        }
        tx_hash = self._compute_record_hash(record_data)

        if self._enabled:
            tx_hash = await self._submit_to_fabric(record_data)

        record = BlockchainRecord(
            profile_id=profile_id,
            ipv6_address=ipv6_address,
            event_type="anomaly_detected",
            fingerprint_digest=fingerprint_digest,
            transaction_hash=tx_hash,
            is_verified=not self._enabled,
            recorded_at=recorded_at,
            raw_data=record_data,
        )
        db.add(record)
        await db.flush()

        return record

    async def verify_record(self, record: BlockchainRecord) -> Dict:
        """Verify the integrity of a blockchain record."""
        if not record.transaction_hash:
            return {
                "record_id": record.id,
                "verified": False,
                "reason": "No transaction hash available.",
            }

        # Reconstruct expected hash
        record_data = record.raw_data or {
            "profile_id": record.profile_id,
            "ipv6_address": record.ipv6_address or "",
            "event_type": record.event_type,
            "fingerprint_digest": record.fingerprint_digest or "",
            "timestamp": record.recorded_at.isoformat() if record.recorded_at else "",
        }

        if self._enabled:
            # Verify against Hyperledger Fabric ledger
            return await self._verify_on_fabric(record)
        else:
            # Local verification using hash
            expected_hash = self._compute_record_hash(record_data)
            is_valid = record.transaction_hash == expected_hash

            record.is_verified = is_valid
            return {
                "record_id": record.id,
                "verified": is_valid,
                "transaction_hash": record.transaction_hash,
                "method": "local_hash_verification",
                "note": (
                    "Verified locally using SHA-256 hash integrity. "
                    "Full blockchain verification available when "
                    "Hyperledger Fabric is enabled."
                ),
            }

    async def get_audit_trail(
        self,
        profile_id: str,
        db: AsyncSession,
    ) -> list:
        """Get the complete audit trail for a profile."""
        result = await db.execute(
            select(BlockchainRecord)
            .where(BlockchainRecord.profile_id == profile_id)
            .order_by(BlockchainRecord.recorded_at)
        )
        records = result.scalars().all()

        return [
            {
                "id": r.id,
                "event_type": r.event_type,
                "ipv6_address": r.ipv6_address,
                "fingerprint_digest": r.fingerprint_digest,
                "transaction_hash": r.transaction_hash,
                "is_verified": r.is_verified,
                "recorded_at": r.recorded_at.isoformat() if r.recorded_at else None,
            }
            for r in records
        ]

    async def _submit_to_fabric(self, data: dict) -> str:
        """
        Submit a record to Hyperledger Fabric.
        This is a placeholder for the actual HLF SDK integration (Phase 8).
        """
        raise RuntimeError(
            "Hyperledger Fabric integration is enabled but no Fabric Gateway "
            "client is configured. Set BLOCKCHAIN_ENABLED=false for local "
            "integrity records or configure the Fabric network first."
        )

    async def _verify_on_fabric(self, record: BlockchainRecord) -> dict:
        """
        Verify a record against the Hyperledger Fabric ledger.
        Placeholder for Phase 8 implementation.
        """
        logger.warning(
            "Hyperledger Fabric verification not yet implemented."
        )
        return {
            "record_id": record.id,
            "verified": False,
            "reason": "Fabric verification pending deployment.",
        }


# Singleton instance
blockchain_service = BlockchainService()
