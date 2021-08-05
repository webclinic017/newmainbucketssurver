import requests, os, yahoo_finance
from datetime import datetime, timedelta
from db import db

POLYGON_API_KEY = os.environ.get('POLYGON_API_KEY')
StocksTable = db["stocks"]

def get_current_stats_of_bucket(bucket_id):
    total_market_value = 0
    percent_return_of_bucket = None
    try:
        cursor = StocksTable.find({"bucketId": bucket_id}) 
        did_update = False
        should_fetch = True
        total_cost_basis = 0
        for stock in cursor:
            if "orders" in stock and should_fetch and (datetime.now() - stock["lastUpdated"]) > timedelta(hours=24):
                did_update = True
                ticker = stock["description"].split(":")[0]
                should_fetch = latest_quote = yahoo_finance.get_latest_quote(ticker)
                latest_price = latest_quote if latest_quote else stock["latestPrice"]
                current_market_value = latest_price*stock["totalNoOfShares"]
                StocksTable.update_one(
                    {"_id": stock["_id"]},
                    {"$set": {
                        "latestPrice": latest_price,
                        "currentValue": current_market_value,
                        "lastUpdated": datetime.now()
                    }}
                )
                total_market_value = total_market_value + current_market_value
            else:
                total_market_value = total_market_value + stock["currentValue"]
            total_cost_basis = total_cost_basis + stock["costBasis"]
        if did_update and total_market_value > 0:
            cursor = StocksTable.find({"bucketId": bucket_id}) 
            for stock in cursor:
                stock_updated_weight = (stock["currentValue"]/total_market_value)*100
                StocksTable.update_one(
                    {"_id": stock["_id"]},
                    {"$set": {"percentWeight": stock_updated_weight}}
                )

        if total_cost_basis > 0:
            percent_return_of_bucket = ((total_market_value-total_cost_basis)/total_cost_basis)*100
        
        return total_market_value, percent_return_of_bucket
    except Exception as err:
        print("Error: ", err)
        return total_market_value, percent_return_of_bucket

# def get_latest_quote(ticker):
#     try:
#         response = requests.get(
#             # f"https://api.polygon.io/v1/last/stocks/{ticker}?&apiKey={POLYGON_API_KEY}",
#             f"https://api.polygon.io/v2/aggs/ticker/{ticker}/prev?unadjusted=true&apiKey={POLYGON_API_KEY}",
#             {"Content-Type" : "application/x-www-form-urlencoded"}
#         )
#         response = response.json()
#         if response.get("results", False):
#             return response["results"][0]["c"]
#         else:
#             print(f"\n {ticker}: ", response["error"], "\n")
#             return False
#     except Exception as err:
#         print("Error: ", err)
#         return False