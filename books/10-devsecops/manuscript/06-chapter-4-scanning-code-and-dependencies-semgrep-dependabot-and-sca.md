# Chapter 4 - Scanning Code and Dependencies: Semgrep, Dependabot, and SCA {#ch4}

## 4.1 SAST Without the Noise

**Static application security testing (SAST)** reads source code for patterns that become vulnerabilities: the SQL query built by string concatenation, the subprocess call with `shell=True` and user input, the disabled certificate check. The category has a reputation problem - older SAST products buried teams in false positives until every developer muted the tool - and **Semgrep** is the modern answer to that reputation: an open-source engine whose rules are small, readable, code-shaped patterns rather than opaque heuristics, plus a free community registry of thousands of rules maintained per language.

Running it locally takes a minute and should be the habit before every security-sensitive pull request:

```bash
pip install semgrep                    # or brew install semgrep
semgrep scan --config auto             # pick rules from the OSS registry by language
semgrep scan --config p/owasp-top-ten  # one focused ruleset, OWASP Top 10 patterns
```

The `--config auto` run on the `shopnow` repository surfaces findings as code locations with the matched pattern and a fix suggestion, and the output is honest in the way that matters: `--severity` filtering separates the rule's confidence from its impact, and `--exclude` silences vendored or test directories once, explicitly, in the config rather than by ignoring the tool. Rules are first-class YAML files, so a team can write one for its own framework's footgun - the internal `shopnow.db.query()` call that must never take a raw f-string - and review it like code.

In CI, the gate discipline from [Chapter 1](#ch1) applies: fail the build on `ERROR` severity findings, report `WARNING` to the pull request. The GitHub-native wrapper is **CodeQL**, GitHub's own semantic analysis engine: `github/codeql-action` v4 analyzes the codebase on every push to protected branches and uploads results as SARIF directly into the Security tab, which gives the team one place where scan results, alerts, and dismissals (each with a required reason) live. Semgrep for targeted, custom rules; CodeQL for deep whole-repo analysis; the two coexist without friction.

## 4.2 Dependencies: The Part of Your Code You Didn't Write

A modern application is mostly dependencies - the `shopnow` service imports hundreds of direct packages and thousands of transitive ones, any of which can carry Log4Shell-class risk. **Software composition analysis (SCA)** is the discipline of knowing and vetting that inventory, and its foundation is boring and non-negotiable: **lockfiles**. `package-lock.json`, `go.sum`, `uv.lock`, `Cargo.lock` make the dependency tree reproducible and diffable - without them, "which version of log4j do we run?" is unanswerable, which was exactly the December 2021 scramble for teams without inventory.

GitHub ships the SCA layer natively, and it should simply be on everywhere:

```yaml
# .github/dependabot.yml
version: 2
updates:
  - package-ecosystem: pip
    directory: /
    schedule:
      interval: weekly
    groups:
      minor-and-patch:
        update-types: ["minor", "patch"]   # batch low-risk bumps
  - package-ecosystem: github-actions
    directory: /
    schedule:
      interval: weekly                     # also bumps pinned action SHAs
  - package-ecosystem: docker
    directory: /
    schedule:
      interval: weekly
```

This does two distinct jobs. **Dependabot alerts** continuously match the resolved dependency graph against GitHub's advisory database and flag known CVEs with severity, affected versions, and fixed versions - a passive, always-on inventory check. **Dependabot version updates** (the file above) actively open pull requests to move versions forward, so the dependency tree drifts toward current instead of rotting until a CVE forces a rushed upgrade. The `groups` key is the practical difference between adoption and fatigue: grouped minor/patch bumps arrive as one reviewable PR per week instead of forty individually.

The **dependency review** action completes the loop at the moment it matters: on a pull request, it diffs the lockfile and comments with the licenses and advisories the change *introduces*, and can fail the build when the new dependency's license or severity crosses a threshold. A vulnerable version can therefore never enter `main` silently - it arrives as a red X with the advisory attached.

::: {.note}
**Best practice - treat a new dependency like a new hire**

Version pinning and scanning catch known-bad packages; they do not catch brand-new malicious ones (the 2024-2025 wave of typosquatted packages with immediate malicious releases). For significant additions, the two-minute human check is worth it: download counts and release history on the registry page, the project's repository (maintained? multiple maintainers? recent commits?), and whether the name is a plausible misspelling of something popular. SCA covers the *known*; a hiring standard covers the *unknown*.
:::

## 4.3 Malicious Code in Review: The Gitleaks Reunion

The last scanner in this chapter's belt is already installed: gitleaks from [Chapter 2](#ch2) runs in CI on every pull request, which closes the loop that pre-commit opened. The three scanners now form one pipeline - Semgrep/CodeQL for your code, Dependabot and dependency review for third-party code, gitleaks for the credentials either might carry - and each produces findings in the same pull request where a reviewer can act on them. That integration, rather than any individual tool, is the chapter's deliverable.

::: {.lab}
### Lab 2 - Catch the Planted Threats {#lab2}

1. Create a scratch branch of the `shopnow` repository. Plant two threats: commit a file `scripts/deploy.sh` containing a fake-but-realistic AWS key (`AKIA`-prefixed), and add `requests==2.27.1` (CVE-2023-32681, proxy-credential leak, fixed in 2.31.0) to `requirements.txt`. Push the branch and open a pull request.
2. Watch the checks: the gitleaks step must fail on the key (note the rule name and commit it flags), and dependency review must flag the vulnerable version with its advisory link.
3. Run `semgrep scan --config p/owasp-top-ten` locally against the branch; if `shopnow` has a planted injection pattern from a previous exercise, read the finding and the suggested fix.
4. Fix properly: rotate-and-remove the key (deleting the file is not remediation - say why, out loud), bump `requests` to `>= 2.31.0`, and re-run the scanners to green.
5. Commit the `.pre-commit-config.yaml`, `.gitleaks.toml`, and `.github/dependabot.yml` from this chapter to `main` so the next planted threat never gets this far.
:::

**See also:** [Chapter 5](#ch5) runs the same scanning discipline against the container image, where the dependencies live again as OS packages; [Chapter 6](#ch6) turns the dependency inventory into the SBOM that answers the next Log4Shell in minutes; [Appendix A](#appA) positions Semgrep, CodeQL, Dependabot, and Trivy in the broader tool landscape.
