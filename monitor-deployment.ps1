# Monitor ECS Deployment Progress
# Run this after updating the service to track deployment status

$CLUSTER_NAME = "btap-app4-dev-cluster"
$SERVICE_NAME = "btap-app4-dev-service"
$REGION = "ca-central-1"

Write-Host "=== Monitoring ECS Deployment ===" -ForegroundColor Cyan
Write-Host ""

Write-Host "Service Configuration:" -ForegroundColor Yellow
aws ecs describe-services --cluster $CLUSTER_NAME --services $SERVICE_NAME --region $REGION --query "services[0].{Status:status,Running:runningCount,Desired:desiredCount,GracePeriod:healthCheckGracePeriodSeconds}" --output table

Write-Host ""
Write-Host "Active Deployments:" -ForegroundColor Yellow
aws ecs describe-services --cluster $CLUSTER_NAME --services $SERVICE_NAME --region $REGION --query "services[0].deployments[*].{Status:status,RolloutState:rolloutState,Running:runningCount,Pending:pendingCount,Desired:desiredCount,TaskDef:taskDefinition,CreatedAt:createdAt}" --output table

Write-Host ""
Write-Host "Recent Service Events:" -ForegroundColor Yellow
aws ecs describe-services --cluster $CLUSTER_NAME --services $SERVICE_NAME --region $REGION --query "services[0].events[:8].[createdAt,message]" --output table

Write-Host ""
Write-Host "Target Group Health:" -ForegroundColor Yellow
$tgArn = aws elbv2 describe-target-groups --region $REGION --query "TargetGroups[?contains(TargetGroupName, 'surrogate') || contains(TargetGroupName, 'btap')].TargetGroupArn | [0]" --output text

if ($tgArn -and $tgArn -ne "None") {
    aws elbv2 describe-target-health --target-group-arn $tgArn --region $REGION --query "TargetHealthDescriptions[*].{Target:Target.Id,Port:Target.Port,State:TargetHealth.State,Reason:TargetHealth.Reason}" --output table
} else {
    Write-Host "Could not find target group" -ForegroundColor Gray
}

Write-Host ""
Write-Host "=== Monitor Commands ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Keep running this script to monitor progress:" -ForegroundColor Yellow
Write-Host "  .\monitor-deployment.ps1" -ForegroundColor Gray
Write-Host ""
Write-Host "View CloudWatch Logs:" -ForegroundColor Yellow
Write-Host "  aws logs tail /ecs/$SERVICE_NAME --follow --region $REGION" -ForegroundColor Gray
Write-Host ""
Write-Host "AWS Console:" -ForegroundColor Yellow
Write-Host "  https://ca-central-1.console.aws.amazon.com/ecs/v2/clusters/$CLUSTER_NAME/services/$SERVICE_NAME/health" -ForegroundColor Gray
Write-Host ""
