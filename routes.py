from flask import render_template
from config import app, api
from views import (
    PlaceSingleStockAlpacaOrder,
    LogoutFromRobinhoodAccount,
    LogoutFromAlpacaAccount,
    GetRecentBucketChanges,
    ToggleBucketVisibility,
    SellAllSharesInBucket,
    LinkRobinhoodAccount,
    GetAlpacaAccessToken,
    ExecuteCopiedTrades,
    DeleteBucketStock,
    PlaceAlpacaOrder,
    RebalanceBucket,
    GetUserBuckets,
    UnFollowBucket,
    GetBucketStats,
    GetStockStats,
    GetBucketData,
    FollowBucket,
    UpdateBucket,
    CreateBucket,
    VerifyOtp,
)
from auth import (
    ActivateUserAccountWithOTP,
    VerifyPasswordResetOtp,
    SendPasswordResetOtp,
    RegisterUserWithOTP,
    ActivateUserAccount,
    SetUserOneSignalId,
    ResetPassword,
    FetchUser,
    LoginUser,
    RegisterUser,
    LogoutUser
)

api.add_resource(RegisterUser, "/signup-user")
api.add_resource(RegisterUserWithOTP, "/signup-user-with-otp")
api.add_resource(SendPasswordResetOtp, "/send-password-reset-otp")
api.add_resource(VerifyPasswordResetOtp, "/verify-password-reset-otp")
api.add_resource(SetUserOneSignalId, "/set-user-onesignal-id")
api.add_resource(ResetPassword, "/reset-password")
api.add_resource(PlaceAlpacaOrder, "/place-order-on-alpaca")
api.add_resource(PlaceSingleStockAlpacaOrder, "/place-single-stock-alpaca-order")
api.add_resource(SellAllSharesInBucket, "/sell-bucket-shares")
api.add_resource(GetAlpacaAccessToken, "/get-alpaca-access-token")
api.add_resource(GetStockStats, "/get-stock-stats")
api.add_resource(LinkRobinhoodAccount, "/link-robinhood-account")
api.add_resource(LogoutFromAlpacaAccount, "/logout-from-alpaca-account")
api.add_resource(LogoutFromRobinhoodAccount, "/logout-from-robinhood-account")
api.add_resource(VerifyOtp, "/verify-otp")
api.add_resource(ActivateUserAccount, "/activate-user-account")
api.add_resource(ActivateUserAccountWithOTP, "/activate-user-account-with-otp")
api.add_resource(ExecuteCopiedTrades, "/execute-copied-trades")
api.add_resource(LoginUser, "/login-user")
api.add_resource(LogoutUser, "/logout-user")
api.add_resource(FetchUser, "/fetch-user")
api.add_resource(GetUserBuckets, "/get-user-buckets")
api.add_resource(GetBucketData, "/get-bucket-data")
api.add_resource(CreateBucket, "/create-bucket")
api.add_resource(FollowBucket, "/follow-bucket")
api.add_resource(UnFollowBucket, "/un-follow-bucket")
api.add_resource(DeleteBucketStock, "/delete-bucket-stock")
api.add_resource(UpdateBucket, "/update-bucket")
api.add_resource(GetBucketStats, "/get-bucket-stats")
api.add_resource(RebalanceBucket, "/rebalance-bucket")
api.add_resource(ToggleBucketVisibility, "/toggle-bucket-visibility")
api.add_resource(GetRecentBucketChanges, "/get-recent-bucket-changes")

@app.route("/")
def index():
    return {"status": 200, "message": "Server is up and running successfully!"}

@app.route("/<id>")
def deeplink_redirect(id):
    return render_template('index.html')

@app.route("/verify-email/<uuid>")
def verify_email(uuid):
    return render_template('index.html')
