from flask_restful import Resource, reqparse
from flask import jsonify, request
from utilities import send_email, send_verification_email, send_email_verification_otp, JSONEncoder, generate_otp
from werkzeug.security import safe_str_cmp
from flask_jwt_extended import jwt_required, create_access_token, get_jwt_identity
import json, uuid, bcrypt
from bson import ObjectId
from config import jwt
from db import db

BucketsTable = db["buckets"]
UsersTable = db["users"]

@jwt.user_lookup_loader
def user_lookup_callback(_jwt_header, jwt_data):
    identity = jwt_data["sub"]
    user = UsersTable.find({"_id": ObjectId(identity)})
    return user

class FetchUser(Resource):
    @jwt_required()
    def get(self):
        try:
            id = get_jwt_identity()
            user = UsersTable.find_one({"_id": ObjectId(id)})
            UsersTable.update_one(
                {"_id": ObjectId(id)},
                {
                    "$inc": {
                        "noOfSessions": 1
                    }
                }
            )
            access_token = user.get('alpacaAccessToken', None)
            retJson = {
                "status": 200,
                "user": {
                    "id": id,
                    "firstName": user["firstName"],
                    "lastName": user["lastName"],
                    "email": user["email"],
                },
                "alpaca": {
                    "access_token": access_token if access_token is None else access_token.decode('utf-8')
                }
            }
            if "oneSignalId" in user:
                retJson["user"]["oneSignalId"] = user["oneSignalId"]
            return jsonify(retJson)
        except Exception as err:
            print("Error: ", err)
            retJson = {
                "status": 500,
                "message": str(err)
            }
            return jsonify(retJson)

class RegisterUser(Resource):
    def post(self):
        try:
            data = request.json
            user_already_exist = UsersTable.find_one({"email": data["email"]})
            if user_already_exist:
                retJson = {
                    "status": 500,
                    "message": "User with the given email already exists!"
                }
                return jsonify(retJson)
            unique_id = str(uuid.uuid4())
            email_verification_link = f"https://buckets-server.herokuapp.com/verify-email/{unique_id}"
            username = f"{data['firstName']} {data['lastName']}"
            op_successfull = send_verification_email(email_verification_link, username ,data["email"])
            if op_successfull:
                hashed_password = bcrypt.hashpw(data["password"].encode('utf-8'), bcrypt.gensalt())
                UsersTable.insert_one({
                    "firstName": data["firstName"],
                    "lastName": data["lastName"],
                    "email": data["email"],
                    "uuid": unique_id,
                    "verified": False,
                    "password": hashed_password
                })
                retJson = {
                    "status": 200,
                    "message": "An email verification link is sent on your email address!"
                }
                return jsonify(retJson)
            else:
                retJson = {
                    "status": 500,
                    "message": "Could not send email verification link on given email address!"
                }
                return jsonify(retJson)
        except Exception as err:
            print("Error: ", err)
            retJson = {
                "status": 500,
                "message": str(err)
            }
            return jsonify(retJson)

class RegisterUserWithOTP(Resource):
    def post(self):
        try:
            data = request.json
            user_already_exist = UsersTable.find_one({"email": data["email"]})
            if user_already_exist:
                retJson = {
                    "status": 500,
                    "message": "User with the given email already exists!"
                }
                return jsonify(retJson)
            username = f"{data['firstName']} {data['lastName']}"
            otp = generate_otp()
            op_successfull = send_email_verification_otp(otp, username, data["email"])
            if op_successfull:
                hashed_password = bcrypt.hashpw(data["password"].encode('utf-8'), bcrypt.gensalt())
                UsersTable.insert_one({
                    "firstName": data["firstName"],
                    "lastName": data["lastName"],
                    "email": data["email"],
                    "verified": False,
                    "otp": otp,
                    "password": hashed_password
                })
                retJson = {
                    "status": 200,
                    "message": "An email is sent to your email address containing otp!"
                }
                return jsonify(retJson)
            else:
                retJson = {
                    "status": 500,
                    "message": "Could not send email, containing otp on given email address!"
                }
                return jsonify(retJson)
        except Exception as err:
            print("Error: ", err)
            retJson = {
                "status": 500,
                "message": str(err)
            }
            return jsonify(retJson)

