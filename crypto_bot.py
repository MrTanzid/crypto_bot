import alpaca_trade_api as tradeapi
import pandas as pd
import ta
from datetime import datetime, timedelta, timezone
import time

# Alpaca API credentials
API_KEY = 'PKCNNUJ3EIX5QTXZDOAI'
API_SECRET = 'S6ZcrGv6NLeY3hIcIdlt849lox2F1ua3xRqohgdz'
BASE_URL = 'https://paper-api.alpaca.markets'

# Initialize the Alpaca API
api = tradeapi.REST(API_KEY, API_SECRET, BASE_URL, api_version='v2')

# Parameters for the trading strategy
FAST_LENGTH = 50
SLOW_LENGTH = 200
RSI_LENGTH = 14
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30
MACD_FAST_LENGTH = 12
MACD_SLOW_LENGTH = 26
MACD_SIGNAL_SMOOTHING = 9
RISK_PERCENT = 1
STOP_LOSS_PERCENT = 2
TAKE_PROFIT_PERCENT = 5

# Trading symbol and timeframe
symbol = 'BTC/USD'  # Or 'BTCUSD' depending on Alpaca's expected format
timeframe = tradeapi.rest.TimeFrame(5, tradeapi.rest.TimeFrameUnit.Minute)

def get_data(symbol, start, end, timeframe):
    barset = api.get_crypto_bars(symbol, timeframe, start=start, end=end).df
    return barset

def calculate_indicators(df):
    df['fast_ma'] = ta.trend.sma_indicator(df['close'], FAST_LENGTH)
    df['slow_ma'] = ta.trend.sma_indicator(df['close'], SLOW_LENGTH)
    df['rsi'] = ta.momentum.rsi(df['close'], RSI_LENGTH)
    macd = ta.trend.MACD(df['close'], MACD_FAST_LENGTH, MACD_SLOW_LENGTH, MACD_SIGNAL_SMOOTHING)
    df['macd_line'] = macd.macd()
    df['signal_line'] = macd.macd_signal()
    df['volume_increasing'] = df['volume'] > df['volume'].shift(1)
    return df

def check_conditions(df):
    latest = df.iloc[-1]
    is_bullish = latest['fast_ma'] > latest['slow_ma']
    is_bearish = latest['fast_ma'] < latest['slow_ma']
    long_condition = is_bullish and latest['rsi'] > RSI_OVERSOLD and latest['macd_line'] > latest['signal_line'] and latest['volume_increasing']
    short_condition = is_bearish and latest['rsi'] < RSI_OVERBOUGHT and latest['macd_line'] < latest['signal_line'] and latest['volume_increasing']
    return long_condition, short_condition

def calculate_order_size(balance, price):
    risk_amount = balance * (RISK_PERCENT / 100)
    order_size = risk_amount / price
    return order_size

def place_order(side, qty):
    try:
        api.submit_order(
            symbol=symbol,
            qty=qty,
            side=side,
            type='market',
            time_in_force='gtc',
        )
        print(f"Placed {side} order for {qty} {symbol}")
    except Exception as e:
        print(f"Order placement failed: {e}")

def trade():
    clock = api.get_clock()
    if not clock.is_open:
        print("Market is closed.")
        return

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=7)
    start_str = start.strftime('%Y-%m-%dT%H:%M:%SZ')
    end_str = end.strftime('%Y-%m-%dT%H:%M:%SZ')
    df = get_data(symbol, start_str, end_str, timeframe)
    df = calculate_indicators(df)

    long_condition, short_condition = check_conditions(df)
    
    account = api.get_account()
    cash_balance = float(account.cash)
    price = df['close'].iloc[-1]

    position_size = calculate_order_size(cash_balance, price)

    # Use list_positions() instead of get_position()
    positions = api.list_positions()
    btc_position = None
    for position in positions:
        if position.symbol == symbol or position.symbol == symbol.replace('/', ''):
            btc_position = position
            break

    available_btc = float(btc_position.qty) if btc_position else 0

    # Check available balance and adjust position size
    if long_condition and available_btc == 0:
        if cash_balance >= position_size * price:
            place_order('buy', position_size)
        else:
            print(f"Insufficient cash balance to buy {position_size} BTC.")
            
    elif short_condition and available_btc > 0:
        if available_btc >= position_size:
            place_order('sell', available_btc)
        else:
            print(f"Insufficient BTC balance to sell {position_size} BTC.")

if __name__ == '__main__':
    while True:
        try:
            trade()
            time.sleep(300)  # Run every 5 minutes (5 minutes * 60 seconds)
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(60)  # Wait a minute before retrying
