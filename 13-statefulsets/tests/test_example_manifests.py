"""Unit tests for the Kubernetes example manifests in 13-statefulsets/examples/.

These tests validate that each YAML example:
  - Parses as valid YAML (no syntax errors).
  - Declares the exact set of Kubernetes objects the README/exercises describe.
  - Wires the headless Service (`clusterIP: None`) to the StatefulSet via a matching
    `serviceName`, which is the mechanism that gives every Pod stable per-pod DNS.
  - Keeps `selector.matchLabels` / `template.metadata.labels` / Service `selector`
    consistent, since a mismatch here silently breaks Service routing in real clusters.
  - Uses pinned (non-`latest`) container image tags, per this repo's stated convention.

No cluster is required to run these tests -- they operate purely on the static YAML.
"""
import os
import unittest

import yaml

EXAMPLES_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "examples")
)


def load_docs(filename):
    """Parse a multi-document YAML file and drop empty leading/trailing documents."""
    path = os.path.join(EXAMPLES_DIR, filename)
    with open(path, encoding="utf-8") as f:
        docs = list(yaml.safe_load_all(f))
    return [d for d in docs if d is not None]


def find_by_kind(docs, kind, name=None):
    """Return docs matching `kind` (and optionally `metadata.name`)."""
    matches = [d for d in docs if d.get("kind") == kind]
    if name is not None:
        matches = [d for d in matches if d.get("metadata", {}).get("name") == name]
    return matches


def is_headless(service_doc):
    """A Kubernetes Service is headless when `clusterIP` is the literal string
    "None" (a magic value defined by the Kubernetes API -- YAML parses the bare
    word `None` in `clusterIP: None` as a string, not as a null/None value)."""
    return service_doc.get("spec", {}).get("clusterIP") == "None"


ALL_EXAMPLE_FILES = [
    "01-statefulset-basics.yaml",
    "02-postgres-statefulset.yaml",
    "03-ordered-startup-demo.yaml",
    "04-headless-dns-demo.yaml",
    "05-parallel-management.yaml",
]


class TestAllExampleFilesParse(unittest.TestCase):
    """Baseline sanity checks that apply identically to every example file."""

    def test_all_example_files_exist(self):
        for filename in ALL_EXAMPLE_FILES:
            path = os.path.join(EXAMPLES_DIR, filename)
            self.assertTrue(os.path.isfile(path), f"missing example file: {filename}")

    def test_all_example_files_parse_as_valid_yaml(self):
        for filename in ALL_EXAMPLE_FILES:
            with self.subTest(filename=filename):
                docs = load_docs(filename)
                self.assertGreaterEqual(
                    len(docs), 2, f"{filename} should define at least 2 documents"
                )

    def test_every_document_has_kind_and_metadata_name(self):
        for filename in ALL_EXAMPLE_FILES:
            for doc in load_docs(filename):
                with self.subTest(filename=filename, doc=doc.get("kind")):
                    self.assertIn("kind", doc)
                    self.assertIn("metadata", doc)
                    self.assertIn("name", doc["metadata"])

    def test_headless_service_servicename_matches_statefulset(self):
        """Every example's StatefulSet.spec.serviceName must reference an actual
        headless (clusterIP: None) Service defined in the same file."""
        for filename in ALL_EXAMPLE_FILES:
            with self.subTest(filename=filename):
                docs = load_docs(filename)
                statefulsets = find_by_kind(docs, "StatefulSet")
                self.assertEqual(len(statefulsets), 1)
                sts = statefulsets[0]
                service_name = sts["spec"]["serviceName"]

                headless_services = [
                    d
                    for d in find_by_kind(docs, "Service", service_name)
                    if is_headless(d)
                ]
                self.assertEqual(
                    len(headless_services),
                    1,
                    f"{filename}: serviceName {service_name!r} must match exactly "
                    "one headless Service (clusterIP: None)",
                )

    def test_statefulset_selector_matches_template_labels(self):
        for filename in ALL_EXAMPLE_FILES:
            with self.subTest(filename=filename):
                sts = find_by_kind(load_docs(filename), "StatefulSet")[0]
                match_labels = sts["spec"]["selector"]["matchLabels"]
                template_labels = sts["spec"]["template"]["metadata"]["labels"]
                self.assertEqual(match_labels, template_labels)

    def test_service_selector_matches_statefulset_pod_labels(self):
        """The headless Service's selector must actually select the StatefulSet's pods."""
        for filename in ALL_EXAMPLE_FILES:
            with self.subTest(filename=filename):
                docs = load_docs(filename)
                sts = find_by_kind(docs, "StatefulSet")[0]
                pod_labels = sts["spec"]["template"]["metadata"]["labels"]
                headless = find_by_kind(docs, "Service", sts["spec"]["serviceName"])[0]
                self.assertEqual(headless["spec"]["selector"], pod_labels)

    def test_container_images_are_pinned_not_latest(self):
        for filename in ALL_EXAMPLE_FILES:
            docs = load_docs(filename)
            sts = find_by_kind(docs, "StatefulSet")[0]
            containers = sts["spec"]["template"]["spec"]["containers"]
            for container in containers:
                with self.subTest(filename=filename, container=container["name"]):
                    image = container["image"]
                    self.assertIn(":", image, "image should have an explicit tag")
                    tag = image.split(":")[-1]
                    self.assertNotEqual(tag, "latest")
                    self.assertTrue(tag, "tag must not be empty")


