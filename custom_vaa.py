import logging
import matplotlib.pyplot as plt
import numpy as np
import os
import pandas as pd
import subprocess
import sys
# https://pandas.pydata.org/pandas-docs/stable/10min.html

logging.basicConfig(format='%(levelname)s %(funcName)s | %(message)s', level=logging.DEBUG)
log = logging.getLogger()

# _________________________________________________________________________________________________
class DateSync():
    '''to ontrol date in all asset classes at once'''
    def __init__(self, date:pd.Timestamp):
        self.date = date

    @property
    def now(self):
        return self.date


# data: panda dataframe 
#       index=dates 
#       columns=Open, High, Low, Close, Volume


# _________________________________________________________________________________________________
class Asset():
    def __init__(self, name:str, data:pd.DataFrame, date:DateSync):
        self.name = name
        self.data = data  # panda dataframe as specified
        self._date = date  # a DateSync object

    @property
    def date(self):
        self._date.now

    @property
    def close(self):
        return self.data.loc[self.today, ['close']][0]  # todays close price

    @property
    def open(self):
        return self.data.loc[self.today, ['open']][0]  # todays close price

    @property
    def today(self):
        return self._date.now

    @property
    def last_bussiness_days(self):
        data_start_date = self.data.index[0] 
        data_end_date = self.data.index[-1]
        return [d.date() for d in pd.date_range(data_start_date, data_end_date, freq='BM')]

    @property
    def i_13612W(self):
        # todo get closest last_bussiness_day
        # assume only called on a last_bussiness_day
        start_idx = self.last_bussiness_days.index(self.today)
        end_of_months = list(reversed(self.last_bussiness_days[start_idx-12:start_idx+1]))
        # log.debug(f'end_of_months [{len(end_of_months)}]= {end_of_months} ')

        emc = [self.data.loc[d].close for d in end_of_months]
        p0, p1, p3, p6, p12 = emc[0], emc[1], emc[3], emc[6], emc[12]  # map for nice formula

        # assign the momentum value to the linebuffer
        return round(12*(p0/p1 - 1) + 4*(p0/p3 - 1) + 2*(p0/p6 - 1) + (p0/p12 - 1), 2)


# _________________________________________________________________________________________________
class Position():
    def __init__(self, asset:Asset, amount:int, commission=6.5, close=True):
        self.asset = asset
        self.amount = amount
        self.commission = commission  # commission per buy/sell operation, not accumulating
        self.buy_date = asset.today
        self.buy_price = asset.close if close else asset.open
        self.sell_date = None
        self.sell_price = None
        # todo strategy/position money management; subtract commission from total money

    @property
    def active(self):
        return not bool(self.sell_price)

    @property
    def value(self):
        return self.amount*self.asset.close

    @property
    def profit(self):
        if self.sell_price:
            return self.amount*(self.sell_price - self.buy_price) - self.commission*2
        else:
            log.warning(f'position on {self.asset.name} is still open, no actual profit')
            return self.amount*(self.asset.close - self.buy_price) - self.commission*2

    def _sell(self, close=True):
        self.sell_date = self.asset.today
        self.sell_price = self.asset.close if close else self.asset.open


# _________________________________________________________________________________________________
class Strategy():
    def __init__(self, cash, assets:list, date:DateSync):
        self.assets = {a.name: a for a in assets}  # dict of Asset objects
        self._date = date  # DataSync object
        self.cash = cash
        for a in assets:  # sync all assets date
            a._date = self._date
        self._positions = []

    @property
    def value(self):
        return self.cash + sum(p.value for p in self.positions)

    @property
    def now(self):
        return self._date.now

    def status(self):
        log.debug('{}: cash={}, value={}, assets: {}'.format(
            self.now, self.cash, self.value, {p.asset.name: p.value for p in self.positions}))

    @property
    def positions(self):
        return [p for p in self._positions if p.active]

    @property
    def closed_positions(self):
        return [p for p in self._positions if not p.active]

    def buy_position(self, position): 
        if position.amount * position.buy_price + position.commission < self.cash:
            self._positions.append(position)
            self.cash -= position.value + position.commission
            log.debug(f'bought position {position.asset.name} {position.value:.2f}')
            return position
        else:
            log.warning(f'cannot buy position for {position.asset.name}')

    def sell_position(self, position):
        if position.active:
            position._sell()
            self.cash += position.value - position.commission
        else:
            log.error('cannot sell inactive position on {position.asset.name}')

    def execute(self, date):
        pass   # logic here


# _________________________________________________________________________________________________
class VAA_Strategy(Strategy):
    def __init__(self, assets:list, date:DateSync):
        super().__init__(self, assets, date)
        self.risk_assets = ['SPY', 'AGG']
        self.cash_assets = ['SHY']

    def execute(self, date):
        pass


# _________________________________________________________________________________________________
def read_yahoo_csv(file_path):
    return pd.read_csv(file_path, index_col=0, usecols=[0, 1, 2, 3, 4, 6], parse_dates=True)

# _________________________________________________________________________________________________
# _________________________________________________________________________________________________
if __name__ == '__main__':

    data_start = pd.to_datetime('2006-01-01')
    data_end = pd.to_datetime('2007-08-01')
    asset_tickers = ['SPY', 'AGG', 'SHY']  # 'EFA', 'EEM', 'AGG', 'LQD', 'IEF', 'SHY'
    start_date = pd.to_datetime('2007-02-28')  # for the simulation, make this relative ...

    log.debug('start_date = {} '.format(start_date))
    date = DateSync(start_date)

    # assert data files are present, else download
    data_dir = 'data'
    if not os.path.isdir(data_dir):
        os.mkdir(data_dir)

    assets = []
    for ticker_name in asset_tickers:
        ticker_file = '{}/{}.dat'.format(data_dir, ticker_name)

        if not os.path.isfile(ticker_file):  # get data if not available
            log.debug(f'downloading {ticker_file}')
            subprocess.call(['python',
                             './backtrader.git/tools/yahoodownload.py',
                             '--ticker', ticker_name,
                             '--fromdate', str(data_start.date()),
                             '--todate', str(data_end.date()),
                             '--outfile', ticker_file,
                             ])
        else:
            log.debug(f'using available ticker file {ticker_file}')

        asset = Asset(ticker_name, read_yahoo_csv(ticker_file), date)  # create asset object
        asset.data.columns = [c.lower() for c in asset.data.columns]  # make headers lower-case
        assets.append(asset)
                         

    # create strategy object
    strategy = VAA_Strategy(assets, date)
    strategy.cash = 10e3  # starting money

    # main loop

    for day in assets[0].last_bussiness_days[13:]:
        log.debug(f'last trading day: {day} ____________________________________________________')
        date.date = day  # update all dates
        log.debug(f'day = {day}')

        # gather indicators
        risk_indicators = {strategy.assets[a].name: strategy.assets[a].i_13612W for a in strategy.risk_assets}
        cash_indicators = {strategy.assets[a].name: strategy.assets[a].i_13612W for a in strategy.cash_assets}

        good = bool([i for key, i in risk_indicators.items() if i > 0.0])
        g_str = 'good' if good else 'bad'
        log.debug(f'indicators: risk={risk_indicators}>{g_str}, cash={cash_indicators}')

        if good:
            best_asset = 
            position = Position(strategy.assets['SPY'], 10)
            log.debug(f'{position.buy_price}')
            log.debug(f'{position.value}')
            strategy.status()
            strategy.buy_position(position)
            strategy.status()
            strategy.sell_position(strategy.positions[-1])
            strategy.status()


        sys.exit(0)


    # buy: create position and try to buy it
    # sell: 



















