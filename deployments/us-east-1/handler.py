import boto3
import json
import requests
import logging
import os
import urllib.parse
import botocore


logger = logging.getLogger()
logger.setLevel( logging.DEBUG )
s3_handle = boto3.resource( 's3',   region_name=os.environ['MOCKCACHE_AWS_REGION'] )
s3_bucket = s3_handle.Bucket( os.environ['MOCKCACHE_S3_BUCKET'] )
s3_client = boto3.client('s3', region_name=os.environ['MOCKCACHE_AWS_REGION'] )


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


def clear_cache_entry_point(event, context):
    logger.info("Clear cache entry point hit")

    # Find all items in S3 bucket and nuke them
    delete_objects_field = { 
        'Objects'   : [],
        'Quiet'     : True,
    }

    for curr_object in s3_bucket.objects.all():
        #all_s3_keys.append( curr_object.key )
        delete_objects_field[ 'Objects' ].append( 
            {
                'Key'   : curr_object.key 
            }
        )

    if len( delete_objects_field['Objects'] ) > 0:

        #logger.info( "Delete objects field:\n{0}".format( json.dumps(delete_objects_field, indent=4, sort_keys=True)) )

        delete_response = s3_client.delete_objects(
            Bucket      = os.environ['MOCKCACHE_S3_BUCKET'],
            Delete      = delete_objects_field
        )

        files_deleted = len( delete_response['Deleted'] )

    else:

        files_deleted = 0
    

    status_code = 200

    headers = { 
        "access-control-allow-method": "*",
        "access-control-allow-origin": "*",
    }

    response = {
        "statusCode"    : status_code,
        "headers"       : headers,
        "body"          : json.dumps( { "files_deleted": files_deleted }, indent=4, sort_keys=True )
    }

    return response