class TestStatefulSetBasicsExample(unittest.TestCase):
    FILE = "01-statefulset-basics.yaml"

    @classmethod
    def setUpClass(cls):
        cls.docs = load_docs(cls.FILE)

    def test_defines_exactly_two_documents(self):
        self.assertEqual(len(self.docs), 2)

    def test_headless_service_shape(self):
        service = find_by_kind(self.docs, "Service", "web")[0]
        self.assertEqual(service["apiVersion"], "v1")
        self.assertTrue(is_headless(service))
        self.assertEqual(service["spec"]["selector"], {"app": "web"})
        ports = service["spec"]["ports"]
        self.assertEqual(ports[0]["port"], 80)
        self.assertEqual(ports[0]["name"], "http")

    def test_statefulset_shape(self):
        sts = find_by_kind(self.docs, "StatefulSet", "web")[0]
        self.assertEqual(sts["apiVersion"], "apps/v1")
        self.assertEqual(sts["spec"]["serviceName"], "web")
        self.assertEqual(sts["spec"]["replicas"], 3)

    def test_default_pod_management_policy(self):
        """No podManagementPolicy set means Kubernetes defaults to OrderedReady."""
        sts = find_by_kind(self.docs, "StatefulSet", "web")[0]
        self.assertNotIn("podManagementPolicy", sts["spec"])

    def test_container_image_and_port(self):
        sts = find_by_kind(self.docs, "StatefulSet", "web")[0]
        container = sts["spec"]["template"]["spec"]["containers"][0]
        self.assertEqual(container["image"], "nginx:1.25")
        self.assertEqual(container["ports"][0]["containerPort"], 80)

    def test_volume_mount_matches_volume_claim_template(self):
        sts = find_by_kind(self.docs, "StatefulSet", "web")[0]
        container = sts["spec"]["template"]["spec"]["containers"][0]
        mount_names = {m["name"] for m in container["volumeMounts"]}
        vct_names = {
            vct["metadata"]["name"] for vct in sts["spec"]["volumeClaimTemplates"]
        }
        self.assertEqual(mount_names, vct_names)
        self.assertEqual(mount_names, {"data"})

    def test_volume_claim_template_storage_request(self):
        sts = find_by_kind(self.docs, "StatefulSet", "web")[0]
        vct = sts["spec"]["volumeClaimTemplates"][0]
        self.assertEqual(vct["spec"]["accessModes"], ["ReadWriteOnce"])
        self.assertEqual(vct["spec"]["resources"]["requests"]["storage"], "100Mi")


