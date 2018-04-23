#!/usr/bin/python3
import backtrader as bt
import datetime
import dateutil
import logging
import math
import os
import pandas as pd # for last business day of the month
import subprocess
import sys

logging.basicConfig(format='%(levelname)s %(funcName)s | %(message)s', level=logging.DEBUG)
log = logging.getLogger()

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
    # dbg(data)
    # date order is reversed only for yahoo ?!?!
    to_date = data.num2date(data.datetime[0])
    from_date = data.num2date(data.datetime[-data.buflen()+1])
    # log.debug('from_date = {} '.format(from_date))
    # log.debug('to_date = {} '.format(to_date))
    last_bussiness_days = [d.date() for d in pd.date_range(from_date, to_date, freq='BM')]
    # log.debug('last business days:{}'.format(last_bussiness_days))
    # log.debug('last business days:')
    # [log.debug('  {}'.format(d)) for d in last_bussiness_days]
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
    # params = {'p1'
    lines = ('momentum',)
    # plotinfo(dict(plothlines=[0.0]))

    def __init__(self, data):
        self.lookback_period = 300  # tolerance ...
        self.addminperiod(self.lookback_period)
        self.datas[0] = data

        self.last_bussiness_days = get_last_bussiness_days(self.data)
        super().__init__()

    def next(self):
        # today = self.data.num2date(self.data.datetime[0]).date()
        # assert today in self.last_bussiness_days, 'indicator is only valid on last business day: {}'.format(today)

        # gather all end-of-month indices from now on backwards
        emc_idx = [i for i in range(0, -self.lookback_period, -1) 
                   if self.data.num2date(self.data.datetime[i]).date() in self.last_bussiness_days]

        emc = []
        for i in range(0, -self.lookback_period, -1):  # iterate backwards in time 
            date = self.data.num2date(self.data.datetime[i]).date()  # the data points date
            close = self.data.close[i]  # the closing price

            if date in self.last_bussiness_days:
                emc.append(close)
                # log.debug('{}: {}'.format(date, close))
        # log.debug('emc [{}] = {} '.format(len(emc), emc))
        assert len(emc) >= 13, 'not enough end-of-month closing prices found'
        p0, p1, p3, p6, p12 = emc[0], emc[1], emc[3], emc[6], emc[12]  # map for nice formula

        # assign the momentum value to the linebuffer
        self.lines.momentum[0] = 12*(p0/p1 - 1) + 4*(p0/p3 - 1) + 2*(p0/p6 - 1) + (p0/p12 - 1)



class VAA(bt.Strategy):
    params = (
              ('risk', ['SPY', 'EFA', 'EEM', 'AGG']),
              ('cash', ['LQD', 'IEF', 'SHY']),
              ('lazytrade', False),
             )


    def log(self, txt, doprint=True):
        current_dt = self.datas[0].datetime.date(0)
        if doprint:
            log.debug('{} {}'.format(current_dt.isoformat(), txt))


    def __init__(self):
        self.order = None
        self.equity_position = False
        self.last_bussiness_days = get_last_bussiness_days(self.data)

        self.indicators = {}
        for dat in self.datas:
            log.debug('adding indicator for: {}'.format(dat._name))
            self.indicators[dat]['13612W'] = Momentum13612W(dat)

    def notify_order(self, order):
        # is called for every order status change: Submitted, Accepted, Completed
        # self.order = None  # no more order, why here?
        # log('order {}'.format(order.getstatusname()))
        if order.status == order.Completed:
            order_type = 'BUY' if order.isbuy() else 'SELL'
            log.debug('{} order {}'.format(order_type, order.getstatusname()))
            self.order = None if order.issell() else self.order


    def notify_trade(self, trade):
        # its 0 for buying
        if trade.isclosed:
            log.debug('operation profit {:.2f} ({})'.format(trade.pnlcomm, trade.pnl))


    def next(self):
        log.debug('close {:.2f}, ({:.2f})'.format(self.dclose[0], cerebro.broker.getvalue()))
        today = self.data.num2date(self.data.datetime[0]).date()
        if today in self.last_bussiness_days:
            log.info('end of month')
            mom = self.indicators[self.datas[0]].momentum[0]
            log.debug('mom = {} '.format(mom))
            mom = self.indicators[self.datas[1]].momentum[0]
            log.debug('mom2 = {} '.format(mom2))
            log.debug(self.equity_position)

            if mom > 0.0 and not self.equity_position:
                log.debug('>BUY')
                self.equity_position = True # fixme dependent ...
                self.buy()  #fixme how much

            elif mom < 0.0 and self.equity_position:
                log.debug('>SELL')
                self.equity_position = False # fixme dependent ...
                self.sell()

            else:
                log.debug('do nothing (mom={}, position={}...'.format(mom, self.equity_position))



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

    for ticker_name in ('SPY', 'AGG'):# 'EFA', 'EEM', 'AGG', 'LQD', 'IEF', 'SHY'):
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



