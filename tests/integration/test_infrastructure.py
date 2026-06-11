"""
Infrastructure validation tests for the SAM template (infra/template.yaml).

Tests parse the actual SAM template and validate:
- Required resources exist (S3, DynamoDB, Lambda, API Gateway, Cognito, CloudFront)
- Security configuration (encryption, public access blocks, SSL enforcement)
- IAM least privilege (no wildcard actions except where scoped)
- DynamoDB billing mode (PAY_PER_REQUEST)
- S3 lifecycle rules for cleanup
- Cognito password policy
- Lambda configuration (runtime, timeout, memory)
"""
import pytest
import yaml
from pathlib import Path

TEMPLATE_PATH = Path(__file__).parent.parent.parent / "infra" / "template.yaml"


class CfnLoader(yaml.SafeLoader):
    """YAML loader that preserves CloudFormation intrinsic functions."""


def _construct_cfn_tag(loader, tag_suffix, node):
    if isinstance(node, yaml.ScalarNode):
        value = loader.construct_scalar(node)
    elif isinstance(node, yaml.SequenceNode):
        value = loader.construct_sequence(node)
    else:
        value = loader.construct_mapping(node)
    return {f"!{tag_suffix}": value}


CfnLoader.add_multi_constructor("!", _construct_cfn_tag)


@pytest.fixture
def template():
    """Load and parse the SAM template."""
    if not TEMPLATE_PATH.exists():
        pytest.skip(f"SAM template not found at {TEMPLATE_PATH}")
    with open(TEMPLATE_PATH, "r") as f:
        return yaml.load(f, Loader=CfnLoader)


@pytest.fixture
def resources(template):
    """Extract the Resources section from the template."""
    return template.get("Resources", {})


# ---------------------------------------------------------------------------
# Resource existence tests
# ---------------------------------------------------------------------------

class TestRequiredResources:
    """Verify all required AWS resources are defined."""

    def test_has_audio_s3_bucket(self, resources):
        """Template must define an S3 bucket for audio uploads."""
        s3_buckets = [k for k, v in resources.items()
                      if v.get("Type") == "AWS::S3::Bucket"]
        assert len(s3_buckets) >= 1, "Must have at least one S3 bucket"
        assert "AudioBucket" in resources

    def test_has_dynamodb_table(self, resources):
        """Template must define a DynamoDB table for analysis records."""
        assert "AnalysisTable" in resources
        assert resources["AnalysisTable"]["Type"] == "AWS::DynamoDB::Table"

    def test_has_lambda_function(self, resources):
        """Template must define a Lambda function for the backend."""
        assert "BackendFunction" in resources
        assert resources["BackendFunction"]["Type"] == "AWS::Serverless::Function"

    def test_has_http_api(self, resources):
        """Template must define an HTTP API Gateway."""
        assert "HttpApi" in resources
        assert resources["HttpApi"]["Type"] == "AWS::Serverless::HttpApi"

    def test_has_cognito_user_pool(self, resources):
        """Template must define a Cognito User Pool."""
        assert "UserPool" in resources
        assert resources["UserPool"]["Type"] == "AWS::Cognito::UserPool"

    def test_has_cognito_client(self, resources):
        """Template must define a Cognito User Pool Client."""
        assert "UserPoolClient" in resources
        assert resources["UserPoolClient"]["Type"] == "AWS::Cognito::UserPoolClient"

    def test_has_cloudfront_distribution(self, resources):
        """Template must define a CloudFront distribution for the frontend."""
        assert "CloudFrontDistribution" in resources
        assert resources["CloudFrontDistribution"]["Type"] == "AWS::CloudFront::Distribution"

    def test_has_frontend_bucket(self, resources):
        """Template must define an S3 bucket for frontend static assets."""
        assert "FrontendBucket" in resources


# ---------------------------------------------------------------------------
# S3 security tests
# ---------------------------------------------------------------------------

