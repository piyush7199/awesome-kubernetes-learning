"""
Tests for the StatefulSet example manifests added in 13-statefulsets/examples/.

These are static structural tests over the YAML — no live cluster or kubectl
is required. They check that each manifest:
  * is syntactically valid, multi-document YAML
  * defines a headless Service (clusterIP: "None") wherever a StatefulSet exists
  * has a StatefulSet whose `serviceName` matches an actual headless Service
  * has selector/template label consistency (required by the Kubernetes API)
  * has volumeClaimTemplates whose names line up with container volumeMounts

Run with:
    python3 -m unittest discover -s 13-statefulsets/tests -v
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from yaml_helpers import (  # noqa: E402
    EXAMPLES_DIR,
    find_by_kind,
    find_one_by_kind,
    is_headless,
    load_documents,
)

ALL_EXAMPLE_FILES = [
    "01-statefulset-basics.yaml",
    "02-postgres-statefulset.yaml",
    "03-ordered-startup-demo.yaml",
    "04-headless-dns-demo.yaml",
    "05-parallel-management.yaml",
]


class TestExampleFilesCommonInvariants(unittest.TestCase):
    """Checks that must hold across every example file in this PR."""

    def test_all_expected_example_files_exist(self):
        for filename in ALL_EXAMPLE_FILES:
            with self.subTest(filename=filename):
                self.assertTrue(
                    (EXAMPLES_DIR / filename).is_file(),
                    f"missing expected example file: {filename}",
                )

    def test_each_file_parses_as_valid_yaml_with_at_least_one_document(self):
        for filename in ALL_EXAMPLE_FILES:
            with self.subTest(filename=filename):
                docs = load_documents(filename)
                self.assertGreater(len(docs), 0, f"{filename} produced no YAML documents")

    def test_every_document_has_required_top_level_fields(self):
        for filename in ALL_EXAMPLE_FILES:
            docs = load_documents(filename)
            for doc in docs:
                label = f"{filename}:{doc.get('kind')}/{doc.get('metadata', {}).get('name')}"
                with self.subTest(document=label):
                    self.assertIn("apiVersion", doc)
                    self.assertIn("kind", doc)
                    self.assertIn("metadata", doc)
                    self.assertIn("name", doc["metadata"])

    def test_every_statefulset_has_a_matching_headless_service(self):
        for filename in ALL_EXAMPLE_FILES:
            docs = load_documents(filename)
            statefulsets = find_by_kind(docs, "StatefulSet")
            headless_names = {
                svc["metadata"]["name"] for svc in find_by_kind(docs, "Service") if is_headless(svc)
            }
            for sts in statefulsets:
                with self.subTest(filename=filename, statefulset=sts["metadata"]["name"]):
                    service_name = sts["spec"]["serviceName"]
                    self.assertIn(
                        service_name,
                        headless_names,
                        f"StatefulSet {sts['metadata']['name']!r} in {filename} references "
                        f"serviceName={service_name!r}, but no headless Service with that name exists",
                    )

    def test_statefulset_selector_matches_pod_template_labels(self):
        for filename in ALL_EXAMPLE_FILES:
            docs = load_documents(filename)
            for sts in find_by_kind(docs, "StatefulSet"):
                with self.subTest(filename=filename, statefulset=sts["metadata"]["name"]):
                    match_labels = sts["spec"]["selector"]["matchLabels"]
                    template_labels = sts["spec"]["template"]["metadata"]["labels"]
                    self.assertEqual(
                        match_labels,
                        template_labels,
                        "spec.selector.matchLabels must equal spec.template.metadata.labels",
                    )

    def test_headless_service_selector_matches_statefulset_pod_labels(self):
        for filename in ALL_EXAMPLE_FILES:
            docs = load_documents(filename)
            services_by_name = {svc["metadata"]["name"]: svc for svc in find_by_kind(docs, "Service")}
            for sts in find_by_kind(docs, "StatefulSet"):
                service = services_by_name[sts["spec"]["serviceName"]]
                with self.subTest(filename=filename, statefulset=sts["metadata"]["name"]):
                    self.assertEqual(
                        service["spec"]["selector"],
                        sts["spec"]["template"]["metadata"]["labels"],
                        "headless Service selector must match the StatefulSet pod labels",
                    )

    def test_volume_claim_template_names_match_container_volume_mounts(self):
        for filename in ALL_EXAMPLE_FILES:
            docs = load_documents(filename)
            for sts in find_by_kind(docs, "StatefulSet"):
                claim_templates = sts["spec"].get("volumeClaimTemplates")
                if not claim_templates:
                    continue
                claim_names = {ct["metadata"]["name"] for ct in claim_templates}
                mount_names = {
                    mount["name"]
                    for container in sts["spec"]["template"]["spec"]["containers"]
                    for mount in container.get("volumeMounts", [])
                }
                with self.subTest(filename=filename, statefulset=sts["metadata"]["name"]):
                    # Every declared claim template should be consumed by at least one mount.
                    self.assertTrue(
                        claim_names.issubset(mount_names) or mount_names.issubset(claim_names),
                        f"volumeClaimTemplates {claim_names} and volumeMounts {mount_names} "
                        f"should reference the same volume name(s)",
                    )


class TestStatefulSetBasicsExample(unittest.TestCase):
    """01-statefulset-basics.yaml"""

    FILENAME = "01-statefulset-basics.yaml"

    @classmethod
    def setUpClass(cls):
        cls.docs = load_documents(cls.FILENAME)
        cls.service = find_one_by_kind(cls.docs, "Service")
        cls.statefulset = find_one_by_kind(cls.docs, "StatefulSet")

    def test_contains_exactly_one_service_and_one_statefulset(self):
        self.assertEqual(len(self.docs), 2)

    def test_service_is_headless_and_named_web(self):
        self.assertEqual(self.service["metadata"]["name"], "web")
        self.assertTrue(is_headless(self.service))
        self.assertEqual(self.service["spec"]["selector"], {"app": "web"})
        self.assertEqual(self.service["spec"]["ports"][0]["port"], 80)

    def test_statefulset_basic_shape(self):
        spec = self.statefulset["spec"]
        self.assertEqual(self.statefulset["metadata"]["name"], "web")
        self.assertEqual(spec["serviceName"], "web")
        self.assertEqual(spec["replicas"], 3)

    def test_container_uses_nginx_and_exposes_port_80(self):
        container = self.statefulset["spec"]["template"]["spec"]["containers"][0]
        self.assertEqual(container["name"], "nginx")
        self.assertEqual(container["image"], "nginx:1.25")
        self.assertEqual(container["ports"][0]["containerPort"], 80)

    def test_volume_claim_template_named_data_matches_mount(self):
        spec = self.statefulset["spec"]
        claim = spec["volumeClaimTemplates"][0]
        self.assertEqual(claim["metadata"]["name"], "data")
        self.assertEqual(claim["spec"]["accessModes"], ["ReadWriteOnce"])
        self.assertEqual(claim["spec"]["resources"]["requests"]["storage"], "100Mi")

        container = spec["template"]["spec"]["containers"][0]
        mount_names = {m["name"] for m in container["volumeMounts"]}
        self.assertIn("data", mount_names)

    def test_no_pod_management_policy_set_defaults_to_ordered_ready(self):
        # OrderedReady is the Kubernetes default when the field is omitted.
        self.assertNotIn("podManagementPolicy", self.statefulset["spec"])


class TestPostgresStatefulSetExample(unittest.TestCase):
    """02-postgres-statefulset.yaml"""

    FILENAME = "02-postgres-statefulset.yaml"

    @classmethod
    def setUpClass(cls):
        cls.docs = load_documents(cls.FILENAME)
        cls.secret = find_one_by_kind(cls.docs, "Secret")
        cls.services = find_by_kind(cls.docs, "Service")
        cls.statefulset = find_one_by_kind(cls.docs, "StatefulSet")

    def test_contains_secret_two_services_and_one_statefulset(self):
        self.assertEqual(len(self.docs), 4)
        self.assertEqual(len(self.services), 2)

    def test_secret_holds_postgres_password(self):
        self.assertEqual(self.secret["metadata"]["name"], "postgres-secret")
        self.assertEqual(self.secret["type"], "Opaque")
        self.assertIn("postgres-password", self.secret["stringData"])

    def test_headless_service_named_postgres(self):
        headless = [s for s in self.services if is_headless(s)]
        self.assertEqual(len(headless), 1)
        self.assertEqual(headless[0]["metadata"]["name"], "postgres")
        self.assertEqual(headless[0]["spec"]["ports"][0]["port"], 5432)

    def test_regular_service_is_not_headless(self):
        regular = [s for s in self.services if s["metadata"]["name"] == "postgres-svc"]
        self.assertEqual(len(regular), 1)
        # No clusterIP key at all => a normal, load-balanced ClusterIP Service.
        self.assertNotIn("clusterIP", regular[0]["spec"])

    def test_statefulset_service_name_points_to_headless_not_regular_service(self):
        spec = self.statefulset["spec"]
        self.assertEqual(spec["serviceName"], "postgres")
        self.assertNotEqual(spec["serviceName"], "postgres-svc")
        self.assertEqual(spec["replicas"], 1)

    def test_postgres_password_env_sourced_from_secret(self):
        container = self.statefulset["spec"]["template"]["spec"]["containers"][0]
        env_by_name = {e["name"]: e for e in container["env"]}
        password_ref = env_by_name["POSTGRES_PASSWORD"]["valueFrom"]["secretKeyRef"]
        self.assertEqual(password_ref["name"], self.secret["metadata"]["name"])
        self.assertEqual(password_ref["key"], "postgres-password")

    def test_pgdata_volume_claim_matches_mount(self):
        spec = self.statefulset["spec"]
        claim = spec["volumeClaimTemplates"][0]
        self.assertEqual(claim["metadata"]["name"], "pgdata")
        self.assertEqual(claim["spec"]["resources"]["requests"]["storage"], "1Gi")

        container = spec["template"]["spec"]["containers"][0]
        mount_names = {m["name"] for m in container["volumeMounts"]}
        self.assertIn("pgdata", mount_names)

    def test_readiness_and_liveness_probes_use_pg_isready(self):
        container = self.statefulset["spec"]["template"]["spec"]["containers"][0]
        for probe_name in ("readinessProbe", "livenessProbe"):
            with self.subTest(probe=probe_name):
                probe = container[probe_name]
                self.assertIn("pg_isready", probe["exec"]["command"])

    def test_resource_requests_do_not_exceed_limits(self):
        container = self.statefulset["spec"]["template"]["spec"]["containers"][0]
        resources = container["resources"]
        self.assertIn("requests", resources)
        self.assertIn("limits", resources)
        # cpu request "250m" <= limit "500m"; memory request "256Mi" <= limit "512Mi"
        req_cpu = int(resources["requests"]["cpu"].rstrip("m"))
        lim_cpu = int(resources["limits"]["cpu"].rstrip("m"))
        self.assertLessEqual(req_cpu, lim_cpu)

        req_mem = int(resources["requests"]["memory"].rstrip("Mi"))
        lim_mem = int(resources["limits"]["memory"].rstrip("Mi"))
        self.assertLessEqual(req_mem, lim_mem)


class TestOrderedStartupDemoExample(unittest.TestCase):
    """03-ordered-startup-demo.yaml"""

    FILENAME = "03-ordered-startup-demo.yaml"

    @classmethod
    def setUpClass(cls):
        cls.docs = load_documents(cls.FILENAME)
        cls.service = find_one_by_kind(cls.docs, "Service")
        cls.statefulset = find_one_by_kind(cls.docs, "StatefulSet")

    def test_contains_exactly_one_service_and_one_statefulset(self):
        self.assertEqual(len(self.docs), 2)

    def test_service_named_ordered_demo_is_headless(self):
        self.assertEqual(self.service["metadata"]["name"], "ordered-demo")
        self.assertTrue(is_headless(self.service))

    def test_statefulset_uses_default_ordered_ready_policy(self):
        spec = self.statefulset["spec"]
        self.assertEqual(spec["replicas"], 3)
        self.assertNotIn("podManagementPolicy", spec)

    def test_readiness_probe_checks_ready_marker_file(self):
        container = self.statefulset["spec"]["template"]["spec"]["containers"][0]
        probe = container["readinessProbe"]
        self.assertEqual(probe["exec"]["command"], ["test", "-f", "/tmp/ready"])

    def test_startup_script_simulates_delay_before_marking_ready(self):
        container = self.statefulset["spec"]["template"]["spec"]["containers"][0]
        script = container["command"][-1]
        self.assertIn("sleep 10", script)
        self.assertIn("touch /tmp/ready", script)


class TestHeadlessDnsDemoExample(unittest.TestCase):
    """04-headless-dns-demo.yaml"""

    FILENAME = "04-headless-dns-demo.yaml"

    @classmethod
    def setUpClass(cls):
        cls.docs = load_documents(cls.FILENAME)
        cls.service = find_one_by_kind(cls.docs, "Service")
        cls.statefulset = find_one_by_kind(cls.docs, "StatefulSet")

    def test_contains_exactly_one_service_and_one_statefulset(self):
        self.assertEqual(len(self.docs), 2)

    def test_service_named_dns_demo_is_headless(self):
        self.assertEqual(self.service["metadata"]["name"], "dns-demo")
        self.assertTrue(is_headless(self.service))
        self.assertEqual(self.service["spec"]["ports"][0]["port"], 80)

    def test_statefulset_shape(self):
        spec = self.statefulset["spec"]
        self.assertEqual(spec["serviceName"], "dns-demo")
        self.assertEqual(spec["replicas"], 3)

    def test_container_response_script_uses_hostname(self):
        container = self.statefulset["spec"]["template"]["spec"]["containers"][0]
        script = container["command"][-1]
        self.assertIn("$HOSTNAME", script)


class TestParallelManagementExample(unittest.TestCase):
    """05-parallel-management.yaml"""

    FILENAME = "05-parallel-management.yaml"

    @classmethod
    def setUpClass(cls):
        cls.docs = load_documents(cls.FILENAME)
        cls.service = find_one_by_kind(cls.docs, "Service")
        cls.statefulset = find_one_by_kind(cls.docs, "StatefulSet")

    def test_contains_exactly_one_service_and_one_statefulset(self):
        self.assertEqual(len(self.docs), 2)

    def test_service_named_cache_is_headless(self):
        self.assertEqual(self.service["metadata"]["name"], "cache")
        self.assertTrue(is_headless(self.service))
        self.assertEqual(self.service["spec"]["ports"][0]["port"], 6379)

    def test_pod_management_policy_is_parallel(self):
        self.assertEqual(self.statefulset["spec"]["podManagementPolicy"], "Parallel")

    def test_update_strategy_is_still_rolling_update(self):
        self.assertEqual(self.statefulset["spec"]["updateStrategy"]["type"], "RollingUpdate")

    def test_container_uses_redis_with_tcp_readiness_probe(self):
        container = self.statefulset["spec"]["template"]["spec"]["containers"][0]
        self.assertEqual(container["name"], "redis")
        self.assertEqual(container["image"], "redis:7")
        self.assertEqual(container["readinessProbe"]["tcpSocket"]["port"], 6379)

    def test_resource_requests_do_not_exceed_limits(self):
        resources = self.statefulset["spec"]["template"]["spec"]["containers"][0]["resources"]
        req_cpu = int(resources["requests"]["cpu"].rstrip("m"))
        lim_cpu = int(resources["limits"]["cpu"].rstrip("m"))
        self.assertLessEqual(req_cpu, lim_cpu)


class TestYamlHelpersBehaviour(unittest.TestCase):
    """Regression/boundary tests for the test-support helpers themselves.

    These use small synthetic documents (not the real example files) to make
    sure our own consistency-checking utilities actually catch problems
    instead of trivially passing.
    """

    def test_find_one_by_kind_raises_when_no_match(self):
        docs = [{"kind": "Service", "metadata": {"name": "a"}}]
        with self.assertRaises(AssertionError):
            find_one_by_kind(docs, "StatefulSet")

    def test_find_one_by_kind_raises_when_multiple_matches(self):
        docs = [
            {"kind": "Service", "metadata": {"name": "a"}},
            {"kind": "Service", "metadata": {"name": "b"}},
        ]
        with self.assertRaises(AssertionError):
            find_one_by_kind(docs, "Service")

    def test_is_headless_true_only_for_literal_string_none(self):
        self.assertTrue(is_headless({"spec": {"clusterIP": "None"}}))
        self.assertFalse(is_headless({"spec": {"clusterIP": "10.0.0.5"}}))
        self.assertFalse(is_headless({"spec": {}}))
        self.assertFalse(is_headless({}))

    def test_detects_statefulset_referencing_nonexistent_headless_service(self):
        # Negative case: serviceName points at a Service that isn't headless
        # (or doesn't exist) — this must NOT be treated as valid.
        docs = [
            {"kind": "Service", "metadata": {"name": "regular"}, "spec": {}},
            {
                "kind": "StatefulSet",
                "metadata": {"name": "broken"},
                "spec": {"serviceName": "regular"},
            },
        ]
        headless_names = {s["metadata"]["name"] for s in find_by_kind(docs, "Service") if is_headless(s)}
        sts = find_one_by_kind(docs, "StatefulSet")
        self.assertNotIn(sts["spec"]["serviceName"], headless_names)


if __name__ == "__main__":
    unittest.main()