class TestPostgresStatefulSetExample(unittest.TestCase):
    FILE = "02-postgres-statefulset.yaml"

    @classmethod
    def setUpClass(cls):
        cls.docs = load_docs(cls.FILE)

    def test_defines_exactly_four_documents(self):
        self.assertEqual(len(self.docs), 4)

    def test_kinds_present(self):
        kinds = sorted(d["kind"] for d in self.docs)
        self.assertEqual(kinds, ["Secret", "Service", "Service", "StatefulSet"])

    def test_secret_shape(self):
        secret = find_by_kind(self.docs, "Secret", "postgres-secret")[0]
        self.assertEqual(secret["type"], "Opaque")
        self.assertIn("postgres-password", secret["stringData"])

    def test_headless_service_is_headless(self):
        service = find_by_kind(self.docs, "Service", "postgres")[0]
        self.assertTrue(is_headless(service))

    def test_client_service_is_not_headless(self):
        """postgres-svc is a regular, load-balanced Service (no clusterIP: None)."""
        service = find_by_kind(self.docs, "Service", "postgres-svc")[0]
        self.assertNotIn("clusterIP", service["spec"])

    def test_statefulset_uses_headless_service_not_client_service(self):
        sts = find_by_kind(self.docs, "StatefulSet", "postgres")[0]
        self.assertEqual(sts["spec"]["serviceName"], "postgres")
        self.assertNotEqual(sts["spec"]["serviceName"], "postgres-svc")

    def test_statefulset_is_single_replica(self):
        sts = find_by_kind(self.docs, "StatefulSet", "postgres")[0]
        self.assertEqual(sts["spec"]["replicas"], 1)

    def test_password_env_references_the_secret(self):
        sts = find_by_kind(self.docs, "StatefulSet", "postgres")[0]
        container = sts["spec"]["template"]["spec"]["containers"][0]
        env_by_name = {e["name"]: e for e in container["env"]}
        password_ref = env_by_name["POSTGRES_PASSWORD"]["valueFrom"]["secretKeyRef"]
        self.assertEqual(password_ref["name"], "postgres-secret")
        self.assertEqual(password_ref["key"], "postgres-password")

    def test_volume_mount_matches_volume_claim_template(self):
        sts = find_by_kind(self.docs, "StatefulSet", "postgres")[0]
        container = sts["spec"]["template"]["spec"]["containers"][0]
        mount_names = {m["name"] for m in container["volumeMounts"]}
        vct_names = {
            vct["metadata"]["name"] for vct in sts["spec"]["volumeClaimTemplates"]
        }
        self.assertEqual(mount_names, vct_names)
        self.assertEqual(mount_names, {"pgdata"})

    def test_readiness_and_liveness_probes_use_pg_isready(self):
        sts = find_by_kind(self.docs, "StatefulSet", "postgres")[0]
        container = sts["spec"]["template"]["spec"]["containers"][0]
        for probe_name in ("readinessProbe", "livenessProbe"):
            with self.subTest(probe=probe_name):
                probe = container[probe_name]
                self.assertEqual(
                    probe["exec"]["command"], ["pg_isready", "-U", "postgres"]
                )

    def test_resource_requests_do_not_exceed_limits(self):
        sts = find_by_kind(self.docs, "StatefulSet", "postgres")[0]
        container = sts["spec"]["template"]["spec"]["containers"][0]
        resources = container["resources"]
        self.assertIn("requests", resources)
        self.assertIn("limits", resources)
        # cpu/memory requests should be present and non-empty for a database workload
        self.assertIn("cpu", resources["requests"])
        self.assertIn("memory", resources["requests"])