class ActivateUserAccountWithOTP(Resource):
    def post(self):
        try:
            data = request.json
            user = UsersTable.find_one({"email": data["email"]})
            if user and user["otp"] is not None and user["otp"] == data["otp"]:
                update_response = UsersTable.update_one(
                    {"_id": user["_id"]},
                    {"$set": {"verified": True}}
                )
                if update_response.modified_count > 0:
                    retJson = {
                        "status": 200,
                        "message": "Email verified successfully!"
                    }
                    return jsonify(retJson)
            retJson = {
                "status": 500,
                "message": "An error occurred while verifying your email!"
            }
            return jsonify(retJson)
        except Exception as err:
            print("Error: ", err)
            retJson = {
                "status": 500,
                "message": str(err)
            }
            return jsonify(retJson)

class ActivateUserAccount(Resource):
    def post(self):
        try:
            data = request.json
            user = UsersTable.find_one({"uuid": data["uuid"]})
            if user:
                update_response = UsersTable.update_one(
                    {"uuid": data["uuid"]},
                    {"$set": {"verified": True}}
                )
                if update_response.modified_count > 0:
                    retJson = {
                        "status": 200,
                        "message": "Your email address has been verified successfully!"
                    }
                    return jsonify(retJson)
            retJson = {
                "status": 500,
                "message": "An error occurred while verifying your email address!"
            }
            return jsonify(retJson)
        except Exception as err:
            print("Error: ", err)
            retJson = {
                "status": 500,
                "message": str(err)
            }
            return jsonify(retJson)

class SendPasswordResetOtp(Resource):
    def post(self):
        try:
            data = request.json
            user = UsersTable.find_one({"email": data["email"]})
            if user:
                otp = generate_otp()
                title = 'Password Reset Otp'
                message = f"Please find the attached otp to reset your password and do not share this otp with anyone. OTP: {otp}"
                op_successfull = send_email(title, message, data["email"])
                if op_successfull:
                    update_response = UsersTable.update_one(
                        {"_id": user["_id"]},
                        {"$set": {"otp": otp}}
                    )
                    if update_response.modified_count > 0:
                        retJson = {
                            "status": 200,
                            "message": "An email is sent to your email address containing otp!"
                        }
                        return jsonify(retJson)
            retJson = {
                "status": 500,
                "message": "An error occurred while sending otp to your given email address!"
            }
            return jsonify(retJson)
        except Exception as err:
            print("Error: ", err)
            retJson = {
                "status": 500,
                "message": str(err)
            }
            return jsonify(retJson)

class VerifyPasswordResetOtp(Resource):
    def post(self):
        try:
            data = request.json
            user = UsersTable.find_one({"email": data["email"]})
            if user and user["otp"] is not None and user["otp"] == data["otp"]:
                retJson = {
                    "status": 200,
                    "message": "Otp verified successfully!"
                }
                return jsonify(retJson)
            retJson = {
                "status": 500,
                "message": "An error occurred while verifying your otp!"
            }
            return jsonify(retJson)
        except Exception as err:
            print("Error: ", err)
            retJson = {
                "status": 500,
                "message": str(err)
            }
            return jsonify(retJson)

class ResetPassword(Resource):
    def post(self):
        try:
            data = request.json
            user = UsersTable.find_one({"email": data["email"]})
            if user and user["otp"] is not None and user["otp"] == data["otp"]:
                hashed_password = bcrypt.hashpw(data["password"].encode('utf-8'), bcrypt.gensalt())
                update_response = UsersTable.update_one(
                    {"_id": user["_id"]},
                    {"$set": {
                        "otp": None,
                        "password": hashed_password
                    }}
                )
                if update_response.modified_count > 0:
                    retJson = {
                        "status": 200,
                        "message": "Your password has been reset successfully!"
                    }
                    return jsonify(retJson)
            retJson = {
                "status": 500,
                "message": "An error occurred while reseting your password!"
            }
            return jsonify(retJson)
        except Exception as err:
            print("Error: ", err)
            retJson = {
                "status": 500,
                "message": str(err)
            }
            return jsonify(retJson)

