"""Tests for the 13-statefulsets topic: example manifests and documentation.

This topic is documentation + example Kubernetes YAML (no application code), so
these tests validate:
  - Each example YAML file parses and contains the expected Kubernetes objects
    with the field values the README/exercises describe (serviceName, replicas,
    volumeClaimTemplates, headless Service configuration, etc.)
  - Cross-cutting StatefulSet invariants that Kubernetes itself enforces
    (selector/template label match, serviceName -> headless Service, PVC/mount
    name alignment) so a future edit can't silently break a "working" example.
  - The README.md and exercises/README.md reference files that actually exist,
    and any embedded ```yaml``` snippets in the README are valid YAML.

Run with:
    python3 -m unittest discover -s 13-statefulsets/tests -v
"""

import os
import re
import unittest

import yaml

TOPIC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
EXAMPLES_DIR = os.path.join(TOPIC_DIR, "examples")
EXERCISES_DIR = os.path.join(TOPIC_DIR, "exercises")
README_PATH = os.path.join(TOPIC_DIR, "README.md")
EXERCISES_README_PATH = os.path.join(EXERCISES_DIR, "README.md")

EXAMPLE_FILES = [
    "01-statefulset-basics.yaml",
    "02-postgres-statefulset.yaml",
    "03-ordered-startup-demo.yaml",
    "04-headless-dns-demo.yaml",
    "05-parallel-management.yaml",
]


def load_yaml_documents(path):
    """Parse a multi-document YAML file, dropping empty documents."""
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    return [doc for doc in yaml.safe_load_all(content) if doc is not None]