class TestS3Security:
    """Verify S3 bucket security configuration."""

    def test_audio_bucket_blocks_public_access(self, resources):
        """Audio S3 bucket must block all public access."""
        props = resources["AudioBucket"]["Properties"]
        pac = props["PublicAccessBlockConfiguration"]
        assert pac["BlockPublicAcls"] is True
        assert pac["BlockPublicPolicy"] is True
        assert pac["IgnorePublicAcls"] is True
        assert pac["RestrictPublicBuckets"] is True

    def test_audio_bucket_has_encryption(self, resources):
        """Audio bucket must have server-side encryption."""
        props = resources["AudioBucket"]["Properties"]
        encryption = props["BucketEncryption"]
        sse_config = encryption["ServerSideEncryptionConfiguration"]
        assert len(sse_config) > 0
        algo = sse_config[0]["ServerSideEncryptionByDefault"]["SSEAlgorithm"]
        assert algo in ("AES256", "aws:kms")

    def test_audio_bucket_enforces_ssl(self, resources):
        """Audio bucket must have a bucket policy enforcing SSL."""
        assert "AudioBucketPolicy" in resources
        policy = resources["AudioBucketPolicy"]["Properties"]["PolicyDocument"]
        statements = policy["Statement"]
        ssl_statements = [s for s in statements if s.get("Sid") == "EnforceSSL"
                          or (s.get("Condition", {}).get("Bool", {}).get("aws:SecureTransport") == "false"
                              or s.get("Condition", {}).get("Bool", {}).get("aws:SecureTransport") is False)]
        assert len(ssl_statements) > 0, "Must have an SSL enforcement policy"

    def test_audio_bucket_has_lifecycle_rules(self, resources):
        """Audio bucket should have lifecycle rules for cleanup."""
        props = resources["AudioBucket"]["Properties"]
        lifecycle = props.get("LifecycleConfiguration", {})
        rules = lifecycle.get("Rules", [])
        assert len(rules) >= 1, "Must have at least one lifecycle rule"

        # Check that uploads get cleaned up
        upload_rules = [r for r in rules if r.get("Prefix", "").startswith("uploads")]
        assert len(upload_rules) >= 1, "Must have a lifecycle rule for uploads/"

    def test_audio_bucket_cors_configured(self, resources):
        """Audio bucket should have CORS configuration for presigned uploads."""
        props = resources["AudioBucket"]["Properties"]
        cors = props.get("CorsConfiguration", {})
        rules = cors.get("CorsRules", [])
        assert len(rules) >= 1, "Must have CORS rules for presigned URL uploads"
        assert "PUT" in rules[0].get("AllowedMethods", [])

    def test_frontend_bucket_blocks_public_access(self, resources):
        """Frontend bucket must block direct public access (CloudFront only)."""
        props = resources["FrontendBucket"]["Properties"]
        pac = props["PublicAccessBlockConfiguration"]
        assert pac["BlockPublicAcls"] is True
        assert pac["BlockPublicPolicy"] is True


# ---------------------------------------------------------------------------
# DynamoDB tests
# ---------------------------------------------------------------------------

class TestDynamoDB:
    """Verify DynamoDB configuration."""

    def test_pay_per_request_billing(self, resources):
        """DynamoDB table should use PAY_PER_REQUEST for cost efficiency."""
        props = resources["AnalysisTable"]["Properties"]
        assert props["BillingMode"] == "PAY_PER_REQUEST"

    def test_analysis_id_is_hash_key(self, resources):
        """Primary key should be analysis_id (HASH)."""
        props = resources["AnalysisTable"]["Properties"]
        key_schema = props["KeySchema"]
        hash_key = [k for k in key_schema if k["KeyType"] == "HASH"]
        assert len(hash_key) == 1
        assert hash_key[0]["AttributeName"] == "analysis_id"

    def test_has_user_id_gsi(self, resources):
        """Should have a GSI on user_id for listing user's analyses."""
        props = resources["AnalysisTable"]["Properties"]
        gsis = props.get("GlobalSecondaryIndexes", [])
        user_gsi = [g for g in gsis if g["IndexName"] == "user-index"]
        assert len(user_gsi) == 1
        # Hash key of GSI should be user_id
        gsi_hash = [k for k in user_gsi[0]["KeySchema"] if k["KeyType"] == "HASH"]
        assert gsi_hash[0]["AttributeName"] == "user_id"

    def test_ttl_enabled(self, resources):
        """TTL should be enabled for automatic record expiry."""
        props = resources["AnalysisTable"]["Properties"]
        ttl = props.get("TimeToLiveSpecification", {})
        assert ttl.get("Enabled") is True


# ---------------------------------------------------------------------------
# Lambda configuration tests
# ---------------------------------------------------------------------------

