# Appendix A - AWS CLI Quick Reference {#appA}

This appendix collects the invocations that recur across the book, organized by service. All commands assume AWS CLI v2, a configured profile ([Chapter 1](#ch1)), and `--output json` unless stated. Replace Region (`eu-central-1`) and the example identifiers with your own.

## Identity and Account

| Task | Command |
| --- | --- |
| Who am I acting as? | `aws sts get-caller-identity` |
| Assume a role | `aws sts assume-role --role-arn <arn> --role-session-name <name>` |
| List profiles' accounts | `aws sts get-caller-identity --profile <name>` |
| Account aliases | `aws iam list-account-aliases` |

## EC2 and EBS

| Task | Command |
| --- | --- |
| Instances as a table | `aws ec2 describe-instances --query 'Reservations[].Instances[].[InstanceId,InstanceType,State.Name,PublicIpAddress]' --output table` |
| Latest AL2023 AMI | `aws ssm get-parameters --names /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 --query 'Parameters[0].Value' --output text` |
| Launch (with tags, IMDSv2) | `aws ec2 run-instances --image-id <ami> --instance-type t4g.small --key-name <key> --security-group-ids <sg> --metadata-options "HttpTokens=required" --tag-specifications 'ResourceType=instance,Tags=[{Key=project,Value=shopnow}]'` |
| Start / stop / terminate | `aws ec2 start-instances --instance-ids <id>` / `stop-instances` / `terminate-instances` |
| Session shell (no SSH) | `aws ssm start-session --target <id>` |
| Volumes of an instance | `aws ec2 describe-volumes --filters Name=attachment.instance-id,Values=<id>` |
| Snapshot a volume | `aws ec2 create-snapshot --volume-id <vol> --description "<why>"` |
| My snapshots | `aws ec2 describe-snapshots --owner-ids self` |

## VPC and Networking

| Task | Command |
| --- | --- |
| VPCs | `aws ec2 describe-vpcs --query 'Vpcs[].[VpcId,CidrBlock,Tags[?Key==`Name`].Value|[0]]' --output table` |
| Subnets of a VPC | `aws ec2 describe-subnets --filters Name=vpc-id,Values=<vpc>` |
| Route tables | `aws ec2 describe-route-tables --filters Name=vpc-id,Values=<vpc>` |
| Security groups | `aws ec2 describe-security-groups --query 'SecurityGroups[].[GroupId,GroupName]' --output table` |
| Who admits my port? | `aws ec2 describe-security-groups --filters Name=ip-permission.from-port,Values=22` |
| Flow logs | `aws ec2 describe-flow-logs` |

## S3

| Task | Command |
| --- | --- |
| List buckets | `aws s3 ls` |
| Bucket size by prefix | `aws s3 ls s3://<bucket> --recursive --summarize \| grep Total` |
| Sync a directory (mirror) | `aws s3 sync ./site s3://<bucket>/site --delete` |
| Copy with server-side class | `aws s3 cp big.dat s3://<bucket>/ --storage-class INTELLIGENT_TIERING` |
| Presign a download | `aws s3 presign s3://<bucket>/<key> --expires-in 900` |
| Versioning status | `aws s3api get-bucket-versioning --bucket <bucket>` |
| Lifecycle rules | `aws s3api get-bucket-lifecycle-configuration --bucket <bucket>` |
| Empty (incl. versions) | `aws s3 rm s3://<bucket> --recursive` then `aws s3api delete-objects --bucket <bucket> --delete "$(aws s3api list-object-versions --bucket <bucket> --query '{Objects: Versions[].{Key:Key,VersionId:VersionId}}')"` |

## RDS

| Task | Command |
| --- | --- |
| Instances | `aws rds describe-db-instances --query 'DBInstances[].[DBInstanceIdentifier,Engine,DBInstanceClass,MultiAZ,DBInstanceStatus]' --output table` |
| Create (Graviton, autoscale) | `aws rds create-db-instance --db-instance-identifier <id> --engine postgres --db-instance-class db.t4g.medium --allocated-storage 20 --max-allocated-storage 200 --manage-master-user-password --no-publicly-accessible --vpc-security-group-ids <sg>` |
| Manual snapshot | `aws rds create-db-snapshot --db-instance-identifier <id> --db-snapshot-identifier <snap>` |
| Safe delete | `aws rds delete-db-instance --db-instance-identifier <id> --final-db-snapshot-identifier <id>-final` |
| Restore PITR | `aws rds restore-db-instance-to-point-in-time --source-db-instance-identifier <id> --target-db-instance-identifier <id>-restored --use-latest-restorable-time` |

## EKS, ECR, and Containers

| Task | Command |
| --- | --- |
| Clusters | `aws eks list-clusters` |
| Cluster detail + version | `aws eks describe-cluster --name <name> --query 'cluster.{version:version,status:status,endpoint:endpoint}'` |
| kubeconfig merge | `aws eks update-kubeconfig --name <name> --region eu-central-1` |
| Node groups | `aws eks list-nodegroups --cluster-name <name>` |
| ECR login token | `aws ecr get-login-password --region eu-central-1 \| docker login --username AWS --password-stdin <account>.dkr.ecr.eu-central-1.amazonaws.com` |
| List repos / images | `aws ecr describe-repositories` / `aws ecr list-images --repository-name <repo>` |
| ECR lifecycle policy | `aws ecr put-lifecycle-policy --repository-name <repo> --lifecycle-policy-text file://ecr-lifecycle.json` |

## Lambda and EventBridge

| Task | Command |
| --- | --- |
| Create function | `aws lambda create-function --function-name <fn> --runtime python3.13 --handler handler.handler --zip-file fileb://function.zip --role <exec-role-arn> --memory-size 256 --timeout 10 --architectures arm64` |
| Update code | `aws lambda update-function-code --function-name <fn> --zip-file fileb://function.zip` |
| Invoke | `aws lambda invoke --function-name <fn> --payload '{}' --cli-binary-format raw-in-base64-out out.json` |
| Tail logs | `aws logs tail /aws/lambda/<fn> --since 10m` |
| Set retention | `aws logs put-retention-policy --log-group-name <group> --retention-in-days 30` |
| Cron rule | `aws events put-rule --name <rule> --schedule-expression "cron(0 2 * * ? *)"` |
| Insights query | `aws logs start-query --log-group-name <group> --start -3600 --end 0 --query-string 'filter level = "ERROR" \| stats count() by bin(5m)'` |

## CloudWatch and Cost

| Task | Command |
| --- | --- |
| Metric statistics | `aws cloudwatch get-metric-statistics --namespace AWS/RDS --metric-name CPUUtilization --dimensions Name=DBInstanceIdentifier,Value=<id> --start-time <t> --end-time <t> --period 300 --statistic Average` |
| Put an alarm | `aws cloudwatch put-metric-alarm --alarm-name <name> ... --alarm-actions <sns-arn>` |
| Alarm states | `aws cloudwatch describe-alarms --state-value ALARM` |
| Cost by tag | `aws ce get-cost-and-usage --time-period Start=<date>,End=<date> --granularity DAILY --metrics UnblendedCost --group-by Type=TAG,Key=project` |
| Create a budget | `aws budgets create-budget --account-id <id> --budget file://budget.json` |

## IAM

| Task | Command |
| --- | --- |
| My policies in effect | `aws iam list-attached-user-policies --user-name <user>` |
| List roles | `aws iam list-roles --query 'Roles[].[RoleName,CreateDate]' --output table` |
| Role trust policy | `aws iam get-role --role-name <role> --query 'Role.AssumeRolePolicyDocument'` |
| Credential report | `aws iam generate-credential-report` then `aws iam get-credential-report` |
| Access keys audit | `aws iam list-access-keys --user-name <user>` |
