"""Unit tests for the StatefulSets topic documentation:
  - 13-statefulsets/README.md
  - 13-statefulsets/exercises/README.md

These tests treat the Markdown as structured content: they check that expected
sections exist, that embedded YAML snippets are syntactically valid, and that
relative links/example references actually resolve to files on disk. This catches
the most common regressions in a docs-only PR: broken links, renamed sections, and
YAML code blocks that don't actually parse.
"""
import os
import re
import unittest

import yaml

TOPIC_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
README_PATH = os.path.join(TOPIC_DIR, "README.md")
EXERCISES_README_PATH = os.path.join(TOPIC_DIR, "exercises", "README.md")
EXAMPLES_DIR = os.path.join(TOPIC_DIR, "examples")


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def extract_fenced_blocks(text, lang):
    """Extract the contents of ```<lang> ... ``` fenced code blocks."""
    pattern = r"```" + re.escape(lang) + r"\n(.*?)```"
    return re.findall(pattern, text, re.DOTALL)


def resolve_link(base_file, relative_link):
    return os.path.normpath(os.path.join(os.path.dirname(base_file), relative_link))


class TestTopicReadme(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.content = read(README_PATH)

    def test_file_exists_and_is_not_empty(self):
        self.assertTrue(os.path.isfile(README_PATH))
        self.assertGreater(len(self.content.strip()), 0)

    def test_title_is_first_line(self):
        first_line = self.content.splitlines()[0]
        self.assertEqual(first_line, "# 13 — StatefulSets")

    def test_required_sections_present_in_order(self):
        required_sections = [
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
        positions = []
        for section in required_sections:
            with self.subTest(section=section):
                self.assertIn(section, self.content)
                positions.append(self.content.index(section))
        self.assertEqual(
            positions,
            sorted(positions),
            "sections should appear in the documented order",
        )

    def test_embedded_yaml_blocks_are_syntactically_valid(self):
        blocks = extract_fenced_blocks(self.content, "yaml")
        self.assertEqual(len(blocks), 3, "expected exactly 3 fenced yaml blocks")
        for i, block in enumerate(blocks):
            with self.subTest(block_index=i):
                try:
                    yaml.safe_load(block)
                except yaml.YAMLError as exc:
                    self.fail(f"yaml block {i} failed to parse: {exc}")

    def test_headless_service_snippet_uses_clusterip_none(self):
        # `clusterIP: None` is Kubernetes' magic string value for "headless".
        # YAML parses the bare word `None` as the string "None", not a null.
        blocks = extract_fenced_blocks(self.content, "yaml")
        headless_blocks = [b for b in blocks if "clusterIP: None" in b]
        self.assertGreaterEqual(len(headless_blocks), 1)
        parsed = yaml.safe_load(headless_blocks[0])
        self.assertEqual(parsed["kind"], "Service")
        self.assertEqual(parsed["spec"]["clusterIP"], "None")

    def test_statefulset_walkthrough_snippet_matches_headless_service_name(self):
        """The doc's own example must be internally consistent: the StatefulSet's
        serviceName should reference the same name used by the headless Service
        snippet shown just above it."""
        blocks = extract_fenced_blocks(self.content, "yaml")
        service_doc = yaml.safe_load(blocks[0])
        statefulset_doc = yaml.safe_load(blocks[1])
        self.assertEqual(service_doc["kind"], "Service")
        self.assertEqual(statefulset_doc["kind"], "StatefulSet")
        self.assertEqual(
            statefulset_doc["spec"]["serviceName"], service_doc["metadata"]["name"]
        )

    def test_statefulset_walkthrough_volume_mount_matches_claim_template(self):
        blocks = extract_fenced_blocks(self.content, "yaml")
        statefulset_doc = yaml.safe_load(blocks[1])
        container = statefulset_doc["spec"]["template"]["spec"]["containers"][0]
        mount_names = {m["name"] for m in container["volumeMounts"]}
        vct_names = {
            vct["metadata"]["name"]
            for vct in statefulset_doc["spec"]["volumeClaimTemplates"]
        }
        self.assertEqual(mount_names, vct_names)

    def test_ondelete_snippet_is_valid_and_uses_ondelete_type(self):
        blocks = extract_fenced_blocks(self.content, "yaml")
        ondelete_block = yaml.safe_load(blocks[2])
        self.assertEqual(ondelete_block["spec"]["updateStrategy"]["type"], "OnDelete")

    def test_previous_topic_link_resolves_to_existing_file(self):
        match = re.search(
            r"\*\*Previous topic:\*\*\s*\[[^\]]*\]\(([^)]+)\)", self.content
        )
        self.assertIsNotNone(match, "Previous topic link not found")
        resolved = resolve_link(README_PATH, match.group(1))
        self.assertTrue(
            os.path.isfile(resolved), f"Previous topic link target missing: {resolved}"
        )

    def test_next_topic_link_has_expected_target(self):
        match = re.search(
            r"\*\*Next topic:\*\*\s*\[[^\]]*\]\(([^)]+)\)", self.content
        )
        self.assertIsNotNone(match, "Next topic link not found")
        self.assertEqual(match.group(1), "../14-daemonsets/README.md")

    def test_exercises_link_resolves_to_existing_file(self):
        match = re.search(r"\[exercises/README\.md\]\(([^)]+)\)", self.content)
        self.assertIsNotNone(match, "exercises/README.md link not found")
        resolved = resolve_link(README_PATH, match.group(1))
        self.assertTrue(os.path.isfile(resolved))

    def test_vocabulary_table_defines_expected_terms(self):
        expected_terms = [
            "StatefulSet",
            "Headless Service",
            "Ordinal",
            "Stable network identity",
            "VolumeClaimTemplate",
            "Ordered deployment",
            "Ordered termination",
            "podManagementPolicy",
            "updateStrategy",
        ]
        for term in expected_terms:
            with self.subTest(term=term):
                self.assertIn(f"**{term}**", self.content)

    def test_interview_questions_use_details_disclosure_widgets(self):
        self.assertGreaterEqual(self.content.count("<details>"), 5)
        self.assertEqual(
            self.content.count("<details>"), self.content.count("</details>")
        )
        self.assertEqual(self.content.count("<summary>"), self.content.count("</summary>"))


class TestExercisesReadme(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.content = read(EXERCISES_README_PATH)

    def test_file_exists_and_is_not_empty(self):
        self.assertTrue(os.path.isfile(EXERCISES_README_PATH))
        self.assertGreater(len(self.content.strip()), 0)

    def test_title_is_first_line(self):
        first_line = self.content.splitlines()[0]
        self.assertEqual(first_line, "# Topic 13 Exercises — StatefulSets")

    def test_exactly_seven_exercises_present(self):
        for i in range(1, 8):
            with self.subTest(exercise=i):
                self.assertIn(f"## Exercise {i} —", self.content)
        self.assertNotIn("## Exercise 8", self.content)
        self.assertNotIn("## Exercise 0", self.content)

    def test_exercises_appear_in_ascending_order(self):
        positions = [
            self.content.index(f"## Exercise {i} —") for i in range(1, 8)
        ]
        self.assertEqual(positions, sorted(positions))

    def test_referenced_example_files_all_exist(self):
        referenced = set(re.findall(r"\.\./examples/([\w.-]+\.yaml)", self.content))
        self.assertTrue(referenced, "expected at least one example file reference")
        for filename in referenced:
            with self.subTest(filename=filename):
                self.assertTrue(
                    os.path.isfile(os.path.join(EXAMPLES_DIR, filename)),
                    f"exercises reference missing example file: {filename}",
                )

    def test_every_example_referenced_at_least_once_except_parallel_demo(self):
        """05-parallel-management.yaml is intentionally not used by any exercise;
        every other example should be referenced at least once."""
        referenced = set(re.findall(r"\.\./examples/([\w.-]+\.yaml)", self.content))
        expected_referenced = {
            "01-statefulset-basics.yaml",
            "02-postgres-statefulset.yaml",
            "03-ordered-startup-demo.yaml",
            "04-headless-dns-demo.yaml",
        }
        self.assertTrue(expected_referenced.issubset(referenced))
        self.assertNotIn("05-parallel-management.yaml", referenced)

    def test_checkpoint_section_present(self):
        self.assertIn("## Checkpoint — Can you answer these?", self.content)

    def test_next_topic_link_target(self):
        match = re.search(
            r"\*\*Next topic:\*\*\s*\[[^\]]*\]\(([^)]+)\)", self.content
        )
        self.assertIsNotNone(match, "Next topic link not found")
        self.assertEqual(match.group(1), "../../14-daemonsets/README.md")

    def test_checklist_items_use_markdown_checkboxes(self):
        checkbox_count = self.content.count("- [ ]")
        self.assertGreaterEqual(
            checkbox_count, 20, "expected numerous checkpoint checkboxes"
        )


if __name__ == "__main__":
    unittest.main()