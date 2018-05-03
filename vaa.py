import logging
import matplotlib.pyplot as plt
import numpy as np
import os
import time
import pandas as pd
import requests
import subprocess
import sys
from alpha_vantage.timeseries import TimeSeries
# https://pandas.pydata.org/pandas-docs/stable/10min.html

start_time = time.time()

# logging.basicConfig(format='%(levelname)s %(funcName)s | %(message)s', level=logging.DEBUG)
logging.basicConfig(format='  %(message)s', level=logging.DEBUG)
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
    def closed_positions(self):
        return [p for p in self._positions if not p.active]

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
        return (12*(p0/p1 - 1) + 4*(p0/p3 - 1) + 2*(p0/p6 - 1) + (p0/p12 - 1))*100


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

    @property
    def profit_percent(self):
        return self.profit/(self.buy_price * self.amount)*100

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
        self.stop_losses = []
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
        return [p for a in self.assets.values() for p in a.positions]

    @property
    def closed_positions(self):
        return [p for a in self.assets.values() for p in a.closed_positions]

    @property
    def all_positions(self):
        return [p for a in self.assets.values() for p in a._positions]


    @property
    def worst_month(self):
        # log.debug(
        return min(p.profit_percent for p in self.all_positions)

    @property
    def best_month(self):
        # log.debug(
        return max(p.profit_percent for p in self.all_positions)

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
        # self.cash += (position.value - position.buy_price*position.amount)*0.75 + position.buy_price*position.amount - position.commission
        log.info(f'sold position {position.asset.name} profit {position.profit:.2f} = {position.profit_percent:.0f}%')

    def execute(self, date):
        pass   # logic here


