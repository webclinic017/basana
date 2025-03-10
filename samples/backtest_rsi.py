# Basana
#
# Copyright 2022 Gabriel Martin Becedillas Ruiz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Bars can be downloaded using this command:
# python -m basana.external.bitstamp.tools.download_bars -c BTC/USD -p 1d -s 2021-01-01 -e 2021-12-31 \
# -o bitstamp_btcusd_day.csv

from decimal import Decimal
import asyncio
import logging

from basana.backtesting import charts
from basana.external.bitstamp import csv
import basana as bs
import basana.backtesting.exchange as backtesting_exchange

from samples.backtesting import position_manager
from samples.strategies import rsi


async def main():
    logging.basicConfig(level=logging.INFO, format="[%(asctime)s %(levelname)s] %(message)s")

    event_dispatcher = bs.backtesting_dispatcher()
    pair = bs.Pair("BTC", "USD")
    exchange = backtesting_exchange.Exchange(
        event_dispatcher,
        initial_balances={"BTC": Decimal(0), "USD": Decimal(1200)}
    )
    exchange.set_symbol_precision(pair.base_symbol, 8)
    exchange.set_symbol_precision(pair.quote_symbol, 2)

    # Connect the strategy to the bar events from the exchange.
    oversold_level = 30
    overbought_level = 70
    strategy = rsi.Strategy(event_dispatcher, 7, oversold_level, overbought_level)
    exchange.subscribe_to_bar_events(pair, strategy.on_bar_event)

    # Connect the position manager to different types of events. Borrowing is disabled in this example.
    position_mgr = position_manager.PositionManager(
        exchange, position_amount=Decimal(1000), quote_symbol=pair.quote_symbol, stop_loss_pct=Decimal(6),
        borrowing_disabled=True
    )
    strategy.subscribe_to_trading_signals(position_mgr.on_trading_signal)
    exchange.subscribe_to_bar_events(pair, position_mgr.on_bar_event)
    exchange.subscribe_to_order_events(position_mgr.on_order_event)

    # Load bars from the CSV file.
    exchange.add_bar_source(csv.BarSource(pair, "bitstamp_btcusd_day.csv", "1d"))

    # Setup chart.
    chart = charts.LineCharts(exchange)
    chart.add_pair(pair)
    chart.add_portfolio_value(pair.quote_symbol)
    chart.add_custom("RSI", "RSI", charts.DataPointFromSequence(strategy.rsi))
    chart.add_custom("RSI", "Overbought", lambda _: overbought_level)
    chart.add_custom("RSI", "Oversold", lambda _: oversold_level)

    # Run the backtest.
    await event_dispatcher.run()

    # Log balances.
    balances = await exchange.get_balances()
    for currency, balance in balances.items():
        logging.info("%s balance: %s", currency, balance.available)

    chart.show()

if __name__ == "__main__":
    asyncio.run(main())
