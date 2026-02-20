# Monitor ECS Deployment - CORRECT Service
$CLUSTER = "btap-app-test3-dev-tgw-3-cluster"
$SERVICE = "btap-app-test3-dev-tgw-3-service"
$REGION = "ca-central-1"

Write-Host "=== Deployment Status ===" -ForegroundColor Cyan
aws ecs describe-services --cluster $CLUSTER --services $SERVICE --region $REGION --query "services[0].{Running:runningCount,Desired:desiredCount,GracePeriod:healthCheckGracePeriodSeconds,Deployments:deployments[].{Running:runningCount,Desired:desiredCount,RolloutState:rolloutState}}" --output json

Write-Host ""
Write-Host "=== Recent Events ===" -ForegroundColor Cyan
aws ecs describe-services --cluster $CLUSTER --services $SERVICE --region $REGION --query "services[0].events[:8]" --output json

Write-Host ""
Write-Host "=== AWS Console Link ===" -ForegroundColor Cyan
Write-Host "https://ca-central-1.console.aws.amazon.com/ecs/v2/clusters/$CLUSTER/services/$SERVICE/health" -ForegroundColor Gray
Write-Host ""
Write-Host "Re-run this to check progress: .\monitor-ecs.ps1" -ForegroundColor Yellow
