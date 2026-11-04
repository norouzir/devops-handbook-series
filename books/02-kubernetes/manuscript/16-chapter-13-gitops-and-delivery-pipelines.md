# Chapter 13 - GitOps and Delivery Pipelines {#ch13}

The Docker book ended its pipeline chapter at the registry: image built, scanned, pushed with a digest. This chapter completes the journey into the cluster, and it argues for a specific architecture: continuous integration builds and verifies artifacts, but the cluster is not pushed to by the CI system, it is reconciled from `git`. That inversion, GitOps, is now the standard delivery pattern for Kubernetes, and Argo CD is its most deployed implementation. Along the way this chapter keeps an old promise: secrets must reach the cluster without ever living in plaintext in a repository.

## 13.1 CI, CD, and GitOps

A conventional pipeline builds the image, tests it, then pushes the new manifest to the cluster from the CI job, and it works until you audit it. The credentials that CI holds against production become the softest target in the estate; whatever deploys last wins over whatever `git` says; and nobody can answer what is running right now without querying the cluster. GitOps moves the final step: the repository, not the pipeline, declares desired state, and an in-cluster controller continuously reconciles the cluster toward that declaration. The pipeline's job shrinks to exactly one write: update the image tag in the environment overlay and let the pull-based controller take it from there.

The benefits compound quietly. The cluster becomes provable: `kubectl diff` against `git` is the drift detector, and an unauthorized `kubectl edit` visibly disagrees with the declared state within seconds. Rollback is a `git revert`, reviewable like any change. Credentials for deployment disappear entirely, since the controller pulls, nothing pushes. And environments are comparable by construction, because prod and staging differ by overlays, not by undocumented console clicks. The cost is a new daemon to operate and a new habit for humans who liked `kubectl apply`; Chapter 9's RBAC is how you enforce the habit, by revoking write access that the controller alone should hold.

| Aspect | Push from CI | GitOps pull |
| ------------- | ------------------- | ------------------- |
| Who holds prod credentials | The CI system | Nobody; the in-cluster controller pulls |
| Source of truth | Last pipeline that ran | The repository, continuously reconciled |
| Drift behavior | Undetected until next deploy | Detected and optionally auto-reverted |
| Rollback | Re-run an old pipeline | `git revert`; controller converges |
| Audit story | Pipeline logs, scattered | One `git` history of every state change |

: Table 13.1 - Push-based CD versus GitOps

## 13.2 The Pipeline, End to End

Concretely, the path from commit to cluster has five stations. CI builds with BuildKit as the Docker book prescribed, runs tests, and pushes the image tagged with both the commit SHA and, for release lines, a semantic version; the digest is the immutable handle everything else references. Security gates run next, scanning and policy checks on the image before it can be promoted. The delivery step is a pull request or an automated commit that bumps the tag in the environment's Kustomize overlay or Helm values, which is the only change that reaches production paths. Argo CD sees the repository change, applies it, and waits for health. The changelog writes itself, because the `git` history of the overlay is the release history.

```bash
# CI (GitHub Actions sketch): build, then bump the environment overlay
- name: Build and push
  run: |
    docker buildx build --push \
      -t registry.example.com/myorg/api:${GITHUB_SHA} \
      --provenance=true --sbom=true .

- name: Update staging overlay
  run: |
    cd overlays/staging
    kustomize edit set image myorg/api=registry.example.com/myorg/api:${GITHUB_SHA}
    git commit -am "staging: api ${GITHUB_SHA}" && git push
# Argo CD Application watching overlays/staging takes it from here
```

## 13.3 Argo CD in Practice

Argo CD's model is small: an `Application` watches one source, a `git` repo and path or a Helm chart with values, and syncs it to one destination cluster and namespace, rendering through Helm or Kustomize as needed. `AppProjects` group `Applications` with guardrails, which source repos and destinations an application may use, making the multi-team estate manageable, and `ApplicationSets` generate `Applications` from templates: one entry per cluster, per environment, or per `git` branch, which is how a growing fleet avoids hand-registering every app on every cluster. The sync policy choices encode intent: automated with pruning means `git` wins and deleted manifests are deleted for real, self-heal reverts drift immediately, and sync windows can hold a risky change until the operator is awake.

The two Argo concepts that prevent the most confusion are health and sync status, which are deliberately different. `Synced` means the cluster matches `git`; healthy means the resulting objects are working, `Deployments` `Available`, `Services` with endpoints, and the two can disagree in the most instructive ways: a synced but degraded rollout is your new image failing readiness, while an `OutOfSync` but healthy cluster is usually drift from a human edit or a controller writing fields, and the fix is deciding whose field-ownership story is right, with server-side apply diffing from Chapter 5 as the referee.

## 13.4 Progressive Delivery

A rolling update is not a release strategy; it is a default. Progressive delivery makes the canary real: send a fraction of traffic to the new version, compare its metrics to the stable version, and either promote or abort automatically. Argo Rollouts is the standard implementation: a `Rollout` resource replaces the `Deployment`, `TrafficRouting` splits traffic through the Gateway API or mesh from Chapter 6, and `AnalysisTemplates` query Prometheus from Chapter 12 so promotion is earned by p99 and error ratio, not by a timer. Blue-green is the other pattern Rollouts supports, keeping the old version warm and switching traffic atomically, which trades resource cost for a clean instant rollback. The pattern to avoid is the hand-rolled canary: a second `Deployment` behind one `Service` with manual weight juggling is exactly the state machine Rollouts already implements, with the metrics gates you would skip under deadline.

## 13.5 Secrets in a GitOps World

GitOps collides with secrets head-on: the repository must describe desired state, but credentials must not sit in it. The three working patterns all keep plaintext out of `git`. External Secrets Operator is the current default for new estates: manifests in `git` declare an `ExternalSecret` pointing at your real vault, AWS Secrets Manager, Vault, Azure Key Vault, and the operator materializes a Kubernetes `Secret` in the cluster, so `git` holds only references and the vault holds rotation duty. SealedSecrets encrypts the `Secret` with the cluster's key so the ciphertext is safe to commit, fully self-contained but rotation means re-encrypting. `SOPS` encrypts values in files with `age` or cloud KMS keys, pragmatic for smaller estates that like file-level control. What all three replace is the habit Chapter 5 warned about, and the rule survives every tooling argument: plaintext production credentials never enter `git`, the container layer, or a pipeline log.

::: {.warn}
**Watch out**

Auto-sync plus pruning is a powerful default and a spectacular foot-gun when the `Application` points at the wrong path: point an auto-syncing, pruning `Application` at an empty or half-migrated directory and it will faithfully delete everything it manages in the destination namespace. Guard the blast radius: `AppProject` restrictions on source and destination, a manual sync gate for production `Applications`, and a staging `Application` with identical structure that hits the same mistake first, on purpose, as a drill.
:::

**See also:** [Chapter 8](#ch8) for the artifacts a GitOps flow deploys, [Chapter 9](#ch9) for the credentials it must not leak, and [Chapter 14](#ch14) for the operations it still leaves you.