def read_text(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def find_doc(docs, kind, name=None):
    """Find a single document by kind (and optionally metadata.name)."""
    for doc in docs:
        if doc.get("kind") != kind:
            continue
        if name is not None and doc.get("metadata", {}).get("name") != name:
            continue
        return doc
    return None


def get_container(doc, name=None, index=0):
    containers = doc["spec"]["template"]["spec"]["containers"]
    if name is None:
        return containers[index]
    for c in containers:
        if c.get("name") == name:
            return c
    raise AssertionError("no container named %r" % name)


def extract_fenced_code_blocks(markdown_text, lang):
    pattern = r"```" + re.escape(lang) + r"\n(.*?)```"
    return re.findall(pattern, markdown_text, re.DOTALL)


class ExamplesDirectoryTests(unittest.TestCase):
    """Sanity checks on the examples/ directory as a whole."""

    def test_all_expected_example_files_exist(self):
        for filename in EXAMPLE_FILES:
            path = os.path.join(EXAMPLES_DIR, filename)
            self.assertTrue(os.path.isfile(path), "missing example file: %s" % filename)

    def test_no_unexpected_yaml_files(self):
        actual = sorted(f for f in os.listdir(EXAMPLES_DIR) if f.endswith((".yaml", ".yml")))
        self.assertEqual(actual, sorted(EXAMPLE_FILES))

    def test_all_example_files_are_valid_yaml(self):
        for filename in EXAMPLE_FILES:
            path = os.path.join(EXAMPLES_DIR, filename)
            with self.subTest(filename=filename):
                docs = load_yaml_documents(path)
                self.assertGreaterEqual(len(docs), 2, "expected at least a Service and a StatefulSet")
                for doc in docs:
                    self.assertIn("apiVersion", doc)
                    self.assertIn("kind", doc)
                    self.assertIn("metadata", doc)


class StatefulSetBasicsExampleTests(unittest.TestCase):
    """01-statefulset-basics.yaml"""

    @classmethod
    def setUpClass(cls):
        cls.docs = load_yaml_documents(os.path.join(EXAMPLES_DIR, "01-statefulset-basics.yaml"))
        cls.service = find_doc(cls.docs, "Service", "web")
        cls.sts = find_doc(cls.docs, "StatefulSet", "web")

    def test_exactly_two_documents(self):
        self.assertEqual(len(self.docs), 2)

    def test_headless_service_is_present_and_headless(self):
        self.assertIsNotNone(self.service)
        self.assertEqual(self.service["apiVersion"], "v1")
        self.assertEqual(self.service["spec"]["clusterIP"], "None")
        self.assertEqual(self.service["spec"]["selector"], {"app": "web"})
        self.assertEqual(self.service["spec"]["ports"], [{"port": 80, "name": "http"}])

    def test_statefulset_basic_fields(self):
        self.assertIsNotNone(self.sts)
        self.assertEqual(self.sts["apiVersion"], "apps/v1")
        self.assertEqual(self.sts["spec"]["serviceName"], "web")
        self.assertEqual(self.sts["spec"]["replicas"], 3)

    def test_selector_matches_template_labels(self):
        self.assertEqual(
            self.sts["spec"]["selector"]["matchLabels"],
            self.sts["spec"]["template"]["metadata"]["labels"],
        )

    def test_container_and_volume_mount(self):
        container = get_container(self.sts, "nginx")
        self.assertEqual(container["image"], "nginx:1.25")
        self.assertEqual(container["volumeMounts"], [
            {"name": "data", "mountPath": "/usr/share/nginx/html"}
        ])

    def test_volume_claim_template_name_matches_mount(self):
        vct = self.sts["spec"]["volumeClaimTemplates"][0]
        self.assertEqual(vct["metadata"]["name"], "data")
        self.assertEqual(vct["spec"]["accessModes"], ["ReadWriteOnce"])
        self.assertEqual(vct["spec"]["resources"]["requests"]["storage"], "100Mi")


class PostgresStatefulSetExampleTests(unittest.TestCase):
    """02-postgres-statefulset.yaml"""

    @classmethod
    def setUpClass(cls):
        cls.docs = load_yaml_documents(os.path.join(EXAMPLES_DIR, "02-postgres-statefulset.yaml"))
        cls.secret = find_doc(cls.docs, "Secret", "postgres-secret")
        cls.headless_svc = find_doc(cls.docs, "Service", "postgres")
        cls.regular_svc = find_doc(cls.docs, "Service", "postgres-svc")
        cls.sts = find_doc(cls.docs, "StatefulSet", "postgres")

    def test_exactly_four_documents(self):
        self.assertEqual(len(self.docs), 4)

    def test_secret_fields(self):
        self.assertIsNotNone(self.secret)
        self.assertEqual(self.secret["type"], "Opaque")
        self.assertEqual(self.secret["stringData"]["postgres-password"], "supersecret")

    def test_headless_service_is_headless(self):
        self.assertIsNotNone(self.headless_svc)
        self.assertEqual(self.headless_svc["spec"]["clusterIP"], "None")
        self.assertEqual(self.headless_svc["spec"]["selector"], {"app": "postgres"})

    def test_regular_service_is_not_headless(self):
        self.assertIsNotNone(self.regular_svc)
        self.assertNotIn("clusterIP", self.regular_svc["spec"])
        self.assertEqual(self.regular_svc["spec"]["selector"], {"app": "postgres"})
        self.assertEqual(self.regular_svc["spec"]["ports"][0]["port"], 5432)

    def test_statefulset_basic_fields(self):
        self.assertIsNotNone(self.sts)
        self.assertEqual(self.sts["spec"]["serviceName"], "postgres")
        self.assertEqual(self.sts["spec"]["replicas"], 1)

    def test_selector_matches_template_labels(self):
        self.assertEqual(
            self.sts["spec"]["selector"]["matchLabels"],
            self.sts["spec"]["template"]["metadata"]["labels"],
        )

    def test_postgres_password_env_from_secret(self):
        container = get_container(self.sts, "postgres")
        env_by_name = {e["name"]: e for e in container["env"]}
        self.assertIn("POSTGRES_PASSWORD", env_by_name)
        secret_ref = env_by_name["POSTGRES_PASSWORD"]["valueFrom"]["secretKeyRef"]
        self.assertEqual(secret_ref["name"], "postgres-secret")
        self.assertEqual(secret_ref["key"], "postgres-password")

    def test_pgdata_env_avoids_mount_point_conflict(self):
        container = get_container(self.sts, "postgres")
        env_by_name = {e["name"]: e for e in container["env"]}
        self.assertEqual(env_by_name["PGDATA"]["value"], "/var/lib/postgresql/data/pgdata")
        # PGDATA must live *inside* the mounted volume, not equal the mount path itself.
        mount_path = container["volumeMounts"][0]["mountPath"]
        self.assertTrue(env_by_name["PGDATA"]["value"].startswith(mount_path + "/"))

    def test_volume_claim_template_name_matches_mount(self):
        container = get_container(self.sts, "postgres")
        mount_names = {m["name"] for m in container["volumeMounts"]}
        vct_names = {v["metadata"]["name"] for v in self.sts["spec"]["volumeClaimTemplates"]}
        self.assertEqual(mount_names, vct_names)
        self.assertEqual(vct_names, {"pgdata"})

    def test_readiness_and_liveness_probes(self):
        container = get_container(self.sts, "postgres")
        self.assertEqual(
            container["readinessProbe"]["exec"]["command"],
            ["pg_isready", "-U", "postgres"],
        )
        self.assertEqual(container["readinessProbe"]["periodSeconds"], 5)
        self.assertEqual(
            container["livenessProbe"]["exec"]["command"],
            ["pg_isready", "-U", "postgres"],
        )
        self.assertEqual(container["livenessProbe"]["initialDelaySeconds"], 30)

    def test_resource_requests_and_limits(self):
        container = get_container(self.sts, "postgres")
        self.assertEqual(container["resources"]["requests"], {"cpu": "250m", "memory": "256Mi"})
        self.assertEqual(container["resources"]["limits"], {"cpu": "500m", "memory": "512Mi"})


class OrderedStartupDemoExampleTests(unittest.TestCase):
    """03-ordered-startup-demo.yaml"""

    @classmethod
    def setUpClass(cls):
        cls.docs = load_yaml_documents(os.path.join(EXAMPLES_DIR, "03-ordered-startup-demo.yaml"))
        cls.service = find_doc(cls.docs, "Service", "ordered-demo")
        cls.sts = find_doc(cls.docs, "StatefulSet", "ordered-demo")

    def test_exactly_two_documents(self):
        self.assertEqual(len(self.docs), 2)

    def test_headless_service(self):
        self.assertIsNotNone(self.service)
        self.assertEqual(self.service["spec"]["clusterIP"], "None")

    def test_statefulset_defaults_to_ordered_ready(self):
        self.assertIsNotNone(self.sts)
        self.assertEqual(self.sts["spec"]["serviceName"], "ordered-demo")
        self.assertEqual(self.sts["spec"]["replicas"], 3)
        # podManagementPolicy is intentionally omitted -> Kubernetes default (OrderedReady)
        self.assertNotIn("podManagementPolicy", self.sts["spec"])

    def test_readiness_probe_checks_ready_marker_file(self):
        container = get_container(self.sts, "app")
        self.assertEqual(
            container["readinessProbe"]["exec"]["command"],
            ["test", "-f", "/tmp/ready"],
        )
        self.assertEqual(container["readinessProbe"]["periodSeconds"], 3)

    def test_startup_script_touches_ready_file_after_delay(self):
        container = get_container(self.sts, "app")
        script = container["command"][-1]
        self.assertIn("sleep 10", script)
        self.assertIn("touch /tmp/ready", script)


class HeadlessDnsDemoExampleTests(unittest.TestCase):
    """04-headless-dns-demo.yaml"""

    @classmethod
    def setUpClass(cls):
        cls.docs = load_yaml_documents(os.path.join(EXAMPLES_DIR, "04-headless-dns-demo.yaml"))
        cls.service = find_doc(cls.docs, "Service", "dns-demo")
        cls.sts = find_doc(cls.docs, "StatefulSet", "dns-demo")

    def test_exactly_two_documents(self):
        self.assertEqual(len(self.docs), 2)

    def test_headless_service(self):
        self.assertIsNotNone(self.service)
        self.assertEqual(self.service["spec"]["clusterIP"], "None")

    def test_statefulset_fields(self):
        self.assertIsNotNone(self.sts)
        self.assertEqual(self.sts["spec"]["serviceName"], "dns-demo")
        self.assertEqual(self.sts["spec"]["replicas"], 3)

    def test_container_returns_hostname(self):
        container = get_container(self.sts, "nginx")
        script = container["command"][-1]
        self.assertIn("$HOSTNAME", script)


class ParallelManagementExampleTests(unittest.TestCase):
    """05-parallel-management.yaml"""

    @classmethod
    def setUpClass(cls):
        cls.docs = load_yaml_documents(os.path.join(EXAMPLES_DIR, "05-parallel-management.yaml"))
        cls.service = find_doc(cls.docs, "Service", "cache")
        cls.sts = find_doc(cls.docs, "StatefulSet", "cache")

    def test_exactly_two_documents(self):
        self.assertEqual(len(self.docs), 2)

    def test_headless_service(self):
        self.assertIsNotNone(self.service)
        self.assertEqual(self.service["spec"]["clusterIP"], "None")

    def test_pod_management_policy_is_parallel(self):
        self.assertIsNotNone(self.sts)
        self.assertEqual(self.sts["spec"]["podManagementPolicy"], "Parallel")

    def test_update_strategy_is_still_rolling_update(self):
        self.assertEqual(self.sts["spec"]["updateStrategy"]["type"], "RollingUpdate")

    def test_readiness_probe_is_tcp(self):
        container = get_container(self.sts, "redis")
        self.assertEqual(container["readinessProbe"]["tcpSocket"]["port"], 6379)

    def test_no_volume_claim_templates(self):
        # This example demonstrates parallel management with ephemeral, stateless
        # cache pods; it deliberately has no per-pod persistent storage.
        self.assertNotIn("volumeClaimTemplates", self.sts["spec"])


class StatefulSetInvariantsAcrossExamplesTests(unittest.TestCase):
    """Cross-cutting checks Kubernetes itself enforces for every example that
    defines a StatefulSet, applied uniformly so a future edit to any one file
    can't silently drift from a valid configuration."""

    @classmethod
    def setUpClass(cls):
        cls.docs_by_file = {
            filename: load_yaml_documents(os.path.join(EXAMPLES_DIR, filename))
            for filename in EXAMPLE_FILES
        }

    def _statefulsets(self):
        for filename, docs in self.docs_by_file.items():
            for doc in docs:
                if doc.get("kind") == "StatefulSet":
                    yield filename, doc, docs

    def test_service_name_resolves_to_a_headless_service_in_same_file(self):
        for filename, sts, docs in self._statefulsets():
            with self.subTest(filename=filename):
                service_name = sts["spec"]["serviceName"]
                svc = find_doc(docs, "Service", service_name)
                self.assertIsNotNone(
                    svc, "serviceName %r has no matching Service in %s" % (service_name, filename)
                )
                self.assertEqual(
                    svc["spec"].get("clusterIP"),
                    "None",
                    "StatefulSet governing Service must be headless in %s" % filename,
                )

    def test_selector_matches_template_labels(self):
        for filename, sts, _ in self._statefulsets():
            with self.subTest(filename=filename):
                self.assertEqual(
                    sts["spec"]["selector"]["matchLabels"],
                    sts["spec"]["template"]["metadata"]["labels"],
                )

    def test_volume_claim_template_names_align_with_container_mounts(self):
        for filename, sts, _ in self._statefulsets():
            vcts = sts["spec"].get("volumeClaimTemplates")
            if not vcts:
                continue
            with self.subTest(filename=filename):
                vct_names = {v["metadata"]["name"] for v in vcts}
                mount_names = set()
                for container in sts["spec"]["template"]["spec"]["containers"]:
                    for mount in container.get("volumeMounts", []):
                        mount_names.add(mount["name"])
                self.assertTrue(
                    vct_names.issubset(mount_names),
                    "volumeClaimTemplates %r not all mounted in containers %r (%s)"
                    % (vct_names, mount_names, filename),
                )

    def test_replicas_is_a_positive_integer(self):
        for filename, sts, _ in self._statefulsets():
            with self.subTest(filename=filename):
                replicas = sts["spec"]["replicas"]
                self.assertIsInstance(replicas, int)
                self.assertGreater(replicas, 0)

    def test_api_version_and_kind(self):
        for filename, sts, _ in self._statefulsets():
            with self.subTest(filename=filename):
                self.assertEqual(sts["apiVersion"], "apps/v1")
                self.assertEqual(sts["kind"], "StatefulSet")


class ReadmeDocumentationTests(unittest.TestCase):
    """13-statefulsets/README.md"""

    @classmethod
    def setUpClass(cls):
        cls.text = read_text(README_PATH)

    def test_file_exists(self):
        self.assertTrue(os.path.isfile(README_PATH))

    def test_title(self):
        self.assertTrue(self.text.startswith("# 13 — StatefulSets"))

    def test_contains_expected_headings(self):
        expected_headings = [
            "## The Problem",
            "## The Analogy",
            "## Core Vocabulary",
            "## StatefulSet vs Deployment",
            "## How It Works (Architecture)",
            "## The Headless Service",
            "## YAML Walkthrough",
            "## What Happens When a Pod Restarts",
            "## Update Strategy",
            "## Scaling",
            "## Common Mistakes / Gotchas",
            "## Common Questions & Doubts",
            "## Interview Questions",
            "## Summary",
            "## Exercises",
        ]
        for heading in expected_headings:
            with self.subTest(heading=heading):
                self.assertIn(heading, self.text)

    def test_links_to_exercises_readme_and_file_exists(self):
        self.assertIn("[exercises/README.md](./exercises/README.md)", self.text)
        self.assertTrue(os.path.isfile(EXERCISES_README_PATH))

    def test_previous_topic_link_resolves_to_existing_file(self):
        match = re.search(r"\*\*Previous topic:\*\* \[.*?\]\((.*?)\)", self.text)
        self.assertIsNotNone(match)
        target = os.path.normpath(os.path.join(TOPIC_DIR, match.group(1)))
        self.assertTrue(os.path.isfile(target), "previous topic link target missing: %s" % target)

    def test_next_topic_link_is_present(self):
        # 14-daemonsets does not exist yet at this point in the course; every
        # prior topic's README follows the same forward-reference convention
        # (see 12-helm/README.md -> 13-statefulsets/README.md), so we only
        # assert the link's presence/format, not that the target exists yet.
        match = re.search(r"\*\*Next topic:\*\* \[14 — DaemonSets\]\((.*?)\)", self.text)
        self.assertIsNotNone(match)

    def test_embedded_yaml_snippets_are_valid_yaml(self):
        blocks = extract_fenced_code_blocks(self.text, "yaml")
        self.assertGreaterEqual(len(blocks), 3)
        for block in blocks:
            with self.subTest(block=block[:40]):
                yaml.safe_load(block)

    def test_headless_service_snippet_matches_documented_behavior(self):
        blocks = extract_fenced_code_blocks(self.text, "yaml")
        service_block = next(b for b in blocks if "kind: Service" in b)
        doc = yaml.safe_load(service_block)
        self.assertEqual(doc["spec"]["clusterIP"], "None")

    def test_statefulset_walkthrough_snippet_matches_documented_behavior(self):
        blocks = extract_fenced_code_blocks(self.text, "yaml")
        sts_block = next(b for b in blocks if "kind: StatefulSet" in b)
        doc = yaml.safe_load(sts_block)
        self.assertEqual(doc["spec"]["serviceName"], "mydb")
        self.assertEqual(doc["spec"]["volumeClaimTemplates"][0]["metadata"]["name"], "data")

    def test_core_vocabulary_table_defines_key_terms(self):
        for term in [
            "**StatefulSet**",
            "**Headless Service**",
            "**Ordinal**",
            "**VolumeClaimTemplate**",
            "**podManagementPolicy**",
            "**updateStrategy**",
        ]:
            with self.subTest(term=term):
                self.assertIn(term, self.text)

    def test_interview_question_count(self):
        summaries = re.findall(r"<summary>(.*?)</summary>", self.text, re.DOTALL)
        self.assertEqual(len(summaries), 7)
        details_open = self.text.count("<details>")
        details_close = self.text.count("</details>")
        self.assertEqual(details_open, details_close)
        self.assertEqual(details_open, 7)


class ExercisesReadmeTests(unittest.TestCase):
    """13-statefulsets/exercises/README.md"""

    @classmethod
    def setUpClass(cls):
        cls.text = read_text(EXERCISES_README_PATH)

    def test_file_exists(self):
        self.assertTrue(os.path.isfile(EXERCISES_README_PATH))

    def test_title(self):
        self.assertTrue(self.text.startswith("# Topic 13 Exercises — StatefulSets"))

    def test_contains_seven_numbered_exercises_in_order(self):
        headings = re.findall(r"^## Exercise (\d+) — ", self.text, re.MULTILINE)
        self.assertEqual(headings, [str(n) for n in range(1, 8)])

    def test_every_referenced_example_file_exists(self):
        referenced = sorted(set(re.findall(r"\.\./examples/([\w.-]+\.yaml)", self.text)))
        self.assertTrue(referenced, "expected at least one example file reference")
        for filename in referenced:
            with self.subTest(filename=filename):
                self.assertIn(filename, EXAMPLE_FILES)
                self.assertTrue(os.path.isfile(os.path.join(EXAMPLES_DIR, filename)))

    def test_exercised_examples_are_referenced(self):
        # 05-parallel-management.yaml is a standalone comparison demo (see its
        # own header comment) and deliberately has no dedicated numbered
        # exercise, unlike the other four examples.
        referenced = set(re.findall(r"\.\./examples/([\w.-]+\.yaml)", self.text))
        expected = set(EXAMPLE_FILES) - {"05-parallel-management.yaml"}
        self.assertEqual(referenced, expected)

    def test_has_final_checkpoint_section(self):
        self.assertIn("## Checkpoint — Can you answer these?", self.text)

    def test_has_checklist_items(self):
        checklist_items = re.findall(r"^- \[ \] ", self.text, re.MULTILINE)
        self.assertGreater(len(checklist_items), 10)

    def test_pod_ordinals_referenced_match_statefulset_names_in_examples(self):
        # Each exercise references specific pod ordinals produced by a specific
        # example (web-0/web-1 from example 01, postgres-0 from example 02,
        # ordered-demo-0/-2 from example 03, dns-demo-0 from example 04). Verify
        # those ordinal names actually correspond to a StatefulSet defined in
        # the examples directory, so the exercise text can't silently drift
        # from the manifests it walks through.
        sts_names_in_examples = set()
        for filename in EXAMPLE_FILES:
            for doc in load_yaml_documents(os.path.join(EXAMPLES_DIR, filename)):
                if doc.get("kind") == "StatefulSet":
                    sts_names_in_examples.add(doc["metadata"]["name"])

        expected_ordinal_refs = ["web-0", "web-1", "postgres-0", "ordered-demo-0", "ordered-demo-2", "dns-demo-0"]
        for ref in expected_ordinal_refs:
            with self.subTest(ref=ref):
                self.assertIn(ref, self.text)
                base_name = ref.rsplit("-", 1)[0]
                self.assertIn(base_name, sts_names_in_examples)

    def test_next_topic_link_is_present(self):
        self.assertIn("**Next topic:** [14 — DaemonSets]", self.text)


if __name__ == "__main__":
    unittest.main()