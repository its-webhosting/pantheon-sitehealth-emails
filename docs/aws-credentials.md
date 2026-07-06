
# Setting up AWS credentials for pantheon-sitehealth-email

The `pantheon-sitehealth-emails` script currently needs to do the following in AWS:

* Read the secret `webinfo` in account aws-webhosting-admin, us-east-1.
* Read the secret `pantheon-sitehealth-emails` in account aws-webhosting-admin, us-east-1.

That's it.

## Set shell variables

```bash
AWS_REGION="us-east-1"
SECRET_IDS=("webinfo" "pantheon-sitehealth-emails")
POLICY_NAME="PantheonSitehealthEmails"
GROUP_NAME="PantheonSitehealthEmails"
USER_NAME="markmont-PantheonSitehealthEmails"
```

## Build the policy document

Both the "create" and "update" sections below use the same `aws-policy.json`.
This resolves each secret name to its full ARN and builds a policy that grants
read access to exactly those secrets (and nothing else).

```bash
# Resolve each secret name to its full ARN:
SECRET_ARNS=()
for SECRET_ID in "${SECRET_IDS[@]}"; do
  SECRET_ARNS+=("$(
    aws secretsmanager describe-secret \
      --region "$AWS_REGION" \
      --secret-id "$SECRET_ID" \
      --query ARN \
      --output text
  )")
done
printf '%s\n' "${SECRET_ARNS[@]}"

# JSON array of the secret ARNs, for use in the policy document:
SECRET_ARNS_JSON=$(printf '%s\n' "${SECRET_ARNS[@]}" | jq -R . | jq -s .)

# Build the policy document:
jq -n \
  --argjson arns "$SECRET_ARNS_JSON" \
  --arg via "secretsmanager.${AWS_REGION}.amazonaws.com" \
  '{
    "Version": "2012-10-17",
    "Statement": [
      {
        "Sid": "AllowReadSpecificSecrets",
        "Effect": "Allow",
        "Action": [
          "secretsmanager:GetSecretValue",
          "secretsmanager:DescribeSecret"
        ],
        "Resource": $arns
      },
      {
        "Sid": "AllowKmsDecryptForTheseSecretsOnly",
        "Effect": "Allow",
        "Action": "kms:Decrypt",
        "Resource": "*",
        "Condition": {
          "StringEquals": {
            "kms:ViaService": $via,
            "kms:EncryptionContext:aws:secretsmanager:arn": $arns
          }
        }
      },
      {
        "Sid": "DenyReadingOtherSecrets",
        "Effect": "Deny",
        "Action": [
          "secretsmanager:GetSecretValue",
          "secretsmanager:DescribeSecret"
        ],
        "NotResource": $arns
      },
      {
        "Sid": "DenyEverythingExceptReadingTheseSecrets",
        "Effect": "Deny",
        "NotAction": [
          "secretsmanager:GetSecretValue",
          "secretsmanager:DescribeSecret",
          "kms:Decrypt"
        ],
        "Resource": "*"
      }
    ]
  }' > aws-policy.json

cat aws-policy.json
```

The `kms:Decrypt` statement is scoped by condition rather than by a KMS key ARN:
it only allows decryption performed *via* Secrets Manager for the encryption
context of exactly these two secrets, so it works whether the secrets use the
default `aws/secretsmanager` managed key or a customer-managed key.

## Create the IAM policy

This is already done; skip ahead to the next section unless you are creating the
policy from scratch. To **modify** the existing policy (e.g. to add the second
secret), use **Update the existing policy** below instead.

```bash
# Build aws-policy.json first (see "Build the policy document" above), then:

export POLICY_ARN=$(
  aws iam create-policy \
    --policy-name "$POLICY_NAME" \
    --policy-document file://aws-policy.json \
    --query Policy.Arn \
    --output text
)
echo "$POLICY_ARN"

rm aws-policy.json


# Create a group and attach the policy:

aws iam create-group --group-name "$GROUP_NAME"

aws iam attach-group-policy \
  --group-name "$GROUP_NAME" \
  --policy-arn "$POLICY_ARN"
```

## Update the existing policy

Use this to publish a new version of the already-created `PantheonSitehealthEmails`
policy (for example, to grant access to the second secret). Updating a customer
managed policy is done by creating a new policy version and marking it the
default; the policy ARN and all group/user attachments are unchanged.

```bash
# Find the ARN of the existing policy:
POLICY_ARN=$(
  aws iam list-policies \
    --scope Local \
    --query "Policies[?PolicyName=='$POLICY_NAME'].Arn" \
    --output text
)
echo "$POLICY_ARN"

# Build aws-policy.json first (see "Build the policy document" above).

# IAM keeps at most 5 versions of a policy. If create-policy-version fails with
# LimitExceeded, delete a non-default version first. List the non-default ones:
aws iam list-policy-versions \
  --policy-arn "$POLICY_ARN" \
  --query "Versions[?IsDefaultVersion==\`false\`].[VersionId,CreateDate]" \
  --output table

# ...then delete the oldest as needed (replace v1 with a VersionId from above):
#   aws iam delete-policy-version --policy-arn "$POLICY_ARN" --version-id v1

# Create the new version and make it the default:
aws iam create-policy-version \
  --policy-arn "$POLICY_ARN" \
  --policy-document file://aws-policy.json \
  --set-as-default

rm aws-policy.json

# Verify the default version now grants both secrets:
DEFAULT_VERSION=$(
  aws iam get-policy \
    --policy-arn "$POLICY_ARN" \
    --query Policy.DefaultVersionId \
    --output text
)
aws iam get-policy-version \
  --policy-arn "$POLICY_ARN" \
  --version-id "$DEFAULT_VERSION" \
  --query 'PolicyVersion.Document' \
  --output json | jq .
```


### Add a new user

```bash
# Create a user and an access key:

aws iam create-user --user-name "$USER_NAME"

aws iam create-access-key \
  --user-name "$USER_NAME" \
  --output json > "$USER_NAME.json"
cat "$USER_NAME.json"


# Add the credentials for the new user to 1Password:

# Vault: Pantheon Sitehealth Emails
# Item: AWS Access Key
# Fields: AccessKeyId, credential, username, type=Other

rm "$USER_NAME.json"


# Add the user to the group:

aws iam add-user-to-group \
  --user-name "$USER_NAME" \
  --group-name "$GROUP_NAME"

```
