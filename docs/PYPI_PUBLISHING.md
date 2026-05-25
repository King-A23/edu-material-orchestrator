# PyPI Publishing Setup

The repository publishes Python distributions through `.github/workflows/publish-pypi.yml`.

## Trusted Publishing Prerequisites

1. Create or sign in to both a `PyPI` account and a `TestPyPI` account.
2. Register a trusted publisher on PyPI for:
   - project name: `edu_materials`
   - repository owner and repository name
   - workflow filename: `publish-pypi.yml`
   - environment name: `pypi`
3. Register a trusted publisher on TestPyPI with the same repository and workflow filename, but environment name `testpypi`.
4. In GitHub repository settings, require manual approval for the `pypi` environment before public publication.

## Workflow Paths

- `workflow_dispatch` with `target=testpypi` publishes to TestPyPI for dry runs.
- `workflow_dispatch` with `target=pypi` publishes to PyPI manually.
- `release.published` publishes to PyPI automatically after the build and verification jobs pass.

## Release Notes

- `python tools/verify_release_artifacts.py` validates both `sdist` and `wheel`, runs `twine check`, installs the wheel into an isolated target, and reruns smoke tests outside the source tree.
- The publish jobs use GitHub OIDC Trusted Publishing via `pypa/gh-action-pypi-publish@release/v1`; no long-lived PyPI API token should be stored in repository secrets.
