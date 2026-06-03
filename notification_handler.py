import json
import boto3

# CONFIGURATION
AWS_REGION = "us-east-1"

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
    """Get existing SNS topic for a tag or create new one"""
    topic_name = f"wildlife-tag-{tag.lower().replace(' ', '-')}"

    response = sns.list_topics()
    for topic in response.get("Topics", []):
        if topic_name in topic["TopicArn"]:
            return topic["TopicArn"]

    response = sns.create_topic(Name=topic_name)
    print(f"Created new SNS topic: {topic_name}")
    return response["TopicArn"]

def subscribe_email(topic_arn, email):
    """Subscribe an email to an SNS topic"""
    sns.subscribe(
        TopicArn=topic_arn,
        Protocol="email",
        Endpoint=email
    )
    print(f"Subscribed {email} to {topic_arn}")

def publish_notification(topic_arn, tag, file_url, thumbnail_url=None):
    """Publish notification to SNS topic"""
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

def lambda_handler(event, context):
    """
    POST /subscribe  → subscribe email to tag notifications
    {
        "email": "user@example.com",
        "tags": ["koala", "wombat"]
    }

    OR called internally by tagging_handler:
    {
        "action": "notify",
        "tags": {"koala": 2, "wombat": 1},
        "file_url": "https://...",
        "thumbnail_url": "https://..."
    }
    """
    # Handle CORS preflight
    if event.get("httpMethod") == "OPTIONS":
        return success_response({})

    try:
        if isinstance(event.get("body"), str):
            body = json.loads(event["body"])
        else:
            body = event

        action = body.get("action", "subscribe")

        # Subscribe user to tag notifications
        if action == "subscribe":
            email = body.get("email", "")
            tags = body.get("tags", [])

            if not email or not tags:
                return error_response("Email and tags are required")

            subscribed = []
            for tag in tags:
                topic_arn = get_or_create_topic(tag)
                subscribe_email(topic_arn, email)
                subscribed.append({"tag": tag, "topic_arn": topic_arn})

            return success_response({
                "message": f"Subscribed {email} to {len(tags)} tag(s)",
                "subscriptions": subscribed
            })

        # Send notifications (called by tagging_handler)
        elif action == "notify":
            tags = body.get("tags", {})
            file_url = body.get("file_url", "")
            thumbnail_url = body.get("thumbnail_url", "")

            if not tags:
                return error_response("No tags provided")

            notifications_sent = []
            for tag, count in tags.items():
                try:
                    topic_arn = get_or_create_topic(tag)
                    publish_notification(topic_arn, tag, file_url, thumbnail_url)
                    notifications_sent.append({
                        "tag": tag,
                        "count": count,
                        "status": "sent"
                    })
                except Exception as e:
                    notifications_sent.append({
                        "tag": tag,
                        "status": "failed",
                        "error": str(e)
                    })

            return success_response({
                "message": "Notifications processed",
                "notifications": notifications_sent
            })

        else:
            return error_response("Invalid action. Use 'subscribe' or 'notify'")

    except Exception as e:
        return error_response(f"Internal server error: {str(e)}", 500)
