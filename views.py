from flask_restful import Resource, reqparse
from flask import jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from yahoofinancials import YahooFinancials
from datetime import datetime, timedelta
from functools import reduce
from utilities import (
    JSONEncoder, schedule_bucket_rebalance,
    rebalance_bucket_to_initial_weights,
    check_if_market_open
)
from bson import ObjectId
from db import db
from config import fernet, scheduler
import polygon, time
import robin_stocks
import alpaca, pyportfolio, onesignal
import json, copy, requests, os

BucketsTable = db["buckets"]
StocksTable = db["stocks"]
UsersTable = db["users"]


class GetAlpacaAccessToken(Resource):
    @jwt_required()
    def post(self):
        try:
            data = request.json
            access_data = alpaca.get_access_token(data["authCode"])
            if access_data.get("access_token", False):
                encrypted_token = fernet.encrypt(access_data["access_token"].encode('utf-8'))
                update_response = UsersTable.update_one(
                    {"_id": ObjectId(get_jwt_identity())},
                    {"$set": {
                        "alpacaAccessToken": encrypted_token,
                        "isAlpacaAuthorized": True
                    }}
                )
                if update_response.modified_count > 0:
                    retJson = {
                        "status": 200,
                        "access_token": encrypted_token.decode('utf-8'),
                        "message": "Alpaca account is successfully linked!"
                    }
                    return jsonify(retJson)
                else:
                    retJson = {
                        "status": 500,
                        "message": "An error occurred during alpaca account linking!"
                    }
                    return jsonify(retJson)
            else:
                retJson = {
                    "status": 500,
                    "message": f'Error: {access_data["message"]}'
                }
                return jsonify(retJson)
        except Exception as err:
            print("Error: ", err)
            retJson = {
                "status": 500,
                "message": str(err)
            }
            return jsonify(retJson)

class PlaceAlpacaOrder(Resource):
    # @jwt_required()
    def post(self):
        try:
            if check_if_market_open(datetime.now()):
                data = request.json
                res = StocksTable.find({
                    "bucketId": ObjectId(data["bucketId"])
                })
                stocks = copy.deepcopy(res)
                # transactions = []
                if data["type"].lower() == "sell":
                    for stock in res:
                        percentage = float(stock["targetWeight"]/100)
                        amount = round(percentage*data["value"], 2)
                        if stock["currentValue"] < amount:
                            retJson = {
                                "status": 500,
                                "message": "Insufficient shares, you can't sell more than the amount of shares you hold!"
                            }
                            return jsonify(retJson)
                overall_bucket_value = 0
                decrypted_token = fernet.decrypt(data["accessToken"].encode('utf-8')).decode('utf-8')
                for stock in stocks:
                    symbol = stock["ticker"]
                    percentage = float(stock["targetWeight"]/100)
                    amount = round(percentage*data["value"], 2)
                    print("\nTotal Amount: ", data["value"])
                    print("Share symbol: ", symbol)
                    print("Stock percentage: ", percentage)
                    print("Stock amount: ", amount)
                    response = alpaca.place_order(decrypted_token, symbol, amount, data["type"])
                    if "code" in response and response["code"] in [40110000, 40010001, 40310000]:
                        return jsonify(response)
                    print("Order Response: ", response)
                    order_details = alpaca.get_order_details(decrypted_token, response["id"])
                    while order_details["status"] != 'filled':
                        time.sleep(10)
                        order_details = alpaca.get_order_details(decrypted_token, response["id"])
                    print("Order Details: ", order_details)
                    new_no_of_shares = float(order_details["filled_qty"]) if data["type"].lower()=="buy" else -float(order_details["filled_qty"])
                    overall_price = stock.get("overallPrice", 0)
                    overall_no_of_shares = new_no_of_shares+stock["totalNoOfShares"]
                    if data["type"].lower() == "buy":
                        overall_price = ((stock["totalNoOfShares"]*overall_price)+(float(order_details["filled_qty"])*float(order_details["filled_avg_price"])))/(overall_no_of_shares)
                    cost_basis = (overall_no_of_shares)*(overall_price)
                    current_stock_value = float(order_details["filled_avg_price"])*overall_no_of_shares
                    overall_bucket_value = overall_bucket_value + current_stock_value
                    print("Overall number of shares: ", overall_no_of_shares)
                    print("Cost basis: ", cost_basis)
                    print("Overall price: ", overall_price)
                    print("Current stock value: ", current_stock_value)
                    StocksTable.update_one(
                        {"_id": stock["_id"]},
                        {
                            "$inc": {
                                "totalNoOfShares": new_no_of_shares
                            },
                            "$set": {
                                "overallPrice": overall_price,
                                "costBasis": cost_basis,
                                "lastUpdated": datetime.now(),
                                "currentValue": current_stock_value
                            },
                            "$push": {
                                "orders": {
                                    "id": response["id"],
                                    "price": float(order_details["filled_avg_price"]),
                                    "type": data["type"].lower(),
                                    "qty": new_no_of_shares,
                                    "timestamp": order_details["filled_at"],
                                }
                            }
                        }
                    )
                    # transactions.append({
                    #     "stockId": stock["_id"],
                    #     "orderId": response["id"],
                    #     "percentage": float(stock["value"])/total,
                    #     "by": "percentage",
                    #     "symbol": symbol,
                    #     "copied": False,
                    #     "type": data["type"],
                    #     "timestamp": order_details["filled_at"]
                    # })
                stocks = StocksTable.find({
                    "bucketId": ObjectId(data["bucketId"])
                })
                bucket = BucketsTable.find_one({
                    "_id": ObjectId(data["bucketId"])
                })
                # if "followers" in bucket and len(bucket["followers"]):
                #     player_ids = []
                #     bucket_ids = []
                #     for follower in bucket["followers"]:
                #         player_ids.append(follower.oneSignalId)
                #         bucket_ids.append(follower.bucketId)
                #     message = f'The owner of {bucket["name"]} bucket has just changed something!'
                #     onesignal.send_notification(player_ids, message)
                    # BucketsTable.update_many(
                    #     {"_id": {"$in": bucket_ids}},
                    #     {
                    #         "$push": {
                    #             "recentChanges": {"$each": transactions}
                    #         },
                    #         "$set": {
                    #             "hasChanged": True
                    #         }
                    #     }
                    # )
                print("Overall bucket value: ", overall_bucket_value)
                for stock in stocks:
                    StocksTable.update_one(
                        {"_id": stock["_id"]},
                        {
                            "$set": {
                                "percentWeight": (stock["currentValue"]/overall_bucket_value)*100
                            }
                        }
                    )
                    print("Percent weight: ", (current_stock_value/overall_bucket_value)*100, "\n")
                BucketsTable.update_one(
                    {"_id": ObjectId(data["bucketId"])},
                    {"$set": {"value": overall_bucket_value}}
                )
                retJson = {
                    "status": 200,
                    "message": "Bucket value modified successfully!"
                }
                return jsonify(retJson)
            else:
                retJson = {
                    "status": 500,
                    "message": "Shares can only be traded during market hours!"
                }
                return jsonify(retJson)
        except Exception as err:
            print("Error: ", err)
            retJson = {
                "status": 500,
                "message": str(err)
            }
            return jsonify(retJson)