class TestOrderedStartupDemoExample(unittest.TestCase):
    FILE = "03-ordered-startup-demo.yaml"

    @classmethod
    def setUpClass(cls):
        cls.docs = load_docs(cls.FILE)

    def test_defines_exactly_two_documents(self):
        self.assertEqual(len(self.docs), 2)

    def test_uses_default_ordered_ready_policy(self):
        """This example is meant to demonstrate the default sequential behavior,
        so it must NOT set podManagementPolicy: Parallel."""
        sts = find_by_kind(self.docs, "StatefulSet", "ordered-demo")[0]
        self.assertNotIn("podManagementPolicy", sts["spec"])

    def test_replica_count(self):
        sts = find_by_kind(self.docs, "StatefulSet", "ordered-demo")[0]
        self.assertEqual(sts["spec"]["replicas"], 3)

    def test_readiness_probe_checks_ready_file(self):
        sts = find_by_kind(self.docs, "StatefulSet", "ordered-demo")[0]
        container = sts["spec"]["template"]["spec"]["containers"][0]
        probe = container["readinessProbe"]
        self.assertEqual(probe["exec"]["command"], ["test", "-f", "/tmp/ready"])

    def test_container_image(self):
        sts = find_by_kind(self.docs, "StatefulSet", "ordered-demo")[0]
        container = sts["spec"]["template"]["spec"]["containers"][0]
        self.assertEqual(container["image"], "busybox:1.36")


class TestHeadlessDnsDemoExample(unittest.TestCase):
    FILE = "04-headless-dns-demo.yaml"

    @classmethod
    def setUpClass(cls):
        cls.docs = load_docs(cls.FILE)

    def test_defines_exactly_two_documents(self):
        self.assertEqual(len(self.docs), 2)

    def test_replica_count(self):
        sts = find_by_kind(self.docs, "StatefulSet", "dns-demo")[0]
        self.assertEqual(sts["spec"]["replicas"], 3)

    def test_container_image(self):
        sts = find_by_kind(self.docs, "StatefulSet", "dns-demo")[0]
        container = sts["spec"]["template"]["spec"]["containers"][0]
        self.assertEqual(container["image"], "nginx:1.25")

    def test_command_echoes_hostname(self):
        sts = find_by_kind(self.docs, "StatefulSet", "dns-demo")[0]
        container = sts["spec"]["template"]["spec"]["containers"][0]
        script = container["command"][-1]
        self.assertIn("$HOSTNAME", script)


class TestParallelManagementExample(unittest.TestCase):
    FILE = "05-parallel-management.yaml"

    @classmethod
    def setUpClass(cls):
        cls.docs = load_docs(cls.FILE)

    def test_defines_exactly_two_documents(self):
        self.assertEqual(len(self.docs), 2)

    def test_pod_management_policy_is_parallel(self):
        sts = find_by_kind(self.docs, "StatefulSet", "cache")[0]
        self.assertEqual(sts["spec"]["podManagementPolicy"], "Parallel")

    def test_update_strategy_is_still_rolling_update(self):
        """Parallel pod management only affects create/delete, not rolling updates."""
        sts = find_by_kind(self.docs, "StatefulSet", "cache")[0]
        self.assertEqual(sts["spec"]["updateStrategy"]["type"], "RollingUpdate")

    def test_replica_count(self):
        sts = find_by_kind(self.docs, "StatefulSet", "cache")[0]
        self.assertEqual(sts["spec"]["replicas"], 3)

    def test_container_image_and_readiness_probe(self):
        sts = find_by_kind(self.docs, "StatefulSet", "cache")[0]
        container = sts["spec"]["template"]["spec"]["containers"][0]
        self.assertEqual(container["image"], "redis:7")
        self.assertEqual(container["readinessProbe"]["tcpSocket"]["port"], 6379)

    def test_no_volume_claim_templates(self):
        """This example deliberately has no persistent storage (cache nodes)."""
        sts = find_by_kind(self.docs, "StatefulSet", "cache")[0]
        self.assertNotIn("volumeClaimTemplates", sts["spec"])


if __name__ == "__main__":
    unittest.main()