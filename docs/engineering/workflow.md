# Workflow — strategic handoff and delivery

The build pack is the durable strategic contract. It defines the outcome, scope, non-negotiables, architecture boundaries, research conclusions and gates, risks, dependencies, final acceptance, and a high-level suggested implementation approach. The implementation lead owns tactical decomposition with the user.

Treat suggested order as informed guidance, not a command. Preserve hard causal dependencies, but revise advisory sequencing when current code, tests, or unforeseen constraints justify a better route.

## Authority model

- **Strategic lead:** sets outcomes, guardrails, company-wide delivery governance, and final acceptance.
- **Implementation lead:** proposes and manages slices, actual order, integration, replanning, and delegation.
- **Execution agents:** complete bounded assignments and surface surprises; they do not change wider scope or architecture.
- **Human:** approves each tactical slice and is the only authority that physically merges to `main` in GitHub. This authority cannot be delegated.

## Before implementation

1. Read `AGENTS.md` and every active strategic document in order.
2. Inspect current code, tests, manifests, CI, branch state, and repository rules.
3. Resolve required research gates or return them to the user; do not adopt an irreversible design while its gate is open.
4. Evaluate the suggested implementation approach against repository reality.
5. Select and propose only the single best next slice: its outcome, boundaries, rationale, checks, risks, delivery shape, and useful delegation.
6. Discuss and revise that slice with the user before coding or creating its plan, issues, branches, PRs, or agent assignments. Do not build an upfront execution backlog for the full feature.

When evidence invalidates the plan, stop affected work, explain the impact, and propose a revision. Do not force reality to match the original suggestion.

## Delivery topology

Active topology: **per-slice spine with leaf PRs**. Every approved slice merges to `main` on its own, so `main` advances many times while the MVP is built. Branch names: spine `slice/<name>`, leaf `<name>/<short-unit>` (a leaf never shares a prefix path with its spine, since Git cannot hold both `slice/x` and `slice/x/y`).

### Per-slice spine with leaf PRs

1. Create the slice spine `slice/<name>` from current `main` when the human approves the slice.
2. Create each leaf branch from the current spine for a tactical unit chosen by the implementation lead. A slice usually has several leaves; a slice small enough for one unit may have one.
3. Implement the unit, tests, and affected docs; run self-verification and self-review.
4. Sync the leaf with the spine; stop on a non-trivial conflict.
5. Open a leaf PR to the spine, run the review loop, and require green CI.
6. The implementation lead may **squash-merge the clean leaf PR into the spine** and confirm the spine remains green.
7. Replan and repeat leaves as needed; leaf order remains tactical and adaptable.
8. When the slice's verification passes on the spine, sync it with `main`, resolve only trivial conflicts, and open the spine PR to `main` with the slice's `Closes` references.
9. Stop for the human to review and merge the spine PR. Propose the next slice only after that merge lands.

The agent never merges the spine to `main`, never enables auto-merge or a merge queue on `main`, never calls a merge API or automates the GitHub merge UI for a PR whose base is `main`, never pushes directly to `main`, and never delegates any of those actions. Squash-merging a clean leaf PR into the spine, as step 6 allows, is not covered by this prohibition. When the spine PR is ready, the human physically pushes the merge button in GitHub. One spine is active at a time.

## Delegation

The implementation lead retains slice selection, plan, issue, ordering, integration, and verification ownership. Delegate production code and test writing as concrete bounded assignments after the slice is approved. Size every assignment independently and use the least expensive capable model and reasoning effort; do not inherit an expensive primary configuration by default. Give each execution agent its scope, exclusions, constraints, interfaces, expected result, checks, branch ownership, and stop conditions. Require a concise return receipt with changed files, verification, decisions, surprises, and a commit or diff reference. Review delegated work before integration. If capable delegation is unavailable, stop and tell the human instead of silently moving implementation into the primary context.

## Build and self-verify

For each tactical unit:

1. Research unfamiliar or drift-prone APIs in current official documentation.
2. Implement only approved active scope and preserve strategic invariants.
3. Add or update tests and affected docs in the same change.
4. Run every command in the `AGENTS.md` definition of done until green.
5. Review the diff against [`code-quality.md`](code-quality.md), strategic acceptance, and the unit's derived checks.

## Pull request mechanics

- Use one PR for a complete, reviewable delivery unit chosen by the implementation lead; do not let this rule predetermine feature slicing.
- Follow repository branch naming and use a Conventional Commits PR title.
- In the PR body, state scope, verification evidence, material risks or deviations, documentation changes, and related issues.
- Use `Closes #N` only on a PR whose base is `main`. A leaf PR to a spine references its issue without closing it; the final spine PR carries the appropriate closing references. Confirm closure after the human merges to `main`.
- Re-sync the PR base and re-run relevant checks before review. Stop on non-trivial conflicts and never force-push a protected/shared branch.

## PR review loop

Use this reviewer precedence:

