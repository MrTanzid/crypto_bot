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
symbol = 'BTC/USD'
timeframe = tradeapi.rest.TimeFrame(5, tradeapi.rest.TimeFrameUnit.Minute)  # Set your preferred timeframe here

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

def calculate_order_size(balance, risk_percent, price):
    risk_amount = balance * (risk_percent / 100)
    stop_loss_level = price * (STOP_LOSS_PERCENT / 100)
    position_size = risk_amount / stop_loss_level
    return position_size

def place_order(side, qty):
    api.submit_order(
        symbol=symbol,
        qty=qty,
        side=side,
        type='market',
        time_in_force='gtc',
    )

def place_stop_loss(side, qty, stop_price):
    api.submit_order(
        symbol=symbol,
        qty=qty,
        side=side,
        type='stop',
        stop_price=stop_price,
        time_in_force='gtc',
    )

def place_take_profit(side, qty, limit_price):
    api.submit_order(
        symbol=symbol,
        qty=qty,
        side=side,
        type='limit',
        limit_price=limit_price,
        time_in_force='gtc',
    )

def manage_position():
    try:
        position = api.get_position(symbol.replace('/', ''))
        current_price = float(position.current_price)
        side = 'sell' if position.side == 'long' else 'buy'
        qty = abs(float(position.qty))
        
        stop_loss_price = current_price * (1 - STOP_LOSS_PERCENT / 100) if side == 'sell' else current_price * (1 + STOP_LOSS_PERCENT / 100)
        take_profit_price = current_price * (1 + TAKE_PROFIT_PERCENT / 100) if side == 'sell' else current_price * (1 - TAKE_PROFIT_PERCENT / 100)

        place_stop_loss(side, qty, stop_loss_price)
        place_take_profit(side, qty, take_profit_price)

        print(f"Placed stop loss at {stop_loss_price} and take profit at {take_profit_price}")
    except tradeapi.rest.APIError as e:
        if e.code == 404:
            print("No position found.")
        else:
            print(f"API error: {e}")

def trade():
    clock = api.get_clock()
    if not clock.is_open:
        print("Market is closed.")
        return

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=7)  # Adjust the lookback period as needed
    start_str = start.strftime('%Y-%m-%dT%H:%M:%SZ')
    end_str = end.strftime('%Y-%m-%dT%H:%M:%SZ')
    df = get_data(symbol, start_str, end_str, timeframe)
    df = calculate_indicators(df)

    long_condition, short_condition = check_conditions(df)
    
    account = api.get_account()
    balance = float(account.cash)
    price = df['close'].iloc[-1]

    position_size = calculate_order_size(balance, RISK_PERCENT, price)
    
    # Check for existing position
    positions = api.list_positions()
    in_position = any(position.symbol == symbol.replace('/', '') for position in positions)

    if long_condition and not in_position:
        place_order('buy', position_size)
        print(f"Bought {position_size} of {symbol}")
        manage_position()

    elif short_condition and not in_position:
        place_order('sell', position_size)
        print(f"Sold {position_size} of {symbol}")
        manage_position()

if __name__ == '__main__':
    while True:
        try:
            trade()
            time.sleep(300)  # Run every 5 minutes (5 minutes * 60 seconds)
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(60)  # Wait a minute before retrying
