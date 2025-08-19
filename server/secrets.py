import boto3
import json
from botocore.exceptions import ClientError

def get_secret(secret_name="game-server/ab3"):
    """
    Retrieve secrets from AWS Secrets Manager
    """
    # Create a Secrets Manager client
    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name='us-east-1'
    )
    
    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=secret_name
        )
    except ClientError as e:
        # For development/local testing, fall back to environment variables
        print(f"Could not retrieve secret {secret_name}, falling back to environment variables")
        return None
    
    # Parse the secret
    secret = get_secret_value_response['SecretString']
    return json.loads(secret)

def get_config():
    """
    Get configuration from Secrets Manager or environment variables (fallback)
    """
    secrets = get_secret()
    
    if secrets:
        return secrets
    else:
        # Fallback to environment variables for local development
        import os
        from dotenv import load_dotenv
        load_dotenv()
        
        return {
            'AWS_COGNITO_USER_POOL_ID': os.getenv('AWS_COGNITO_USER_POOL_ID'),
            'AWS_COGNITO_CLIENT_ID': os.getenv('AWS_COGNITO_CLIENT_ID'),
            'AWS_COGNITO_CLIENT_SECRET': os.getenv('AWS_COGNITO_CLIENT_SECRET'),
            'AWS_DEFAULT_REGION': os.getenv('AWS_DEFAULT_REGION'),
            'DB_ENGINE': os.getenv('DB_ENGINE'),
            'DB_NAME': os.getenv('DB_NAME'),
            'DB_USER': os.getenv('DB_USER'),
            'DB_PASSWORD': os.getenv('DB_PASSWORD'),
            'DB_HOST': os.getenv('DB_HOST'),
            'DB_PORT': os.getenv('DB_PORT'),
        }