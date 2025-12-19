param(
    [string]$Message = "update",
    [string]$Tag
)

git status
git add .
git commit -m "$Message"
git push

if ($Tag) {
    git tag $Tag
    git push origin $Tag
}
