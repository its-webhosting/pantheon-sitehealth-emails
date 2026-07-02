
# Setting up AWS credentials for pantheon-sitehealth-email

The `pantheon-sitehealth-emails` script currently needs to do the following in AWS:

* Read the secret webinfo in account aws-webhosting-admin, us-east-1.

That's it.

## Set shell variables

```bash
AWS_REGION="us-east-1"
SECRET_ID="webinfo"
POLICY_NAME="PantheonSitehealthEmails"
GROUP_NAME="PantheonSitehealthEmails"
USER_NAME="markmont-PantheonSitehealthEmails"
```

## Create an IAM policy

This is already done, skip ahead to the next section unless you're modifying the policy to add/remove permissions.

```bash
# Get the ARN for the secret:
SECRET_ARN=$(
  aws secretsmanager describe-secret \
    --region "$AWS_REGION" \
    --secret-id "$SECRET_ID" \
    --query ARN \
    --output text
)
echo $SECRET_ARN

KMS_KEY_ID=$(
  aws secretsmanager describe-secret \
    --region "$AWS_REGION" \
    --secret-id "$SECRET_ARN" \
    --query KmsKeyId \
    --output text
)
echo $KMS_KEY_ID

# Create the policy:
cat > aws-policy.json <<EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "AllowReadSpecificSecret",
            "Effect": "Allow",
            "Action": [
                "secretsmanager:GetSecretValue",
                "secretsmanager:DescribeSecret"
            ],
            "Resource": "$SECRET_ARN"
        },
        {
            "Sid": "AllowKmsDecryptForThisSecretOnly",
            "Effect": "Allow",
            "Action": "kms:Decrypt",
            "Resource": "$SECRET_ARN,
            "Condition": {
                "StringEquals": {
                    "kms:ViaService": "secretsmanager.us-east-1.amazonaws.com",
                    "kms:EncryptionContext:aws:secretsmanager:arn": "arn:aws:secretsmanager:us-east-1:123456789012:secret:my/app/secret-AbCdEf"
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
            "NotResource": "$SECRET_ARN"
        },
        {
            "Sid": "DenyEverythingExceptReadingThisSecret",
            "Effect": "Deny",
            "NotAction": [
                "secretsmanager:GetSecretValue",
                "secretsmanager:DescribeSecret",
                "kms:Decrypt"
            ],
            "Resource": "*"
        }
    ]
}
EOF

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
