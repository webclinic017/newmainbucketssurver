from yahoo_fin import stock_info as si

def get_latest_quote(ticker):
    try:
        response = si.get_live_price(ticker)
        print(f"\n Live price response of {ticker}: ", response)
        return response
    except Exception as err:
        print("Error: ", err)
        return False