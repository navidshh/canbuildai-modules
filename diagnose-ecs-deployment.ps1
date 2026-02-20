# ECS Deployment Diagnostic Script
# This script checks the status of your ECS deployment

Write-Host "=== ECS Deployment Diagnostics ===" -ForegroundColor Cyan
Write-Host ""

# Check if AWS CLI is configured
try {
    $awsIdentity = aws sts get-caller-identity 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: AWS CLI not configured or credentials expired" -ForegroundColor Red
        Write-Host "Please configure AWS credentials first" -ForegroundColor Yellow
        exit 1
    }
    Write-Host "✓ AWS CLI configured" -ForegroundColor Green
    Write-Host ""
} catch {
    Write-Host "ERROR: AWS CLI not found. Please install AWS CLI" -ForegroundColor Red
    exit 1
}

# Get ECS cluster and service names from GitHub secrets (you'll need to fill these in)
$CLUSTER_NAME = Read-Host "Enter your ECS Cluster Name"
$SERVICE_NAME = Read-Host "Enter your ECS Service Name"
$REGION = Read-Host "Enter AWS Region (e.g. ca-central-1)"

Write-Host ""
Write-Host "Checking ECS Service: $SERVICE_NAME in Cluster: $CLUSTER_NAME" -ForegroundColor Cyan
Write-Host ""

# 1. Check service status
Write-Host "--- 1. Service Status ---" -ForegroundColor Yellow
aws ecs describe-services `
    --cluster $CLUSTER_NAME `
    --services $SERVICE_NAME `
    --region $REGION `
    --query "services[0].{Status:status,DesiredCount:desiredCount,RunningCount:runningCount,PendingCount:pendingCount,Deployments:deployments[].{Status:status,DesiredCount:desiredCount,RunningCount:runningCount,PendingCount:pendingCount,RolloutState:rolloutState,CreatedAt:createdAt}}" `
    --output json

Write-Host ""

# 2. Check recent service events (last 10)
Write-Host "--- 2. Recent Service Events ---" -ForegroundColor Yellow
aws ecs describe-services `
    --cluster $CLUSTER_NAME `
    --services $SERVICE_NAME `
    --region $REGION `
    --query "services[0].events[:10].[createdAt,message]" `
    --output table

Write-Host ""

# 3. List tasks in the service
Write-Host "--- 3. Tasks in Service ---" -ForegroundColor Yellow
$taskArns = aws ecs list-tasks `
    --cluster $CLUSTER_NAME `
    --service-name $SERVICE_NAME `
    --region $REGION `
    --query "taskArns" `
    --output json | ConvertFrom-Json

if ($taskArns.Count -eq 0) {
    Write-Host "No tasks found!" -ForegroundColor Red
} else {
    Write-Host "Found $($taskArns.Count) task(s)" -ForegroundColor Green
    
    # Get details of the first task
    if ($taskArns.Count -gt 0) {
        $firstTask = $taskArns[0]
        Write-Host ""
        Write-Host "--- 4. Task Details (First Task) ---" -ForegroundColor Yellow
        aws ecs describe-tasks `
            --cluster $CLUSTER_NAME `
            --tasks $firstTask `
            --region $REGION `
            --query "tasks[0].{TaskArn:taskArn,TaskDefinition:taskDefinitionArn,LastStatus:lastStatus,DesiredStatus:desiredStatus,HealthStatus:healthStatus,Containers:containers[].{Name:name,LastStatus:lastStatus,HealthStatus:healthStatus}}" `
            --output json
        
        Write-Host ""
        Write-Host "--- 5. Task Stopped Reason (if stopped) ---" -ForegroundColor Yellow
        aws ecs describe-tasks `
            --cluster $CLUSTER_NAME `
            --tasks $firstTask `
            --region $REGION `
            --query "tasks[0].stoppedReason" `
            --output text
    }
}

Write-Host ""

# 4. Check target group health
Write-Host "--- 6. Target Group Health Status ---" -ForegroundColor Yellow
Write-Host "First, let's find the target group ARN..." -ForegroundColor Gray

$targetGroupArn = aws elbv2 describe-target-groups `
    --region $REGION `
    --query "TargetGroups[?contains(TargetGroupName, 'surrogate')].TargetGroupArn | [0]" `
    --output text

if ($targetGroupArn -and $targetGroupArn -ne "None") {
    Write-Host "Target Group ARN: $targetGroupArn" -ForegroundColor Gray
    aws elbv2 describe-target-health `
        --target-group-arn $targetGroupArn `
        --region $REGION `
        --query "TargetHealthDescriptions[].{Target:Target.Id,Port:Target.Port,State:TargetHealth.State,Reason:TargetHealth.Reason,Description:TargetHealth.Description}" `
        --output table
} else {
    Write-Host "Could not find target group automatically. Please check manually in AWS Console." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "--- 7. Recent CloudWatch Logs (Last 20 lines) ---" -ForegroundColor Yellow
$logGroup = "/ecs/$SERVICE_NAME"
Write-Host "Log Group: $logGroup" -ForegroundColor Gray

$logStreams = aws logs describe-log-streams `
    --log-group-name $logGroup `
    --region $REGION `
    --order-by LastEventTime `
    --descending `
    --max-items 1 `
    --query "logStreams[0].logStreamName" `
    --output text 2>&1

if ($LASTEXITCODE -eq 0 -and $logStreams -ne "None") {
    Write-Host "Latest log stream: $logStreams" -ForegroundColor Gray
    aws logs get-log-events `
        --log-group-name $logGroup `
        --log-stream-name $logStreams `
        --region $REGION `
        --limit 20 `
        --query "events[].message" `
        --output text
} else {
    Write-Host "Could not retrieve logs. The log group might not exist or no logs available yet." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== Diagnostic Complete ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Common Issues:" -ForegroundColor Yellow
Write-Host "  - If tasks are unhealthy: Check if /health endpoint is responding"
Write-Host "  - If tasks are stopping: Check container logs for startup errors"
Write-Host "  - If models loading fails: Verify retrofit_planner/output/models is in Docker image"
Write-Host "  - If deployment stuck: Consider manually stopping the service and restarting"
