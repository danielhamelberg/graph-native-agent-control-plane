# Security Policy

## Supported versions

This project is pre-release. Security fixes are applied only to the latest commit on `main` until a
stable release policy is published.

## Report a vulnerability

Do not open a public issue for a suspected vulnerability. Use GitHub's private vulnerability
reporting form:

<https://github.com/danielhamelberg/graph-native-agent-control-plane/security/advisories/new>

Include the affected revision, a minimal reproduction, expected impact, and whether the issue has
been disclosed elsewhere. Do not include real credentials, private benchmark payloads, personal
data, or destructive proof-of-concept material.

You should receive an acknowledgement within seven calendar days. This is a response target, not a
service-level guarantee.

## Security model

The package supplies deterministic control-plane primitives, not a security sandbox. Hash chains
are tamper-evident records, not signatures. Integrators remain responsible for agent isolation,
credential handling, authentication, authorization, network policy, durable storage, and trusted
confirmation of external side effects.
