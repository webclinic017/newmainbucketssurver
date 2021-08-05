import requests, os

def get_access_token(auth_code):
    response = requests.post(
        "https://api.alpaca.markets/oauth/token",
        {"grant_type": "authorization_code", "code" : auth_code, "client_id": os.environ.get('ALPACA_CLIENT_ID'), "client_secret": os.environ.get('ALPACA_CLIENT_SECRET'), "redirect_uri": "buckets://oauth"},
        {"Content-Type" : "application/x-www-form-urlencoded"}
    )
    return response.json()

def place_order(access_token, symbol, amount, side, order="by_money"):
    data = {
        "symbol": symbol,
        "side": side,
        "type": "market",
        "time_in_force": "day"
    }
    if order == "by_money":
        data["notional"] = amount
    else:
        data["qty"] = amount
    response = requests.post(
        "https://paper-api.alpaca.markets/v2/orders",
        headers={"Authorization": f'Bearer {access_token}'},
        json=data
    )
    return response.json()

def get_order_details(access_token, order_id):
    response = requests.get(
        f"https://paper-api.alpaca.markets/v2/orders/{order_id}",
        headers={"Authorization": f'Bearer {access_token}'}
    )
    return response.json()

# def check_if_market_open(access_token, date):
#     print("\n Date: ", date, "\n")
#     if date.weekday() < 5:
        
#     else:
#         return False
#     try:
#         response = requests.get(
#             f"https://paper-api.alpaca.markets/v2/calendar?start={date}&end={date}",
#             headers={"Authorization": f'Bearer {access_token}'}
#         )
#         response = response.json()
#         if 'code' in response and response['code'] in [40110000]:
#             print("\n", response["message"], "\n")
#             return False
#         else:
#             return response[0].get("open", False) and response[0].get("close", False)
#     except Exception as err:
#         print("Error: ", err)
#         return False