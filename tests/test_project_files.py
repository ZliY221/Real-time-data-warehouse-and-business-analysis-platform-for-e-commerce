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

    def test_compose_uses_pinned_clickhouse_with_local_only_ports(self) -> None:
        self.assertIn(
            "image: clickhouse/clickhouse-server:25.8.33.6",
            self.compose_text,
        )
        self.assertIn('"127.0.0.1:8123:8123"', self.compose_text)
        self.assertIn('"127.0.0.1:9000:9000"', self.compose_text)
        self.assertNotIn("clickhouse/clickhouse-server:latest", self.compose_text)

    def test_clickhouse_schema_uses_replay_safe_replacement_semantics(self) -> None:
        schema = (
            self.root / "infra" / "clickhouse" / "init" / "001_schema.sql"
        ).read_text(encoding="utf-8")
        self.assertIn("ReplacingMergeTree(version)", schema)
        self.assertIn("ORDER BY (window_start, region, channel)", schema)
        self.assertIn("FROM ecommerce.minute_metrics FINAL", schema)
        self.assertNotIn("SummingMergeTree", schema)

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

    def test_required_clickhouse_scripts_exist(self) -> None:
        names = {
            "clickhouse-up.ps1",
            "clickhouse-query.ps1",
            "clickhouse-smoke-test.ps1",
        }
        actual_names = {path.name for path in (self.root / "scripts").glob("*.ps1")}
        self.assertTrue(names.issubset(actual_names))
        smoke_test = (
            self.root / "scripts" / "clickhouse-smoke-test.ps1"
        ).read_text(encoding="utf-8")
        self.assertIn("FROM $testTable FINAL", smoke_test)
        self.assertIn("Expected one deduplicated metric row", smoke_test)

    def test_query_api_dependencies_and_start_script_are_pinned(self) -> None:
        pyproject = (self.root / "pyproject.toml").read_text(encoding="utf-8")
        api_script = (self.root / "scripts" / "api-up.ps1").read_text(encoding="utf-8")
        self.assertIn('"fastapi==0.142.2"', pyproject)
        self.assertIn('"uvicorn==0.54.0"', pyproject)
        self.assertIn('"httpx2==2.13.1"', pyproject)
        self.assertIn('"metrics_api.app:app"', api_script)
        self.assertIn('"127.0.0.1"', api_script)

    def test_query_api_uses_bound_clickhouse_parameters(self) -> None:
        repository = (self.root / "src" / "metrics_api" / "repository.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("{region:String}", repository)
        self.assertIn("{channel:String}", repository)
        self.assertIn("{limit:UInt32}", repository)
        self.assertIn('query_parameters[f"param_{name}"]', repository)

    def test_dashboard_uses_pinned_echarts_with_integrity_and_accessible_charts(self) -> None:
        dashboard = self.root / "dashboard" / "static"
        html = (dashboard / "index.html").read_text(encoding="utf-8")
        javascript = (dashboard / "app.js").read_text(encoding="utf-8")
        css = (dashboard / "styles.css").read_text(encoding="utf-8")
        self.assertIn("echarts@6.1.0/dist/echarts.min.js", html)
        self.assertIn("sha384-C2iskrW/", html)
        self.assertIn('aria: {', javascript)
        self.assertIn('decal: { show: true }', javascript)
        self.assertIn("ResizeObserver", javascript)
        self.assertIn("prefers-reduced-motion", css)
        self.assertIn("@media (prefers-color-scheme: dark)", css)

    def test_ci_and_unified_script_run_dashboard_tests(self) -> None:
        workflow = (self.root / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )
        test_all = (self.root / "scripts" / "test-all.ps1").read_text(encoding="utf-8")
        self.assertIn("node --test dashboard/tests/data.test.mjs", workflow)
        self.assertIn('Get-Command "node"', test_all)
        self.assertIn('"dashboard\\tests\\data.test.mjs"', test_all)

    def test_data_quality_gate_is_wired_into_local_and_ci_verification(self) -> None:
        workflow = (self.root / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )
        test_all = (self.root / "scripts" / "test-all.ps1").read_text(encoding="utf-8")
        for content in (workflow, test_all):
            self.assertIn("python -m data_quality.cli", content.replace("& $runtimePython @runtimePythonArguments", "python"))
            self.assertIn("data/sample/order_events.ndjson", content)
            self.assertIn("config/data-quality-rules.json", content)

    def test_quality_issue_fixture_covers_every_configured_rule_type(self) -> None:
        config = (self.root / "config" / "data-quality-rules.json").read_text(
            encoding="utf-8"
        )
        fixture = (
            self.root / "data" / "quality" / "order_events_with_quality_issues.ndjson"
        ).read_text(encoding="utf-8")
        for rule_type in (
            "contract",
            "completeness",
            "uniqueness",
            "range",
            "timeliness",
            "distribution",
        ):
            self.assertIn(f'"type": "{rule_type}"', config)
        self.assertIn("evt_quality_001", fixture)
        self.assertIn('"total_amount":"20000.00"', fixture)
        self.assertIn('"ingest_time":"2026-10-02T10:02:12Z"', fixture)

    def test_dashboard_preview_is_explicitly_marked_as_non_production_data(self) -> None:
        preview_script = (self.root / "scripts" / "dashboard-preview.ps1").read_text(
            encoding="utf-8"
        )
        preview_repository = (
            self.root / "src" / "metrics_api" / "preview.py"
        ).read_text(encoding="utf-8")
        dashboard = (
            self.root / "dashboard" / "static" / "index.html"
        ).read_text(encoding="utf-8")
        self.assertIn("Preview data only", preview_script)
        self.assertIn('data_mode="preview"', preview_repository)
        self.assertIn('id="preview-banner"', dashboard)
        self.assertIn("内存演示数据", dashboard)

    def test_ci_workflow_uses_least_privilege_and_pinned_actions(self) -> None:
        workflow = (self.root / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("contents: read", workflow)
        self.assertIn("actions/checkout@v6", workflow)
        self.assertIn("actions/setup-python@v5", workflow)
        self.assertIn("actions/setup-java@v4", workflow)
        self.assertIn('pip install --disable-pip-version-check -e ".[api,test]"', workflow)
        self.assertIn("python -W error -m unittest", workflow)
        self.assertNotIn("@main", workflow)
        self.assertNotIn("@master", workflow)

    def test_ci_runs_all_four_verification_layers(self) -> None:
        workflow = (self.root / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("python-tests:", workflow)
        self.assertIn("flink-tests:", workflow)
        self.assertIn("kafka-smoke-test:", workflow)
        self.assertIn("clickhouse-smoke-test:", workflow)
        self.assertIn("needs: [python-tests, flink-tests]", workflow)
        self.assertIn("if: ${{ always() }}", workflow)

    def test_flink_kafka_source_dependency_and_entrypoint_are_pinned(self) -> None:
        pom = (self.root / "flink-job" / "pom.xml").read_text(encoding="utf-8")
        job = (
            self.root
            / "flink-job"
            / "src"
            / "main"
            / "java"
            / "com"
            / "zhangliyang"
            / "portfolio"
            / "job"
            / "KafkaOrderMetricsJob.java"
        ).read_text(encoding="utf-8")
        self.assertIn("<flink.version>1.20.1</flink.version>", pom)
        self.assertIn(
            "<flink.kafka.connector.version>3.3.0-1.20</flink.kafka.connector.version>",
            pom,
        )
        self.assertIn(
            "<flink.jdbc.connector.version>3.4.0-1.20</flink.jdbc.connector.version>",
            pom,
        )
        self.assertIn(
            "<clickhouse.jdbc.version>0.10.0</clickhouse.jdbc.version>",
            pom,
        )
        self.assertIn("KafkaSource<String>", job)
        self.assertIn("CheckpointingMode.EXACTLY_ONCE", job)
        self.assertIn("WatermarkStrategy.noWatermarks()", job)


if __name__ == "__main__":
    unittest.main()

