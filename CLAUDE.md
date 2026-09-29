# Basecamp

The shared platform every portfolio project runs on: single-node k3s on an AWS EC2 `t4g.medium`, Cloudflare Tunnel for ingress, Flux for GitOps, CloudNativePG + Valkey shared by tenants. Global conventions and cross-cutting standards live in `~/.claude/CLAUDE.md` and the vault. This file only covers repo-local mechanics.

**Vault note**: `Projects/P0 Basecamp.md`, with the full design in `Architecture/Shared Platform Architecture.md` (paths relative to the vault root; see `Source of truth` in the global `CLAUDE.md`).

## The one rule that shapes everything here

**Only the host layer may know which machine it runs on.** `terraform/modules/host-aws` is AWS-specific; everything under `clusters/`, `infrastructure/`, `charts/` and `tenants/` must work unchanged on a home server. Concretely:

- No AWS SDKs, IRSA annotations or AWS-only CSI drivers in cluster workloads.
- Object storage only via an S3-compatible endpoint URL (S3 on AWS, MinIO/R2 elsewhere).
- Images must be multi-arch (`linux/arm64` + `linux/amd64`).
- `clusters/aws`, `clusters/home` and `clusters/ci` may differ **only** in backup endpoint, storage path and hostnames. Anything else that differs is a bug.

## Memory budget

The node has 4 GB. Every cluster component gets requests/limits that fit the budget recorded in ADR 0001 (~2.7 GB steady, ~3.2 GB peak). A new component states its footprint in the PR. The step-up to `t4g.large` is triggered by sustained > 75% memory or any OOM kill, not by convenience.

## Layout

- `terraform/bootstrap` — state bucket, GitHub OIDC role, budgets (applied once by hand)
- `terraform/modules/host-aws` — the host layer
- `terraform/cloudflare` — zone, tunnel, DNS
- `scripts/bootstrap-host.sh` — the host → cluster seam (cloud-init on EC2, by hand at home)
- `clusters/{aws,home,ci}` — Flux entry points per environment
- `infrastructure/` — cluster components (Traefik config, cloudflared, CNPG, Valkey, Alloy, policies)
- `charts/basecamp-app` — the golden-path library chart
- `tenants/<app>/values.yaml` — one per tenant; onboarding an app is one PR here
- `docs/adr/` — decision records

## Commands

- Hooks (once per clone): `scripts/setup-hooks.sh`
- Secret scan: `scripts/gitleaks.sh git --no-banner .`
- Gitleaks rule regression test: `scripts/test-gitleaks-rules.py`
- Terraform: `terraform fmt -check -recursive` (CI runs it on every PR)

## CI conventions

- The single required check is `ci`, an aggregate. **Every new job must be added to `ci`'s `needs`**, or it can't block a merge.
- Third-party actions are pinned to a commit SHA with the version in a comment; GitHub-owned actions (`actions/*`) use the major tag. Dependabot moves both.
- No trigger-level `paths:` filters: a skipped workflow never reports, and the required check would wait forever.

## Secret scanning

`.gitleaks.toml` extends the bundled ruleset with rules for the credential shapes the bundle was measured not to catch (datastore URLs with inline passwords, k3s tokens, Tailscale keys, Cloudflare tunnel tokens). If you add a credential shape to the repo's world, add a fixture to `scripts/test-gitleaks-rules.py` first and see whether it fires. Allowlist entries are scoped to a **value** with a written reason, never to a path.
