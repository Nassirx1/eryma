# Security

This SDK is an additional probabilistic check, not a security boundary or safety certification. Use authorization, data minimization and deterministic validation independently. Model callbacks must not execute tools or other side effects.

For suspected vulnerabilities, do not post live credentials or private conversations in public issues. Use private vulnerability reporting on the eventual repository when enabled. A public reporting contact has not yet been configured for this local prerelease.

Guard errors block by default. No raw exception messages or blocked candidates are returned. The application must avoid exposing private context or keys through its own logs. Both guard switches and trusted policy/context must be controlled by the developer.
