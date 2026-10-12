from __future__ import annotations

import json
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path

REPOSITORY = "Tyosx/ComfyUI-TYOS-MediaPrompt"
LEGACY_REPOSITORY = "Tyosx/ComfyUI-TYOS-LlamaSwap"
PLUGIN_DIR = Path(__file__).resolve().parent
PROMPTS = PLUGIN_DIR / "system_prompts.json"
DEFAULTS = "system_prompts.example.json"
SOURCE_URLS = [
    f"https://github.com/{REPOSITORY}/archive/refs/heads/main.zip",
    f"https://github.com/{LEGACY_REPOSITORY}/archive/refs/heads/main.zip",
]

PRESERVE = {".git", ".env", "system_prompts.json"}


def download(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "TYOS-MediaPrompt-Updater"})
    with urllib.request.urlopen(request, timeout=60) as stream, destination.open("wb") as output:
        shutil.copyfileobj(stream, output)


def read_prompts(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def find_source(archive: Path, target: Path) -> Path:
    with zipfile.ZipFile(archive) as bundle:
        # GitHub-generated archives use one top-level directory.
        bundle.extractall(target)
    for candidate in target.iterdir():
        if candidate.is_dir() and (candidate / "__init__.py").is_file():
            return candidate
    raise RuntimeError("The download does not contain a valid ComfyUI plugin.")


def update() -> None:
    saved = read_prompts(PROMPTS)
    with tempfile.TemporaryDirectory(prefix="tyos_mediaprompt_") as temp:
        staging = Path(temp)
        archive = staging / "release.zip"
        source = None
        errors = []
        for url in SOURCE_URLS:
            try:
                download(url, archive)
                source = find_source(archive, staging / "extracted")
                print(f"Source: {url}")
                break
            except Exception as error:
                errors.append(str(error))
                shutil.rmtree(staging / "extracted", ignore_errors=True)
        if source is None:
            raise RuntimeError("No valid release could be downloaded: " + "; ".join(errors))

        # Validate all required application files before touching the installation.
        for required in ("__init__.py", "web/js/tyos_llamaswap_vision_node.js"):
            if not (source / required).is_file():
                raise RuntimeError(f"Update is missing {required}; existing installation unchanged.")

        # Preserve user data in memory and a local backup before replacing anything.
        if PROMPTS.exists():
            backup = PLUGIN_DIR / "system_prompts.json.backup"
            shutil.copy2(PROMPTS, backup)
            print(f"Prompt backup: {backup.name}")

        # Replace only project-controlled files. Other local files are untouched.
        managed = (
            "__init__.py", "web", "README.md", "CHANGELOG.md",
            "LICENSE", "requirements.txt", DEFAULTS,
            "updater.py", "update.bat", ".gitignore",
        )
        for name in managed:
            new = source / name
            if not new.exists():
                continue
            current = PLUGIN_DIR / name
            if current.is_dir():
                shutil.rmtree(current)
            elif current.exists():
                current.unlink()
            if new.is_dir():
                shutil.copytree(new, current)
            else:
                shutil.copy2(new, current)

        if not PROMPTS.exists():
            defaults = read_prompts(PLUGIN_DIR / DEFAULTS)
            merged = dict(defaults)
            merged.update(saved)
            PROMPTS.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")

    print("Update completed. Saved system prompts were preserved.")
    print("Restart ComfyUI and refresh the browser.")


if __name__ == "__main__":
    try:
        update()
    except Exception as error:
        print(f"Update failed: {error}")
        raise SystemExit(1)
