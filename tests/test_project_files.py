from __future__ import annotations

from pathlib import Path
import unittest


class KafkaProjectFilesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).parents[1]
        cls.compose_text = (cls.root / "compose.yaml").read_text(encoding="utf-8")

    def test_compose_uses_a_pinned_official_kafka_image(self) -> None:
        self.assertIn("image: apache/kafka:3.9.1", self.compose_text)
        self.assertNotIn("apache/kafka:latest", self.compose_text)

    def test_compose_contains_required_kraft_configuration(self) -> None:
        required_names = {
            "CLUSTER_ID",
            "KAFKA_NODE_ID",
            "KAFKA_PROCESS_ROLES",
            "KAFKA_CONTROLLER_QUORUM_VOTERS",
            "KAFKA_CONTROLLER_LISTENER_NAMES",
            "KAFKA_INTER_BROKER_LISTENER_NAME",
            "KAFKA_LISTENER_SECURITY_PROTOCOL_MAP",
            "KAFKA_LISTENERS",
            "KAFKA_ADVERTISED_LISTENERS",
            "KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR",
            "KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR",
            "KAFKA_TRANSACTION_STATE_LOG_MIN_ISR",
            "KAFKA_LOG_DIRS",
        }
        for name in required_names:
            self.assertIn(f"{name}:", self.compose_text)

    def test_single_node_internal_topics_use_replication_factor_one(self) -> None:
        self.assertIn("KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1", self.compose_text)
        self.assertIn("KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR: 1", self.compose_text)
        self.assertIn("KAFKA_TRANSACTION_STATE_LOG_MIN_ISR: 1", self.compose_text)

    def test_required_kafka_scripts_exist(self) -> None:
        names = {
            "kafka-up.ps1",
            "kafka-produce-sample.ps1",
            "kafka-consume.ps1",
            "kafka-smoke-test.ps1",
            "kafka-down.ps1",
        }
        actual_names = {path.name for path in (self.root / "scripts").glob("*.ps1")}
        self.assertTrue(names.issubset(actual_names))


if __name__ == "__main__":
    unittest.main()

