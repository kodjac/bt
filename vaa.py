import logging
import matplotlib.pyplot as plt
import numpy as np
import os
import time
import pandas as pd
import subprocess
import sys
# https://pandas.pydata.org/pandas-docs/stable/10min.html

start_time = time.time()

# logging.basicConfig(format='%(levelname)s %(funcName)s | %(message)s', level=logging.DEBUG)
logging.basicConfig(format='  %(message)s', level=logging.DEBUG)
# logging.basicConfig(format='  %(message)s', level=logging.INFO)
log = logging.getLogger()

# _________________________________________________________________________________________________
class DateSync():
    '''to ontrol date in all asset classes at once'''
    def __init__(self, date:pd.Timestamp):
        self.date = date

    @property
    def now(self):
        return self.date


# _________________________________________________________________________________________________
class Asset():
    def __init__(self, name:str, data:pd.DataFrame, date:DateSync):
        self.name = name
        self.data = data  # panda dataframe as specified
        self._date = date  # a DateSync object
        self._last_bussiness_days = []
        self._positions = []

    @property
    def today(self):
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
    def positions(self):
        return [p for p in self._positions if p.active]

    @property
    def last_bussiness_days(self):
        # pandas BM not working, so now with brute force
        if not self._last_bussiness_days:  # only if not already done ...
            data_start_date = self.data.index[0] 
            data_end_date = self.data.index[-1]
            for idx, day in enumerate(self.data.index[:-1]):
                if day.month != self.data.index[idx+1].month:
                    self._last_bussiness_days.append(day)

        return self._last_bussiness_days

    @property
    def i_13612W(self):
        # assume only called on a last_bussiness_day
        start_idx = self.last_bussiness_days.index(self.today)
        end_of_months = list(reversed(self.last_bussiness_days[start_idx-12:start_idx+1]))
        # log.debug(f'end_of_months [{len(end_of_months)}]= {end_of_months} ')

        emc = [self.data.loc[d].close for d in end_of_months]
        p0, p1, p3, p6, p12 = emc[0], emc[1], emc[3], emc[6], emc[12]  # map for nice formula

        # assign the momentum value to the linebuffer
        return round((12*(p0/p1 - 1) + 4*(p0/p3 - 1) + 2*(p0/p6 - 1) + (p0/p12 - 1))*10, 1)


# _________________________________________________________________________________________________
class Position():
    commission=6.5
    def __init__(self, asset:Asset, amount:int, commission=commission, close=True):
        self.asset = asset
        self.amount = amount
        self.commission = commission  # commission per buy/sell operation, not accumulating
        self.buy_date = asset.today
        self.buy_price = asset.close if close else asset.open
        # self.buy_value = self.value
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
        self.high = self.cash
        self.maxDD = 0
        for a in assets:  # sync all assets date
            a._date = self._date
            a.scale = self.cash/a.close
        self.plotdata = None
        self.update_plotdata()

    def update_plotdata(self):
        plotdata = {a.name: a.close*a.scale for a in self.assets.values()} 
        # plotdata.update({a.name+'_i': a.i_13612W for a in self.assets.values()})
        plotdata['value'] = self.value
        plotdata['maxDD'] = self.maxDD

        if isinstance(self.plotdata, pd.DataFrame):
            plotdata['incr'] = self.value - self.plotdata[-1:].value
            plotdata = pd.DataFrame(plotdata, index=[self.today])
            self.plotdata = self.plotdata.append(plotdata)
        else:
            plotdata['incr'] = 0
            plotdata = pd.DataFrame(plotdata, index=[self.today])
            self.plotdata = plotdata

    @property
    def value(self):
        return self.cash + sum(p.value for p in self.positions)

    @property
    def today(self):
        return self._date.now

    def status(self, logger=log.info):
        logger('{}: cash={:.2f}, value={:.2f}, positions: {}'.format(
            self.today, self.cash, self.value, [f'{p.asset.name}: {p.value:.0f}' for p in self.positions]))

    @property
    def positions(self):
        return [p for key, a in self.assets.items() for p in a.positions if p.active]

    @property
    def closed_positions(self):
        return [p for p in self._positions if not p.active]

    def buy_position(self, name, amount): 
        asset = self.assets[name]
        position = Position(asset, amount)
        if amount * asset.data.loc[self.today].close + position.commission < self.cash:
            asset._positions.append(position)
            self.cash -= position.value + position.commission
            log.info(f'bought position {position.asset.name}x{position.amount}'
                      f' for total {position.value:.2f}')
            return position
        else:
            log.warning(f'cannot buy position for {position.asset.name}')

    def sell_position(self, position):  # fixme can only sell complete position
        if isinstance(position, str):
            positions = self.assets[position].positions
            assert len(positions) == 1, '{} position'.format('more than one' if positions else 'no')
            position = positions[0]

        position._sell()
        self.cash += position.value - position.commission
        # self.cash += (position.value - position.buy_price*position.amount)*0.75 + position.value - position.commission
        log.info(f'sold position {position.asset.name} profit {position.profit:.2f}')

    def execute(self, date):
        pass   # logic here


