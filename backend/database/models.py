"""
AIORI Database Models
SQLAlchemy ORM models for SQLite database.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    Boolean,
    DateTime,
    Text,
    ForeignKey,
    JSON,
    Enum as SAEnum,
)
from sqlalchemy.orm import relationship, DeclarativeBase
import enum


class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


# --- Enums ---

class DeviceType(str, enum.Enum):
    CCTV_CAMERA = "cctv_camera"
    TEMPERATURE_SENSOR = "temperature_sensor"
    SMART_DOOR_LOCK = "smart_door_lock"
    SMART_LIGHT = "smart_light"
    MOTION_SENSOR = "motion_sensor"


class DeviceStatus(str, enum.Enum):
    CREATED = "created"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


class AlertSeverity(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ExperimentStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# --- Utility ---

def generate_uuid() -> str:
    return str(uuid.uuid4())


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# --- Models ---

class Device(Base):
    """Virtual IoT device record."""
    __tablename__ = "devices"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(128), nullable=False, unique=True)
    device_type = Column(SAEnum(DeviceType), nullable=False)
    status = Column(SAEnum(DeviceStatus), default=DeviceStatus.CREATED, nullable=False)
    profile_id = Column(String(36), ForeignKey("device_profiles.id"), nullable=True)
    current_ipv6 = Column(String(64), nullable=True)
    network_interface = Column(String(32), nullable=True)
    namespace_name = Column(String(64), nullable=True)
    traffic_config = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    # Relationships
    profile = relationship("DeviceProfile", back_populates="devices")
    ipv6_history = relationship("IPv6AddressRecord", back_populates="device", cascade="all, delete-orphan")
    traffic_stats = relationship("TrafficStats", back_populates="device", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Device(id={self.id}, name={self.name}, type={self.device_type})>"


class DeviceProfile(Base):
    """
    Pseudonymous behavioral profile for a device.
    This is the identity-resolution anchor -- not tied to any single IPv6 address.
    """
    __tablename__ = "device_profiles"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    label = Column(String(128), nullable=True)
    device_type_prediction = Column(SAEnum(DeviceType), nullable=True)
    fingerprint = Column(JSON, nullable=True)  # Behavioral fingerprint vector
    baseline_features = Column(JSON, nullable=True)  # Baseline behavioral features
    confidence = Column(Float, default=0.0, nullable=False)
    first_seen = Column(DateTime, default=utc_now, nullable=False)
    last_seen = Column(DateTime, default=utc_now, nullable=False)
    total_addresses = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    # Relationships
    devices = relationship("Device", back_populates="profile")
    address_associations = relationship(
        "AddressAssociation", back_populates="profile", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<DeviceProfile(id={self.id}, label={self.label})>"


class IPv6AddressRecord(Base):
    """Historical record of IPv6 addresses assigned to devices."""
    __tablename__ = "ipv6_address_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    device_id = Column(String(36), ForeignKey("devices.id"), nullable=False)
    ipv6_address = Column(String(64), nullable=False)
    address_type = Column(String(32), default="slaac")  # slaac, privacy, manual
    assigned_at = Column(DateTime, default=utc_now, nullable=False)
    expired_at = Column(DateTime, nullable=True)
    is_current = Column(Boolean, default=True, nullable=False)

    # Relationships
    device = relationship("Device", back_populates="ipv6_history")

    def __repr__(self):
        return f"<IPv6AddressRecord(device={self.device_id}, addr={self.ipv6_address})>"


class AddressAssociation(Base):
    """
    Identity-resolution result: links an observed IPv6 address to a behavioral profile.
    """
    __tablename__ = "address_associations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    profile_id = Column(String(36), ForeignKey("device_profiles.id"), nullable=False)
    ipv6_address = Column(String(64), nullable=False)
    similarity_score = Column(Float, nullable=False)
    confidence = Column(Float, nullable=False)
    resolution_method = Column(String(64), default="behavioral_similarity")
    resolved_at = Column(DateTime, default=utc_now, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    ground_truth_device_id = Column(String(36), nullable=True)  # For evaluation only

    # Relationships
    profile = relationship("DeviceProfile", back_populates="address_associations")

    def __repr__(self):
        return (
            f"<AddressAssociation(profile={self.profile_id}, "
            f"addr={self.ipv6_address}, score={self.similarity_score})>"
        )


class TrafficStats(Base):
    """Aggregated traffic statistics for a device in a time window."""
    __tablename__ = "traffic_stats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    device_id = Column(String(36), ForeignKey("devices.id"), nullable=False)
    ipv6_address = Column(String(64), nullable=True)
    window_start = Column(DateTime, nullable=False)
    window_end = Column(DateTime, nullable=False)
    window_seconds = Column(Integer, nullable=False)

    # Feature columns
    total_packets = Column(Integer, default=0)
    total_bytes = Column(Integer, default=0)
    avg_packet_size = Column(Float, default=0.0)
    avg_inter_arrival_time = Column(Float, default=0.0)
    packet_frequency = Column(Float, default=0.0)
    upload_bytes = Column(Integer, default=0)
    download_bytes = Column(Integer, default=0)
    upload_download_ratio = Column(Float, default=0.0)
    tcp_packets = Column(Integer, default=0)
    udp_packets = Column(Integer, default=0)
    icmpv6_packets = Column(Integer, default=0)
    tcp_udp_ratio = Column(Float, default=0.0)
    unique_destinations = Column(Integer, default=0)
    avg_connection_duration = Column(Float, default=0.0)
    connection_count = Column(Integer, default=0)
    periodicity_score = Column(Float, default=0.0)
    duty_cycle = Column(Float, default=0.0)

    # Raw feature vector (for ML)
    feature_vector = Column(JSON, nullable=True)

    # Relationships
    device = relationship("Device", back_populates="traffic_stats")

    def __repr__(self):
        return (
            f"<TrafficStats(device={self.device_id}, "
            f"window={self.window_start}-{self.window_end})>"
        )


class ConnectionLog(Base):
    """Parsed Zeek connection log entry."""
    __tablename__ = "connection_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    zeek_uid = Column(String(64), nullable=True)
    timestamp = Column(DateTime, nullable=False)
    src_ipv6 = Column(String(64), nullable=False)
    dst_ipv6 = Column(String(64), nullable=False)
    src_port = Column(Integer, nullable=True)
    dst_port = Column(Integer, nullable=True)
    protocol = Column(String(16), nullable=False)
    duration = Column(Float, nullable=True)
    orig_bytes = Column(Integer, nullable=True)
    resp_bytes = Column(Integer, nullable=True)
    orig_pkts = Column(Integer, nullable=True)
    resp_pkts = Column(Integer, nullable=True)
    conn_state = Column(String(16), nullable=True)
    service = Column(String(64), nullable=True)
    raw_log = Column(Text, nullable=True)

    def __repr__(self):
        return (
            f"<ConnectionLog(src={self.src_ipv6}, dst={self.dst_ipv6}, "
            f"proto={self.protocol})>"
        )


class SecurityAlert(Base):
    """Security anomaly alert."""
    __tablename__ = "security_alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    profile_id = Column(String(36), nullable=True)
    device_id = Column(String(36), nullable=True)
    current_ipv6 = Column(String(64), nullable=True)
    severity = Column(SAEnum(AlertSeverity), nullable=False)
    category = Column(String(64), nullable=False)
    anomaly_score = Column(Float, nullable=True)
    observed_value = Column(Text, nullable=True)
    expected_baseline = Column(Text, nullable=True)
    explanation = Column(Text, nullable=False)
    is_acknowledged = Column(Boolean, default=False, nullable=False)
    detected_at = Column(DateTime, default=utc_now, nullable=False)

    def __repr__(self):
        return (
            f"<SecurityAlert(severity={self.severity}, "
            f"category={self.category})>"
        )


class BlockchainRecord(Base):
    """Local mirror of blockchain audit records."""
    __tablename__ = "blockchain_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    profile_id = Column(String(36), nullable=False)
    ipv6_address = Column(String(64), nullable=True)
    event_type = Column(String(64), nullable=False)
    fingerprint_digest = Column(String(128), nullable=True)
    transaction_hash = Column(String(256), nullable=True)
    block_number = Column(Integer, nullable=True)
    is_verified = Column(Boolean, default=False, nullable=False)
    recorded_at = Column(DateTime, default=utc_now, nullable=False)
    raw_data = Column(JSON, nullable=True)

    def __repr__(self):
        return (
            f"<BlockchainRecord(profile={self.profile_id}, "
            f"event={self.event_type})>"
        )


class Experiment(Base):
    """Experiment tracking record."""
    __tablename__ = "experiments"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(256), nullable=False)
    description = Column(Text, nullable=True)
    experiment_type = Column(String(64), nullable=False)
    status = Column(SAEnum(ExperimentStatus), default=ExperimentStatus.PENDING)
    config = Column(JSON, nullable=True)
    results = Column(JSON, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    def __repr__(self):
        return f"<Experiment(id={self.id}, name={self.name}, status={self.status})>"
