import json
import boto3
import os
import re

AWS_REGION = os.environ.get("REGION", "us-east-1")
sns = boto3.client("sns", region_name=AWS_REGION)

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Authorization,Content-Type",
    "Access-Control-Allow-Methods": "GET,POST,DELETE,OPTIONS"
}

def success_response(data, status_code=200):
    return {
        "statusCode": status_code,
        "headers": CORS_HEADERS,
        "body": json.dumps({"success": True, "data": data})
    }

def error_response(message, status_code=400):
    return {
        "statusCode": status_code,
        "headers": CORS_HEADERS,
        "body": json.dumps({"success": False, "error": message})
    }

def get_or_create_topic(tag):
    topic_name = f"wildlife-tag-{tag.lower().replace(' ', '-')}"
    
    paginator = sns.get_paginator('list_topics')
    for page in paginator.paginate():
        for topic in page.get("Topics", []):
            if topic_name in topic["TopicArn"]:
                return topic["TopicArn"]

    response = sns.create_topic(Name=topic_name)
    print(f"Created new SNS topic: {topic_name}")
    return response["TopicArn"]

def is_valid_email(email):
    return re.match(r"[^@]+@[^@]+\.[^@]+", email) is not None

def subscribe_email(topic_arn, email):
    # Check if already subscribed
    paginator = sns.get_paginator('list_subscriptions_by_topic')
    for page in paginator.paginate(TopicArn=topic_arn):
        for sub in page.get("Subscriptions", []):
            if sub["Endpoint"] == email:
                print(f"{email} is already subscribed to {topic_arn}")
                return False # Already subscribed

    sns.subscribe(
        TopicArn=topic_arn,
        Protocol="email",
        Endpoint=email
    )
    print(f"Subscribed {email} to {topic_arn}")
    return True

def publish_notification(topic_arn, tag, file_url, thumbnail_url=None):
    # Check if there are confirmed subscribers
    response = sns.get_topic_attributes(TopicArn=topic_arn)
    confirmed_subs = int(response.get('Attributes', {}).get('SubscriptionsConfirmed', 0))
    
    if confirmed_subs == 0:
        print(f"No confirmed subscribers for {topic_arn}, skipping publish.")
        return False

    message = {
        "message": f"New wildlife sighting detected: {tag}",
        "tag": tag,
        "file_url": file_url,
        "thumbnail_url": thumbnail_url or "N/A"
    }

    sns.publish(
        TopicArn=topic_arn,
        Subject=f"New {tag.title()} Detected - Aussie EcoLens",
        Message=json.dumps(message, indent=2)
    )
    print(f"Notification sent for tag: {tag}")
    return True

def lambda_handler(event, context):
    is_api_gateway = "httpMethod" in event
    
    if is_api_gateway and event.get("httpMethod") == "OPTIONS":
        return success_response({})

    try:
        if is_api_gateway:
            body_str = event.get("body")
            if not body_str:
                return error_response("Request body is required")
            try:
                body = json.loads(body_str)
            except json.JSONDecodeError:
                return error_response("Invalid JSON in request body")
        else:
            body = event # Internal invoke

        action = body.get("action", "subscribe")

        if action == "subscribe":
            email = body.get("email", "")
            tags = body.get("tags", [])
            species = body.get("species", "")

            if species and not tags:
                tags = [species]

            if not email or not tags:
                return error_response("Email and tags are required")
                
            if not is_valid_email(email):
                return error_response("Invalid email format")

            subscribed = []
            for tag in tags:
                topic_arn = get_or_create_topic(tag)
                new_sub = subscribe_email(topic_arn, email)
                subscribed.append({"tag": tag, "topic_arn": topic_arn, "new_subscription": new_sub})

            if not is_api_gateway:
                return {"status": "ok"}
                
            return success_response({
                "message": f"Subscription processed for {email}.",
                "subscriptions": subscribed
            })

        elif action == "notify":
            tags = body.get("tags", {})
            file_url = body.get("file_url", "")
            thumbnail_url = body.get("thumbnail_url", "")

            if not tags:
                if not is_api_gateway:
                    return {"status": "error", "message": "No tags provided"}
                return error_response("No tags provided")

            notifications_sent = []
            for tag, count in tags.items():
                try:
                    topic_arn = get_or_create_topic(tag)
                    published = publish_notification(topic_arn, tag, file_url, thumbnail_url)
                    notifications_sent.append({
                        "tag": tag,
                        "count": count,
                        "status": "sent" if published else "skipped_no_subscribers"
                    })
                except Exception as e:
                    notifications_sent.append({
                        "tag": tag,
                        "status": "failed",
                        "error": str(e)
                    })

            if not is_api_gateway:
                return {"status": "ok"}
                
            return success_response({
                "message": "Notifications processed",
                "notifications": notifications_sent
            })

        else:
            if not is_api_gateway:
                return {"status": "error", "message": "Invalid action"}
            return error_response("Invalid action. Use 'subscribe' or 'notify'")

    except Exception as e:
        if not is_api_gateway:
            raise e
        return error_response(f"Internal server error: {str(e)}", 500)
