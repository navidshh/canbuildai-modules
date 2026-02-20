# EC2 Diagnostic Commands
# Run these via AWS Systems Manager Session Manager

Write-Host "=== EC2 Instance Diagnostic Commands ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Instance ID: i-0c3799ced57374e04" -ForegroundColor Yellow
Write-Host "Region: ca-central-1" -ForegroundColor Yellow
Write-Host ""

Write-Host "=== Option 1: Connect via AWS Console ===" -ForegroundColor Green
Write-Host "1. Go to: https://ca-central-1.console.aws.amazon.com/ec2/v2/home?region=ca-central-1#Instances:instanceId=i-0c3799ced57374e04"
Write-Host "2. Click 'Connect' button"
Write-Host "3. Choose 'Session Manager' tab"
Write-Host "4. Click 'Connect'"
Write-Host ""

Write-Host "=== Commands to Run on EC2 Instance ===" -ForegroundColor Green
Write-Host ""
Write-Host "# Check if Docker is running:"  -ForegroundColor Yellow
Write-Host "sudo systemctl status docker"
Write-Host ""

Write-Host "# Check running containers:" -ForegroundColor Yellow  
Write-Host "sudo docker ps -a"
Write-Host ""

Write-Host "# Check if application is listening on port 8000:" -ForegroundColor Yellow
Write-Host "sudo netstat -tlnp | grep 8000"
Write-Host "curl http://localhost:8000/health"
Write-Host ""

Write-Host "# Check Docker logs (if container exists):" -ForegroundColor Yellow
Write-Host "sudo docker logs \`$(sudo docker ps -q | head -1)"
Write-Host ""

Write-Host "# Pull latest image and restart:" -ForegroundColor Yellow
Write-Host "cd /home/ec2-user  # or wherever your app is"
Write-Host "sudo docker pull navidshh/surrogate-app:latest  # or your actual tag"
Write-Host "sudo docker-compose down"
Write-Host "sudo docker-compose up -d"
Write-Host ""
