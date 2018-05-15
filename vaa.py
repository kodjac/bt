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
    def __init__(self, date:pd.Timestamp=None):
        self.date = date if date else pd.to_datetime('1900-01-01')

    @property
    def now(self):
        return self.date


# _________________________________________________________________________________________________
class Asset():
    def __init__(self, name:str, date:DateSync, cash:float):
        self.name = name

        self.data_dir = 'data'
        self.data_file = '{}/{}.dat'.format(self.data_dir, self.name)
        self.get_data()  # panda dataframe as specified

        self._date = date  # a DateSync object

        self.y0 = cash - self.close

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

    def get_data(self):
        alphavantage_key = 'HR91R8PS4P19GES7'  # flo.rieger@gmx.net
        if not os.path.isdir(self.data_dir):  # assert data dir exists
            os.mkdir(self.data_dir)

        if not os.path.isfile(self.data_file):  # get data if not available
            ts = TimeSeries(key=alphavantage_key, output_format='pandas')
            # daily adjusted for "correct" values for backtesting
            data, meta_data = ts.get_daily_adjusted(symbol=self.name, outputsize='full')
            data.to_json(self.data_file)  # store the 
        else:
            log.debug(f'using available ticker-data file {self.data_file}')

        self.data = pd.read_json(data_file)  # load the data

        # modify column headers
        # log.debug(f'original columns: {self.data.columns}')
        # self.data.columns = ['_'.join(c.split()[1:]).lower() for c in self.data.columns]  # lower
        self.data.columns = ['open', 'high', 'low', 'unadjusted_close', 'close', 'volume',
                             'dividend_amount', 'split_coefficient']
        # log.debug(f'renamed columns: {self.data.columns}')

    def buy_position(self, amount=None, cash=None):
        assert bool(amount) ^ bool(cash), 'need equity amount or cash for buying'  # ^ : xor
        if cash:  # calculate amount
            amount = self.get_amount(cash)

        new_position = Position(self, amount)
        self._positions.append(new_position)
        log.info(f'bought position {self.name}x{amount} for total {new_position.value:.2f}')
        return new_position.buy_costs

    def get_amount(self, cash):
        return int((cash - Position.commission)/self.close)

    @property
    def i_13612W(self):
        # assume only called on a last_bussiness_day
        start_idx = self.last_bussiness_days.index(self.today)
        end_of_months = list(reversed(self.last_bussiness_days[start_idx-12:start_idx+1]))
        # log.debug(f'end_of_months [{len(end_of_months)}]= {end_of_months} ')

        emc = [self.data.loc[d].close for d in end_of_months]
        p0, p1, p3, p6, p12 = emc[0], emc[1], emc[3], emc[6], emc[12]  # map for nice formula

        # assign the momentum value to the linebuffer
        return (12*(p0/p1 - 1) + 4*(p0/p3 - 1) + 2*(p0/p6 - 1) + (p0/p12 - 1))*10

    def i_momentum(self, lookback=10):
        start_idx = self.last_bussiness_days.index(self.today)
        end_of_months = list(reversed(self.last_bussiness_days[start_idx-12:start_idx+1]))
        emc = [self.data.loc[d].close for d in end_of_months]
        return round(10*(emc[0] - emc[lookback]), 0)


# _________________________________________________________________________________________________
class Position():
    commission = 6.5  # commission per buy/sell operation, not accumulating
    def __init__(self, asset:Asset, amount:int, commission=commission, close=True):
        self.asset = asset
        self.amount = amount
        self.buy_date = asset.today
        self.buy_price = asset.close if close else asset.open
        self.sell_date = None
        self.sell_price = None

    @property
    def buy_costs(self):
        # total cost for buying, subtract from total cash
        return self.value + self.commission

    @property
    def active(self):
        return not bool(self.sell_price)

    @property
    def value(self):
        return self.amount * self.asset.close

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

    def sell(self):
        self.sell_date = self.asset.today
        self.sell_price = self.asset.close
        log.info(f'sold position {self.name} profit {self.profit:.0f}/{self.profit_percent:.1f}%')
        # positions return, add to total cash
        return self.value - self.commission


# _________________________________________________________________________________________________
class Strategy():
    def __init__(self, cash, assets:list, date:DateSync):
        self.assets = {a: Asset(a, date, cash) for a in self.assets}  # dict of Asset objects
        self._date = date  # DataSync object
        self.cash = cash

        self.plotdata = None
        self.high = self.cash
        self.maxDD = 0
        self.stop_losses = []
        self.update_plotdata()

    def update(self):
        self.update_metrics()
        self.update_plotdata()

    def update_metrics(self):
        self.high = max(self.value, self.high)
        self.maxDD = max((self.high - self.value)/self.high*100, self.maxDD)

    def update_plotdata(self):
        plotdata = {a.name: a.close * a.y0 for a in self.assets.values()} 
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

    @property
    def latest_asset(date):
        return max(self.assets, key=lambda a: a.data.index[0])

    def execute(self, date):
        pass   # logic here


