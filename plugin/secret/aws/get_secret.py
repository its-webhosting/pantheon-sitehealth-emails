# If you need more information about configurations or implementing the sample code, visit the AWS docs:
# https://aws.amazon.com/developers/getting-started/python/

import boto3
import base64

import botocore.exceptions


def get_secret(secret_name, region_name='', profile_name=''):
    # Create a Secrets Manager client
    if profile_name != '':
        try:
            session = boto3.session.Session(profile_name=profile_name)
        except botocore.exceptions.ProfileNotFound:
            session = boto3.session.Session()
    else:
        session = boto3.session.Session()

    if region_name != '':
        client = session.client(
            service_name='secretsmanager',
            region_name=region_name,
        )
    else:
        client = session.client(service_name='secretsmanager')

    # get_secret_value can throw exceptions.  We deliberately do not catch them here.
    # See https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_GetSecretValue.html
    get_secret_value_response = client.get_secret_value(SecretId=secret_name)

    # Decrypts secret using the associated KMS CMK.
    # Depending on whether the secret is a string or binary, one of these fields will be populated.
    if 'SecretString' in get_secret_value_response:
        return get_secret_value_response['SecretString']
    else:
        return base64.b64decode(get_secret_value_response['SecretBinary'])