class PlaceSingleStockAlpacaOrder(Resource):
    # @jwt_required()
    def post(self):
        try:
            if check_if_market_open(datetime.now()):
                data = request.json
                stock = StocksTable.find_one({
                    "_id": ObjectId(data["stockId"])
                })
                bucket = BucketsTable.find_one({
                    "_id": stock["bucketId"]
                })
                decrypted_token = fernet.decrypt(data["accessToken"].encode('utf-8')).decode('utf-8')
                symbol = stock["ticker"]
                amount = data["value"]
                if data["type"] == "sell" and stock["currentValue"] < float(amount):
                    retJson = {
                        "status": 500,
                        "message": "Insufficient shares, you can't sell more than the amount of shares you hold!"
                    }
                    return jsonify(retJson)
                print("Share symbol: ", symbol)
                print("Stock amount: ", amount)
                # percentage = 100
                # if bucket["value"] > 0:
                #     percentage = (float(amount)/bucket["value"])*100
                response = alpaca.place_order(decrypted_token, symbol, amount, data["type"])
                if "code" in response and response["code"] in [40110000, 40010001, 40310000]:
                    return jsonify(response)
                print("Order Response: ", response)
                order_details = alpaca.get_order_details(decrypted_token, response["id"])
                while order_details["status"] != 'filled':
                    time.sleep(10)
                    order_details = alpaca.get_order_details(decrypted_token, response["id"])
                print("Order Details: ", order_details)
                new_no_of_shares = float(order_details["filled_qty"]) if data["type"]=="buy" else -float(order_details["filled_qty"])
                overall_price = stock.get("overallPrice", 0)
                overall_no_of_shares = new_no_of_shares+stock["totalNoOfShares"]
                if data["type"] == "buy":
                    overall_price = ((stock["totalNoOfShares"]*overall_price)+(float(order_details["filled_qty"])*float(order_details["filled_avg_price"])))/(overall_no_of_shares)
                cost_basis = (overall_no_of_shares)*(overall_price)
                current_stock_value = float(order_details["filled_avg_price"])*overall_no_of_shares
                transacted_stock_value = float(order_details["filled_avg_price"])*new_no_of_shares
                print("Overall number of shares: ", overall_no_of_shares)
                print("Cost basis: ", cost_basis)
                print("Overall price: ", overall_price)
                print("Current stock value: ", transacted_stock_value)
                overall_bucket_value = transacted_stock_value + bucket["value"]
                StocksTable.update_one(
                    {"_id": stock["_id"]},
                    {
                        "$inc": {
                            "totalNoOfShares": new_no_of_shares,
                            "currentValue": transacted_stock_value,
                        },
                        "$set": {
                            "overallPrice": overall_price,
                            "costBasis": cost_basis,
                            "lastUpdated": datetime.now(),
                            "percentWeight": (current_stock_value/overall_bucket_value)*100
                        },
                        "$push": {
                            "orders": {
                                "id": response["id"],
                                "price": float(order_details["filled_avg_price"]),
                                "type": data["type"],
                                "qty": new_no_of_shares,
                                "timestamp": order_details["filled_at"],
                            }
                        }
                    }
                )
                # if "followers" in bucket and len(bucket["followers"]):
                #     player_ids = []
                #     bucket_ids = []
                #     for follower in bucket["followers"]:
                #         player_ids.append(follower["oneSignalId"])
                #         bucket_ids.append(follower["bucketId"])
                #     message = f'The owner of {bucket["name"]} bucket has just {"bought a new stock" if data["type"] == "buy" else "sold a stock"}!'
                #     onesignal.send_notification(player_ids, message)
                #     BucketsTable.update_many(
                #         {"_id": {"$in": bucket_ids}},
                #         {
                #             "$push": {
                #                 "recentChanges": {
                #                     "stockId": stock["_id"],
                #                     "orderId": response["id"],
                #                     "symbol": symbol,
                #                     "by": "percentage",
                #                     "copied": False,
                #                     "percentage": percentage,
                #                     "type": data["type"],
                #                     "timestamp": order_details["filled_at"],
                #                 }
                #             },
                #             "$set": {
                #                 "hasChanged": True
                #             }
                #         }
                #     )
                stocks = StocksTable.find({
                    "bucketId": stock["bucketId"]
                })
                final_stocks = []
                for itr_stock in stocks:
                    if itr_stock["_id"] != stock["_id"]:
                        BucketsTable.update_one(
                            {"_id": itr_stock["_id"]},
                            {"$set": {
                                "percentWeight": (itr_stock["currentValue"]/overall_bucket_value)*100
                            }}
                        )
                        final_stocks.append({
                            "id": JSONEncoder().encode(itr_stock["_id"]).replace('"', ''),
                            "name": itr_stock["name"],
                            "ticker": itr_stock["ticker"],
                            "currentValue": itr_stock["currentValue"],
                            "percentWeight": (itr_stock["currentValue"]/overall_bucket_value)*100,
                            "targetWeight": itr_stock["targetWeight"],
                            "bucketId": JSONEncoder().encode(itr_stock["bucketId"]).replace('"', ''),
                            "orders": len(itr_stock.get("orders", []))
                        })
                    elif itr_stock["_id"] == stock["_id"]:
                        final_stocks.append({
                            "id": JSONEncoder().encode(itr_stock["_id"]).replace('"', ''),
                            "name": itr_stock["name"],
                            "ticker": itr_stock["ticker"],
                            "currentValue": itr_stock["currentValue"],
                            "percentWeight": itr_stock["percentWeight"],
                            "targetWeight": itr_stock["targetWeight"],
                            "bucketId": JSONEncoder().encode(itr_stock["bucketId"]).replace('"', ''),
                            "orders": len(itr_stock.get("orders", []))
                        })
                BucketsTable.update_one(
                    {"_id": stock["bucketId"]},
                    {"$set": {"value": overall_bucket_value}}
                )
                retJson = {
                    "status": 200,
                    "stocks": final_stocks,
                    "stock_stats": {
                        "newNoOfShares": new_no_of_shares,
                        "totalPrice": overall_price,
                        "totalCost": cost_basis,
                        "percentWeight": (current_stock_value/overall_bucket_value)*100,
                        "transactedStockValue": transacted_stock_value
                    },
                    "order": {
                        "id": response["id"],
                        "price": float(order_details["filled_avg_price"]),
                        "type": data["type"],
                        "qty": new_no_of_shares,
                        "timestamp": order_details["filled_at"],
                    },
                    "overall_bucket_value": overall_bucket_value,
                    "message": f'Stock {"bought" if data["type"] == "buy" else "sold"} successfully!'
                }
                return jsonify(retJson)
            else:
                retJson = {
                    "status": 500,
                    "message": "Shares can only be traded during market hours!"
                }
                return jsonify(retJson)
        except Exception as err:
            print("Error: ", err)
            retJson = {
                "status": 500,
                "message": str(err)
            }
            return jsonify(retJson)

