from config import mail, scheduler, fernet
from flask_mail import Message
from bson import ObjectId
from datetime import datetime, timedelta
import json, random, math, alpaca, copy, os, pytz
from db import db
from functools import reduce
from flask import render_template

holidays_2021 = [datetime(2021, 1, 1), datetime(2021, 1, 18), datetime(2021, 2, 15), datetime(2021, 4, 2), datetime(2021, 5, 31), datetime(2021, 7, 5), datetime(2021, 9, 6), datetime(2021, 11, 25), datetime(2021, 12, 24)]
holidays_2022 = [datetime(2022, 1, 17), datetime(2022, 2, 21), datetime(2022, 4, 15), datetime(2022, 5, 30), datetime(2022, 6, 4), datetime(2022, 9, 5), datetime(2022, 11, 24), datetime(2022, 12, 26)]

BucketsTable = db["buckets"]
ScheduledJobsTable = db["scheduled_jobs"]
StocksTable = db["stocks"]

class JSONEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, ObjectId):
            return str(o)
        elif isinstance(o, datetime):
            return o.isoformat()
        return json.JSONEncoder.default(self, o)

def send_email(title, message, recipient):
    try:
        msg = Message(title, sender = os.environ.get('MAIL_USERNAME'), recipients = [recipient])
        msg.body = message
        mail.send(msg)
        return True
    except Exception as err:
        print("Error: ", err)
        return False

def send_verification_email(email_verification_link, username, recipient):
    try:
        msg = Message(f"Hi {username}, welcome to buckets", sender=os.environ.get('MAIL_USERNAME'), recipients=[recipient])
        msg.body = render_template("email_templates/verify_email.html", email_verification_link=email_verification_link, username=username)
        msg.html = render_template("email_templates/verify_email.html", email_verification_link=email_verification_link, username=username)
        mail.send(msg)
        return True
    except Exception as err:
        print("Error: ", err)
        return False

def send_email_verification_otp(otp, username, recipient):
    try:
        msg = Message(f"Hi {username}, welcome to buckets", sender=os.environ.get('MAIL_USERNAME'), recipients=[recipient])
        msg.body = render_template("email_templates/verify_email_otp.html", otp=otp, username=username)
        msg.html = render_template("email_templates/verify_email_otp.html", otp=otp, username=username)
        mail.send(msg)
        return True
    except Exception as err:
        print("Error: ", err)
        return False

def generate_otp(length=6):
    digits = [i for i in range(0, 10)]
    random_str = ""
    for i in range(length):
        index = math.floor(random.random() * 10)
        random_str += str(digits[index])
    return random_str

def check_if_market_open(date):
    # print("\n Raw Date: ", date)
    # date = datetime(date.year, date.month, date.day)
    # print("Modified Date: ", date)
    nyc_datetime = datetime.now(pytz.timezone('US/Eastern'))
    # print("NYC Date Time Raw: ", nyc_datetime)
    hrs = nyc_datetime.hour
    mins = nyc_datetime.minute + (nyc_datetime.second/60)
    nyc_datetime = datetime(nyc_datetime.year, nyc_datetime.month, nyc_datetime.day)
    # print("NYC Date Time Modified: ", nyc_datetime)
    print("NYC Date Time Hours:Mins ", hrs, ":", mins)
    try:
        if nyc_datetime.weekday() < 5:
            if nyc_datetime in holidays_2021 or nyc_datetime in holidays_2022:
                return False
            elif (hrs==9 and mins>=30) or (hrs>=10 and hrs<16 and mins<=60):
                return True
            else:
                return False
        else:
            return False
    except Exception as err:
        print("Error: ", err)
        return False

