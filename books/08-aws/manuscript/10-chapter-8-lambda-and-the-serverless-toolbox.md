# Chapter 8 - Lambda and the Serverless Toolbox {#ch8}

## 8.1 The Model: Events, Functions, Execution Environments

**Lambda** runs your code in response to events without you managing any server, and its mental model is three nouns. A **function** is your code plus configuration (memory, timeout, role, runtime). An **event** is the JSON payload that triggers it - an HTTP request, an S3 object creation, a queue message, a schedule. An **execution environment** is the short-lived micro-VM Lambda creates to run your function: cold-started on demand, kept warm and reused across invocations when traffic allows, frozen between calls. You never see the machine; you configure the function and pay per invocation and per GB-second of execution.

What the model buys is a different shape of platform. A handful of functions replaces a fleet of small always-on servers, the scaling is AWS's problem up to your account's concurrency limit, and idle costs nothing - which is why Lambda owns the "glue" layer of every serious AWS platform: resize the image when the upload lands, enrich the record when the queue fills, run the report when the cron fires. What it costs is equally concrete: execution time is capped (15 minutes maximum per invocation), cold starts add latency after idle periods, and code that assumed a persistent server (in-process caches, connection pools, background threads) needs the patterns of Section 8.4. The honest division of labor: long-running, stateful, steady-traffic services belong in containers on EKS ([Chapter 7](#ch7)); event-shaped, spiky, glue-shaped work belongs here.

## 8.2 A First Function

The minimum viable function is a zip and one command. Python handler:

```python
# handler.py
import json

def handler(event, context):
    name = event.get("queryStringParameters", {}).get("name", "world")
    return {
        "statusCode": 200,
        "body": json.dumps({"message": f"hello, {name}"})
    }
```

```bash
zip function.zip handler.py

aws lambda create-function \
  --function-name shopnow-hello \
  --runtime python3.13 \
  --handler handler.handler \
  --zip-file fileb://function.zip \
  --role arn:aws:iam::111122223333:role/shopnow-lambda-exec \
  --memory-size 256 --timeout 10 \
  --architectures arm64
```

Four configuration decisions hide in that command, and each recurs through the chapter. The **execution role** is [Chapter 2](#ch2) again: the function's AWS permissions are a role (the `AWSLambdaBasicExecutionRole` managed policy, which writes the function's logs to CloudWatch, is the baseline; everything beyond it - S3 reads, database access - is your policy work). The **runtime** (`python3.13`; Node.js, Java, Go, Ruby, .NET, and custom runtimes also exist) is a pinned language platform that AWS patches and eventually deprecates, so runtimes get reviewed like any dependency. The **architecture** `arm64` runs on Graviton at a lower per-GB-second price - the same default as every other compute choice in this book. And **memory** is the one knob that sets both memory *and* CPU proportionally (Section 8.3).

Invoke it, then read its first log line:

```bash
aws lambda invoke \
  --function-name shopnow-hello \
  --cli-binary-format raw-in-base64-out \
  --payload '{"queryStringParameters":{"name":"shopnow"}}' \
  out.json && cat out.json
aws logs tail /aws/lambda/shopnow-hello --since 5m
```

## 8.3 Memory, Timeout, and the Cost Model

Lambda's bill is `invocations × duration × (memory / 1024 GB-seconds)`, and memory is the only sizing knob that matters - because CPU scales linearly with it. A function given 1,792 MB gets one vCPU; give it 3,584 MB and it gets two, often finishing *faster*, which can make the bigger setting cheaper in total. This is why "guess 128 MB because it is the floor" is the classic first-month mistake: the professional move is a one-off **power tuning** pass (deploy the function at several memory sizes, compare average duration and cost - AWS publishes a lambda-power-tuning tool for exactly this), then pin the winner. The **timeout** is the second decision: it caps each invocation, defaults to 3 seconds, and its correct value is "a bit more than your worst case, never the maximum" - a 15-minute timeout on a function that should finish in 5 is how stuck pipelines hide for a day.

## 8.4 Cold Starts, Concurrency, and the Execution Environment

Three runtime behaviors define Lambda's engineering realities. **Cold starts**: after idleness, the first invocation pays environment creation - runtime init plus your code's init (module imports, connection setup). Python and Node pay hundreds of milliseconds; JVM pays more. The mitigations are code-side first (lazy imports, slim packages, init outside the handler) and platform-side second: **provisioned concurrency** pre-creates environments for a price, the fix when a user-facing endpoint cannot tolerate the tail. **Concurrency**: the account-level limit (default one thousand concurrent executions) throttles beyond it; **reserved concurrency** partitions that pool per function - the standard control to guarantee a critical function headroom *or* to fence a recursive-function accident (the Watch out box below). **Persistence**: the environment survives between invocations, so module-level objects (an SDK client, a config cache) are re-used warm - but treat the disk (`/tmp`, up to 10 GB) as scratch that *may* vanish, never as storage.

::: {.warn}
**Watch out - the recursive S3 → Lambda loop**

A function triggered by `s3:ObjectCreated:*` that writes back into the same prefix re-triggers itself, potentially at the speed of your bill. Guard every event-driven function: write to a different bucket or prefix, filter the notification by suffix, and set reserved concurrency on anything event-driven as the circuit breaker. AWS adds loop-detection for some patterns, but the design rule is yours to follow.
:::

## 8.5 Event Sources: S3, SQS, EventBridge

Event sources fall into two shapes. **Push** sources call the function directly: S3 event notifications ([Chapter 5](#ch5)' `s3:ObjectCreated:*`), API Gateway ([Section 8.6](#ch8-api)), and EventBridge rules. **Poll** sources make Lambda the consumer: **SQS** queues (Lambda polls, batches, and deletes on success - retry and dead-letter semantics come from the queue's redrive), DynamoDB Streams, Kinesis. The SQS pairing is the workhorse of asynchronous design: a function that might fail belongs behind a queue, because the queue owns the retry cadence, the dead-letter queue catches the poison messages, and the function stays stateless. Scheduled work comes from **EventBridge**: a rule with a cron expression triggers a function on schedule - the serverless replacement for the cron server, and how the running example runs its nightly report.

```bash
aws events put-rule --name nightly-report \
  --schedule-expression "cron(0 2 * * ? *)"
aws lambda add-permission --function-name shopnow-report \
  --statement-id eventbridge-invoke \
  --action lambda:InvokeFunction \
  --principal events.amazonaws.com
```

Note the second command: triggers are *also* IAM - the source service needs `lambda:InvokeFunction` permission on the function (a resource policy), and forgetting it is the classic "the schedule fired but nothing happened" diagnosis.

## 8.6 HTTP in Front: API Gateway {#ch8-api}

To expose a function over HTTP, **API Gateway** sits in front: an **HTTP API** (the cheaper, simpler kind - enough for most services) routes paths and methods to function ARNs, handles CORS, throttles, and can require an authorizer; a **REST API** adds usage plans, API keys, request validation, and caching at a higher price. The function's contract is the event-in/JSON-out shape of Section 8.2 (the book's handler already returns API Gateway's expected envelope). The platform shape this yields - API Gateway front, Lambda middle, managed services behind, nothing running when nobody calls - is the serverless application pattern in one sentence, and it pairs naturally with [Chapter 10](#ch10): API Gateway and Lambda both emit CloudWatch metrics natively, so p99 latency and error rates are one alarm away.

## 8.7 Layers, VPC Access, and When Not to Use Lambda

Three closing topics round out the toolbox. **Layers** package shared dependencies (a compiled library, a common utility module) once and attach to many functions - useful below ~a handful of functions, and past that the honest advice is "containerize the build" or use Lambda's container-image support instead of orchestrating layer versions. **VPC access** lets a function reach private resources (the [Chapter 6](#ch6) database): the function gets ENIs in your private subnets, needs the right security groups, and - with the [Chapter 4](#ch4) endpoints in place - keeps its NAT bill at zero; RDS Proxy (Section 6.6) then solves the connection-count problem the function fleet creates. And the *when not to* deserves its own sentence: sustained high-traffic compute is usually cheaper and operationally simpler on EKS with autoscaling (the crossover point is workload-specific - [Chapter 12](#ch12) shows how to measure your own), latency-critical paths pay cold-start tax, and anything longer than 15 minutes is not a Lambda problem at all.

**See also:** [Chapter 9](#ch9) deploys functions from CI with the same OIDC role that deploys the cluster, [Chapter 10](#ch10) alarms on its errors and durations, and [Chapter 11](#ch11) replaces `create-function` with reviewed Terraform. The queue-and-function patterns here pair with the ingest philosophy of the *Elastic Stack* volume when logs, not business events, are the payload.