# _________________________________________________________________________________________________
class VAA_Strategy(Strategy):
    # _____________________________________________________________________________________________
    ignore_risk = []
    # standard
    # risk_assets = ['SPY', 'EFA', 'EEM', 'AGG']
    risk_assets = ['SPY', 'EFA', 'EEM', 'LQD'] # better performance ...
    cash_assets = ['SHY', 'IEF', 'TLT']
    # _____________________________________________________________________________________________
    # vanguard
    # risk_assets = ['VOO', 'VEA', 'VWO', 'BND']  # LQD or AGG
    # cash_assets = ['SHY', 'IEF', 'TLT']
    # _____________________________________________________________________________________________
    # leveraged x2
    # risk_assets = ['SSO', 'EFO', 'EET', 'LQD']  # leveraged x2, x3 is a bad idea
    # cash_assets = ['SHY', 'UST', 'UBT']

    # risk_assets = ['SPY', 'EFA', 'EEM', 'LQD']
    # cash_assets = ['SHY', 'IEF', 'TLT']

    # ISQA iShares MSCI EAFE ETF ShS WKN 534355

    # risk_assets = [#'EXSA',  # iShares EuroStoxx 600 DE0002635307
                   #'LYPS',  # Lyxor S&P 500 LU0496786574
                   # 'X014',  # ComStage MSCI Pacific TRN LU0392495023
                   # 'LYM7',  # Lyxor MSCI Emerging Markets FR0010429068
                   # 'AGG' # 'EUN4',  # iShares Euro Aggregate Bond IE00B3DKXQ41
                  # ]
    # cash_assets = [#'SHY',
                   # 'EUN5',  # iShares Core Euro Corporate Bond IE00B3F81R35
                   # 'IS0Y',  # iShares Euro Corporate Bond Interest Rate Hedged IE00B6X2VY59
                   # 'IBCA',  # iShares Euro Government Bond 1-3yr IE00B14X4Q57
                   # # 'SXRP',  # iShares Euro Government Bond 3-7yr IE00B3VTML14
                   # 'IBCM',  # iShares Euro Government Bond 7-10yr IE00B1FZS806
                   # 'IBCL',  # iShares Euro Government Bond 15-30yr IE00B1FZS913
                   # # 'EUN8',  # iShares Euro Government Bond 10-15yr IE00B4WXJH41
                  # ]
    # cash_assets = ['SHY', 'LQD', 'IEF', 'TLT', 'HYG', 'BNDX', 'EMB']
    risk_assets = ['SPY', 'EFA', 'EEM', 'LQD', 'AGG'] # better performance ...
    ignore_risk = ['EZU', 'QQQ', 'IWM']
    cash_assets = ['SHY', 'IEF', 'TLT'] 
    # ignore_risk = ['QQQ', 'IWM', 'EPP', 'EZU']

    # risk_assets = ['QLD', 'EET', 'LQD']  # leveraged x2, x3 is a bad idea
    # ignore_risk = ['SSO', 'EFO', 'EET', 'LQD']  # leveraged x2, x3 is a bad idea
    # ignore_risk = ['QLD']
    # cash_assets = ['SHY', 'UST', ]
    # cash_assets = ['SHY', 'UST', 'UBT']


    risk_assets += ignore_risk

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
    alphavantage_key = 'HR91R8PS4P19GES7'  # flo.rieger@gmx.net

    data_start = pd.to_datetime('1999-01-01')
    # data_end = pd.to_datetime('2018-04-10')
    cash_start = 10e3
    custom_start_date = pd.to_datetime('2009-01-01')
    # custom_end_date = pd.to_datetime('2012-01-01')
    try:
        start_date = custom_start_date
    except:
        start_date = None

    try:
        end_date = custom_end_date
    except:
        end_date = None

    saving_monthly = 0

    asset_tickers = VAA_Strategy.risk_assets + VAA_Strategy.cash_assets

    date = DateSync(data_start)

    # assert data files are present, else download
    data_dir = 'data'
    if not os.path.isdir(data_dir):
        os.mkdir(data_dir)

    assets = []
    ts = TimeSeries(key=alphavantage_key, output_format='pandas')

    for ticker_name in asset_tickers:
        ticker_file = '{}/{}.dat'.format(data_dir, ticker_name)

        if not os.path.isfile(ticker_file):  # get data if not available
            data, meta_data = ts.get_daily_adjusted(symbol=ticker_name, outputsize='full')
            data.to_json(ticker_file)
        else:
            log.debug(f'using available ticker file {ticker_file}')

        asset = Asset(ticker_name, pd.read_json(ticker_file), date)  # create asset object
        # asset.data.columns = ['_'.join(c.split()[1:]).lower() for c in asset.data.columns]  # make headers lower-case
        # log.debug(f'original columns: {asset.data.columns}')
        asset.data.columns = ['open', 'high', 'low', 'unadjusted_close', 'close', 'volume', 'dividend_amount', 'split_coefficient']
        # log.debug(f'renamed columns: {asset.data.columns}')
        assets.append(asset)
                         
    latest_asset = max(assets, key=lambda a: a.data.index[0])  # starts the latest
    ultimo = pd.DataFrame(index=latest_asset.last_bussiness_days)  # for bool slicing
    start = start_date if start_date else latest_asset.data.index[0]
    log.debug('start = {} '.format(start))
    end = end_date if end_date else latest_asset.data.index[-1]
    last_bussiness_days = ultimo[ultimo.index > start]
    latest_start = last_bussiness_days.index[12]
    # assert latest_start < start, f'cannot start from {start.date()} but only from {latest_asset.data.index[0]}'
    log.debug('latest_start = {} '.format(latest_start))
    last_bussiness_days = last_bussiness_days[12:]
    date.date = latest_start

    # create strategy object
    strategy = VAA_Strategy(cash_start, assets, date)  # start money

    duration = 0
    start = None

    for idx, day in enumerate(last_bussiness_days.index):
        start = day if not start else start

        if end_date and day > end_date:
            break
        log.debug('_'*100)
        log.debug(f'last trading day: {day}')
        strategy.status(log.debug)
        date.date = day  # update all dates

        log.info(f'savings: {saving_monthly}')
        strategy.cash += saving_monthly

        # gather indicators
        risk_indicators = {strategy.assets[a].name: strategy.assets[a].i_13612W 
                           for a in strategy.risk_assets}
        cash_indicators = {strategy.assets[a].name: strategy.assets[a].i_13612W 
                           for a in strategy.cash_assets}


        bad_indicator = {key:i for key, i in risk_indicators.items() if i < 0.0}
        bad_indicator = {key:i for key, i in risk_indicators.items() if i < 0.0 and not key in strategy.ignore_risk}
        good = not bad_indicator
        g_str = 'good' if good else f'bad {tuple(bad_indicator.keys())}'
        log.debug(f'indicators: RISK:{", ".join([f"{k} {int(v)}" for k,v in risk_indicators.items()])} > {g_str}')
        log.debug(f'            CASH:{", ".join([f"{k} {int(v)}" for k,v in cash_indicators.items()])}')

        if good:
            asset_class = risk_indicators
        else:
            asset_class = cash_indicators

        best_asset = max(asset_class, key=lambda k: asset_class[k])  # in respective class
        if best_asset in ['LQD', 'AGG']:
            best_asset = max(cash_indicators, key=lambda k: cash_indicators[k])  # in respective class

        log.debug(f'best_asset = {best_asset} ')

        # ensure old position is the best or sell it
        if not strategy.positions:
            # log.debug('no positions, starting or in cash')
            pass

        elif not strategy.positions[-1].asset.name == best_asset:
            strategy.sell_position(strategy.positions[-1])
        
        if not strategy.positions:  # either we're still in the best position or sold the old one
            amount = int((strategy.cash-Position.commission)/strategy.assets[best_asset].close)
            # if not best_asset in ['LQD']:
            strategy.buy_position(best_asset, amount)

        strategy.high = max(strategy.value, strategy.high)
        strategy.maxDD = max((strategy.high - strategy.value)/strategy.high*100, strategy.maxDD)

        strategy.update_plotdata()
        # if idx > 3:
            # sys.exit(0)
            # strategy.plotdata
        strategy.status()

        # pos = strategy.positions[-1]
        # dat = pos.asset.data
        # end_tp = last_bussiness_days.index[min(idx+1, len(last_bussiness_days)-1)] 
        # max_price = max(dat.loc[day:end_tp, 'close'])
        # end_price = dat.loc[end_tp, 'close']
        # log.warning(f'{pos.buy_price}, {max_price}, {end_price} {end_price/pos.buy_price*100-100:.0f}')
        
        # inner month trading ...
        # actually a end-of-day stop loss ...
        loss_percent=0.95
        pos = strategy.positions[-1]
        dat = pos.asset.data
        end_tp = last_bussiness_days.index[min(idx+1, len(last_bussiness_days)-1)] 
        closes = dat.loc[day:end_tp, 'close']
        # for idx, close in enumerate(closes):
            # max_close = max(closes[:idx]) if not closes[:idx].empty else 1
            # if close < loss_percent * max_close:
                # end_price = dat.loc[end_tp, 'close']
                # print(f'stop-loss after {idx} days ({loss_percent}%) : buy={pos.buy_price} SL={close} end={end_price}')
                # gain_actual = close - pos.buy_price
                # gain_possible = end_price - pos.buy_price
                # profit = (gain_actual - gain_possible)*pos.amount/strategy.value
                # # print(f'actual loss {loss_actual:.2f} possible loss {loss_possible:.2f}')
                # verdict = 'GOOD' if close > end_price else 'BAD'
                # # print('{} {:.2f}'.format(verdict, profit))
                # strategy.sell_position(strategy.positions[-1])
                # # strategy.stop_losses.append((verdict, profit))
                # break

        strategy.status()
        # sys.exit(0)

    duration = idx/12  # trading months /12


    if strategy.positions: # sell at end of time
        strategy.sell_position(strategy.positions[-1])

    strategy.status()
    cash_end = strategy.cash

    log.debug(f'duration {duration} years')
    CAGR = ((cash_end/cash_start)**(1/duration)-1)*100

    log.info('')
    log.info('-'*100)
    log.info(f'risk           {", ".join(strategy.risk_assets)}')
    log.info(f'cash           {", ".join(strategy.cash_assets)}')
    log.info('----------------------------------------------------')
    log.info(f'start value    {cash_start:.0f} {start.date()}')
    log.info(f'final value    {cash_end:.0f} {(cash_end/cash_start-1)*100:+.0f}%')
    log.info('----------------------------------------------------')
    log.info(f'CAGR           {CAGR:.2f}%')
    log.info(f'max drawdown   {strategy.maxDD:.0f}%')
    log.info(f'worst month    {strategy.worst_month:.0f}%')
    log.info(f'best month    {strategy.best_month:.0f}%')
    log.info('----------------------------------------------------')

    log.info('asset profit:')
    for asset in assets:
        all_positions = [f'{int(p.profit)}/{int(p.profit_percent)}%' for p in asset._positions]
        log.info(f'  {asset.name}: {sum(p.profit for p in asset._positions):.0f}: {all_positions}')

    # log.info('stop-losses {sum(p for v, p in strategy.stop_losses)}:')
    # [log.info(f'  {v}: {p}') for v, p in strategy.stop_losses]
    # strategy.plotdata.plot()
    d = strategy.plotdata
    d.loc[:, ['value'] + VAA_Strategy.risk_assets + VAA_Strategy.cash_assets].plot()
    plt.yscale('log')
    plt.ylim(cash_start*0.9, strategy.cash*1.1)
    log.info('time in secs {:.2f}'.format(time.time()-start_time))
    # d.loc[:, 'maxDD'].plot()
    plt.show()





# todo test with german bonds
# todo plotting
# todo sharpe ratio
# done leveraged 
# todo stopp-loss
# done taxes
# todo freibetrag
# todo lazy trading
# done profile this, printing_update is bad
# todo buy in last week
# done exclude EEM from indicators nope
# done never buy LQD/AGG not much influence ...