class SellAllSharesInBucket(Resource):
    @jwt_required()
    def post(self):
        try:
            if check_if_market_open(datetime.now()):
                data = request.json
                stocks = StocksTable.find({
                    "bucketId": ObjectId(data["bucketId"])
                })
                decrypted_token = fernet.decrypt(data["accessToken"].encode('utf-8')).decode('utf-8')
                for stock in stocks:
                    symbol = stock["description"][0:stock["description"].index(':')]
                    amount = stock["totalNoOfShares"]
                    response = alpaca.place_order(decrypted_token, symbol, amount, "sell", order="by_quantity")
                    if "code" in response and response["code"] in [40110000, 40010001, 40310000]:
                        return jsonify(response)
                    print("\n\nResponse: ", response, "\n\n")
                    order_details = alpaca.get_order_details(decrypted_token, response["id"])
                    while order_details["status"] != 'filled':
                        order_details = alpaca.get_order_details(decrypted_token, response["id"])
                    print("\n\nOrder Details: ", order_details, "\n\n")
                    StocksTable.update_one(
                        {"_id": stock["_id"]},
                        {
                            "$set": {
                                "totalNoOfShares": 0,
                                "costBasis": 0,
                                "lastUpdated": datetime.now(),
                                "percentWeight": stock["initialWeight"],
                                "currentValue": 0
                            },
                            "$push": {
                                "orders": {
                                    "id": response["id"],
                                    "price": float(order_details["filled_avg_price"]),
                                    "type": "sell",
                                    "qty": -stock["totalNoOfShares"],
                                    "timestamp": order_details["filled_at"],
                                }
                            }
                        }
                    )
                BucketsTable.update_one(
                    {"_id": ObjectId(data["bucketId"])},
                    {"$set": {"value": 0}}
                )
                retJson = {
                    "status": 200,
                    "message": "Sold all of the bucket's stocks successfully!"
                }
                return jsonify(retJson)
            else:
                retJson = {
                    "status": 500,
                    "message": "Shares can only be sold during market hours!"
                }
                return jsonify(retJson)
        except Exception as err:
            print("Error: ", err)
            retJson = {
                "status": 500,
                "message": str(err)
            }
            return jsonify(retJson)