# _________________________________________________________________________________________________
class VAA_Strategy(Strategy):
    # _____________________________________________________________________________________________
    ignore_indicator = []
    # standard
    risk_assets = ['SPY', 'EFA', 'EEM', 'AGG']
    # risk_assets = ['SPY', 'EFA', 'EEM', 'LQD'] # better performance ...
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
    risk_assets = ['AGG', 'EFA', 'EEM', 'SPY']
    ignore_indicator = ['QQQ', 'IWM']
    cash_assets = ['IEF', 'TLT']
    # cash_assets = ['SHY']
    # ignore_indicator = ['QQQ', 'IWM', 'EPP', 'EZU']

    # risk_assets = ['QLD', 'EET', 'LQD']  # leveraged x2, x3 is a bad idea
    # ignore_indicator = ['SSO', 'EFO', 'EET', 'LQD']  # leveraged x2, x3 is a bad idea
    # ignore_indicator = ['QLD']
    # cash_assets = ['SHY', 'UST', ]
    # cash_assets = ['SHY', 'UST', 'UBT']
    risk_assets += ignore_indicator

    def __init__(self, cash, assets:list, date:DateSync):
        super().__init__(cash, assets, date)


    def execute(self, date):
        pass


# _________________________________________________________________________________________________
def read_csv(file_path):
    return pd.read_csv(file_path, index_col=0, usecols=[0, 1, 2, 3, 4], parse_dates=True)

