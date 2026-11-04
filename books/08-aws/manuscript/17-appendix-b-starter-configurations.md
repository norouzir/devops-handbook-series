# Appendix B - Starter Configurations {#appB}

Copy these into a repository and adapt. Each corresponds to a chapter's running example and uses only services the book built. Versions are pinned as of October 2026; review pins when you adopt.

## B.1 EC2 Bootstrap Script (user data)

```bash
#!/bin/bash
# Chapter 3 - idempotent nginx bootstrap for AL2023
set -euo pipefail

dnf install -y nginx

cat > /usr/share/nginx/html/index.html <<'EOF'
<h1>shopnow - served by EC2</h1>
EOF

systemctl enable --now nginx

# Fetch a secret at boot with the instance role - never bake secrets into user data
# TOKEN=$(curl -sX PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 300")
# DB_URL=$(curl -sH "X-aws-ec2-metadata-token: $TOKEN" \
#   http://169.254.169.254/latest/meta-data/... || true)
```

## B.2 Terraform: VPC + EKS Skeleton

```hcl
# environments/prod/main.tf - Chapter 11 layout; modules own the details
terraform {
  required_version = "~> 1.9"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.70" }
  }
  backend "s3" {
    bucket       = "shopnow-tfstate-eu-central-1-prod"
    key          = "platform/terraform.tfstate"
    region       = "eu-central-1"
    use_lockfile = true
    encrypt      = true
  }
}

provider "aws" {
  region = "eu-central-1"
  default_tags { tags = { project = "shopnow", managed_by = "terraform", env = "prod" } }
}

module "network" {
  source        = "../../modules/network"
  name          = "shopnow"
  cidr          = "10.0.0.0/16"
  azs           = ["eu-central-1a", "eu-central-1b"]
  public_cidrs  = ["10.0.0.0/20", "10.0.16.0/20"]
  private_cidrs = ["10.0.32.0/20", "10.0.48.0/20"]
  single_nat    = false
}

module "eks" {
  source       = "../../modules/eks"
  cluster_name = "shopnow"
  subnet_ids   = module.network.private_subnet_ids
  node_type    = "t4g.medium"
  min_size     = 2
  max_size     = 4
}
```

## B.3 S3 Lifecycle Policy (deploy artifacts)

```json
{
  "Rules": [
    {
      "ID": "tier-assets",
      "Filter": { "Prefix": "assets/" },
      "Status": "Enabled",
      "Transitions": [
        { "Days": 30, "StorageClass": "INTELLIGENT_TIERING" },
        { "Days": 180, "StorageClass": "GLACIER_IR" }
      ]
    },
    {
      "ID": "expire-deploys",
      "Filter": { "Prefix": "deploys/" },
      "Status": "Enabled",
      "Expiration": { "Days": 90 }
    },
    {
      "ID": "expire-noncurrent",
      "Filter": {},
      "Status": "Enabled",
      "NoncurrentVersionExpiration": { "NoncurrentDays": 30 }
    }
  ]
}
```

## B.4 GitHub Actions Workflow (OIDC deploy to EKS)

```yaml
# .github/workflows/deploy.yml - Chapter 9
name: deploy
on:
  push:
    branches: [main]
permissions:
  id-token: write
  contents: read
jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v4

      - name: Configure AWS
        uses: aws-actions/configure-aws-credentials@v6
        with:
          role-to-assume: arn:aws:iam::111122223333:role/shopnow-deploy
          aws-region: eu-central-1

      - name: Login to ECR
        id: ecr
        uses: aws-actions/amazon-ecr-login@v2

      - name: Build and push (arm64)
        env:
          REGISTRY: ${{ steps.ecr.outputs.registry }}
        run: |
          docker buildx build --platform linux/arm64 \
            -t "$REGISTRY/shopnow:${{ github.sha }}" --push .

      - name: Deploy to EKS
        env:
          REGISTRY: ${{ steps.ecr.outputs.registry }}
        run: |
          aws eks update-kubeconfig --name shopnow --region eu-central-1
          kubectl set image deployment/shopnow-web \
            web="$REGISTRY/shopnow:${{ github.sha }}"
          kubectl rollout status deployment/shopnow-web --timeout=180s
```

## B.5 IAM Trust Policy for GitHub OIDC

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {
      "Federated": "arn:aws:iam::111122223333:oidc-provider/token.actions.githubusercontent.com"
    },
    "Action": "sts:AssumeRoleWithWebIdentity",
    "Condition": {
      "StringEquals": {
        "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
      },
      "StringLike": {
        "token.actions.githubusercontent.com:sub": "repo:acme/shopnow:environment:production"
      }
    }
  }]
}
```

## B.6 CloudWatch Alarms Starter (three every platform deserves)

```bash
# RDS free storage < 5 GB (Chapter 10)
aws cloudwatch put-metric-alarm \
  --alarm-name shopnow-db-low-storage \
  --namespace AWS/RDS --metric-name FreeStorageSpace \
  --dimensions Name=DBInstanceIdentifier,Value=shopnow-db \
  --statistic Average --period 300 --evaluation-periods 2 \
  --threshold 5368709120 --comparison-operator LessThanThreshold \
  --alarm-actions arn:aws:sns:eu-central-1:111122223333:platform-alerts

# Lambda errors above 5 in 5 minutes
aws cloudwatch put-metric-alarm \
  --alarm-name shopnow-fn-errors \
  --namespace AWS/Lambda --metric-name Errors \
  --dimensions Name=FunctionName,Value=shopnow-hello \
  --statistic Sum --period 300 --evaluation-periods 1 \
  --threshold 5 --comparison-operator GreaterThanThreshold \
  --alarm-actions arn:aws:sns:eu-central-1:111122223333:platform-alerts

# Estimated billing over 100 USD (Chapter 1's alarm, productionized)
aws cloudwatch put-metric-alarm \
  --alarm-name billing-over-100-usd \
  --namespace AWS/Billing --metric-name EstimatedCharges \
  --dimensions Name=Currency,Value=USD \
  --statistic Maximum --period 21600 --evaluation-periods 1 \
  --threshold 100 --comparison-operator GreaterThanThreshold \
  --alarm-actions arn:aws:sns:eu-central-1:111122223333:platform-alerts
```

## B.7 Log Retention Baseline

```bash
# The never-expire default is a cost leak - set retention on every group (Chapter 10)
for group in $(aws logs describe-log-groups --query 'logGroups[?retentionInDays==null].logGroupName' --output text); do
  case "$group" in
    /aws/lambda/*)  aws logs put-retention-policy --log-group-name "$group" --retention-in-days 30 ;;
    /aws/rds/*)     aws logs put-retention-policy --log-group-name "$group" --retention-in-days 90 ;;
    *)              aws logs put-retention-policy --log-group-name "$group" --retention-in-days 14 ;;
  esac
done
```