class ExecuteCopiedTrades(Resource):
    @jwt_required()
    def post(self):
        try:
            if check_if_market_open(datetime.now()):
                data = request.json
                decrypted_token = fernet.decrypt(data["accessToken"].encode('utf-8')).decode('utf-8')
                transactions = []
                overall_bucket_value = 0
                bucket = BucketsTable.find_one({
                    "_id": ObjectId(data["bucketId"])
                })
                stocks = []
                cursor = StocksTable.find({
                    "bucketId": ObjectId(data["bucketId"])
                })
                bucket_stock_symbols = []
                for stock in cursor:
                    bucket_stock_symbols.append(stock["description"][0:stock["description"].index(':')])
                    stocks.append(stock)
                orders = [order for order in bucket["recentChanges"] if order["orderId"] in data["orderIds"]]
                for order in orders:
                    if order["symbol"] in bucket_stock_symbols:
                        response = None
                        stock = list(filter(lambda s: s["description"][0:s["description"].index(':')]==order["symbol"], stocks))[0]
                        # if order["by"] == "amount":
                        #     response = alpaca.place_order(decrypted_token, order["symbol"], order["amount"], order["type"])
                        # else:
                        amount = (bucket["value"]/100)*order["percentage"]
                        response = alpaca.place_order(decrypted_token, order["symbol"], amount, order["type"])
                        if "code" in response and response["code"] in [40110000, 40010001, 40310000]:
                            return jsonify(response)
                        print("Order Response: ", response)
                        order_details = alpaca.get_order_details(decrypted_token, response["id"])
                        while order_details["status"] != 'filled':
                            order_details = alpaca.get_order_details(decrypted_token, response["id"])
                        print("Order Details: ", order_details)
                        new_no_of_shares = float(order_details["filled_qty"]) if order["type"]=="buy" else -float(order_details["filled_qty"])
                        overall_price = stock.get("overallPrice", 0)
                        overall_no_of_shares = new_no_of_shares+stock["totalNoOfShares"]
                        if order["type"] == "buy":
                            overall_price = ((stock["totalNoOfShares"]*overall_price)+(float(order_details["filled_qty"])*float(order_details["filled_avg_price"])))/(overall_no_of_shares)
                        cost_basis = (overall_no_of_shares)*(overall_price)
                        current_stock_value = float(order_details["filled_avg_price"])*overall_no_of_shares
                        transacted_stock_value = float(order_details["filled_avg_price"])*new_no_of_shares
                        print("Overall number of shares: ", overall_no_of_shares)
                        print("Cost basis: ", cost_basis)
                        print("Overall price: ", overall_price)
                        print("Current stock value: ", transacted_stock_value)
                        overall_bucket_value = transacted_stock_value + bucket["value"]
                        StocksTable.update_one(
                            {"_id": stock["_id"]},
                            {
                                "$inc": {
                                    "totalNoOfShares": new_no_of_shares
                                },
                                "$set": {
                                    "overallPrice": overall_price,
                                    "costBasis": cost_basis,
                                    "lastUpdated": datetime.now(),
                                    "currentValue": current_stock_value
                                },
                                "$push": {
                                    "orders": {
                                        "id": response["id"],
                                        "price": float(order_details["filled_avg_price"]),
                                        "type": order["type"],
                                        "qty": new_no_of_shares,
                                        "timestamp": order_details["filled_at"],
                                    }
                                }
                            }
                        )
                        transactions.append({
                            "stockId": stock["_id"],
                            "orderId": response["id"],
                            "percentage": order["percentage"],
                            "by": "percentage",
                            "symbol": order["symbol"],
                            "copied": False,
                            "type": order["type"],
                            "timestamp": order_details["filled_at"]
                        })
                BucketsTable.update_many(
                    {"_id": ObjectId(data["bucketId"])},
                    {
                        "$set": {
                            "recentChanges.$[element].copied": True
                        }
                    },
                    upsert=False,
                    array_filters=[{"element.orderId": {"$in": data["orderIds"]}}],
                )
                stocks = StocksTable.find({
                    "bucketId": ObjectId(data["bucketId"])
                })
                if "followers" in bucket and len(bucket["followers"]):
                    player_ids = []
                    bucket_ids = []
                    for follower in bucket["followers"]:
                        player_ids.append(follower.oneSignalId)
                        bucket_ids.append(follower.bucketId)
                    message = f'The owner of {bucket["name"]} bucket has just changed something!'
                    onesignal.send_notification(player_ids, message)
                    BucketsTable.update_many(
                        {"_id": {"$in": bucket_ids}},
                        {
                            "$push": {
                                "recentChanges": {"$each": transactions}
                            },
                            "$set": {
                                "hasChanged": True
                            }
                        }
                    )
                print("Overall bucket value: ", overall_bucket_value)
                for stock in stocks:
                    StocksTable.update_one(
                        {"_id": stock["_id"]},
                        {
                            "$set": {
                                "percentWeight": (stock["currentValue"]/overall_bucket_value)*100
                            }
                        }
                    )
                BucketsTable.update_one(
                    {"_id": ObjectId(data["bucketId"])},
                    {"$set": {"value": overall_bucket_value}}
                )
                retJson = {
                    "status": 200,
                    "message": "Copied transactions executed successfully!"
                }
                return jsonify(retJson)
            else:
                retJson = {
                    "status": 500,
                    "message": "Copied trades can only be executed during market hours!"
                }
                return jsonify(retJson)
        except Exception as err:
            print("Error: ", err)
            retJson = {
                "status": 500,
                "message": str(err)
            }
            return jsonify(retJson)

