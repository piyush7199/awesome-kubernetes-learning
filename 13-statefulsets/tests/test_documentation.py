"""
Tests for the documentation added in this PR:
  * 13-statefulsets/README.md
  * 13-statefulsets/exercises/README.md

These are static checks over the Markdown content: required sections exist,
fenced YAML snippets are syntactically valid, internal relative links resolve
to real files, and structural elements (like <details>/<summary> blocks) are
well-formed and balanced.
"""
import re
import unittest
from pathlib import Path

import yaml

TOPIC_DIR = Path(__file__).resolve().parent.parent
README = TOPIC_DIR / "README.md"
EXERCISES_README = TOPIC_DIR / "exercises" / "README.md"

# The next-topic link intentionally points at a topic folder that doesn't
# exist yet in the repo (it's a forward reference, consistent with the root
# README's "coming soon" topics). We don't fail the link-resolution test for
# these known, deliberate forward references.
KNOWN_FORWARD_REFERENCES = {"../14-daemonsets/README.md", "../../14-daemonsets/README.md"}


def extract_markdown_links(text):
    """Return all markdown link targets, e.g. from [label](target)."""
    return re.findall(r"\]\(([^)\s]+)\)", text)


def extract_fenced_code_blocks(text, language):
    pattern = rf"```{language}\n(.*?)```"
    return re.findall(pattern, text, flags=re.DOTALL)


def strip_fenced_code_blocks(text):
    """Remove all ```...``` fenced blocks so heading regexes don't match
    shell comments (e.g. '# Apply:') that happen to look like Markdown
    headings when scanned line-by-line."""
    return re.sub(r"```.*?```", "", text, flags=re.DOTALL)


