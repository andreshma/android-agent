# Project governance

This document describes how **android-agent** is run, so contributors know how
decisions are made and how to get involved. It is deliberately lightweight and
will grow with the project.

## Current model

android-agent is a small, early-stage project with a **single maintainer**
([@andreshma](https://github.com/andreshma)), who is responsible for reviewing
contributions, cutting releases, and the final decision on scope and direction.

As the project grows, additional maintainers may be added (see below) and this
document will be updated to reflect a more shared model.

## Scope and non-goals

The project's scope is fixed and security-relevant: android-agent operates
**only on a device its user owns and physically controls**, behind an explicit
consent gate. Helping bypass lock screens, Factory Reset Protection (FRP),
carrier locks, or the security of a device the user does not own is an
**explicit non-goal** and will not be accepted, regardless of implementation
quality. See [README](README.md) and [SECURITY.md](SECURITY.md).

## How decisions are made

- **Everyday changes** (bug fixes, docs, tests, dependency bumps) are decided
  through normal pull-request review.
- **Design-level changes** (new capabilities, changes to the security boundary,
  the allowlist, or the sandbox) should start as a GitHub
  [Discussion](https://github.com/andreshma/android-agent/discussions) or an
  issue, and significant ones are recorded as an
  [ADR](docs/adr). The maintainer makes the final call.
- Changes that would widen the scope beyond the non-goals above are declined.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the branching model (Gitflow),
coding standards, and the pull-request process. All participation is governed by
the [Code of Conduct](CODE_OF_CONDUCT.md).

## Becoming a maintainer

There is no fixed quota. A contributor who has shown sustained, high-quality
involvement — good reviews, reliable patches, and care for the project's
security scope — may be invited by the current maintainer to become a
maintainer. Maintainers are expected to uphold this document and the Code of
Conduct.

## Releases

Releases follow [Semantic Versioning](https://semver.org) and are published from
`main` via tagged GitHub Releases. The changelog lives in
[CHANGELOG.md](CHANGELOG.md).
