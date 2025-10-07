
import base64
import json

import boto3
import botocore.exceptions

import script_context as sc


secrets = {}
session = None
client = None


def get_secret(secret_name, key_name = None, region_name='', profile_name=''):

    global secrets, session, client

    # Load and cache the secret if it hasn't been loaded yet
    if secret_name not in secrets:
        sc.debug(f'Loading secret {secret_name} from AWS Secrets Manager')
        if profile_name != '':
            try:
                session = boto3.session.Session(profile_name=profile_name)
            except botocore.exceptions.ProfileNotFound:
                session = boto3.session.Session()
        else:
            session = boto3.session.Session()

        if region_name != '':
            client = session.client(service_name='secretsmanager', region_name=region_name)
        else:
            client = session.client(service_name='secretsmanager')

        # get_secret_value can throw exceptions.  We deliberately do not catch them here.
        # See https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_GetSecretValue.html
        get_secret_value_response = client.get_secret_value(SecretId=secret_name)

        # Decrypts secret using the associated KMS CMK.
        # Depending on whether the secret is a string or binary, one of these fields will be populated.
        if 'SecretString' in get_secret_value_response:
            secret = get_secret_value_response['SecretString']
        else:
            secret = base64.b64decode(get_secret_value_response['SecretBinary'])

        secrets[secret_name] = json.loads(secret)

    # Return the requested secret or just the requested key
    if key_name is None:
        return secrets[secret_name]
    if key_name not in secrets[secret_name]:
        raise KeyError(f'Key {key_name} not found in secret {secret_name}')
    #sc.debug(f'Secret {secret_name}.{key_name}: {secrets[secret_name][key_name]}')
    return secrets[secret_name][key_name]
