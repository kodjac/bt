#!/usr/bin/python3
import backtrader as bt
import datetime
import sys

class FixedCommisionScheme(bt.CommInfoBase):
    ''' This is a simple fixed commission scheme '''
    params = (
        ('commission', 5),
        ('stocklike', True),
        ('commtype', bt.CommInfoBase.COMM_FIXED),
        )

    def _getcommission(self, size, price, pseudoexec):
        return self.p.commission


class VAA(bt.Strategy):
    params = (
              ('sma_period', 20),
              ('exitbars', 5),
             )


    def log(self, txt, dt=None, doprint=False):
        current_dt = dt or self.datas[0].datetime.date(0)
        if doprint:
            print('{} {}'.format(current_dt.isoformat(), txt))


    def __init__(self):
        self.dclose = self.datas[0].close  # reference to feed-line
        self.order = None
        self.buy_date = None
        self.price = []
        self.sma = bt.indicators.SimpleMovingAverage(self.datas[0], period=self.params.sma_period)


    def notify_order(self, order):
        # is called for every order status change: Submitted, Accepted, Completed
        # self.order = None  # no more order, why here?
        if order.status == order.Completed:
            order_type = 'BUY' if order.isbuy() else 'SELL'
            self.log('{} order {}'.format(order_type, order.getstatusname()))
            self.order = None if order.issell() else self.order

    def notify_trade(self, trade):
        # its 0 for buying
        if trade.isclosed:
            self.log('operation profit {:.2f} ({})'.format(trade.pnlcomm, trade.pnl))


    def next(self):
        self.price.append(self.dclose[0])
        # dclose, 0: current price >0: future prices = current prices, -1 yesterdays price
        # len(dclose) gives the length of past days, printing shows the upcoming days ?!!

        if (len(self.dclose) > 2 and not self.order
                and self.dclose[0] < self.dclose[-1] 
                and self.dclose[-1] < self.dclose[-2]):
            self.log('ordered at {}'.format(self.dclose[0]))

            self.buy_date = len(self)
            self.order = self.buy()

        elif self.order and len(self) >= self.buy_date + self.params.exitbars:
            self.log('sold at {}'.format(self.dclose[0]))
            self.buy_date = None
            self.order = self.sell()

        else:
            
            self.log('close {:.2f}, ({:.2f})'.format(self.dclose[0], cerebro.broker.getvalue()))


    def stop(self):
        self.log('VAA-{} end value {:.2f} EUR'.format(self.params.exitbars, self.broker.getvalue()),
                 doprint=True)
                 


if __name__ == '__main__':

    alphavantage_key = 'HR91R8PS4P19GES7'
    # print('_'*80)
    cerebro = bt.Cerebro()
    cerebro.broker.setcash(5500)
    cerebro.broker.addcommissioninfo(FixedCommisionScheme())
    cerebro.addstrategy(VAA, exitbars=7, sma_period=10)
    # cerebro.optstrategy(VAA, exitbars=range(5,30,5))

    data = bt.feeds.YahooFinanceData(
            dataname='^GSPC',
            fromdate=datetime.datetime(2000, 1, 1),
            todate=datetime.datetime(2000, 5, 25),
            )

    cerebro.adddata(data)

    print('Starting Portfolio Value: %.2f' % cerebro.broker.getvalue())

    cerebro.run()
    # cerebro.plot()


    print('Final Portfolio Value: %.2f' % cerebro.broker.getvalue())