# _________________________________________________________________________________________________
if __name__ == '__main__':

    start_cash = 10e3
    monthly_savings = 0
    custom_start = pd.to_datetime('2014-01-01')

    date = DateSync()
    strategy = VAA_Strategy(start_cash, date)

    try:  # fails for no custom_start_date
        earliest_start = strategy.latest_asset.index[0]
        start_date = custom_start if custom_start > earliest_start else earliest_start
    except:
        start_date = strategy.earliest_start

    # due to indicators we need more pre-data ...
    last_bussiness_days = pd.DataFrame(index=strategy.latest_asset.last_bussiness_days)  # for bool slicing
    last_bussiness_days = last_bussiness_days[last_bussiness_days.index > start_date]
    last_bussiness_days = last_bussiness_days[12:]  # a year of pre-data

    start_date = last_bussiness_days.index[0]
    date.date = start_date

    protections = []

    duration = 0

    # todo execute(start), move date thing to here

    for idx, day in enumerate(last_bussiness_days.index):
        log.debug('_'*100)
        log.debug(f'last trading day: {day}')

        date.date = day  # update all dates

        # log.info(f'savings: {saving_monthly}')
        strategy.cash += saving_monthly

        # gather indicators
        indicator = 2
        if  indicator == 1:
            risk_indicators = {strategy.assets[a].name: strategy.assets[a].i_13612W 
                               for a in strategy.risk_assets}
            cash_indicators = {strategy.assets[a].name: strategy.assets[a].i_13612W 
                               for a in strategy.cash_assets}

        elif indicator == 2:
            risk_indicators = {strategy.assets[a].name: strategy.assets[a].i_momentum(3) 
                               for a in strategy.risk_assets}
            cash_indicators = {strategy.assets[a].name: strategy.assets[a].i_momentum(3)
                               for a in strategy.cash_assets}

        bad_indicator = {key:i for key, i in risk_indicators.items() if i < 0.0 and not key in strategy.ignore_indicator}
        good = not bad_indicator
        g_str = 'good' if good else f'bad {tuple(bad_indicator.keys())}'

        # evaluate predictions
        end_tp = last_bussiness_days.index[min(idx+1, len(last_bussiness_days)-1)] 

        profits = []
        best_asset = max(risk_indicators, key=lambda k: risk_indicators[k])  # in respective class
        for a in strategy.assets.values():
            start_price = a.data.loc[day].close
            end_price = a.data.loc[end_tp].close 
            profit = (end_price - start_price)/start_price*100
            
            if a.name == best_asset:
                name = f'*{a.name}*'
                risk_assets = strategy.risk_assets + [name]
                possible_profit = profit
            else:
                name = a.name

            profits.append((name, profit))

        log.debug(f'indicators RISK: {", ".join([f"{k:5s} {v:3.0f}" for k,v in risk_indicators.items()])} > {g_str} > {best_asset}')
        log.debug(f'indicators CASH: {", ".join([f"{k:5s} {v:3.0f}" for k,v in cash_indicators.items()])}')
        # if not good and risk_indicators['AGG'] < 0:
            # log.debug(f'indicators RISK: {", ".join([f"{k:5s} {v:3.0f}" for k,v in risk_indicators.items()])} > {g_str}')
            # log.debug(f'returns    RISK: {", ".join([f"{k:5s} {v:3.0f}" for k,v in profits if k in risk_assets])}')
            # log.debug(f'indicators CASH: {", ".join([f"{k:5s} {v:3.0f}" for k,v in cash_indicators.items()])}')
            # log.debug(f'returns    CASH: {", ".join([f"{k:5s} {v:3.0f}" for k,v in profits if k in strategy.cash_assets])}')
            # log.debug('risk_assets = {} '.format(risk_assets))

            # protections.append(possible_profit)



        if good:
            asset_class = risk_indicators
        else:
            asset_class = cash_indicators

        # best_asset = max(asset_class, key=lambda k: asset_class[k])  # in respective class
        sorted_indicators = sorted(asset_class, key=lambda k: asset_class[k])
        best_asset = sorted_indicators[-1]
        # if best_asset in risk_assets:
        # todo remove heavy dependency on last month, use decreasingly weighted exponential
        # todo test R^2, i.e., deviation from exponential increase as measure
            # best_asset = 'QQQ'
        if best_asset in ['LQD', 'AGG']:
            best_asset = max(cash_indicators, key=lambda k: cash_indicators[k])  # in respective class

        # ensure old position is the best or sell it
        if not strategy.positions:
            # log.debug('no positions, starting or in cash')
            pass

        elif not strategy.positions[-1].asset.name == best_asset:
            strategy.sell_position(strategy.positions[-1])
            pass
        
        if not strategy.positions:  # either we're still in the best position or sold the old one
            amount = int((strategy.cash-Position.commission)/strategy.assets[best_asset].close)
            # if not best_asset in ['SHY']:
            strategy.buy_position(best_asset, get_amount(strategy.assets[best_asset], strategy.cash))

        strategy.update()
        # if idx > 3:
            # sys.exit(0)
            # strategy.plotdata
        # strategy.status()

        # pos = strategy.positions[-1]
        # dat = pos.asset.data
        # end_tp = last_bussiness_days.index[min(idx+1, len(last_bussiness_days)-1)] 
        # max_price = max(dat.loc[day:end_tp, 'close'])
        # end_price = dat.loc[end_tp, 'close']
        # log.warning(f'{pos.buy_price}, {max_price}, {end_price} {end_price/pos.buy_price*100-100:.0f}')
        
        # inner month trading ...
        # actually a end-of-day stop loss ...
        # loss_percent=0.95
        # # pos = strategy.positions[-1]
        # dat = pos.asset.data
        # end_tp = last_bussiness_days.index[min(idx+1, len(last_bussiness_days)-1)] 
        # closes = dat.loc[day:end_tp, 'close']
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

        # strategy.status()
        # sys.exit(0)

    log.debug(' ')
    log.debug('#'*100)
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
    log.info(f'start value    {cash_start:.0f} {start_date.date()}')
    log.info(f'final value    {cash_end:.0f} {(cash_end/cash_start-1)*100:+.0f}%')
    log.info('----------------------------------------------------')
    log.info(f'CAGR           {CAGR:.2f}%')
    log.info(f'max drawdown   {strategy.maxDD:.0f}%')
    log.info(f'worst month    {strategy.worst_month:.0f}%')
    log.info(f'best month    {strategy.best_month:.0f}%')
    log.info('----------------------------------------------------')

    log.info('asset profit:')
    for asset in assets:
        # all_positions = [f'{int(p.profit)}/{int(p.profit_percent)}%' for p in asset._positions]
        all_positions = ' '.join([f'{int(p.profit_percent)}' for p in asset._positions])
        log.info(f'  {asset.name}: {sum(p.profit for p in asset._positions):.0f}: %: {all_positions}')


    # log.info('stop-losses {sum(p for v, p in strategy.stop_losses)}:')
    # [log.info(f'  {v}: {p}') for v, p in strategy.stop_losses]
    # strategy.plotdata.plot()
    d = strategy.plotdata
    d.loc[:, ['value'] + VAA_Strategy.risk_assets + VAA_Strategy.cash_assets].plot()
    plt.yscale('log')
    # plt.ylim(cash_start*0.9, strategy.cash*1.1)
    log.info('time in secs {:.2f}'.format(time.time()-start_time))
    # d.loc[:, 'maxDD'].plot()

    # percent_good = len([1 for p in protections if p < 0])/len(protections)*100
    # log.info(f'AGG predictions {percent_good:.0f}% GOOD')
    # log.info(f'overall_gain    {-sum(protections):.1f}%')
    # log.info(f'max_protection  {min(protections):.1f}')
    # log.info(f'max_loss        {max(protections):.1f}')
    # [log.debug(f' {p}') for p in protections]






    plt.show()






'''
T test with german bonds
T sharpe ratio
T plotting
T freibetrag, track profit/losses
T evaluate spoiler efficiency ignore stocks < ignoring stocks is better ...
T test with Vanguard assets:VTI VO  VB      SHY BND TLT TIP MUB     VEU VSS VWO     VNQ DBC GLD
T buy in last week

d evaluate spoiler efficiency AGG/LQD > AGG is better 
d second best asset is a bad idea, CAGR 17 > 11
d taxes
d stopp-loss > bad, months end almost always  higher ...
d simple momentum with different lookback periods > all worse
d profile this, printing_update is bad
d never buy LQD/AGG > not much influence
d leveraged 
d lazy trading > only .5% difference without commission
d exclude EEM from indicators > often triggers first, not a good idea
'''









