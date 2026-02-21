# Separate Surrogate and Retrofit Deployments Guide

## Overview
This guide configures **two separate GitHub Actions workflows** that automatically build, push, and deploy Docker images to separate ECS clusters when you push tags.

## Architecture

### Surrogate Model API
- **Docker Image**: `nshirzad/surrogate-app`
- **Workflow**: `.github/workflows/deploy-surrogate.yml`
- **Tag Pattern**: `surrogate-v*.*.*` (e.g., `surrogate-v1.0.0`)
- **ECS Cluster**: `surrogate-api-dev-tgw-3-cluster`
- **ECS Service**: `surrogate-api-dev-tgw-3-service`
- **Task Definition**: `surrogate-api-dev-tgw-3-task`

### Retrofit Planner API
- **Docker Image**: `nshirzad/retrofit-app`
- **Workflow**: `.github/workflows/deploy-retrofit.yml`
- **Tag Pattern**: `retrofit-v*.*.*` (e.g., `retrofit-v1.0.0`)
- **ECS Cluster**: `retrofit-api-dev-tgw-3-cluster`
- **ECS Service**: `retrofit-api-dev-tgw-3-service`
- **Task Definition**: `retrofit-api-dev-tgw-3-task`

## Prerequisites

### 1. Docker Hub Credentials (Already Configured)
- ✅ Stored in AWS Secrets Manager: `dockerhub-credentials`
- This prevents Docker Hub rate limit errors

### 2. ECS Infrastructure
You need to ensure both ECS clusters and services exist. Currently:
- ✅ `surrogate-api-dev-tgw-3-cluster` exists (empty)
- ❌ `retrofit-api-dev-tgw-3-cluster` needs to be created **OR** reuse `btap-app-test3-dev-tgw-3-cluster`

## Required GitHub Secrets

Go to: **GitHub Repository → Settings → Secrets and variables → Actions**

### Shared Secrets (Common to both workflows)
```plaintext
DOCKER_USERNAME=nshirzad
DOCKER_PASSWORD=<your-docker-hub-token>
AWS_ROLE_ARN=arn:aws:iam::834599497928:role/dev2-terraform_deployer_role
AWS_REGION=ca-central-1
COGNITO_REGION=ca-central-1
COGNITO_USER_POOL_ID=<your-cognito-pool-id>
COGNITO_APP_CLIENT_ID=<your-app-client-id>
COGNITO_APP_PUBLIC_CLIENT_ID=<your-public-client-id>
COGNITO_APP_CLIENT_SECRET=<your-client-secret>
COGNITO_DOMAIN=<your-cognito-domain>
APP_BASE_URL=<your-api-gateway-url>
REDIS_ENDPOINT=<your-redis-endpoint>
REDIS_PORT=6379
BUCKET_NAME=<your-s3-bucket-name>
```

### Surrogate-Specific Secrets
```plaintext
SURROGATE_ECS_CLUSTER=surrogate-api-dev-tgw-3-cluster
SURROGATE_ECS_SERVICE=surrogate-api-dev-tgw-3-service
SURROGATE_ECS_TASK_FAMILY=surrogate-api-dev-tgw-3-task
```

### Retrofit-Specific Secrets
```plaintext
RETROFIT_ECS_CLUSTER=retrofit-api-dev-tgw-3-cluster
RETROFIT_ECS_SERVICE=retrofit-api-dev-tgw-3-service
RETROFIT_ECS_TASK_FAMILY=retrofit-api-dev-tgw-3-task
```

## Deployment Process

### Deploy Surrogate Model
```bash
# Tag and push
git tag surrogate-v1.0.1
git push origin surrogate-v1.0.1

# This automatically:
# 1. Builds Docker image using Dockerfile.surrogate
# 2. Pushes to nshirzad/surrogate-app:1.0.1 and :latest
# 3. Registers new ECS task definition
# 4. Updates surrogate-api-dev-tgw-3-service with new image
```

