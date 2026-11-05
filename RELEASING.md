# Releasing

Releases are automated. Pushing a version tag (`vX.Y.Z`) triggers
[`.github/workflows/release.yml`](.github/workflows/release.yml), which builds
the sdist + wheel and publishes them to [PyPI](https://pypi.org/p/android-agent)
via **Trusted Publishing** (OIDC) — no API token is stored in the repository.

## One-time PyPI setup (Trusted Publishing)

Do this once, before the first tag that should publish. It cannot be done from
CI — it is a manual step on PyPI by the project owner.

Because the project does not exist on PyPI yet, use a **pending** publisher:

1. Sign in to <https://pypi.org/> as the project owner (`andreshma`).
2. Go to **Account → Publishing** (<https://pypi.org/manage/account/publishing/>).
3. Under **Add a new pending publisher**, fill in:
   - **PyPI Project Name:** `android-agent`
   - **Owner:** `andreshma`
   - **Repository name:** `android-agent`
   - **Workflow name:** `release.yml`
   - **Environment name:** `pypi`
4. Save. PyPI will now trust the `pypi-publish` job in this repo's `release.yml`
   to publish `android-agent` — the project is created on the first successful
   publish.

(Optionally mirror the same for [TestPyPI](https://test.pypi.org/) to rehearse.)

## Cutting a release

1. Make sure `main` is green (all CI jobs) and the working tree is clean.
2. Bump `version` in [`pyproject.toml`](pyproject.toml) and regenerate the lock:
   ```bash
   uv lock
   ```
3. Move the `[Unreleased]` entries in [`CHANGELOG.md`](CHANGELOG.md) under a new
   `[X.Y.Z] - <date>` heading, add a fresh empty `[Unreleased]`, and update the
   compare links at the bottom.
4. Commit (`release: vX.Y.Z …`) and push `main`.
5. Create the GitHub release + tag (this is what triggers publishing):
   ```bash
   gh release create vX.Y.Z --title "vX.Y.Z" --notes-file <(sed -n '/## \[X.Y.Z\]/,/## \[/p' CHANGELOG.md)
   ```
   or write the notes inline. The tag push starts the `Release` workflow.
6. Watch the run: `gh run watch` (or the Actions tab). On success the new version
   appears on PyPI.

## Verifying a build locally (optional)

```bash
python -m pip install --upgrade build twine
python -m build
twine check dist/*
```

This is exactly what the workflow does before publishing.
