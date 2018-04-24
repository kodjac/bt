#!/usr/bin/python3
import datetime
import dateutil
import logging
import math
import os
import pandas as pd # for last business day of the month
import subprocess
import sys
from collections import namedtuple

sys.path.append(os.path.join(os.path.dirname(__file__), 'backtrader.git'))
import backtrader as bt

logging.basicConfig(format='%(levelname)s %(funcName)s | %(message)s', level=logging.DEBUG)
log = logging.getLogger()

asset = namedtuple('asset', 'name, indicator, data')

def dbg(func, no_cols = 4, width=130):
    log.debug('_'*width, '\n', func, '\n', type(func))
    attributes = dir(func) + ['TEST']
    lines_per_col = math.floor(len(attributes)/no_cols)
    remainder = (len(attributes) - lines_per_col*no_cols)%3
    attributes += ['']*(no_cols-remainder)

    lines_per_col = math.floor(len(attributes)/no_cols) # update the no of lines
    print_str = '{}:{}s{} '.format('{', math.floor(width/no_cols), '}')*no_cols

    for i in range(lines_per_col):
        line = [attributes[i + lines_per_col*col] for col in range(no_cols)]
        print(print_str.format(*line))


def get_last_bussiness_days(data):
    to_date = data.num2date(data.datetime[0])
    from_date = data.num2date(data.datetime[-data.buflen()+1])
    last_bussiness_days = [d.date() for d in pd.date_range(from_date, to_date, freq='BM')]
    return last_bussiness_days


class FixedCommisionScheme(bt.CommInfoBase):
    ''' This is a simple fixed commission scheme '''
    params = (
        ('commission', 6.5),
        # ('commission', 0.0),
        ('stocklike', True),
        ('commtype', bt.CommInfoBase.COMM_FIXED),
        )

    def _getcommission(self, size, price, pseudoexec):
        return self.p.commission


class Momentum13612W(bt.Indicator):
    lines = ('momentum',)
    # plotinfo(dict(plothlines=[0.0]))

    def __init__(self):
        self.lookback_period = 300  # tolerance ...
        self.addminperiod(self.lookback_period)
        log.debug('dat = {} {} '.format(self.data._name, self.data, self.datas))

        self.last_bussiness_days = get_last_bussiness_days(self.data)

    def next(self):
        # today = self.data.num2date(self.data.datetime[0]).date()
        # assert today in self.last_bussiness_days, f'indicator is only valid on last business day: {today}'

        # gather all end-of-month indices from now on backwards
        emc_idx = [i for i in range(0, -self.lookback_period, -1) 
                   if self.data.num2date(self.data.datetime[i]).date() in self.last_bussiness_days]

        emc = []
        for i in range(0, -self.lookback_period, -1):  # iterate backwards in time 
            date = self.data.num2date(self.data.datetime[i]).date()  # the data points date
            close = self.data.close[i]  # the closing price

            if date in self.last_bussiness_days:
                emc.append(close)
        assert len(emc) >= 13, 'not enough end-of-month closing prices found'
        p0, p1, p3, p6, p12 = emc[0], emc[1], emc[3], emc[6], emc[12]  # map for nice formula

        # assign the momentum value to the linebuffer
        self.lines.momentum[0] = round(
                12*(p0/p1 - 1) + 4*(p0/p3 - 1) + 2*(p0/p6 - 1) + (p0/p12 - 1), 2)
        # log.debug(f'{self.data._name} {self.lines.momentum[0]}')



