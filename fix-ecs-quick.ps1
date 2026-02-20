# Fix ECS Deployment - Increase Health Check Grace Period
# Quick fix for stuck deployment

$CLUSTER_NAME = "btap-app4-dev-cluster"
$SERVICE_NAME = "btap-app4-dev-service"
$REGION = "ca-central-1"
$NEW_GRACE_PERIOD = 900  # 15 minutes

Write-Host "=== Fixing ECS Deployment ===" -ForegroundColor Cyan
Write-Host "Cluster: $CLUSTER_NAME" -ForegroundColor Yellow
Write-Host "Service: $SERVICE_NAME" -ForegroundColor Yellow
Write-Host "New Grace Period: $NEW_GRACE_PERIOD seconds (15 min)" -ForegroundColor Yellow
Write-Host ""

# Check current status
Write-Host "Checking current service status..." -ForegroundColor Cyan
aws ecs describe-services --cluster $CLUSTER_NAME --services $SERVICE_NAME --region $REGION --query "services[0].{Status:status,Running:runningCount,Desired:desiredCount,GracePeriod:healthCheckGracePeriodSeconds}" --output table

Write-Host ""
Write-Host "Recent events:" -ForegroundColor Cyan
aws ecs describe-services --cluster $CLUSTER_NAME --services $SERVICE_NAME --region $REGION --query "services[0].events[:3]" --output table

Write-Host ""
$confirm = Read-Host "Update service with new grace period? (yes/no)"

if ($confirm -ne "yes") {
    Write-Host "Cancelled" -ForegroundColor Yellow
    exit 0
}

Write-Host ""
Write-Host "Updating ECS service..." -ForegroundColor Green

aws ecs update-service `
    --cluster $CLUSTER_NAME `
    --service $SERVICE_NAME `
    --region $REGION `
    --health-check-grace-period-seconds $NEW_GRACE_PERIOD `
    --force-new-deployment

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "[SUCCESS] Service updated successfully!" -ForegroundColor Green
    Write-Host ""
    Write-Host "New deployment started. Monitor progress with:" -ForegroundColor Cyan
    Write-Host "  aws ecs describe-services --cluster $CLUSTER_NAME --services $SERVICE_NAME --region $REGION --query 'services[0].deployments'" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Or view in console:" -ForegroundColor Cyan
    Write-Host "  https://ca-central-1.console.aws.amazon.com/ecs/v2/clusters/$CLUSTER_NAME/services/$SERVICE_NAME/health" -ForegroundColor Gray
} else {
    Write-Host ""
    Write-Host "[ERROR] Update failed" -ForegroundColor Red
    exit 1
}
