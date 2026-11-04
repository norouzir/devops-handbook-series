# Appendix B - Starter Workflows {#appB}

## B.1 Standard CI for a Node.js Service

```yaml
name: CI
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
permissions:
  contents: read
concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true
jobs:
  ci:
    runs-on: ubuntu-24.04
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v6
      - uses: actions/setup-node@v5
        with:
          node-version: 22
          cache: npm
      - run: npm ci
      - run: npm run lint
      - run: npm test -- --coverage
      - run: npm run build
```

## B.2 Container Build and Push to GHCR

```yaml
name: Container
on:
  push:
    branches: [main]
permissions:
  contents: read
  packages: write
  id-token: write
jobs:
  build:
    runs-on: ubuntu-24.04
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@v6
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: docker/build-push-action@v6
        with:
          context: .
          push: true
          tags: |
            ghcr.io/${{ github.repository }}:${{ github.sha }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
          provenance: mode=max
          sbom: true
      - uses: actions/attest-build-provenance@v2
        with:
          subject-name: ghcr.io/${{ github.repository }}
          subject-digest: ${{ steps.push.outputs.digest }}
```

## B.3 Environment-Gated Production Deploy

```yaml
name: CD
on:
  push:
    branches: [main]
permissions:
  contents: read
concurrency:
  group: cd-production
cancel-in-progress: false
jobs:
  deploy-production:
    runs-on: ubuntu-24.04
    timeout-minutes: 20
    environment:
      name: production
      url: https://app.example.com
    permissions:
      contents: read
      id-token: write
      deployments: write
    steps:
      - uses: actions/checkout@v6
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::123456789012:role/gha-deploy
          aws-region: eu-central-1
      - run: ./scripts/deploy.sh "$GITHUB_SHA"
```

## B.4 Reusable Workflow: Definition and Caller

```yaml
# .github/workflows/service-ci.yml  (in org/platform)
name: Reusable service CI
on:
  workflow_call:
    inputs:
      service-dir:
        type: string
        required: true
      node-version:
        type: string
        default: '22'
    outputs:
      version:
        value: ${{ jobs.build.outputs.version }}
jobs:
  build:
    runs-on: ubuntu-24.04
    timeout-minutes: 15
    permissions:
      contents: read
    outputs:
      version: ${{ steps.ver.outputs.version }}
    defaults:
      run:
        working-directory: ${{ inputs.service-dir }}
    steps:
      - uses: actions/checkout@v6
      - uses: actions/setup-node@v5
        with: { node-version: '${{ inputs.node-version }}', cache: npm }
      - run: npm ci
      - run: npm test
      - id: ver
        run: echo "version=$(git describe --tags --always)" >> "$GITHUB_OUTPUT"

# ---- caller in any service repository ----
jobs:
  ci:
    uses: org/platform/.github/workflows/service-ci.yml@v3
    with:
      service-dir: services/api
    permissions:
      contents: read
```
