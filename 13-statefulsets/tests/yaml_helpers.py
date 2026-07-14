"""Shared helpers for loading and inspecting the StatefulSet example manifests.

These are small, dependency-free (PyYAML only) utilities used by the test
modules in this directory. They intentionally avoid any Kubernetes client
library since the tests are purely static/structural checks over the YAML
files added in 13-statefulsets/examples/ — no live cluster is required.
"""
from pathlib import Path

import yaml

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"


def load_documents(filename):
    """Parse a (possibly multi-document) YAML file and return non-empty docs.

    Leading comment-only documents (e.g. a stray '---' before the first real
    document) parse to `None` and are filtered out.
    """
    path = EXAMPLES_DIR / filename
    with path.open("r", encoding="utf-8") as fh:
        docs = list(yaml.safe_load_all(fh))
    return [doc for doc in docs if doc is not None]


def find_by_kind(docs, kind):
    """Return all documents whose `kind` matches."""
    return [doc for doc in docs if doc.get("kind") == kind]


def find_one_by_kind(docs, kind):
    """Return the single document of a given `kind`.

    Raises AssertionError if there isn't exactly one match, which is useful
    for catching accidental duplicate/missing resources in a manifest.
    """
    matches = find_by_kind(docs, kind)
    if len(matches) != 1:
        raise AssertionError(
            f"expected exactly one document of kind={kind!r}, found {len(matches)}"
        )
    return matches[0]


def is_headless(service):
    """A Service is 'headless' when spec.clusterIP is the literal string 'None'.

    Note: in YAML, `clusterIP: None` parses to the Python string "None" (not
    the YAML null type), since "None" is not a YAML 1.1 null literal. This is
    also how Kubernetes itself interprets the field.
    """
    return service.get("spec", {}).get("clusterIP") == "None"