<!-- One issue per PR. Link it so merging closes it. -->

## Summary

<!-- One line: what changed and why. Not a diff summary. -->

Closes #

## Tradeoff / most likely to be wrong

<!-- The part you'd want a reviewer to look at hardest. "Nothing" is rarely true. -->

## Invented, not specified

<!--
Anything decided that the issue didn't specify: names, paths, defaults, sizes,
hostnames. These harden into later work, so flag them for a human decision.
Write "none" if the issue specified everything.
-->

## Cost and portability

- [ ] **Recurring cost**: does this add anything billed monthly (a NAT, a load
      balancer, a volume, a managed service)? If so, state the $/month here.
- [ ] **Portability**: nothing AWS-specific above the host layer (no AWS SDKs or
      IRSA in cluster workloads, object storage only via an S3-compatible
      endpoint). The k3d check enforces this once it exists (#8).
- [ ] **Memory**: new cluster components have requests/limits that fit the
      budget in ADR 0001.

## Definition of done

- [ ] `terraform fmt` / `validate` / `terraform test` pass for any Terraform touched
- [ ] Policies and charts touched have tests (a violating fixture for every policy)
- [ ] No secrets in code, committed env files or plan output; SOPS for anything encrypted
- [ ] Anything noticed but out of scope was **filed as an issue**, not folded in

## ADR

- [ ] **Did this need an ADR?** A decision that's expensive to reverse goes in
      `docs/adr/`. Say "no ADR needed" if that's the answer.

## Related issues filed from this work

<!-- "Filed #N — noticed while doing this", or "none". -->

---

The single required status check is **`ci`**, an aggregate that fails if any job
it `needs` failed. A new CI job that isn't added to `ci`'s `needs` still runs,
but can't block a merge.
