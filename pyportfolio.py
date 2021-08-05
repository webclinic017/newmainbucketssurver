from pypfopt.discrete_allocation import DiscreteAllocation, get_latest_prices
from pandas_datareader import data as web
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

def get_stats(assets, weights):
    weights = np.array(weights)
    keys = assets
    values = weights
    weightsdict = dict(zip(keys, values))

    # Get the stocks ending date aka todays date and format it in the form YYYY-MM-DD
    today = datetime.today().strftime('%Y-%m-%d')
    stockStartDate = (datetime.today() - timedelta(days=1100)).strftime('%Y-%m-%d')
    #Create a dataframe to store the adjusted close price of the stocks
    df = pd.DataFrame()
    for stock in assets:
        df[stock] = web.DataReader(stock,data_source='yahoo',start=stockStartDate , end=today)['Adj Close']
        
    returns = df.pct_change()
    cov_matrix_annual = returns.cov() * 252
    port_variance = np.dot(weights.T, np.dot(cov_matrix_annual, weights))
    port_volatility = np.sqrt(port_variance)
    portfolioSimpleAnnualReturn = np.sum(returns.mean()*weights) * 252
    port_sharpe=portfolioSimpleAnnualReturn/port_volatility

    return {
        "annualPercentReturn": portfolioSimpleAnnualReturn*100,
        "annualPercentVolatility": port_volatility*100,
        "annualVariance": port_variance*100,
        "portfolioSharp": port_sharpe
    }