def schedule_bucket_rebalance(bucket_id, rebalance_frequency, access_token):
    if rebalance_frequency in ["monthly", "quarterly", "yearly"]:
        date = None
        is_market_open = False
        if rebalance_frequency == "monthly":
            date = datetime.now()+timedelta(days=30)
        elif rebalance_frequency == "quarterly":
            date = datetime.now()+timedelta(days=120)
        else:
            date = datetime.now()+timedelta(days=365)
        while not is_market_open:
            is_market_open = alpaca.check_if_market_open(date)
            if is_market_open:
                break
            else:
                date = date+timedelta(days=1)
        print("\n\nScheduling rebalancing on ", date, "\n\n")
        scheduler.add_job(id=bucket_id, func=rebalance_bucket_to_initial_weights, args=[bucket_id, rebalance_frequency, access_token], trigger='date', run_date=date, replace_existing=True)
    else:
        print("Removing scheduled rebalancing job...")
        scheduler.remove_job(bucket_id)

# **************************************************************************************
# We are going to enable the rebalance scheduling feature by frequency in future version
# **************************************************************************************
# def rebalance_bucket_to_initial_weights(bucket_id, rebalance_frequency, access_token):
def rebalance_bucket_to_initial_weights(bucket_id, access_token):
    try:
        bucket = BucketsTable.find_one({
            "_id": ObjectId(bucket_id)
        })
        res = StocksTable.find({
            "bucketId": ObjectId(bucket_id)
        })
        stocks = copy.deepcopy(res)
        total = reduce(lambda x, y: x + float(y['value']), res, 0)
        type = "buy"
        for stock in stocks:
            percentage = float((stock["initialWeight"]/100)-(stock["percentWeight"]/100))
            amount = round(percentage*bucket["value"], 2)
            if amount==0:
                continue
            elif amount<0:
                type = "sell"
            if type == "sell" and stock["currentValue"] < abs(amount):
                response = {
                    "success": False,
                    "message": "Insufficient shares, you can't sell more than the amount of shares you hold!"
                }
                return response
        overall_bucket_value = 0
        decrypted_token = fernet.decrypt(access_token.encode('utf-8')).decode('utf-8')
        for stock in stocks:
            symbol = stock["description"][0:stock["description"].index(':')]
            percentage = float((stock["initialWeight"]/100)-(stock["percentWeight"]/100))
            amount = round(percentage*bucket["value"], 2)
            type = "buy"
            if amount==0:
                continue
            elif amount<0:
                type = "sell"
            print("\n", symbol, abs(amount), type, "\n")
            response = alpaca.place_order(decrypted_token, symbol, abs(amount), type)
            if "code" in response and response["code"] in [40110000, 40010001, 40310000]:
                print("Rebalance Order Response: ", response)
                response = {
                    "success": False,
                    "message": f"{response['symbol']}: {response['message']}"
                }
                return response
            order_details = alpaca.get_order_details(decrypted_token, response["id"])
            while order_details["status"] != 'filled':
                order_details = alpaca.get_order_details(decrypted_token, response["id"])
            new_no_of_shares = float(order_details["filled_qty"]) if type=="buy" else -float(order_details["filled_qty"])
            overall_price = stock.get("overallPrice", 0)
            overall_no_of_shares = new_no_of_shares+stock["totalNoOfShares"]
            if type == "buy":
                overall_price = ((stock["totalNoOfShares"]*overall_price)+(float(order_details["filled_qty"])*float(order_details["filled_avg_price"])))/(overall_no_of_shares)
            cost_basis = (overall_no_of_shares)*(overall_price)
            current_stock_value = float(order_details["filled_avg_price"])*overall_no_of_shares
            overall_bucket_value = overall_bucket_value + current_stock_value
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
                            "type": type,
                            "qty": new_no_of_shares,
                            "timestamp": order_details["filled_at"],
                        }
                    }
                }
            )
        stocks = StocksTable.find({
            "bucketId": ObjectId(bucket_id)
        })
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
            {"_id": ObjectId(bucket_id)},
            {"$set": {"value": overall_bucket_value}}
        )
        response = {
            "success": True,
            "message": "Bucket rebalanced to initial weights successfully!"
        }
        return response
        # *************************************************************************
        # We are going to enable the rebalance scheduling feature in future version
        # *************************************************************************
        # schedule_bucket_rebalance(bucket_id, rebalance_frequency, access_token)
    except Exception as err:
        print("Error: ", err)
        response = {
            "success": False,
            "message": str(err)
        }
        return response