"""
version_store.py — Policy document version tracking.

Manages a versions.json manifest for each policy group.

Usage:
    from analysis.version_store import VersionStore

    store = VersionStore("samples/policy/cms_ncd")
    store.register("2024-report-congress.txt", label="v1", date="2024-08-01")
    store.register("2025-report-congress.txt", label="v2", date="2025-04-01")
    store.list_versions()
"""

import json
import os
from datetime import datetime


class VersionStore:

    def __init__(self, policy_dir):
        self.policy_dir = policy_dir
        self.manifest_path = os.path.join(policy_dir, "versions.json")
        self._ensure_manifest()

    def _ensure_manifest(self):
        os.makedirs(self.policy_dir, exist_ok=True)
        if not os.path.exists(self.manifest_path):
            manifest = {
                "policy_name": os.path.basename(self.policy_dir),
                "versions": [],
                "latest": None,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            }
            self._save(manifest)

    def _load(self):
        with open(self.manifest_path, "r") as f:
            return json.load(f)

    def _save(self, manifest):
        manifest["updated_at"] = datetime.now().isoformat()
        with open(self.manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)

    def register(self, filename, label=None, date=None, notes=None):
        manifest = self._load()
        file_path = os.path.join(self.policy_dir, "processed", filename)

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        existing = [v for v in manifest["versions"] if v["file"] == filename]
        if existing:
            print(f"  ⚠️  '{filename}' already registered as {existing[0]['label']}")
            return existing[0]

        if label is None:
            label = f"v{len(manifest['versions']) + 1}"

        existing_labels = [v["label"] for v in manifest["versions"]]
        if label in existing_labels:
            raise ValueError(f"Label '{label}' already exists.")

        version_record = {
            "label": label,
            "file": filename,
            "date": date or datetime.now().strftime("%Y-%m-%d"),
            "registered_at": datetime.now().isoformat(),
            "notes": notes or "",
        }

        manifest["versions"].append(version_record)
        manifest["latest"] = label
        self._save(manifest)

        print(f"  ✅ Registered: {filename} → {label} (date: {version_record['date']})")
        return version_record

    def list_versions(self):
        manifest = self._load()
        versions = manifest["versions"]

        print(f"\n  Policy : {manifest['policy_name']}")
        print(f"  {'─' * 55}")

        if not versions:
            print("  No versions registered yet.")
            return []

        for v in versions:
            latest_tag = " ← latest" if v["label"] == manifest["latest"] else ""
            print(f"  {v['label']}  |  {v['file']}  |  {v['date']}{latest_tag}")

        print(f"  {'─' * 55}")
        print(f"  Total versions: {len(versions)}")
        return versions

    def get_version(self, label):
        manifest = self._load()
        for v in manifest["versions"]:
            if v["label"] == label:
                v["path"] = os.path.join(self.policy_dir, "processed", v["file"])
                return v
        raise ValueError(f"Version '{label}' not found.")

    def get_latest(self):
        manifest = self._load()
        if not manifest["latest"]:
            raise ValueError("No versions registered yet.")
        return self.get_version(manifest["latest"])

    def get_last_two(self):
        manifest = self._load()
        versions = manifest["versions"]
        if len(versions) < 2:
            raise ValueError(f"Need at least 2 versions. Currently have {len(versions)}.")
        older = {**versions[-2], "path": os.path.join(self.policy_dir, "processed", versions[-2]["file"])}
        newer = {**versions[-1], "path": os.path.join(self.policy_dir, "processed", versions[-1]["file"])}
        return older, newer

    def get_by_labels(self, label_a, label_b):
        """Get any two versions by their labels for flexible comparison."""
        return self.get_version(label_a), self.get_version(label_b)