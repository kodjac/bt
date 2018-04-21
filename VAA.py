# #!/usr/bin/python3
import backtrader as bt
import datetime
import pandas as pd # for last business day of the month
import sys

def dbg(func):
    [print(a) for a in dir(func)]

def get_date(fl):
    # internally stored as float of ordinal timestamp
    return datetime.date.fromordinal(int(fl))

class FixedCommisionScheme(bt.CommInfoBase):
    ''' This is a simple fixed commission scheme '''
    params = (
        ('commission', 6.5),
        ('commission', 0.0),
        ('stocklike', True),
        ('commtype', bt.CommInfoBase.COMM_FIXED),
        )

    def _getcommission(self, size, price, pseudoexec):
        return self.p.commission


class Momentum13612W(bt.Indicator):
    lines = ('momentum',)
    # plotinfo(dict(plothlines=[0.0]))

    def __init__(self):
        month = 21
        self.addminperiod(12*month)
        # fixme get actual end of month closing prices
        print('fixme: actual end prices')
        print(self.last_businees_days)
        p0 = self.data
        p1 = self.data(-month*1)
        p3 = self.data(-month*3)
        p6 = self.data(-month*6)
        p12 = self.data(-month*12)
        self.lines.momentum = 12*(p0/p1 - 1) + 4*(p0/p3 - 1) + 2*(p0/p6 - 1) + (p0/p12 - 1)
        super().__init__()


class VAA(bt.Strategy):
    params = (
              ('risk', ['SPY', 'EFA', 'EEM', 'AGG']),
              ('cash', ['LQD', 'IEF', 'SHY']),
              ('lazytrade', False),
             )


    def log(self, txt, doprint=True):
        current_dt = self.datas[0].datetime.date(0)
        if doprint:
            print('{} {}'.format(current_dt.isoformat(), txt))


    def __init__(self):
        print(self.datas[0])
        # dbg(self.datas[0])
        self.dclose = self.datas[0].close  # reference to feed-line
        self.order = None
        self.hold = False
        self.M13612W = Momentum13612W()
        from_date = get_date(self.datas[0].fromdate)
        to_date = get_date(self.datas[0].todate)
        self.last_businees_days = [d.date() for d in pd.date_range(from_date, to_date, freq='BM')]
        # print('last business days:')
        # [print(d) for d in self.last_businees_days]


    def notify_order(self, order):
        # is called for every order status change: Submitted, Accepted, Completed
        # self.order = None  # no more order, why here?
        # self.log('order {}'.format(order.getstatusname()))
        if order.status == order.Completed:
            order_type = 'BUY' if order.isbuy() else 'SELL'
            self.log('{} order {}'.format(order_type, order.getstatusname()))
            self.order = None if order.issell() else self.order


    def notify_trade(self, trade):
        # its 0 for buying
        if trade.isclosed:
            self.log('operation profit {:.2f} ({})'.format(trade.pnlcomm, trade.pnl))


    def next(self):
        now = get_date(self.data_datetime[0])
        if now in self.last_businees_days:
            self.log('close {:.2f}, ({:.2f})'.format(self.dclose[0], cerebro.broker.getvalue()))
            mom = self.M13612W.momentum[0]
            print(mom)
            if mom > 0.0 and not self.hold:
                print('>BUY')
                self.hold = True # fixme dependent ...
                self.buy()  #fixme how much

            elif mom < 0.0 and self.hold:
                print('>SELL')
                self.hold = False # fixme dependent ...
                self.sell()

            else:
                print('do nothing ...')



    def start(self):
        print('_'*80)
        self.log('VAA-G{} start value {:.2f} EUR'.format(
            len(self.params.risk), self.broker.getvalue()))


    def stop(self):
        self.log('VAA-G{} end value {:.2f} EUR'.format(
            len(self.params.risk), self.broker.getvalue()))


if __name__ == '__main__':

    alphavantage_key = 'HR91R8PS4P19GES7'  # flo.rieger@gmx.net
    # print('_'*80)
    cerebro = bt.Cerebro()
    cerebro.broker.setcash(5500)
    cerebro.broker.addcommissioninfo(FixedCommisionScheme())
    cerebro.addstrategy(VAA)
    # cerebro.optstrategy(VAA)

    for name in ('SPY'):# 'EFA', 'EEM', 'AGG', 'LQD', 'IEF', 'SHY'):
        data = bt.feeds.YahooFinanceData(
                dataname=name,
                fromdate=datetime.datetime(2016, 1, 1),
                todate=datetime.datetime(2017, 12, 31),
                )

        cerebro.adddata(data)

    cerebro.run()
    # cerebro.plot()