class LoginUser(Resource):
    def post(self):
        try:
            data = request.json
            user_already_exist = UsersTable.find_one({"email": data["email"]})
            if user_already_exist:
                user = user_already_exist
                if user["verified"]:
                    password = data["password"].encode('utf-8')
                    hashed_password = user["password"]
                    if bcrypt.checkpw(password, hashed_password):
                        alpaca_access_token = user.get('alpacaAccessToken', None)
                        access_token = create_access_token(identity=JSONEncoder().encode(user["_id"]).replace('"', ''))
                        if "platform" in data:
                            UsersTable.update_one(
                                {"_id": user["_id"]},
                                {
                                    "$inc": {
                                        "noOfSessions": 1
                                    },
                                    "$set": {
                                        "platform": data["platform"]
                                    }
                                }
                            )
                        else:
                            UsersTable.update_one(
                                {"_id": user["_id"]},
                                {
                                    "$inc": {
                                        "noOfSessions": 1
                                    }
                                }
                            )
                        retJson = {
                            "status": 200,
                            "user": {
                                "id": JSONEncoder().encode(user["_id"]).replace('"', ''),
                                "firstName": user["firstName"],
                                "lastName": user["lastName"],
                                "email": user["email"],
                                "access_token": access_token
                            },
                            "alpaca": {
                                "access_token": alpaca_access_token if alpaca_access_token is None else alpaca_access_token.decode('utf-8')
                            }
                        }
                        if "oneSignalId" in user:
                            retJson["user"]["oneSignalId"] = user["oneSignalId"]
                        return jsonify(retJson)
                    else:
                        retJson = {
                            "status": 500,
                            "message": "Incorrect email or password!"
                        }
                        return jsonify(retJson)
                else:
                    retJson = {
                        "status": 500,
                        "message": "Please verify your email first by following the link sent on your email address!"
                    }
                    return jsonify(retJson)
            else:
                retJson = {
                    "status": 500,
                    "message": "User with the given email does not exist!"
                }
                return jsonify(retJson)
        except Exception as err:
            print("Error: ", err)
            retJson = {
                "status": 500,
                "message": str(err)
            }
            return jsonify(retJson)

class SetUserOneSignalId(Resource):
    @jwt_required()
    def post(self):
        try:
            data = request.json
            BucketsTable.update_many(
                {"followers.userId": ObjectId(data["userId"])},
                {
                    "$set": {
                        "followers.$[element].oneSignalId": data["oneSignalId"]
                    }
                },
                upsert=False,
                array_filters=[{"element.userId": {"$eq": ObjectId(data["userId"])}}]
            )
            response = UsersTable.update_one(
                {"_id": ObjectId(data["userId"])},
                {
                    "$set": {"oneSignalId": data["oneSignalId"]}
                }
            )
            if response.modified_count > 0:
                retJson = {
                    "status": 200,
                    "message": "Successfully updated user's onesignal id!"
                }
                return jsonify(retJson)
            else:
                retJson = {
                    "status": 500,
                    "message": "An error occurred while updating user's onesignal id!"
                }
                return jsonify(retJson)
        except Exception as err:
            print("Error: ", err)
            retJson = {
                "status": 500,
                "message": str(err)
            }
            return jsonify(retJson)

class LogoutUser(Resource):
    @jwt_required()
    def get(self):
        try:
            # blacklist user's access token
            retJson = {
                "status": 200,
                "message": "You are successfully logged out!"
            }
            return jsonify(retJson)
        except Exception as err:
            print("Error: ", err)
            retJson = {
                "status": 500,
                "message": str(err)
            }
            return jsonify(retJson)