# _________________________________________________________________________________________________
class VAA_Strategy(Strategy):
    risk_assets = ['SPY', 'EFA', 'EEM', 'LQD']
    cash_assets = ['SHY', 'IEF', 'TLT'] # 'GLD']
    # risk_assets = ['EXSA',  # iShares EuroStoxx 600 DE0002635307
                   # 'LYPS',  # Lyxor S&P 500 LU0496786574
                   # 'X014',  # ComStage MSCI Pacific TRN LU0392495023
                   # 'LYM7',  # Lyxor MSCI Emerging Markets FR0010429068
                   # 'AGG' # 'EUN4',  # iShares Euro Aggregate Bond IE00B3DKXQ41
                  # ]
    # cash_assets = ['SHY',
                   # 'EUN5',  # iShares Core Euro Corporate Bond IE00B3F81R35
                   # 'IS0Y',  # iShares Euro Corporate Bond Interest Rate Hedged IE00B6X2VY59
                   # 'IBCA',  # iShares Euro Government Bond 1-3yr IE00B14X4Q57
                   # 'SXRP',  # iShares Euro Government Bond 3-7yr IE00B3VTML14
                   # 'IBCM',  # iShares Euro Government Bond 7-10yr IE00B1FZS806
                   # 'IBCL',  # iShares Euro Government Bond 15-30yr IE00B1FZS913
                   # 'EUN8',  # iShares Euro Government Bond 10-15yr IE00B4WXJH41
                  # ]
    # cash_assets = ['SHY', 'LQD', 'IEF', 'TLT', 'HYG', 'BNDX', 'EMB']
    def __init__(self, cash, assets:list, date:DateSync):
        super().__init__(cash, assets, date)


    def execute(self, date):
        pass


# _________________________________________________________________________________________________
def read_csv(file_path):
    return pd.read_csv(file_path, index_col=0, usecols=[0, 1, 2, 3, 4], parse_dates=True)