1. **GitHub Copilot code review first** when it is available for the repository. It is the preferred external reviewer because it adds no per-review model cost to this workflow.
2. **`review-pr` skill fallback** when Copilot review is unavailable, including private repositories where it is not enabled, or when Copilot cannot produce a usable review. If `address-pr-review` is available, use it to address the resulting comments; otherwise follow the inline mechanics below.
3. **Fresh review sub-agent fallback** only when neither Copilot nor `review-pr` is available. Delegate an independent inline adversarial review with bounded context: the PR diff, relevant strategic constraints, acceptance criteria, and verification evidence. Use the least expensive capable model/effort for the bounded review. If sub-agent delegation is unavailable, stop for human review; the author's self-review is not an independent review.

The selected reviewer changes the review source, not the quality gate. The clean-HEAD and address/reply/resolve requirements below always apply.

Repository facts: `cblack34/inventory`, public, GitHub Copilot code review enabled. Copilot reviews automatically when a PR opens. To request another pass, use `gh api -X POST repos/{owner}/{repo}/pulls/<pr-number>/requested_reviewers -f 'reviewers[]=Copilot'` with the literal PR number (only `{owner}`, `{repo}`, and `{branch}` are `gh api` placeholders) and the plain login `Copilot`. An empty reviewer list in the response is normal, and the review arrives asynchronously, typically within several minutes. If this stops working after a repository settings change, fall back to the Reviewers menu in the PR UI and update this paragraph. In this environment the fallback skills are named `pr-review:pr-review` (review) and `pr-review:address-pr-review` (address comments); use them where this document says `review-pr` and `address-pr-review`.

The **address → reply → resolve** flow is mandatory regardless of reviewer:

- **Settle and trust the right snapshot.** Wait briefly after requesting because a review can arrive as a partial snapshot. Count **all** unresolved review threads. Trust a review only when its commit id matches PR **HEAD**; a stale review does not count.
- **Evaluate every comment.** Fix in-scope issues in the branch. Return scope-changing feedback to the user. For valid deferred work, open a follow-up issue only when issue creation is authorized; otherwise record it in the PR handoff.
- **Reply in every thread, then resolve it.** Push the fix or explain the disposition before resolving—even when pushing back. Resolve before re-requesting so the next pass begins clean.
- **Re-run self-verification and CI** after every code change prompted by review.
- **Re-request review and wait for a zero-new-comment, HEAD-matched pass** before any permitted merge. Resolving the first batch alone is not a clean review.
- **Bound the loop:** at most three request → address cycles total, with a reasonable wait each. If Copilot is unavailable or does not post a usable HEAD review within a reasonable wait, switch to `review-pr`; changing reviewers does not reset the bound. If neither reviewer can complete, delegate the fresh review sub-agent, note that fallback in the PR, and never merge with a genuine unresolved issue.

## CI bootstrap

CI must run the `AGENTS.md` verification commands on every code-bearing PR. If the repository lacks CI, the implementation lead must propose CI bootstrap as the first code-bearing delivery unit. That initial PR is gated by complete local verification and review because CI does not yet exist; every later code-bearing merge requires green CI. Keep CI minimal and do not spend CI time on artifacts nobody consumes. Branch-protection required-status enforcement (a required `ci` check) is available here — the repository is public, and GitHub Free supports required status checks on public repos — so once CI exists, ask the owner to enable it; until then, “never integrate on red CI” remains mandatory agent discipline even without a server-side gate.

CI is GitHub Actions, one workflow at `.github/workflows/ci.yml`, running `make check` on every pull request, including each leaf PR into the spine, and adding `make e2e` in the slice that creates it (see the definition of done in `AGENTS.md`). The workflow's `pull_request` trigger runs against the merge ref, so no CI run ever exists against the spine's own head; confirming the spine “remains green” in step 6 above means running the definition-of-done commands locally against the updated spine, not relying on a CI run taken against it. No other jobs until something consumes their output.

## Final verification

Slice checks prove progress but never replace [`../acceptance.md`](../acceptance.md). Before the human `main` merge, run every final command and acceptance check on the direct PR branch or completed spine. Reconcile shipped behavior with strategic and descriptive docs. Report unresolved gates, accepted risks, deviations from suggested order, and deferred scope.

## Stop and return to the user

Stop affected work when:

- a directive, non-negotiable, or final criterion conflicts with implementation;
- a research gate is unresolved;
- current code requires an unapproved public-contract, architecture-boundary, scope, or material risk change;
- a paid service, incompatible license, destructive action, secret, production write, or broad refactor is required;
- two consecutive PRs fail, or the same test flakes across two runs;
- review finds a genuine unresolved issue or exhausts the fallback;
- integration needs a non-trivial conflict resolution or force-push;
- an external action exceeds the recorded authority;
- a bad merge already landed on `main`; open a revert PR, then stop and report.

- a migration would drop, rewrite, or backfill movement or batch-cost rows once real data exists; propose the compensating-movement alternative instead.

Everything else within the approved plan: keep going until the current delivery gate is reached.
