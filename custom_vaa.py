import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
# https://pandas.pydata.org/pandas-docs/stable/10min.html

logging.basicConfig(format='%(levelname)s %(funcName)s | %(message)s', level=logging.DEBUG)
log = logging.getLogger()

# _________________________________________________________________________________________________
class DateSync():
    '''to ontrol date in all asset classes at once'''
    def __init__(self, date:pd.Timestamp):
        self.date = date

# data: panda dataframe 
#       index=dates 
#       columns=Open, High, Low, Close, Volume


# _________________________________________________________________________________________________
class Asset():
    def __init__(self, name:str, data:pd.DataFrae, date:DataSync):
        self.name = name
        self.data = data  # panda dataframe as specified
        self.date = date  # a DateSync object

    @property
    def close(self):
        return self.data.loc[self.date, ['close']]  # todays close price

    @property
    def open(self):
        return self.data.loc[self.date, ['close']]  # todays close price

    @property
    def today(self):
        return self.date.date

    @property
    def indicator13612W(self):
        # todo algorithm on self.data, based on self.date
        return 0


# _________________________________________________________________________________________________
class Position():
    def __init__(self, asset:Asset, amount:int, commission=6.5, close=True):
        self.asset = asset
        self.amount = amount
        self.commission = commission  # commission for buy/sell operations
        self.buy_date = asset.today
        self.buy_price = asset.close if close else asset.open
        self.sell_date = None
        self.sell_price = None
        # todo strategy/position money management; subtract commission from total money

    @property
    def active(self):
        return bool(self.sell_price)

    @property
    def value(self):
        return self.amount*self.asset.close

    @property
    def profit(self):
        if self.sell_price:
            return self.amount*(self.sell_price - self.buy_price) - self.commission
        else:
            log.warning(f'position on {self.asset.name} is still open, no actual profit')
            return self.amount*(self.asset.close - self.buy_price) - self.commission*2

    def sell(self, close=True):
        self.sell_date = self.asset.today
        self.sell_price = self.asset.close if close else self.asset.open


# _________________________________________________________________________________________________
class Strategy():
    def __init__(self, cash, assets:list, date:DataSync):
        self.assets = {a.name: a for a in assets}  # dict of Asset objects
        self.date = date  # DataSync object
        self.cash = cash
        [a.date = self.date for a in assets]  # sync all assets date
        self._positions = []

    @property
    def value(self):
        return self.cash + [active position values]

    @property
    def positions(self):
        return [p for p in self._positions if p.active]

    @property
    def closed_positions(self):
        return [p for p in self._positions if not p.active]

    def buy_position(self, position): 
        if position.amount * buy_price + position.commission < self.cash:
            self._positions.append(position)
            self.cash -= position.value + position.commission
            return position
        else:
            log.warning(f'cannot buy position for {position.asset.name}')

    def sell_position(self, position):
        if position.active:
            position.sell()
            self.cash += position.value - position.commission
        else:
            log.error('cannot sell inactive position on {position.asset.name}')

    def execute(self, date):
        pass   # logic here


# _________________________________________________________________________________________________
class VAA_Strategy(Strategy):
    def __init__(self, assets:list, date:DataSync):
        super().__init__(assets, date)
        self.risk_assets = ['SPY', 'AGG']
        self.cash_assets = ['SHY']

    def execute(self, date):


# _________________________________________________________________________________________________
if __name__ == '__main__':
    # todo define assets from files
    # todo strategy object
    # todo main loop
    start_date = VAA.assets.items()[0].data[idx0] + 13 months
    for date in panda.timeframe

    # buy: create position and try to buy it
    # sell: 



















