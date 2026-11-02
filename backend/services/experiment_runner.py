"""
AIORI - Experiment Runner Service
Orchestrates end-to-end experiments: traffic generation, capture, feature extraction,
identity resolution, and anomaly detection.
"""

import asyncio
from typing import Dict, Optional
from datetime import datetime, timezone

from loguru import logger

from config import settings
from database.db import async_session_factory
from database.models import Experiment, ExperimentStatus


class ExperimentRunner:
    """
    Runs coordinated experiments that exercise the full monitoring pipeline.

    Experiment types:
    - normal_traffic: Generate normal device traffic and monitor
    - ipv6_rotation: Generate traffic, rotate addresses, attempt re-identification
    - anomaly_injection: Inject anomalous traffic patterns and test detection
    - attack_test: Run controlled attack traffic and classify
    - full_pipeline: Complete end-to-end test of all components
    """

    def __init__(self):
        self._active_experiments: Dict[str, asyncio.Task] = {}

    async def run_experiment(
        self,
        experiment_id: str,
        experiment_type: str,
        config: Optional[dict] = None,
    ):
        """Launch an experiment in the background."""
        task = asyncio.create_task(
            self._execute(experiment_id, experiment_type, config or {})
        )
        self._active_experiments[experiment_id] = task

    async def stop_experiment(self, experiment_id: str):
        """Stop a running experiment."""
        task = self._active_experiments.pop(experiment_id, None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        logger.info(f"Experiment {experiment_id} stopped.")

    async def _execute(
        self,
        experiment_id: str,
        experiment_type: str,
        config: dict,
    ):
        """Execute the experiment pipeline."""
        results = {"steps": [], "errors": []}

        try:
            if experiment_type == "normal_traffic":
                results = await self._run_normal_traffic(config)
            elif experiment_type == "ipv6_rotation":
                results = await self._run_ipv6_rotation(config)
            elif experiment_type == "anomaly_injection":
                results = await self._run_anomaly_injection(config)
            elif experiment_type == "attack_test":
                results = await self._run_attack_test(config)
            elif experiment_type == "full_pipeline":
                results = await self._run_full_pipeline(config)
            else:
                results["errors"].append(f"Unknown experiment type: {experiment_type}")

            final_status = ExperimentStatus.COMPLETED
        except asyncio.CancelledError:
            results["steps"].append("Experiment cancelled.")
            final_status = ExperimentStatus.CANCELLED
            raise
        except Exception as e:
            logger.error(f"Experiment {experiment_id} failed: {e}")
            results["errors"].append(str(e))
            final_status = ExperimentStatus.FAILED

        # Update experiment record
        async with async_session_factory() as db:
            from sqlalchemy import select

            result = await db.execute(
                select(Experiment).where(Experiment.id == experiment_id)
            )
            experiment = result.scalar_one_or_none()
            if experiment:
                experiment.status = final_status
                experiment.results = results
                experiment.completed_at = datetime.now(timezone.utc)
                await db.commit()

        self._active_experiments.pop(experiment_id, None)
        logger.info(f"Experiment {experiment_id} finished: {final_status.value}")

    async def _run_normal_traffic(self, config: dict) -> dict:
        """Generate normal traffic from all running devices and capture it."""
        from services.device_manager import device_manager
        from services.traffic_generator import traffic_generator
        from services.traffic_monitor import traffic_monitor
        from services.feature_extractor import feature_extractor

        steps = []
        duration = config.get("duration_seconds", 30)
        window = config.get("feature_window_seconds", settings.feature_window_seconds)

        # Step 1: Start traffic capture
        async with async_session_factory() as db:
            capture_result = await traffic_monitor.start_capture(
                duration_seconds=duration + 5
            )
            steps.append({"step": "start_capture", "result": capture_result})

            # Step 2: Generate traffic
            gen_result = await traffic_generator.generate(
                device_id=None,
                duration_seconds=duration,
                traffic_type=config.get("traffic_type", "normal"),
                db=db,
            )
            steps.append({"step": "generate_traffic", "result": gen_result})
            await db.commit()

        # Step 3: Wait for traffic to complete
        await asyncio.sleep(duration + 3)

        # Step 4: Stop capture and process
        await traffic_monitor.stop_capture()
        steps.append({"step": "stop_capture", "result": "completed"})

        async with async_session_factory() as db:
            process_result = await traffic_monitor.process_latest_pcap(db=db)
            steps.append({"step": "process_pcap", "result": process_result})

            # Step 5: Extract features
            features = await feature_extractor.extract_features_for_all_devices(
                window_seconds=window, db=db
            )
            steps.append({
                "step": "extract_features",
                "result": f"Extracted features for {len(features)} devices",
            })
            await db.commit()

        return {"steps": steps, "errors": []}

    async def _run_ipv6_rotation(self, config: dict) -> dict:
        """Test identity resolution across IPv6 address changes."""
        from services.device_manager import device_manager
        from services.traffic_generator import traffic_generator
        from services.traffic_monitor import traffic_monitor
        from services.feature_extractor import feature_extractor
        from services.ipv6_manager import ipv6_manager
        from services.identity_resolver import identity_resolver

        steps = []
        duration = config.get("traffic_duration_seconds", 20)
        window = config.get("feature_window_seconds", settings.feature_window_seconds)
        target_device_id = config.get("device_id", None)

        # Phase 1: Generate pre-rotation traffic
        async with async_session_factory() as db:
            gen_result = await traffic_generator.generate(
                device_id=target_device_id,
                duration_seconds=duration,
                traffic_type="normal",
                db=db,
            )
            steps.append({"step": "pre_rotation_traffic", "result": gen_result})
            await db.commit()

        await asyncio.sleep(duration + 2)

        # Phase 2: Extract pre-rotation features
        async with async_session_factory() as db:
            features_before = await feature_extractor.extract_features_for_all_devices(
                window_seconds=window, db=db
            )
            steps.append({
                "step": "pre_rotation_features",
                "result": f"Extracted features for {len(features_before)} devices",
            })
            await db.commit()

        # Phase 3: Rotate IPv6 addresses
        async with async_session_factory() as db:
            rotation_result = await ipv6_manager.trigger_rotation(
                device_id=target_device_id, db=db
            )
            steps.append({"step": "ipv6_rotation", "result": rotation_result})
            await db.commit()

        # Phase 4: Generate post-rotation traffic
        async with async_session_factory() as db:
            gen_result2 = await traffic_generator.generate(
                device_id=target_device_id,
                duration_seconds=duration,
                traffic_type="normal",
                db=db,
            )
            steps.append({"step": "post_rotation_traffic", "result": gen_result2})
            await db.commit()

        await asyncio.sleep(duration + 2)

        # Phase 5: Extract post-rotation features
        async with async_session_factory() as db:
            features_after = await feature_extractor.extract_features_for_all_devices(
                window_seconds=window, db=db
            )
            steps.append({
                "step": "post_rotation_features",
                "result": f"Extracted features for {len(features_after)} devices",
            })

            # Phase 6: Attempt identity resolution on new addresses
            running = device_manager.get_running_devices()
            resolution_results = []
            for did, info in running.items():
                if target_device_id and did != target_device_id:
                    continue
                ipv6 = info.get("ipv6_addr")
                if ipv6:
                    res = await identity_resolver.resolve(ipv6, db, force=True)
                    resolution_results.append(res)

            steps.append({
                "step": "identity_resolution",
                "result": resolution_results,
            })

            # Phase 7: Evaluate accuracy
            accuracy = await identity_resolver.evaluate_accuracy(db)
            steps.append({"step": "accuracy_evaluation", "result": accuracy})
            await db.commit()

        return {"steps": steps, "errors": []}

    async def _run_anomaly_injection(self, config: dict) -> dict:
        """Inject anomalous traffic and test detection."""
        from services.device_manager import device_manager
        from services.traffic_generator import traffic_generator
        from services.feature_extractor import feature_extractor
        from services.anomaly_detector import anomaly_detector

        steps = []
        anomaly_type = config.get("anomaly_type", "flood")
        duration = config.get("duration_seconds", 10)
        target_device_id = config.get("device_id", None)

        running = device_manager.get_running_devices()
        if target_device_id and target_device_id not in running:
            return {"steps": [], "errors": ["Target device not running."]}

        target = target_device_id or (list(running.keys())[0] if running else None)
        if not target:
            return {"steps": [], "errors": ["No running devices."]}

        # Step 1: Generate anomalous traffic
        anomaly_result = await traffic_generator.generate_anomalous_traffic(
            device_id=target,
            anomaly_type=anomaly_type,
            duration_seconds=duration,
        )
        steps.append({"step": "inject_anomaly", "result": anomaly_result})

        await asyncio.sleep(duration + 2)

        # Step 2: Extract features
        async with async_session_factory() as db:
            features = await feature_extractor.extract_features_for_all_devices(
                window_seconds=settings.feature_window_seconds, db=db
            )
            steps.append({
                "step": "extract_features",
                "result": f"Extracted features for {len(features)} devices",
            })

            # Step 3: Run anomaly detection
            alerts = await anomaly_detector.check_all_devices(db)
            steps.append({
                "step": "anomaly_detection",
                "result": f"Generated {len(alerts)} alerts",
                "alerts": [
                    {
                        "severity": a.severity.value,
                        "category": a.category,
                        "explanation": a.explanation,
                    }
                    for a in alerts
                ],
            })
            await db.commit()

        return {"steps": steps, "errors": []}

    async def _run_attack_test(self, config: dict) -> dict:
        """Run controlled attack traffic and classify it."""
        from services.device_manager import device_manager
        from services.traffic_generator import traffic_generator
        from services.attack_analyzer import attack_analyzer

        steps = []
        attack_type = config.get("attack_type", "flood")
        duration = config.get("duration_seconds", 10)
        target_device_id = config.get("device_id", None)

        running = device_manager.get_running_devices()
        target = target_device_id or (list(running.keys())[0] if running else None)
        if not target:
            return {"steps": [], "errors": ["No running devices."]}

        # Generate attack traffic
        attack_result = await traffic_generator.generate_anomalous_traffic(
            device_id=target,
            anomaly_type=attack_type,
            duration_seconds=duration,
        )
        steps.append({"step": "generate_attack", "result": attack_result})

        await asyncio.sleep(duration + 2)

        # Analyze traffic
        async with async_session_factory() as db:
            from sqlalchemy import select
            from database.models import ConnectionLog

            recent_logs = await db.execute(
                select(ConnectionLog)
                .order_by(ConnectionLog.timestamp.desc())
                .limit(200)
            )
            connections = list(recent_logs.scalars().all())

            analysis = await attack_analyzer.analyze_traffic_pattern(
                device_id=target,
                connection_data=connections,
                db=db,
            )
            steps.append({"step": "attack_analysis", "result": analysis})
            await db.commit()

        return {"steps": steps, "errors": []}

    async def _run_full_pipeline(self, config: dict) -> dict:
        """Run the complete end-to-end pipeline."""
        steps = []

        # Phase 1: Normal traffic
        logger.info("Full pipeline: Phase 1 - Normal traffic")
        normal_result = await self._run_normal_traffic(
            {"duration_seconds": config.get("traffic_duration", 20)}
        )
        steps.append({"phase": "normal_traffic", "result": normal_result})

        # Phase 2: IPv6 rotation and re-identification
        logger.info("Full pipeline: Phase 2 - IPv6 rotation")
        rotation_result = await self._run_ipv6_rotation(
            {"traffic_duration_seconds": config.get("traffic_duration", 15)}
        )
        steps.append({"phase": "ipv6_rotation", "result": rotation_result})

        # Phase 3: Anomaly injection
        logger.info("Full pipeline: Phase 3 - Anomaly injection")
        anomaly_result = await self._run_anomaly_injection(
            {"anomaly_type": "flood", "duration_seconds": 10}
        )
        steps.append({"phase": "anomaly_injection", "result": anomaly_result})

        # Phase 4: Train AI model (if enough data)
        logger.info("Full pipeline: Phase 4 - AI training")
        async with async_session_factory() as db:
            from services.ai_fingerprint import fingerprint_engine

            train_result = await fingerprint_engine.train(db)
            steps.append({"phase": "ai_training", "result": train_result})
            await db.commit()

        return {"steps": steps, "errors": []}


# Singleton instance
experiment_runner = ExperimentRunner()