class TestLambdaConfiguration:
    """Verify Lambda function configuration."""

    def test_python_312_runtime(self, template):
        """Lambda should use Python 3.12 runtime."""
        # Check globals
        global_runtime = template.get("Globals", {}).get("Function", {}).get("Runtime")
        backend_props = template["Resources"]["BackendFunction"]["Properties"]
        assert global_runtime == "python3.12" or backend_props.get("PackageType") == "Image"

    def test_backend_function_handler(self, resources):
        """Backend function handler should point to FastAPI Mangum handler."""
        props = resources["BackendFunction"]["Properties"]
        assert props.get("Handler") == "app.main.handler" or props.get("PackageType") == "Image"

    def test_reasonable_timeout(self, resources):
        """Lambda timeout should be reasonable (not too short, not max)."""
        props = resources["BackendFunction"]["Properties"]
        timeout = props.get("Timeout", 60)
        assert 10 <= timeout <= 300

    def test_environment_variables(self, resources):
        """Lambda should have required environment variables."""
        props = resources["BackendFunction"]["Properties"]
        env_vars = props["Environment"]["Variables"]
        required_vars = ["S3_BUCKET", "DYNAMODB_TABLE", "BEDROCK_MODEL_ID"]
        for var in required_vars:
            assert var in env_vars, f"Missing required env var: {var}"


# ---------------------------------------------------------------------------
# IAM / Permissions tests
# ---------------------------------------------------------------------------

class TestIAMPermissions:
    """Verify IAM permissions follow least privilege."""

    def test_lambda_has_s3_access(self, resources):
        """Lambda should have S3 CRUD access to the audio bucket."""
        policies = resources["BackendFunction"]["Properties"]["Policies"]
        s3_policies = [p for p in policies if isinstance(p, dict) and "S3CrudPolicy" in p]
        assert len(s3_policies) >= 1

    def test_lambda_has_dynamodb_access(self, resources):
        """Lambda should have DynamoDB CRUD access to the analysis table."""
        policies = resources["BackendFunction"]["Properties"]["Policies"]
        ddb_policies = [p for p in policies if isinstance(p, dict) and "DynamoDBCrudPolicy" in p]
        assert len(ddb_policies) >= 1

    def test_lambda_has_transcribe_access(self, resources):
        """Lambda should have Transcribe permissions."""
        policies = resources["BackendFunction"]["Properties"]["Policies"]
        # Find Statement-based policies
        statements = []
        for p in policies:
            if isinstance(p, dict) and "Statement" in p:
                statements.extend(p["Statement"])

        transcribe_perms = [s for s in statements
                            if any("transcribe:" in a for a in s.get("Action", []))]
        assert len(transcribe_perms) >= 1

    def test_lambda_has_bedrock_access(self, resources):
        """Lambda should have Bedrock InvokeModel permission."""
        policies = resources["BackendFunction"]["Properties"]["Policies"]
        statements = []
        for p in policies:
            if isinstance(p, dict) and "Statement" in p:
                statements.extend(p["Statement"])

        bedrock_perms = [s for s in statements
                         if any("bedrock:" in a for a in s.get("Action", []))]
        assert len(bedrock_perms) >= 1

    def test_bedrock_resource_scoped_to_claude(self, resources):
        """Bedrock permission should be scoped to Claude models, not wildcard."""
        policies = resources["BackendFunction"]["Properties"]["Policies"]
        statements = []
        for p in policies:
            if isinstance(p, dict) and "Statement" in p:
                statements.extend(p["Statement"])

        bedrock_perms = [s for s in statements
                         if any("bedrock:" in a for a in s.get("Action", []))]
        for perm in bedrock_perms:
            resource = perm.get("Resource", "")
            # Resource should reference claude models, not "*"
            if isinstance(resource, str):
                assert resource != "*", "Bedrock resource should not be wildcard"


# ---------------------------------------------------------------------------
# Cognito security tests
# ---------------------------------------------------------------------------