class LogoutFromAlpacaAccount(Resource):
    @jwt_required()
    def get(self):
        try:

            update_response = UsersTable.update_one(
                {"_id": ObjectId(get_jwt_identity())},
                {"$set": {
                    "alpacaAccessToken": None,
                    "isAlpacaAuthorized": False
                }}
            )
            if update_response.modified_count > 0:
                retJson = {
                    "status": 200,
                    "message": "Successfully logged out from alpaca account!"
                }
                return jsonify(retJson)
            else:
                retJson = {
                    "status": 500,
                    "message": "An error occuring while logging out from alpaca account!"
                }
                return jsonify(retJson)
        except Exception as err:
            print("Error: ", err)
            retJson = {
                "status": 500,
                "message": str(err)
            }
            return jsonify(retJson)

class LinkRobinhoodAccount(Resource):
    @jwt_required()
    def post(self):
        try:
            data = request.json
            response = robin_stocks.robinhood.authentication.login(username=data["username"], password=data["password"])
            if 'otp_essential_data' in response:
                return response
            else:
                retJson = {
                    "status": 200,
                    "response": response,
                    "message": "Robinhood account is successfully linked!"
                }
                return jsonify(retJson)
        except Exception as err:
            print("Error: ", err)
            retJson = {
                "status": 500,
                "message": str(err)
            }
            return jsonify(retJson)

class VerifyOtp(Resource):
    def post(self):
        try:
            data = request.json
            print(data)
            response = robin_stocks.robinhood.authentication.verify_otp(data["username"], data["password"], data["challenge_id"], data["device_token"], data["otp"])
            return response
        except Exception as err:
            print("Error: ", err)
            retJson = {
                "status": 500,
                "message": str(err)
            }
            return jsonify(retJson)

class LogoutFromRobinhoodAccount(Resource):
    @jwt_required()
    def get(self):
        try:
            response = robin_stocks.robinhood.authentication.logout()
            return response
        except Exception as err:
            print("Error: ", err)
            retJson = {
                "status": 500,
                "message": str(err)
            }
            return jsonify(retJson)

class GetUserBuckets(Resource):
    @jwt_required()
    def get(self):
        try:
            user_id = get_jwt_identity()
            cursor = BucketsTable.find({"userId": ObjectId(user_id)})
            buckets = []
            for bucket in cursor:
                current_market_value, percent_return = polygon.get_current_stats_of_bucket(bucket["_id"])
                if bucket["value"] != current_market_value:
                    BucketsTable.update_one(
                        {"_id": bucket["_id"]},
                        {"$set": {
                            "value": current_market_value,
                            "percentReturn": percent_return
                        }}
                    )
                new_bucket = {
                    "id": JSONEncoder().encode(bucket["_id"]).replace('"', ''),
                    "name": bucket["name"],
                    "description": bucket["description"],
                    "createdAt": bucket["createdAt"],
                    "rebalanceFrequency": bucket["rebalanceFrequency"],
                    "value": current_market_value,
                    "percentReturn": percent_return,
                    "userId": JSONEncoder().encode(bucket["userId"]).replace('"', '')
                }
                if "originalBucketId" in bucket:
                    new_bucket["originalBucketId"] = JSONEncoder().encode(bucket["originalBucketId"]).replace('"', '')
                if "hasChanged" in bucket:
                    new_bucket["hasChanged"] = bucket["hasChanged"]
                buckets.append(new_bucket)
            retJson = {
                "status": 200,
                "buckets": sorted(buckets, key=lambda x: x["value"], reverse=True)
            }
            return jsonify(retJson)
        except Exception as err:
            print("Error: ", err)
            retJson = {
                "status": 500,
                "message": str(err)
            }
            return jsonify(retJson)

