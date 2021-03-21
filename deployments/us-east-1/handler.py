import boto3
import json
import requests
import logging
import os
import urllib.parse
import botocore


logger = logging.getLogger()
logger.setLevel( logging.INFO )
s3_handle = boto3.resource( 's3', region_name=os.environ['MOCKCACHE_AWS_REGION'] )


def entry_point(event, context):

    http_verb = event['requestContext']['http']['method']

    # Check S3 bucket for cached results -- if found 
    bucket_object_path = "{0}{1}".format(http_verb, event['rawPath'])
    if event['rawQueryString'] != "":
        bucket_object_path = "{0}?{1}".format( event['rawQueryString'] )
    bucket_object_path = urllib.parse.quote( bucket_object_path ) + ".json"
    s3_object = s3_handle.Object( os.environ['MOCKCACHE_S3_BUCKET'], bucket_object_path )

    try:
        s3_response = s3_object.get()
        found_in_cache = True

        cached_content = json.loads(s3_response['Body'].read())

        status_code = cached_content['status_code']
        body_text = cached_content['body_text']

        logger.info("Cache hit on {0}".format(bucket_object_path) )

    except botocore.exceptions.ClientError as e:
        logger.info( "Cache miss on {0}".format(bucket_object_path) )
        found_in_cache = False


    # If not in cache
    if found_in_cache is False:
        backend_uri = "{0}{1}".format( os.environ['MOCKCACHE_BACKEND_API_URL'], event['rawPath'] ) 

        # If there are query params, copy those over
        if event['rawQueryString'] != "":
            backend_uri = "{0}?{1}".format( backend_uri, event['rawQueryString'] )

        method_map = {
            "GET"       : requests.get,
            "PUT"       : requests.put,
            "POST"      : requests.post,
            "DELETE"    : requests.delete
        }

        # Make the query to the backend
        if http_verb in method_map:
            query_response = method_map[http_verb]( backend_uri )

            # copy status code over
            status_code = query_response.status_code

            # Copy response text over
            body_text = query_response.text

            # Write swagger mock API result to S3 bucket (TODO: figure out expiration)
            s3_data = {
                "status_code"   : status_code,
                "body_text"     : body_text 
            }
            s3_object.put( Body=json.dumps(s3_data) )


        else:
            status_code = 400
            body = {
                'Error': 'Unknown HTTP verb: {0}'.format(http_verb) 
            }
            body_text = json.dumps(body)


    headers = {
        "access-control-allow-method": "*",
        "access-control-allow-origin": "*",
    }

    response = {
        "statusCode"    : status_code,
        "headers"       : headers,
        "body"          : body_text
    }

    return response