# _________________________________________________________________________________________________
# _________________________________________________________________________________________________
if __name__ == '__main__':

    data_start = pd.to_datetime('1999-01-01')
    data_end = pd.to_datetime('2018-04-10')
    cash_start = 10e3
    # start_date = pd.to_datetime('2015-01-01')
    start_date = None
    saving = 400

    asset_tickers = VAA_Strategy.risk_assets + VAA_Strategy.cash_assets

    date = DateSync(data_start)

    # assert data files are present, else download
    data_dir = 'data'
    if not os.path.isdir(data_dir):
        os.mkdir(data_dir)

    assets = []
    for ticker_name in asset_tickers:
        ticker_file = '{}/{}.dat'.format(data_dir, ticker_name)

        if not os.path.isfile(ticker_file):  # get data if not available
            log.info(f'downloading {ticker_file}')
            subprocess.call(['python',
                             './backtrader.git/tools/yahoodownload.py',
                             '--ticker', ticker_name,
                             '--fromdate', str(data_start.date()),
                             '--todate', str(data_end.date()),
                             '--outfile', ticker_file,
                             ])
        else:
            log.debug(f'using available ticker file {ticker_file}')

        asset = Asset(ticker_name, read_csv(ticker_file), date)  # create asset object
        asset.data.columns = [c.lower() for c in asset.data.columns]  # make headers lower-case
        assets.append(asset)
                         
    latest_asset = max(assets, key=lambda a: a.data.index[0])  # starts the latest
    ultimo = pd.DataFrame(index=latest_asset.last_bussiness_days)  # for bool slicing
    start = start_date if start_date else latest_asset.data.index[0]
    last_bussiness_days = ultimo[ultimo.index > start]
    latest_start = last_bussiness_days.index[12]
    last_bussiness_days = last_bussiness_days[12:]
    date.date = latest_start

    # create strategy object
    strategy = VAA_Strategy(cash_start, assets, date)  # start money


    for idx, day in enumerate(last_bussiness_days.index):
        log.debug('_'*100)
        log.debug(f'last trading day: {day}')
        strategy.status(log.debug)
        date.date = day  # update all dates

        log.info(f'savings: {saving}')
        strategy.cash += saving

        # gather indicators
        risk_indicators = {strategy.assets[a].name: strategy.assets[a].i_13612W 
                           for a in strategy.risk_assets}
        cash_indicators = {strategy.assets[a].name: strategy.assets[a].i_13612W 
                           for a in strategy.cash_assets}


        bad_indicator = {key:i for key, i in risk_indicators.items() if i < 0.0}
        good = not bad_indicator
        g_str = 'good' if good else f'bad {tuple(bad_indicator.keys())}'
        log.debug(f'indicators: risk={risk_indicators} > {g_str}')
        log.debug(f'            cash={cash_indicators}')

        if good:
            asset_class = risk_indicators
        else:
            asset_class = cash_indicators

        best_asset = max(asset_class, key=lambda k: asset_class[k])  # in respective class
        # log.debug(f'best_asset = {best_asset} ')

        # ensure old position is the best or sell it
        if not strategy.positions:
            # log.debug('no positions, starting or in cash')
            pass

        elif not strategy.positions[-1].asset.name == best_asset:
            strategy.sell_position(strategy.positions[-1])
        
        if not strategy.positions:  # either we're still in the best position or sold the old one
            amount = int((strategy.cash-Position.commission)/strategy.assets[best_asset].close)
            if not best_asset in ['SHY',]:
                strategy.buy_position(best_asset, amount)

        strategy.high = max(strategy.value, strategy.high)
        strategy.maxDD = max((strategy.high - strategy.value)/strategy.high*100, strategy.maxDD)

        strategy.update_plotdata()
        # if idx > 3:
            # sys.exit(0)
            # strategy.plotdata
        strategy.status()

    if strategy.positions:
        strategy.sell_position(strategy.positions[-1])

    strategy.status()
    cash_end = strategy.cash

    duration = len(last_bussiness_days)/12
    log.debug(f'duration {duration} years')
    CAGR = ((cash_end/cash_start)**(1/duration)-1)*100

    log.info('')
    log.info('-'*100)
    log.info(f'risk           {", ".join(strategy.risk_assets)}')
    log.info(f'cash           {", ".join(strategy.cash_assets)}')
    log.info('----------------------------------------------------')
    log.info(f'start value    {cash_start:.0f}')
    log.info(f'final value    {cash_end:.0f} {(cash_end/cash_start-1)*100:+.0f}%')
    log.info('----------------------------------------------------')
    log.info(f'CAGR           {CAGR:.2f}%')
    log.info(f'max drawdown   {strategy.maxDD:.0f}%')
    log.info('----------------------------------------------------')
    log.info('asset profit:')
    for asset in assets:
        all_positions = [int(p.profit) for p in asset._positions]
        log.info(f'  {asset.name}: {sum(p.profit for p in asset._positions):.0f}: {all_positions}')
    # strategy.plotdata.plot()
    d = strategy.plotdata
    d.loc[:, ['value'] + VAA_Strategy.risk_assets + VAA_Strategy.cash_assets].plot()
    plt.yscale('log')
    # plt.ylim(cash_start*0.9, strategy.cash*1.1)
    log.info('time in secs {:.2f}'.format(time.time()-start_time))
    # d.loc[:, 'maxDD'].plot()
    plt.show()





# todo actually an asset has positions, not a positions an asset, strategy.assets.position
# todo indicators vs actual value
# todo test with german bonds
# todo plotting
# todo sharpe ratio
# todo taxes
# todo lazy trading
# todo profile this, printing_update is bad