class GetBucketData(Resource):
    @jwt_required()
    def post(self):
        try:
            data = request.json
            bucket = BucketsTable.find_one({"_id": ObjectId(data["bucketId"])})
            if bucket is None:
                retJson = {
                    "status": 404,
                    "message": "Could not find specified bucket!"
                }
                return jsonify(retJson)
            cursor = StocksTable.find({"bucketId": ObjectId(data["bucketId"])})
            stocks = []
            for stock in cursor:
                stocks.append({
                    "id": JSONEncoder().encode(stock["_id"]).replace('"', ''),
                    "description": stock["description"],
                    "value": bucket["sumOfStockValues"]*(stock["percentWeight"]/100),
                    "percentWeight": stock["percentWeight"],
                    "initialWeight": stock["initialWeight"],
                    "bucketId": JSONEncoder().encode(stock["bucketId"]).replace('"', ''),
                    "orders": len(stock.get("orders", []))
                })
            print("Bucket Stocks: ", stocks);
            retJson = {
                "status": 200,
                "bucket_data": {
                    "id": JSONEncoder().encode(bucket["_id"]).replace('"', ''),
                    "name": bucket["name"],
                    "description": bucket["description"],
                    "rebalanceFrequency": bucket["rebalanceFrequency"],
                    "userId": JSONEncoder().encode(bucket["userId"]).replace('"', ''),
                    "value": bucket["value"],
                    "followers": [],
                    "createdAt": bucket["createdAt"],
                    "stocks": stocks
                }
            }
            if "originalBucketId" in bucket:
                retJson["bucket_data"]["originalBucketId"] = JSONEncoder().encode(bucket["originalBucketId"]).replace('"', '')
            if "followers" in bucket:
                followers = []
                for follower in bucket["followers"]:
                    followers.append({
                        "bucketId": JSONEncoder().encode(follower["bucketId"]).replace('"', ''),
                        "userId": JSONEncoder().encode(follower["userId"]).replace('"', ''),
                        "oneSignalId": follower["oneSignalId"]
                    })
                retJson["bucket_data"]["followers"] = followers
            return jsonify(retJson)
        except Exception as err:
            print("Error: ", err)
            retJson = {
                "status": 500,
                "message": str(err)
            }
            return jsonify(retJson)

class GetRecentBucketChanges(Resource):
    @jwt_required()
    def post(self):
        try:
            data = request.json
            bucket = BucketsTable.find_one({"_id": ObjectId(data["bucketId"])})
            stocks = StocksTable.find({"bucketId": ObjectId(data["bucketId"])})
            stocks = [stock for stock in stocks]
            recent_changes = []
            for order in bucket["recentChanges"]:
                stock = list(filter(lambda s: s["description"][0:s["description"].index(':')]==order["symbol"], stocks))[0]
                bucket_changes = {
                    "stockId": JSONEncoder().encode(order["stockId"]).replace('"', ''),
                    "orderId": JSONEncoder().encode(order["orderId"]).replace('"', ''),
                    "by": order["by"],
                    "type": order["type"],
                    "copied": order["copied"],
                    "percentage": order["percentage"],
                    "currentStockValue": stock["currentValue"],
                    "amount": ((bucket["value"] if bucket["value"] > 0 else order["percentage"])/100)*order["percentage"],
                    "symbol": order["symbol"],
                    "timestamp": order["timestamp"],
                }
                recent_changes.append(bucket_changes)
            retJson = {
                "status": 200,
                "bucket_changes": sorted(recent_changes, key=lambda x: x["timestamp"], reverse=True),
                "message": "Fetched recent bucket changes successfully!"
            }
            return jsonify(retJson)
        except Exception as err:
            print("Error: ", err)
            retJson = {
                "status": 500,
                "message": str(err)
            }
            return jsonify(retJson)

class FollowBucket(Resource):
    @jwt_required()
    def post(self):
        try:
            data = request.json
            user_id = get_jwt_identity()
            user = UsersTable.find_one({"_id": ObjectId(user_id)})
            bucket_to_follow = BucketsTable.find_one({"_id": ObjectId(data["bucketId"])})
            new_bucket = {
                "name": bucket_to_follow["name"],
                "description": bucket_to_follow["description"],
                "userId": ObjectId(user_id),
                "originalBucketId": ObjectId(data["bucketId"]),
                "createdAt": datetime.now(),
                "hasChanged": False,
                "recentChanges": [],
                "sumOfStockValues": bucket_to_follow["sumOfStockValues"],
                "rebalanceFrequency": bucket_to_follow["rebalanceFrequency"],
                "percentReturn": 0,
                "value": 0
            }
            bucket_create_result = BucketsTable.insert_one(new_bucket)
            new_bucket["id"] = JSONEncoder().encode(bucket_create_result.inserted_id).replace('"', '')
            cursor = StocksTable.find({"bucketId": ObjectId(data["bucketId"])})
            for stock in cursor:
                new_stock = {
                    "description": stock["description"],
                    "value": float(stock["value"]),
                    "bucketId": bucket_create_result.inserted_id,
                    "lastUpdated": datetime.now(),
                    "totalNoOfShares": 0,
                    "percentWeight": 0,
                    "initialWeight": float(stock["initialWeight"]),
                    "currentValue": 0,
                    "overallPrice": 0,
                    "latestPrice": 0,
                    "costBasis": 0
                }
                StocksTable.insert_one(new_stock)
            BucketsTable.update_one(
                {"_id": ObjectId(data["bucketId"])},
                {
                    "$push": {
                        "followers": {
                            "userId": ObjectId(user_id),
                            "oneSignalId": user["oneSignalId"],
                            "bucketId": bucket_create_result.inserted_id
                        }
                    }
                }
            )
            retJson = {
                "status": 200,
                "bucket": {
                    "id": new_bucket["id"],
                    "name": new_bucket["name"],
                    "description": new_bucket["description"],
                    "rebalanceFrequency": new_bucket["rebalanceFrequency"],
                    "originalBucketId": data["bucketId"],
                    "hasChanged": new_bucket["hasChanged"],
                    "recentChanges": new_bucket["recentChanges"],
                    "userId": user_id,
                    "percentReturn": new_bucket["percentReturn"],
                    "value": new_bucket["value"],
                    "createdAt": new_bucket["createdAt"]
                },
                "message": "Bucket followed successfully!"
            }
            return jsonify(retJson)
        except Exception as err:
            print("Error: ", err)
            retJson = {
                "status": 500,
                "message": str(err)
            }
            return jsonify(retJson)

