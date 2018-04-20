#!/usr/bin/python3
import backtrader as bt
import datetime

if __name__ == '__main__':
    cerebro = bt.Cerebro()
    cerebro.broker.setcash(5500)

    data = bt.feeds.YahooFinanceData(dataname='AAPL',
    			fromdate=datetime.datetime(2000, 1, 1),
			todate=datetime.datetime(2000, 12, 31),
			)
    print(data[0])

    cerebro.adddata(data)

    print('Starting Portfolio Value: %.2f' % cerebro.broker.getvalue())

    # cerebro.run()

    print('Final Portfolio Value: %.2f' % cerebro.broker.getvalue())