class VAA(bt.Strategy):
    params = (
              ('risk', ['SPY', 'EFA', 'EEM', 'AGG']),
              ('cash', ['LQD', 'IEF', 'SHY']),
              ('lazytrade', False),
             )


    def log(self, txt, doprint=True):
        current_dt = self.datas[0].datetime.date(0)
        if doprint:
            log.debug(f'{current_dt.isoformat()} {txt}')


    def __init__(self):
        self.order = None
        self.equity_position = None
        self.last_bussiness_days = get_last_bussiness_days(self.data)

        self.indicators = {}
        for dat in self.datas:
            log.debug(f'adding indicator for: {dat._name} {dat}')
            self.indicators[dat._name] = Momentum13612W(dat)

        self.risk_assets = {}
        self.cash_assets = {}
        for d in self.datas:
            this = asset(d._name, self.indicators[d._name], d)
            if this.name in self.p.risk:
                self.risk_assets[this.name] = this
            elif this.name in self.p.cash:
                self.cash_assets[this.name] = this

        for key, aclass in [['risk', self.risk_assets], ['cash', self.cash_assets]]:
            log.debug(f'{key}:')
            [log.debug(f'  > {key}') for key in aclass]

    def notify_order(self, order):
        # is called for every order status change: Submitted, Accepted, Completed
        # self.order = None  # no more order, why here?
        # log(f'order {order.getstatusname()}')
        if order.status == order.Completed:
            order_type = 'BUY' if order.isbuy() else 'SELL'
            log.debug(f'{order_type} order {order.getstatusname()}')
            self.order = None if order.issell() else self.order


    def notify_trade(self, trade):
        # its 0 for buying
        if trade.isclosed:
            log.debug(f'operation profit {trade.pnlcomm:.2f} ({trade.pnl})')


    def next(self):
        closes = {d._name: round(d.close[0], 2) for d in self.datas}
        log.debug('{} close {}, ({:.2f})'.format(self.data.num2date(self.data.datetime[0]).date(),
                closes, cerebro.broker.getvalue()))
        today = self.data.num2date(self.data.datetime[0]).date()

        if today in self.last_bussiness_days:
            log.debug('_'*60)
            log.info('end of month')
            for key in self.indicators.keys():
                log.debug(f'{key}: 13612W = {self.indicators[key].momentum}')

            risk_indicators_good = {key: self.indicators[key].momentum[0] > 0.0 
                                    for key in self.indicators.keys()}
            # cash_indicators_good = {key: self.indicators[key].momentum[0] > 0.0 
                                    # for key in self.indicators.keys()}
            good = not (False in risk_indicators_good.values())  # not one of the indicators negative
            log.debug('risk_indicators_good = {} '.format(risk_indicators_good))
            log.debug('equity_position = {} '.format(self.equity_position))

            # asset_class = self.p.risk if good else self.p.cash
            asset_class = risk_indicators_good
            log.debug('asset_class = {} '.format(asset_class))
            best_asset = sorted(risk_indicators_good.items(), key=lambda x: x[1],
                                reverse=True)[0][0]  # get highest momentum key
            log.debug('best_asset = {} '.format(best_asset))
            if self.equity_position == best_asset:
                log.debug('already invested in best asset: {}'.format(self.equity_position))
                pass # everything is fine
            else:
                log.debug('not invested in best asset {} but in {}'.format(
                          best_asset, self.equity_position))
                if self.equity_position:  # only if already bought something
                    log.debug(f'selling old asset {self.equity_position}')
                    self.sell()
                log.debug(f'buying best asset {best_asset}')
                self.buy()
                self.equity_position = best_asset
            
            # TODO create named tuple, asset(symbol, price, momentum)
        sys.exit(0)


    def start(self):
        log.debug('_'*80)
        log.debug('VAA-G{} start value {:.2f} EUR'.format(
            len(self.params.risk), self.broker.getvalue()))


    def stop(self):
        log.debug('VAA-G{} end value {:.2f} EUR'.format(
            len(self.params.risk), self.broker.getvalue()))


if __name__ == '__main__':

    alphavantage_key = 'HR91R8PS4P19GES7'  # flo.rieger@gmx.net
    # log.debug('_'*80)
    cerebro = bt.Cerebro()
    cerebro.broker.setcash(5500)
    cerebro.broker.addcommissioninfo(FixedCommisionScheme())
    cerebro.addstrategy(VAA)
    # cerebro.optstrategy(VAA)

    from_date = dateutil.parser.parse('2006-01-01')
    to_date = dateutil.parser.parse('2010-04-01')

    data_dir = 'VAA_data'
    if not os.path.isdir(data_dir):
        os.mkdir(data_dir)

    for ticker_name in ('SPY', 'AGG', 'SHY'):# 'EFA', 'EEM', 'AGG', 'LQD', 'IEF', 'SHY'):
        # data = bt.feeds.YahooFinanceData(
                # dataname=ticker_name,
                # fromdate=datetime.datetime(2016, 1, 1),
                # todate=datetime.datetime(2017, 12, 31),
                # )
        # python yahoodownload.py --ticker EFA --fromdate 2000-01-01 --todate 2017-12-30 --outfile ~/bt/efa.dat
        ticker_file = '{}/{}.dat'.format(data_dir, ticker_name)
        log.debug('ticker_file = {} '.format(ticker_file))

        if not os.path.isfile(ticker_file):  # get data if not available
            subprocess.call(['python',
                             './backtrader.git/tools/yahoodownload.py',
                             '--ticker', ticker_name,
                             '--fromdate', str(from_date.date()),
                             '--todate', str(to_date.date()),
                             '--outfile', ticker_file,
                             ])
                         
        data = bt.feeds.YahooFinanceCSVData(dataname=ticker_file)

        cerebro.adddata(data, name=ticker_name)

    cerebro.run()
    # cerebro.plot()



