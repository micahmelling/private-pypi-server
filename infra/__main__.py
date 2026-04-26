import pulumi_aws as aws


def main(bucket_name: str,
         package_name: str,
         aliases: list,
         certificate_arn: str,
         domain_name: str,
         hosted_zone_id: str,
         ip_addresses
         ):
    """
    Creates a static, single-page website accessible via a Route 53 DNS and protected with SSL. This script also
    uploads an index.html and package distribution to create a PyPi server.

    This makes certain assumptions to be compatible with what uv expects.

    :param bucket_name: name of the S3 bucket
    :param package_name: name of the package and version (ex: awesomeutils-1.0.0)
    :param aliases: CloudFront aliases, which must include domain_name
    :param certificate_arn: ARN of the SSL cert, which must be in us-east-1
    :param domain_name: domain name
    :param hosted_zone_id: Route53 hosted zone ID
    :param ip_addresses: IP addresses (in CIDR format) we want to have access (e.g., '192.168.1.1/32')
    """
    web_bucket = aws.s3.Bucket(f"{bucket_name}-bucket",
                               bucket=bucket_name
                               )

    website_config = aws.s3.BucketWebsiteConfiguration(f"{bucket_name}-website-config",
                                                       bucket=web_bucket.id,
                                                       index_document=aws.s3.BucketWebsiteConfigurationV2IndexDocumentArgs(
                                                             suffix="index.html"
                                                         )
                                                       )

    index_obj = aws.s3.BucketObjectv2("index-html",
                                      bucket=web_bucket.id,
                                      key="index.html",
                                      source='../index.html',
                                      content_type="text/html"
                                      )

    html_obj2 = aws.s3.BucketObjectv2("simple-html",
                                      bucket=web_bucket.id,
                                      key="simple/index.html",
                                      source='../simple.html',
                                      content_type="text/html"
                                      )

    html_obj3 = aws.s3.BucketObjectv2("package-html",
                                      bucket=web_bucket.id,
                                      key="simple/awesomeutils/index.html",
                                      source='../package.html',
                                      content_type="text/html"
                                     )

    # this upload has been weird once in a while; can manually upload if needed
    pkg_obj = aws.s3.BucketObjectv2("pkg-dist",
                                    bucket=web_bucket.id,
                                    key=f"simple/awesomeutils/{package_name}.tar.gz",
                                    content_type='application/gzip'
                                    )

    ipset = aws.wafv2.IpSet("ipset",
                            scope="CLOUDFRONT",
                            ip_address_version="IPV4",
                            addresses=ip_addresses
                            )

    waf_acl = aws.wafv2.WebAcl(
        "wafAcl",
        scope="CLOUDFRONT",
        default_action=aws.wafv2.WebAclDefaultActionArgs(
            block={}
        ),
        visibility_config=aws.wafv2.WebAclVisibilityConfigArgs(
            cloudwatch_metrics_enabled=True,
            metric_name="WebACL",
            sampled_requests_enabled=True,
        ),
        rules=[
            aws.wafv2.WebAclRuleArgs(
                name="AllowTrustedIPsOnly",
                priority=0,
                action=aws.wafv2.WebAclRuleActionArgs(
                    allow={}
                ),
                statement=aws.wafv2.WebAclRuleStatementArgs(
                    ip_set_reference_statement=aws.wafv2.WebAclRuleStatementIpSetReferenceStatementArgs(
                        arn=ipset.arn,
                    )
                ),
                visibility_config=aws.wafv2.WebAclVisibilityConfigArgs(
                    cloudwatch_metrics_enabled=True,
                    metric_name="AllowTrustedIPsOnly",
                    sampled_requests_enabled=True,
                )
            ),
            aws.wafv2.WebAclRuleArgs(
                name="AWSManagedRulesCommonRuleSet",
                priority=1,
                override_action=aws.wafv2.WebAclRuleOverrideActionArgs(
                    none={}
                ),
                statement=aws.wafv2.WebAclRuleStatementArgs(
                    managed_rule_group_statement=aws.wafv2.WebAclRuleStatementManagedRuleGroupStatementArgs(
                        name="AWSManagedRulesCommonRuleSet",
                        vendor_name="AWS",
                    )
                ),
                visibility_config=aws.wafv2.WebAclVisibilityConfigArgs(
                    cloudwatch_metrics_enabled=True,
                    metric_name="AWSManagedRules",
                    sampled_requests_enabled=True,
                )
            ),
        ]
    )

    oac = aws.cloudfront.OriginAccessControl(f"{bucket_name}_oac",
                                             description="OAC for S3 static website",
                                             origin_access_control_origin_type="s3",
                                             signing_behavior="always",
                                             signing_protocol="sigv4"
                                             )

    rewrite_function = aws.cloudfront.Function("rewrite-index",
                                               name=f"{bucket_name}-rewrite-index",
                                               runtime="cloudfront-js-1.0",
                                               publish=True,
                                               code="""
            function handler(event) {
                var request = event.request;
                var uri = request.uri;

                // Check if the URI ends with a slash and append index.html
                if (uri.endsWith('/')) {
                    request.uri += 'index.html';
                } 
                // If it doesn't end with a slash and has no file extension, append /index.html
                else if (!uri.includes('.')) {
                    request.uri += '/index.html';
                }
                return request;
            }
            """
                                               )

    cache_policy = aws.cloudfront.get_cache_policy(name="Managed-CachingOptimized")

    s3_distribution = aws.cloudfront.Distribution(f'{bucket_name}_distribution',
                                                  origins=[aws.cloudfront.DistributionOriginArgs(
                                                      domain_name=web_bucket.bucket_regional_domain_name,
                                                      origin_id=f's3{bucket_name}_origin',
                                                      origin_access_control_id=oac.id,
                                                  )],
                                                  enabled=True,
                                                  is_ipv6_enabled=False,
                                                  default_root_object="index.html",
                                                  aliases=aliases,
                                                  web_acl_id=waf_acl.arn,
                                                  default_cache_behavior=aws.cloudfront.DistributionDefaultCacheBehaviorArgs(
                                                      allowed_methods=["DELETE", "GET", "HEAD", "OPTIONS", "PATCH",
                                                                       "POST", "PUT"],
                                                      cached_methods=["GET", "HEAD"],
                                                      target_origin_id=f's3{bucket_name}_origin',
                                                      cache_policy_id=cache_policy.id,
                                                      viewer_protocol_policy="redirect-to-https",
                                                      function_associations=[
                                                          aws.cloudfront.DistributionDefaultCacheBehaviorFunctionAssociationArgs(
                                                              event_type="viewer-request",
                                                              function_arn=rewrite_function.arn,
                                                          )],
                                                  ),
                                                  restrictions=aws.cloudfront.DistributionRestrictionsArgs(
                                                      geo_restriction=aws.cloudfront.DistributionRestrictionsGeoRestrictionArgs(
                                                          restriction_type="none",
                                                      ),
                                                  ),
                                                  viewer_certificate=aws.cloudfront.DistributionViewerCertificateArgs(
                                                      acm_certificate_arn=certificate_arn,
                                                      ssl_support_method='sni-only'
                                                  ),

                                                  )

    source = aws.iam.get_policy_document_output(statements=[
        aws.iam.GetPolicyDocumentStatementArgs(
            actions=["s3:GetObject"],
            resources=[web_bucket.arn.apply(lambda arn: f"{arn}/*")],
            principals=[
                aws.iam.GetPolicyDocumentStatementPrincipalArgs(
                    type="Service",
                    identifiers=["cloudfront.amazonaws.com"]
                ),
            ],
            conditions=[
                aws.iam.GetPolicyDocumentStatementConditionArgs(
                    test="StringEquals",
                    variable="AWS:SourceArn",
                    values=[s3_distribution.arn]
                )
            ]
        ),
        aws.iam.GetPolicyDocumentStatementArgs(
            actions=["s3:GetObject"],
            resources=[web_bucket.arn.apply(lambda arn: f"{arn}/*")],
            principals=[
                aws.iam.GetPolicyDocumentStatementPrincipalArgs(
                    type="*",
                    identifiers=["*"]
                ),
            ],
            conditions=[
                aws.iam.GetPolicyDocumentStatementConditionArgs(
                    test="IpAddress",
                    variable="aws:SourceIp",
                    values=ip_addresses
                )
            ]
        )
    ])

    bucket_policy = aws.s3.BucketPolicy(f"{bucket_name}_bucket-policy",
                                        bucket=web_bucket.id,
                                        policy=source.json
                                        )

    route_53_record = aws.route53.Record(domain_name,
                                         zone_id=hosted_zone_id,
                                         name=domain_name,
                                         type="A",
                                         aliases=[aws.route53.RecordAliasArgs(
                                             name=s3_distribution.domain_name,
                                             zone_id=s3_distribution.hosted_zone_id,
                                             evaluate_target_health=False,
                                         )]
                                         )


if __name__ == "__main__":
    main(
        bucket_name="",  # fill in
        package_name="awesomeutils-1.0.0",
        aliases=[""],  # fill in your desired url and any other aliases
        certificate_arn="",  # make env var
        domain_name="",  # fill in your desired url
        hosted_zone_id="",  # make env var
        ip_addresses=[""]  # fill in ip addresses in CIDR notation
    )