class UnFollowBucket(Resource):
    @jwt_required()
    def post(self):
        try:
            data = request.json
            bucket_id = None
            user_id = get_jwt_identity()
            if "bucketId" in data:
                bucket_id = ObjectId(data["bucketId"])
            else:
                followed_bucket = BucketsTable.find_one({"_id": ObjectId(data["followedBucketId"])})
                bucket_id = list(filter(lambda follower: follower["userId"]==ObjectId(user_id), followed_bucket["followers"]))[0]["bucketId"]
            res = BucketsTable.update_one(
                {"_id": bucket_id},
                {
                    "$unset": {
                        "originalBucketId": 1,
                        "hasChanged": 1,
                        "recentChanges": 1,
                    }
                }
            )
            if res.modified_count == 0:
                retJson = {
                    "status": 500,
                    "message": "An error occurred while un-following bucket!"
                }
                return jsonify(retJson)
            res = BucketsTable.update_one(
                {"_id": ObjectId(data["followedBucketId"])},
                {
                    "$pull": {
                        "followers": {
                            "userId": ObjectId(user_id),
                            "bucketId": bucket_id
                        }
                    }
                }
            )
            if res.modified_count == 0:
                BucketsTable.update_one(
                    {"_id": bucket_id},
                    {
                        "$set": {"originalBucketId": ObjectId(data["followedBucketId"])}
                    }
                )
                retJson = {
                    "status": 500,
                    "message": "An error occurred while un-following bucket!"
                }
                return jsonify(retJson)
            retJson = {
                "status": 200,
                "message": "Bucket un-followed successfully!"
            }
            return jsonify(retJson)
        except Exception as err:
            print("Error: ", err)
            retJson = {
                "status": 500,
                "message": str(err)
            }
            return jsonify(retJson)

class GetStockStats(Resource):
    @jwt_required()
    def post(self):
        try:
            data = request.json
            stock = StocksTable.find_one({"_id": ObjectId(data["stockId"])})
            orders = []
            if 'orders' in stock:
                orders = sorted(stock["orders"], key=lambda x: x["timestamp"], reverse=True)
            retJson = {
                "status": 200,
                "stock_stats": {
                    "totalShares": stock["totalNoOfShares"],
                    "totalPrice": stock["overallPrice"],
                    "totalCost": stock["costBasis"],
                    "percentWeight": stock["percentWeight"],
                    "currentValue": stock["currentValue"],
                    "orders": orders
                }
            }
            return jsonify(retJson)
        except Exception as err:
            print("Error: ", err)
            retJson = {
                "status": 500,
                "message": str(err)
            }
            return jsonify(retJson)

class ToggleBucketVisibility(Resource):
    @jwt_required()
    def post(self):
        try:
            data = request.json
            response = BucketsTable.update_one(
                {"_id": ObjectId(data["bucketId"])},
                {"$set": {"isPublic": data["visibility"]}}
            )
            if response.modified_count > 0:
                retJson = {
                    "status": 200,
                    "message": "Bucket's visibility updated successfully!"
                }
                return jsonify(retJson)
            else:
                retJson = {
                    "status": 200,
                    "message": "Could not update bucket's visibility!"
                }
                return jsonify(retJson)
        except Exception as err:
            print("Error: ", err)
            retJson = {
                "status": 500,
                "message": str(err)
            }
            return jsonify(retJson)

class GetBucketStats(Resource):
    @jwt_required()
    def post(self):
        try:
            data = request.json
            stocks = StocksTable.find({"bucketId": ObjectId(data["bucketId"])})
            assets = []
            weights = []
            for stock in stocks:
                assets.append(stock["description"][0:stock["description"].index(':')])
                weights.append(stock["percentWeight"]/100)
            bucket_stats = pyportfolio.get_stats(assets, weights)
            retJson = {
                "status": 200,
                "bucket_stats": bucket_stats
            }
            return jsonify(retJson)
        except Exception as err:
            print("Error: ", err)
            retJson = {
                "status": 500,
                "message": str(err)
            }
            return jsonify(retJson)

class CreateBucket(Resource):
    @jwt_required()
    def post(self):
        try:
            data = request.json
            user_id = get_jwt_identity()
            stocks = copy.deepcopy(data["stocks"])
            sum_of_stock_values = reduce(lambda x, y: x + float(y['value']), stocks, 0)
            if sum_of_stock_values == 0:
                retJson = {
                    "status": 500,
                    "message": "Stock weights shall be non-zero!"
                }
                return jsonify(retJson)
            result = BucketsTable.insert_one({
                "name": data["bucketName"],
                "description": data["bucketDescription"],
                "userId": ObjectId(user_id),
                "createdAt": datetime.now(),
                "sumOfStockValues": sum_of_stock_values,
                "rebalanceFrequency": "",
                "percentReturn": 0,
                "value": 0,
            })
            for stock in data["stocks"]:
                res = StocksTable.insert_one({
                    "description": stock["description"],
                    "value": float(stock["value"]),
                    "bucketId": ObjectId(result.inserted_id),
                    "lastUpdated": datetime.now(),
                    "totalNoOfShares": 0,
                    "percentWeight": (float(stock["value"])/sum_of_stock_values)*100,
                    "initialWeight": (float(stock["value"])/sum_of_stock_values)*100,
                    "currentValue": 0,
                    "overallPrice": 0,
                    "latestPrice": 0,
                    "costBasis": 0
                })
                stock["id"] = JSONEncoder().encode(res.inserted_id).replace('"', '')
                stock["bucketId"] = JSONEncoder().encode(result.inserted_id).replace('"', '')
                stock["percentWeight"] = (float(stock["value"])/sum_of_stock_values)*100
            retJson = {
                "status": 200,
                "bucketId": JSONEncoder().encode(result.inserted_id).replace('"', ''),
                "stocks": data["stocks"],
                "message": "Bucket created successfully!"
            }
            return jsonify(retJson)
        except Exception as err:
            print("Error: ", err)
            retJson = {
                "status": 500,
                "message": str(err)
            }
            return jsonify(retJson)

