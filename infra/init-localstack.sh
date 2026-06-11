#!/bin/bash
# Initializes LocalStack resources for local development.
# This script runs automatically when LocalStack starts.

set -e

echo "Initializing LocalStack resources..."

# Create S3 bucket for audio uploads
awslocal s3 mb s3://presenters-feedback-audio-dev

# Create DynamoDB table
awslocal dynamodb create-table \
  --table-name presenters-feedback-dev \
  --attribute-definitions \
    AttributeName=PK,AttributeType=S \
    AttributeName=SK,AttributeType=S \
  --key-schema \
    AttributeName=PK,KeyType=HASH \
    AttributeName=SK,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST

echo "LocalStack initialization complete."
echo "  S3 bucket: presenters-feedback-audio-dev"
echo "  DynamoDB table: presenters-feedback-dev"