### Deploy Retrofit Planner
```bash
# Tag and push
git tag retrofit-v1.0.1
git push origin retrofit-v1.0.1

# This automatically:
# 1. Builds Docker image using Dockerfile.retrofit
# 2. Pushes to nshirzad/retrofit-app:1.0.1 and :latest
# 3. Registers new ECS task definition
# 4. Updates retrofit-api-dev-tgw-3-service with new image
```

## Next Steps

### Option A: Create New Retrofit Cluster (Recommended)
**Run Terraform to create the retrofit infrastructure:**
```bash
cd api-infrastructure/surrogate_model_infrastructure/infrastructure
# Copy/modify the terraform configuration for retrofit cluster
terraform plan
terraform apply
```

### Option B: Reuse Existing Cluster
**Update the retrofit workflow secrets to use the existing cluster:**
```plaintext
RETROFIT_ECS_CLUSTER=btap-app-test3-dev-tgw-3-cluster
RETROFIT_ECS_SERVICE=btap-app-test3-dev-tgw-3-service
RETROFIT_ECS_TASK_FAMILY=btap-app-test3-dev-tgw-3-task
```

## Verification

### Check Workflow Status
1. Go to GitHub → Actions
2. Find "Build and Deploy Surrogate Model API"
3. Find "Build and Deploy Retrofit Planner API"

### Check ECS Deployment
```bash
# Check Surrogate service
aws ecs describe-services \
  --cluster surrogate-api-dev-tgw-3-cluster \
  --services surrogate-api-dev-tgw-3-service \
  --region ca-central-1

# Check Retrofit service
aws ecs describe-services \
  --cluster retrofit-api-dev-tgw-3-cluster \
  --services retrofit-api-dev-tgw-3-service \
  --region ca-central-1
```

### Check Running Tasks
```bash
# Surrogate tasks
aws ecs list-tasks \
  --cluster surrogate-api-dev-tgw-3-cluster \
  --service-name surrogate-api-dev-tgw-3-service \
  --region ca-central-1

# Retrofit tasks
aws ecs list-tasks \
  --cluster retrofit-api-dev-tgw-3-cluster \
  --service-name retrofit-api-dev-tgw-3-service \
  --region ca-central-1
```

## Troubleshooting

### Docker Rate Limit Error
**Error**: `toomanyrequests: You have reached your unauthenticated pull rate limit`

**Solution**: The task definition needs to reference the Docker Hub credentials stored in Secrets Manager. Update the task definition to include:

```json
{
  "repositoryCredentials": {
    "credentialsParameter": "arn:aws:secretsmanager:ca-central-1:834599497928:secret:dockerhub-credentials-avsQLG"
  }
}
```

### Service Not Updating
Check the service events:
```bash
aws ecs describe-services \
  --cluster <cluster-name> \
  --services <service-name> \
  --region ca-central-1 \
  --query 'services[0].events[0:10]' \
  --output table
```

### Task Fails to Start
Check stopped task reasons:
```bash
aws ecs describe-tasks \
  --cluster <cluster-name> \
  --tasks <task-id> \
  --region ca-central-1 \
  --query 'tasks[0].{StoppedReason:stoppedReason,ContainerReason:containers[0].reason}'
```

## Current Status

- ✅ Docker images built for both services
- ✅ GitHub workflows configured for automatic deployment
- ✅ Docker Hub credentials stored in AWS Secrets Manager
- ⚠️ ECS infrastructure needs configuration:
  - Surrogate cluster exists but service may need updating
  - Retrofit cluster/service needs to be created or configured

## Files Modified

1. `.github/workflows/deploy-surrogate.yml` - Added ECS deployment steps
2. `.github/workflows/deploy-retrofit.yml` - Added ECS deployment steps
3. `.github/workflows/docker-hub-ci.yml.disabled` - Old unified workflow disabled

## References

- [AWS ECS Deploy Action](https://github.com/aws-actions/amazon-ecs-deploy-task-definition)
- [Docker Hub Rate Limits](https://docs.docker.com/docker-hub/download-rate-limit/)
- [AWS Secrets Manager](https://docs.aws.amazon.com/secretsmanager/)
