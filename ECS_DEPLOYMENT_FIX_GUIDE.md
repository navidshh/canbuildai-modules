# ECS Deployment Stuck - Fix Guide

## Problem Summary
Your ECS deployment has been stuck for 24 hours. This typically happens when:
- New tasks start but fail health checks
- ECS keeps retrying but never succeeds
- Old tasks keep running while new ones fail

## Solution Options (Try in Order)

### Option 1: Check Logs and Diagnose
First, run the diagnostic script to identify the exact issue:
```powershell
.\diagnose-ecs-deployment.ps1
```

Look for:
- **Target health status**: Are targets "unhealthy"?
- **Service events**: Any error messages?
- **Container logs**: Startup errors or crashes?
- **Task status**: Are tasks stopping or stuck?

---

### Option 2: Manual Rollback (Quick Fix)
If you need the service running NOW, roll back to the previous working version:

```powershell
# Get your current task definition revision
aws ecs describe-services --cluster YOUR_CLUSTER_NAME --services YOUR_SERVICE_NAME --query "services[0].deployments[].taskDefinition"

# Find the previous STABLE revision (not the one currently deploying)
aws ecs list-task-definitions --family YOUR_TASK_FAMILY --sort DESC --max-items 5

# Update service to use previous revision
aws ecs update-service `
    --cluster YOUR_CLUSTER_NAME `
    --service YOUR_SERVICE_NAME `
    --task-definition YOUR_TASK_FAMILY:PREVIOUS_REVISION `
    --force-new-deployment
```

---

### Option 3: Stop the Stuck Deployment
Force stop the current deployment and scale back:

```powershell
# Scale down to 0
aws ecs update-service `
    --cluster YOUR_CLUSTER_NAME `
    --service YOUR_SERVICE_NAME `
    --desired-count 0

# Wait 2 minutes

# Scale back up
aws ecs update-service `
    --cluster YOUR_CLUSTER_NAME `
    --service YOUR_SERVICE_NAME `
    --desired-count 1 `
    --force-new-deployment
```

---

### Option 4: Fix the Root Cause

Based on your retrofit_planner integration, here are likely issues:

#### Issue 4A: Models Missing from Docker Image

**Verify models are in image:**
```powershell
# Pull the image locally
docker pull YOUR_DOCKER_USERNAME/surrogate-app:YOUR_TAG

# Check if models directory exists
docker run --rm -it YOUR_DOCKER_USERNAME/surrogate-app:YOUR_TAG ls -la /home/btap_ml/retrofit_planner/output/models/
```

**If models are missing**, add this to your Dockerfile.aws:
```dockerfile
# Verify models are copied
RUN ls -la /home/btap_ml/retrofit_planner/output/models/ || echo "WARNING: Models directory not found"
```

#### Issue 4B: Dependencies Missing

The retrofit_planner needs `lightgbm` and `catboost`. Check if they're installing properly:

```dockerfile
# In Dockerfile.aws, add before CMD:
RUN python -c "import lightgbm; import catboost; print('ML libs OK')" || exit 1
```

#### Issue 4C: Health Check Timing

If model loading takes >5 seconds, add a readiness check:

**Update main.py health check:**
```python
from .routes.retrofit_prediction import MODEL_AVAILABLE

@app.get("/health")
async def health_check():
    # Simple health check - always returns OK
    # This allows container to start even if models aren't loaded yet
    return JSONResponse(status_code=200, content={
        "status": "ok",
        "message": "Server is healthy",
        "retrofit_model_loaded": MODEL_AVAILABLE
    })

@app.get("/health/ready")
async def readiness_check():
    # Detailed readiness check
    if not MODEL_AVAILABLE:
        return JSONResponse(status_code=503, content={
            "status": "not ready",
            "message": "Retrofit models not loaded",
            "error": STARTUP_ERROR
        })
    return JSONResponse(status_code=200, content={
        "status": "ready",
        "message": "All models loaded"
    })
```

**Then update your ECS task definition health check in Terraform:**
```hcl
health_check {
  path                = "/health"      # Simple check
  protocol            = "HTTP"
  healthy_threshold   = 2
  unhealthy_threshold = 5              # Increase tolerance
  timeout             = 10             # Increase timeout
  interval            = 30
}
```

And increase grace period:
```hcl
health_check_grace_period = 600  # 10 minutes instead of 5
```

---

### Option 5: Test Locally First

Before deploying again, test the Docker image locally:

```powershell
# Build the image
cd "c:\CanbuildAI API\canbuildai-modules"
docker build -f Dockerfile.aws -t surrogate-app:test .

# Run it locally
docker run -p 8000:8000 -e COGNITO_REGION=ca-central-1 surrogate-app:test

# In another terminal, test health check
curl http://localhost:8000/health

# Test retrofit endpoint
curl http://localhost:8000/retrofit/status
```

Watch the container logs for any errors during startup.

---

### Option 6: Emergency - Delete and Recreate Service

**LAST RESORT** - This will cause downtime:

```powershell
# Delete the service
aws ecs delete-service `
    --cluster YOUR_CLUSTER_NAME `
    --service YOUR_SERVICE_NAME `
    --force

# Wait for deletion to complete
# Then redeploy using Terraform/Terragrunt
```

---

## Recommended Actions NOW

1. **Run diagnostic script** to identify the exact failure
2. **Check CloudWatch logs** for error messages during container startup
3. **Test Docker image locally** to verify retrofit_planner works
4. **If urgent**, perform manual rollback to previous working version
5. **Fix root cause** based on diagnostic results
6. **Increase health check grace period** to 10 minutes
7. **Redeploy** with fixes

---

## Prevention

Add to your CI/CD workflow:

```yaml
- name: Test Docker Image Before Deploy
  run: |
    docker run -d -p 8000:8000 --name test-container \
      ${{ secrets.DOCKER_USERNAME }}/surrogate-app:${{ steps.tag.outputs.value }}
    
    sleep 30  # Wait for startup
    
    # Test health endpoint
    curl -f http://localhost:8000/health || exit 1
    
    # Test retrofit endpoint
    curl -f http://localhost:8000/retrofit/status || exit 1
    
    docker stop test-container
```

---

## Need Help?

After running diagnostics, share:
1. Service events output
2. Task status and stopped reason
3. Container logs (last 50 lines)
4. Target health status