class DeleteBucketStock(Resource):
    @jwt_required()
    def post(self):
        try:
            data = request.json
            stock = StocksTable.find_one({
                "_id": ObjectId(data["stockId"])
            })
            if stock.get("orders", False) and len(stock["orders"])>0:
                retJson = {
                    "status": 500,
                    "message": "You cannot delete this item!"
                }
                return jsonify(retJson)
            result = StocksTable.delete_one({
                "_id": ObjectId(data["stockId"])
            })
            if result.acknowledged:
                retJson = {
                    "status": 200,
                    "message": "Bucket stock deleted successfully!"
                }
                return jsonify(retJson)
            else:
                retJson = {
                    "status": 500,
                    "message": "An error occurred while deleting bucket stock!"
                }
                return jsonify(retJson)
        except Exception as err:
            print("Error: ", err)
            retJson = {
                "status": 500,
                "message": str(err)
            }
            return jsonify(retJson)

class UpdateBucket(Resource):
    @jwt_required()
    def post(self):
        try:
            data = request.json
            bucket = None
            updated_stocks = []
            if data.get("stocks", False):
                stocks = copy.deepcopy(data["stocks"])
                total = reduce(lambda x, y: x + float(y['value']), stocks, 0)
                bucket = BucketsTable.find_one({"_id": ObjectId(data["id"])})
                for stock in data["stocks"]:
                    if "id" in stock:
                        print("updating old stock......")
                        StocksTable.update_one(
                            {"_id": ObjectId(stock["id"])},
                            {
                                "$set": {
                                    "description": stock["description"],
                                    "initialWeight": (float(stock["value"])/total)*100,
                                }
                            }
                        )
                        stock["initialWeight"] = (float(stock["value"])/total)*100
                        updated_stocks.append(stock)
                    else:
                        print("inserting new stock......")
                        res = StocksTable.insert_one({
                            "description": stock["description"],
                            "value": float(stock["value"]),
                            "bucketId": ObjectId(data["id"]),
                            "initialWeight": (float(stock["value"])/total)*100,
                            "percentWeight": 0,
                            "overallPrice": 0,
                            "costBasis": 0,
                            "lastUpdated": datetime.now(),
                            "latestPrice": 0,
                            "totalNoOfShares": 0,
                            "currentValue": 0
                        })
                        stock["id"] = JSONEncoder().encode(res.inserted_id).replace('"', '')
                        stock["percentWeight"] = 0
                        stock["initialWeight"] = (float(stock["value"])/total)*100
                        stock["orders"] = 0
                        updated_stocks.append(stock)
            # *************************************************************************
            # We are going to enable the rebalance scheduling feature in future version
            # *************************************************************************
            # if "rebalanceFrequency" in data:
            #     schedule_bucket_rebalance(data["id"], data["rebalanceFrequency"], data.get("accessToken", None))
            #     BucketsTable.update_one(
            #         {"_id": ObjectId(data["id"])},
            #         {"$set": {"rebalanceFrequency": data["rebalanceFrequency"]}}
            #     )
            BucketsTable.update_one(
                {"_id": ObjectId(data["id"])},
                {"$set": {
                    "name": data["bucketName"],
                    "description": data["bucketDescription"]
                }}
            )
            retJson = {
                "status": 200,
                "message": "Bucket data has been updated successfully!"
            }
            if "stocks" in data:
                retJson["stocks"] = updated_stocks
            return jsonify(retJson)
        except Exception as err:
            print("Error: ", err)
            retJson = {
                "status": 500,
                "message": str(err)
            }
            return jsonify(retJson)

# **************************************************************************************************
# We are going to remove this view when we enable the rebalance scheduling feature in future version
# **************************************************************************************************
class RebalanceBucket(Resource):
    @jwt_required()
    def post(self):
        try:
            if check_if_market_open(datetime.now()):
                data = request.json
                response = rebalance_bucket_to_initial_weights(data["bucketId"], data["accessToken"])
                if response["success"]:
                    retJson = {
                        "status": 200,
                        "message": response["message"]
                    }
                    return jsonify(retJson)
                else:
                    retJson = {
                        "status": 500,
                        "message": response["message"]
                    }
                    return jsonify(retJson)
            else:
                retJson = {
                    "status": 500,
                    "message": "Bucket rebalancing can only be performed during market hours!"
                }
                return jsonify(retJson)
        except Exception as err:
            print("Error: ", err)
            retJson = {
                "status": 500,
                "message": str(err)
            }
            return jsonify(retJson)