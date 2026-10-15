"""Emit installed Python distribution provenance without additional packages."""

import importlib.metadata
import json

packages = []
for distribution in importlib.metadata.distributions():
    metadata = distribution.metadata
    licenses = [value.removeprefix("License :: ") for value in metadata.get_all("Classifier", [])
                if value.startswith("License :: ")]
    packages.append({
        "name": metadata["Name"], "version": distribution.version,
        "license": metadata.get("License-Expression") or licenses or metadata.get("License"),
        "project_urls": metadata.get_all("Project-URL", []),
        "homepage": metadata.get("Home-page"),
        "license_files": [str(path) for path in distribution.files or []
                          if any(word in str(path).lower() for word in ("license", "copying", "notice"))],
    })
print(json.dumps(sorted(packages, key=lambda p: p["name"].lower()), indent=2))
