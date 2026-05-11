# pyvar-cdk — AWS CDK deployment for pyvar.com
#
# Deploy:
#   pip install -r requirements.txt
#   cdk bootstrap aws://ACCOUNT/eu-west-2 aws://ACCOUNT/us-east-1
#   cdk deploy --context env=dev --all
#
# Per-environment:
#   cdk deploy --context env=prod --context account=123456789012 --all
#
# Stack order (auto-resolved by CDK but shown for clarity):
#   NetworkStack → DataStack → QueueStack → ComputeStack → ApiStack → EdgeStack
#
# Key cost controls:
#   - EC2 Spot workers scale to 0 when SQS is empty
#   - Aurora SV2 min 0.5 ACU (~$45/month baseline)
#   - ElastiCache Serverless (pay-per-use)
#   - CloudFront PriceClass_100 (US + EU PoPs only)
#   - VPC Gateway Endpoints eliminate NAT GW data charges for S3
