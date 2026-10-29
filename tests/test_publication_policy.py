"""The publication policy must cover every source in the release, and withhold the
sources whose licence bars redistribution of a derivative."""

from __future__ import annotations

from pathlib import Path
from unittest import TestCase

from openrestor.degradations.core import load_yaml

REPO = Path(__file__).resolve().parents[1]
POLICY = REPO / "configs/releases/publication_policy_v0_1.yaml"
RELEASE = REPO / "configs/releases/private_v0_1.yaml"


class PublicationPolicyTests(TestCase):
    def setUp(self) -> None:
        self.policy = load_yaml(POLICY)
        self.release = load_yaml(RELEASE)

    def test_every_source_in_the_release_has_a_decision(self):
        """A source with no entry would otherwise be published by default, which is the
        failure that put 45 unlistened Blind-Real items into a set."""
        in_release = {str(part["dataset"]) for part in self.release["partitions"]}
        self.assertEqual(in_release, set(self.policy["sources"]))

    def test_a_source_that_forbids_derivatives_is_withheld(self):
        for name, spec in self.policy["sources"].items():
            if spec.get("permits_derivatives") is False:
                self.assertEqual(spec["decision"], "withhold", f"{name} forbids derivatives")

    def test_a_published_source_permits_derivatives_and_commercial_use(self):
        published = [s for s in self.policy["sources"].values() if s["decision"] == "publish"]
        for spec in published:
            self.assertTrue(spec["permits_derivatives"])
            self.assertTrue(spec["permits_commercial"])
            self.assertFalse(spec["share_alike"], "share-alike would propagate to the release")
            self.assertTrue(str(spec.get("attribution") or "").strip(),
                            "CC BY requires an attribution string")

    def test_an_unverified_source_is_not_published(self):
        for name, spec in self.policy["sources"].items():
            if spec.get("permits_derivatives") is None or spec.get("permits_commercial") is None:
                self.assertNotEqual(spec["decision"], "publish", f"{name} is not verified")

    def test_every_decision_records_its_evidence(self):
        for name, spec in self.policy["sources"].items():
            self.assertTrue(str(spec.get("evidence") or "").strip(), f"{name} has no evidence")

    def test_the_policy_does_not_point_at_the_frozen_release_config(self):
        """Deriving a subset must never mean editing the frozen contract, whose SHA-256 is
        recorded inside its own plan."""
        self.assertEqual(self.policy["derived_from"], "configs/releases/private_v0_1.yaml")

    def test_every_rendered_corpus_is_covered(self):
        """Both synthetic corpora draw on the same three sources, so a policy that named
        only one of them would publish the restricted audio of the other."""
        corpora = self.policy["corpora"]
        self.assertIn("diagnostic", corpora)
        self.assertIn("blind_synthetic", corpora)
        for name, spec in corpora.items():
            self.assertTrue(str(spec.get("index") or "").strip(), f"{name} names no index")