class TestCognitoSecurity:
    """Verify Cognito configuration."""

    def test_password_minimum_length(self, resources):
        """Password policy should require at least 8 characters."""
        props = resources["UserPool"]["Properties"]
        policy = props["Policies"]["PasswordPolicy"]
        assert policy["MinimumLength"] >= 8

    def test_password_requires_uppercase(self, resources):
        """Password should require uppercase letters."""
        props = resources["UserPool"]["Properties"]
        policy = props["Policies"]["PasswordPolicy"]
        assert policy["RequireUppercase"] is True

    def test_password_requires_lowercase(self, resources):
        """Password should require lowercase letters."""
        props = resources["UserPool"]["Properties"]
        policy = props["Policies"]["PasswordPolicy"]
        assert policy["RequireLowercase"] is True

    def test_password_requires_numbers(self, resources):
        """Password should require numbers."""
        props = resources["UserPool"]["Properties"]
        policy = props["Policies"]["PasswordPolicy"]
        assert policy["RequireNumbers"] is True

    def test_admin_only_signup(self, resources):
        """Only admin should be able to create users."""
        props = resources["UserPool"]["Properties"]
        admin_config = props["AdminCreateUserConfig"]
        assert admin_config["AllowAdminCreateUserOnly"] is True

    def test_client_no_secret(self, resources):
        """Client should not generate a secret (public SPA client)."""
        props = resources["UserPoolClient"]["Properties"]
        assert props["GenerateSecret"] is False

    def test_prevent_user_existence_errors(self, resources):
        """Should prevent user enumeration attacks."""
        props = resources["UserPoolClient"]["Properties"]
        assert props["PreventUserExistenceErrors"] == "ENABLED"


# ---------------------------------------------------------------------------
# API Gateway tests
# ---------------------------------------------------------------------------

class TestAPIGateway:
    """Verify API Gateway configuration."""

    def test_cors_configured(self, resources):
        """API Gateway should have CORS configured."""
        props = resources["HttpApi"]["Properties"]
        cors = props.get("CorsConfiguration", {})
        assert "AllowOrigins" in cors
        assert "AllowMethods" in cors
        assert "GET" in cors["AllowMethods"]
        assert "POST" in cors["AllowMethods"]

    def test_cognito_authorizer(self, resources):
        """API Gateway should use Cognito JWT authorizer."""
        props = resources["HttpApi"]["Properties"]
        auth = props.get("Auth", {})
        assert auth.get("DefaultAuthorizer") == "CognitoAuthorizer"
        assert "CognitoAuthorizer" in auth.get("Authorizers", {})

    def test_health_check_no_auth(self, resources):
        """Health check endpoint should not require auth."""
        events = resources["BackendFunction"]["Properties"]["Events"]
        health_event = events.get("HealthCheck", {})
        props = health_event.get("Properties", {})
        auth = props.get("Auth", {})
        assert auth.get("Authorizer") == "NONE"


# ---------------------------------------------------------------------------
# CloudFront tests
# ---------------------------------------------------------------------------

class TestCloudFront:
    """Verify CloudFront configuration."""

    def test_https_redirect(self, resources):
        """CloudFront should redirect HTTP to HTTPS."""
        dist_config = resources["CloudFrontDistribution"]["Properties"]["DistributionConfig"]
        default_behavior = dist_config["DefaultCacheBehavior"]
        assert default_behavior["ViewerProtocolPolicy"] == "redirect-to-https"

    def test_minimum_tls_version(self, resources):
        """Should enforce TLS 1.2 minimum."""
        dist_config = resources["CloudFrontDistribution"]["Properties"]["DistributionConfig"]
        cert = dist_config["ViewerCertificate"]
        assert "TLSv1.2" in cert.get("MinimumProtocolVersion", "")

    def test_spa_error_handling(self, resources):
        """Should handle 404/403 errors for SPA routing."""
        dist_config = resources["CloudFrontDistribution"]["Properties"]["DistributionConfig"]
        error_responses = dist_config.get("CustomErrorResponses", [])
        error_codes = [r["ErrorCode"] for r in error_responses]
        assert 404 in error_codes
        assert 403 in error_codes


# ---------------------------------------------------------------------------
# Template-level tests
# ---------------------------------------------------------------------------

class TestTemplateStructure:
    """Verify overall template structure."""

    def test_has_parameters(self, template):
        """Template should have configurable parameters."""
        params = template.get("Parameters", {})
        assert "Environment" in params
        assert "dev" in params["Environment"].get("AllowedValues", [])

    def test_has_outputs(self, template):
        """Template should export useful outputs."""
        outputs = template.get("Outputs", {})
        assert "ApiUrl" in outputs
        assert "CloudFrontUrl" in outputs
        assert "AudioBucketName" in outputs
        assert "DynamoDBTableName" in outputs
        assert "UserPoolId" in outputs

    def test_uses_sam_transform(self, template):
        """Template should use SAM transform."""
        assert template.get("Transform") == "AWS::Serverless-2016-10-31"