class TestTopicReadme(unittest.TestCase):
    """13-statefulsets/README.md"""

    @classmethod
    def setUpClass(cls):
        cls.text = README.read_text(encoding="utf-8")

    def test_file_exists(self):
        self.assertTrue(README.is_file())

    def test_has_single_top_level_title(self):
        prose = strip_fenced_code_blocks(self.text)
        titles = re.findall(r"^# .+$", prose, flags=re.MULTILINE)
        self.assertEqual(len(titles), 1)
        self.assertIn("StatefulSets", titles[0])

    def test_contains_required_sections(self):
        required_headings = [
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
        for heading in required_headings:
            with self.subTest(heading=heading):
                self.assertIn(heading, self.text)

    def test_fenced_yaml_snippets_are_valid_yaml(self):
        blocks = extract_fenced_code_blocks(self.text, "yaml")
        self.assertGreater(len(blocks), 0, "expected at least one ```yaml fenced block")
        for i, block in enumerate(blocks):
            with self.subTest(block_index=i):
                # Should not raise
                list(yaml.safe_load_all(block))

    def test_walkthrough_statefulset_snippet_is_internally_consistent(self):
        blocks = extract_fenced_code_blocks(self.text, "yaml")
        # Find the full "mydb" StatefulSet walkthrough example.
        walkthrough = next(b for b in blocks if "kind: StatefulSet" in b and "mydb" in b)
        doc = yaml.safe_load(walkthrough)
        self.assertEqual(doc["kind"], "StatefulSet")
        self.assertEqual(doc["spec"]["serviceName"], "mydb")

        claim_name = doc["spec"]["volumeClaimTemplates"][0]["metadata"]["name"]
        mount_names = {
            m["name"]
            for c in doc["spec"]["template"]["spec"]["containers"]
            for m in c.get("volumeMounts", [])
        }
        self.assertIn(claim_name, mount_names)

    def test_headless_service_snippet_has_cluster_ip_none(self):
        blocks = extract_fenced_code_blocks(self.text, "yaml")
        headless_snippet = next(b for b in blocks if "kind: Service" in b)
        doc = yaml.safe_load(headless_snippet)
        self.assertEqual(doc["spec"]["clusterIP"], "None")

    def test_interview_question_details_blocks_are_balanced(self):
        opens = self.text.count("<details>")
        closes = self.text.count("</details>")
        summaries = self.text.count("<summary>")
        self.assertEqual(opens, closes)
        self.assertEqual(opens, summaries)
        self.assertGreaterEqual(opens, 5, "expected several interview Q&A entries")

    def test_code_fence_markers_are_balanced(self):
        fence_count = self.text.count("```")
        self.assertEqual(fence_count % 2, 0, "unbalanced ``` fenced code blocks")

    def test_internal_relative_links_resolve_to_existing_files(self):
        links = extract_markdown_links(self.text)
        relative_links = [
            link for link in links if link.startswith("./") or link.startswith("../")
        ]
        self.assertGreater(len(relative_links), 0)
        for link in relative_links:
            if link in KNOWN_FORWARD_REFERENCES:
                continue
            with self.subTest(link=link):
                resolved = (README.parent / link).resolve()
                self.assertTrue(resolved.is_file(), f"broken relative link: {link}")

    def test_links_to_previous_and_next_topic_present(self):
        self.assertIn("../12-helm/README.md", self.text)
        self.assertIn("../14-daemonsets/README.md", self.text)

    def test_summary_table_mentions_all_key_concepts(self):
        summary_section = self.text.split("## Summary", 1)[1].split("## Exercises", 1)[0]
        for concept in ["volumeClaimTemplates", "Headless Service", "podManagementPolicy"]:
            with self.subTest(concept=concept):
                self.assertIn(concept, summary_section)


class TestExercisesReadme(unittest.TestCase):
    """13-statefulsets/exercises/README.md"""

    @classmethod
    def setUpClass(cls):
        cls.text = EXERCISES_README.read_text(encoding="utf-8")

    def test_file_exists(self):
        self.assertTrue(EXERCISES_README.is_file())

    def test_has_single_top_level_title(self):
        prose = strip_fenced_code_blocks(self.text)
        titles = re.findall(r"^# .+$", prose, flags=re.MULTILINE)
        self.assertEqual(len(titles), 1)
        self.assertIn("StatefulSets", titles[0])

    def test_contains_seven_numbered_exercises_in_order(self):
        headings = re.findall(r"^## Exercise (\d+) — .+$", self.text, flags=re.MULTILINE)
        numbers = [int(n) for n in headings]
        self.assertEqual(numbers, list(range(1, 8)))

    def test_contains_final_checkpoint_section(self):
        self.assertIn("## Checkpoint — Can you answer these?", self.text)

    def test_bash_fenced_blocks_are_balanced_and_non_empty(self):
        blocks = extract_fenced_code_blocks(self.text, "bash")
        self.assertGreater(len(blocks), 0)
        for block in blocks:
            self.assertTrue(block.strip(), "found an empty ```bash block")

    def test_code_fence_markers_are_balanced(self):
        fence_count = self.text.count("```")
        self.assertEqual(fence_count % 2, 0, "unbalanced ``` fenced code blocks")

    def test_referenced_example_files_exist(self):
        links = extract_markdown_links(self.text)
        example_refs = sorted(set(re.findall(r"\.\./examples/[\w.\-]+\.yaml", self.text)))
        self.assertGreater(len(example_refs), 0)
        for ref in example_refs:
            with self.subTest(ref=ref):
                resolved = (EXERCISES_README.parent / ref).resolve()
                self.assertTrue(resolved.is_file(), f"exercise references missing file: {ref}")
        # sanity: every example file added in this PR is referenced somewhere
        for filename in [
            "01-statefulset-basics.yaml",
            "02-postgres-statefulset.yaml",
            "03-ordered-startup-demo.yaml",
            "04-headless-dns-demo.yaml",
        ]:
            with self.subTest(filename=filename):
                self.assertTrue(any(filename in ref for ref in example_refs))

    def test_internal_relative_links_resolve_to_existing_files(self):
        links = extract_markdown_links(self.text)
        relative_links = [
            link for link in links if link.startswith("./") or link.startswith("../")
        ]
        self.assertGreater(len(relative_links), 0)
        for link in relative_links:
            if link in KNOWN_FORWARD_REFERENCES:
                continue
            with self.subTest(link=link):
                resolved = (EXERCISES_README.parent / link).resolve()
                self.assertTrue(resolved.is_file(), f"broken relative link: {link}")

    def test_each_exercise_has_a_goal_line(self):
        exercise_sections = re.split(r"^## Exercise \d+ — .+$", self.text, flags=re.MULTILINE)[1:]
        self.assertEqual(len(exercise_sections), 7)
        for i, section in enumerate(exercise_sections, start=1):
            with self.subTest(exercise=i):
                self.assertIn("**Goal:**", section)


if __name__ == "__main__":
    unittest.main()