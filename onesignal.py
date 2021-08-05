from onesignal_sdk.client import Client
import os

client = Client(
    app_id=os.environ.get('ONESIGNAL_APP_ID'),
    rest_api_key=os.environ.get('ONESIGNAL_API_KEY')
)

def send_notification(player_ids, message):
    notification_body = {
        'contents': {'en': message},
        'include_player_ids': player_ids
    }
    response = client.send_notification(notification_body)
    return response.body