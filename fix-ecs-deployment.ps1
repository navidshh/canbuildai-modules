# Fix ECS Deployment - Option 1: Increase Health Check Grace Period
# This script updates the ECS service to give more time for models to load

Write-Host "=== Fixing ECS Deployment - Option 1 ===" -ForegroundColor Cyan
Write-Host ""

$CLUSTER_NAME = "btap-app4-dev-cluster"
$SERVICE_NAME = "btap-app4-dev-service"
$REGION = "ca-central-1"
$NEW_GRACE_PERIOD = 900  # 15 minutes (increased from 5 minutes)

Write-Host "Configuration:" -ForegroundColor Yellow
Write-Host "  Cluster: $CLUSTER_NAME"
Write-Host "  Service: $SERVICE_NAME"
Write-Host "  Region: $REGION"
Write-Host "  New Grace Period: $NEW_GRACE_PERIOD seconds (15 minutes)"
Write-Host ""

# Verify AWS CLI is configured
Write-Host "Checking AWS CLI configuration..." -ForegroundColor Yellow
try {
    $identity = aws sts get-caller-identity --output json 2>&1 | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: AWS CLI not configured properly" -ForegroundColor Red
        exit 1
    }
    Write-Host "✓ AWS CLI configured as: $($identity.Arn)" -ForegroundColor Green
    Write-Host ""
} catch {
    Write-Host "ERROR: AWS CLI not available" -ForegroundColor Red
    exit 1
}

# Step 1: Check current service status
Write-Host "Step 1: Checking current service status..." -ForegroundColor Yellow
$serviceInfo = aws ecs describe-services `
    --cluster $CLUSTER_NAME `
    --services $SERVICE_NAME `
    --region $REGION `
    --output json | ConvertFrom-Json

if ($LASTEXITCODE -ne 0 -or $null -eq $serviceInfo.services -or $serviceInfo.services.Count -eq 0) {
    Write-Host "ERROR: Could not find service $SERVICE_NAME in cluster $CLUSTER_NAME" -ForegroundColor Red
    exit 1
}

$service = $serviceInfo.services[0]
Write-Host "  Status: $($service.status)" -ForegroundColor Gray
Write-Host "  Running Count: $($service.runningCount) / $($service.desiredCount)" -ForegroundColor Gray
Write-Host "  Current Grace Period: $($service.healthCheckGracePeriodSeconds) seconds" -ForegroundColor Gray
Write-Host "  Deployments in progress: $($service.deployments.Count)" -ForegroundColor Gray
Write-Host ""

# Step 2: Show recent events
Write-Host "Step 2: Recent service events:" -ForegroundColor Yellow
$events = $service.events | Select-Object -First 5
foreach ($event in $events) {
    $timestamp = [DateTime]::Parse($event.createdAt).ToString("yyyy-MM-dd HH:mm:ss")
    Write-Host "  [$timestamp] $($event.message)" -ForegroundColor Gray
}
Write-Host ""

# Step 3: Update service with new grace period
Write-Host "Step 3: Updating ECS service configuration..." -ForegroundColor Yellow
Write-Host "  This will:" -ForegroundColor Gray
Write-Host "    1. Increase health check grace period to $NEW_GRACE_PERIOD seconds" -ForegroundColor Gray
Write-Host "    2. Force a new deployment with current task definition" -ForegroundColor Gray
Write-Host ""

$confirm = Read-Host "Continue with update? (yes/no)"
if ($confirm -ne "yes") {
    Write-Host "Operation cancelled by user" -ForegroundColor Yellow
    exit 0
}

Write-Host ""
Write-Host "Updating service..." -ForegroundColor Cyan

$updateResult = aws ecs update-service `
    --cluster $CLUSTER_NAME `
    --service $SERVICE_NAME `
    --region $REGION `
    --health-check-grace-period-seconds $NEW_GRACE_PERIOD `
    --force-new-deployment `
    --output json 2>&1

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Failed to update service" -ForegroundColor Red
    Write-Host $updateResult -ForegroundColor Red
    exit 1
}

Write-Host "✓ Service update initiated successfully!" -ForegroundColor Green
Write-Host ""

# Step 4: Monitor deployment
Write-Host "Step 4: Monitoring deployment progress..." -ForegroundColor Yellow
Write-Host "  The deployment will now begin. This may take 15-20 minutes." -ForegroundColor Gray
Write-Host "  Press Ctrl+C to stop monitoring (deployment will continue)" -ForegroundColor Gray
Write-Host ""

$maxChecks = 30
$checkInterval = 30
$checkCount = 0

while ($checkCount -lt $maxChecks) {
    Start-Sleep -Seconds $checkInterval
    $checkCount++
    
    $statusInfo = aws ecs describe-services `
        --cluster $CLUSTER_NAME `
        --services $SERVICE_NAME `
        --region $REGION `
        --output json | ConvertFrom-Json
    
    $currentService = $statusInfo.services[0]
    $timestamp = Get-Date -Format "HH:mm:ss"
    
    Write-Host "[$timestamp] Running: $($currentService.runningCount)/$($currentService.desiredCount) | Deployments: $($currentService.deployments.Count)" -ForegroundColor Cyan
    
    # Show deployment details
    foreach ($deployment in $currentService.deployments) {
        $status = $deployment.rolloutState
        if ($null -eq $status) { $status = $deployment.status }
        Write-Host "  - $status : Running=$($deployment.runningCount) Pending=$($deployment.pendingCount) Desired=$($deployment.desiredCount)" -ForegroundColor Gray
    }
    
    # Check if deployment is complete
    if ($currentService.deployments.Count -eq 1 -and 
        $currentService.deployments[0].runningCount -eq $currentService.desiredCount -and
        $currentService.deployments[0].rolloutState -eq "COMPLETED") {
        Write-Host ""
        Write-Host "✓ Deployment completed successfully!" -ForegroundColor Green
        break
    }
    
    # Check for failed deployment
    if ($currentService.deployments[0].rolloutState -eq "FAILED") {
        Write-Host ""
        Write-Host "✗ Deployment failed!" -ForegroundColor Red
        Write-Host "Recent events:" -ForegroundColor Yellow
        $currentService.events | Select-Object -First 3 | ForEach-Object {
            Write-Host "  $($_.message)" -ForegroundColor Red
        }
        break
    }
    
    Write-Host ""
}

if ($checkCount -ge $maxChecks) {
    Write-Host ""
    Write-Host "Monitoring stopped after $($maxChecks * $checkInterval) seconds" -ForegroundColor Yellow
    Write-Host "The deployment is still in progress. Check AWS Console for final status." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== Useful Commands ===" -ForegroundColor Cyan
Write-Host "Check service status:"
Write-Host "  aws ecs describe-services --cluster $CLUSTER_NAME --services $SERVICE_NAME --region $REGION" -ForegroundColor Gray
Write-Host ""
Write-Host "View CloudWatch logs:"
Write-Host "  aws logs tail /ecs/$SERVICE_NAME --follow --region $REGION" -ForegroundColor Gray
Write-Host ""
Write-Host "View in AWS Console:"
$consoleUrl = "https://ca-central-1.console.aws.amazon.com/ecs/v2/clusters/$CLUSTER_NAME/services/$SERVICE_NAME"
Write-Host "  $consoleUrl" -ForegroundColor Gray
