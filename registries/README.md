# Private registries

Log in to the registry before the Codacy step so Docker can pull from it. The examples are plain shell, so they work in any of the CI examples in this repository: put them before the `upload-sbom` step and supply the credentials as pipeline secrets.

When the pipeline builds the image itself and uses the `docker tag` alias from the [root README](../README.md), the image is already on the build machine and no registry login is needed for the upload. Log in when the image only exists in the registry: pull it first, then upload it.

```bash
docker pull "${IMAGE_NAME}:${IMAGE_VERSION}"
```

For registry images, `IMAGE_NAME` includes the registry host, for example `123456789012.dkr.ecr.eu-west-1.amazonaws.com/myapp`.

## Amazon ECR

Needs the AWS CLI and credentials with `ecr:GetAuthorizationToken` and pull access to the repository.

```bash
aws ecr get-login-password --region "${AWS_REGION}" \
  | docker login --username AWS --password-stdin \
      "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
```

Secrets: `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`, or your CI's OIDC role integration.

## Azure Container Registry (ACR)

With the Azure CLI signed in:

```bash
az acr login --name "${ACR_NAME}"
```

Or with a service principal or repository-scoped token, without the Azure CLI:

```bash
echo "${ACR_PASSWORD}" | docker login "${ACR_NAME}.azurecr.io" \
  --username "${ACR_USERNAME}" --password-stdin
```

Secrets: `ACR_USERNAME` and `ACR_PASSWORD`.

## Docker Hub (authenticated)

Use an access token rather than your account password. Authenticated pulls also avoid the anonymous rate limit, and are required for private repositories.

```bash
echo "${DOCKERHUB_TOKEN}" | docker login --username "${DOCKERHUB_USERNAME}" --password-stdin
```

Secrets: `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN`.

## Example: GitHub Actions with ECR

```yaml
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
          aws-region: eu-west-1

      - uses: aws-actions/amazon-ecr-login@v2

      - name: Pull image
        run: docker pull "${IMAGE_NAME}:${IMAGE_VERSION}"
```

For ACR and Docker Hub, use `azure/docker-login@v2` and `docker/login-action@v3` in the same place.
