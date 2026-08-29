# Security Policy

## Supported Versions

Ontographia is pre-1.0. Security fixes are applied to the latest release on the default branch (`main`).

| Version | Supported |
| ------- | --------- |
| `main` (latest) | :white_check_mark: |
| `0.1.x` | :white_check_mark: |
| `< 0.1.0` | :x: |

## Reporting a Vulnerability

**Please do not open a public GitHub issue for security vulnerabilities.**

Report security issues privately using one of these channels:

1. **GitHub Security Advisories (preferred):**  
   [Report a vulnerability](https://github.com/yohei1126/ontographia/security/advisories/new)
2. **Email:** Contact the repository owner via GitHub profile private communication if advisories are unavailable.

Include as much detail as possible:

- Affected component (Rust core, Python/Go bindings, CI, examples, etc.)
- Steps to reproduce
- Impact assessment (e.g. arbitrary code execution, data exposure, denial of service)
- Suggested fix or mitigation, if you have one

### What to expect

| Stage | Timeline |
| ----- | -------- |
| Initial acknowledgment | Within **3 business days** |
| Triage / severity assessment | Within **7 business days** |
| Fix or mitigation plan | Depends on severity; critical issues are prioritized |

We will keep you informed of progress. If the report is accepted, we aim to coordinate disclosure and credit (unless you prefer to remain anonymous). If declined, we will explain why (e.g. out of scope, not reproducible, or mitigated by configuration).

### Out of scope

- Issues in third-party dependencies without a demonstrable impact on Ontographia
- Neo4j deployment hardening not specific to this repository
- Social engineering or physical attacks

Thank you for helping keep Ontographia and its users safe.
