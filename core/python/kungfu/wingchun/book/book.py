import sys
import traceback
import datetime

from .position import StockPosition, FuturePosition, Position
from .position import get_uid as get_position_uid

import kungfu.msg.utils as msg_utils
import kungfu.yijinjing.time as kft
import kungfu.wingchun.constants as wc_constants
import kungfu.wingchun.utils as wc_utils
import kungfu.wingchun.msg as wc_msg

from kungfu.wingchun.constants import *
from kungfu.wingchun.utils import *

import pykungfu
from pykungfu import longfist
from pykungfu import yijinjing as yjj
from pykungfu import wingchun as pywingchun

from collections import namedtuple
from rx.subject import Subject

DATE_FORMAT = "%Y%m%d"
DEFAULT_CASH = 1e7


class AccountBookTags(namedtuple('AccountBookTags', 'holder_uid ledger_category source_id account_id client_id')):
    def __new__(cls, holder_uid, ledger_category, source_id="", account_id="", client_id=""):
        return super(AccountBookTags, cls).__new__(cls, holder_uid, ledger_category, source_id, account_id, client_id)

    @classmethod
    def make_from_location(cls, location):
        if location.category == yjj.category.TD:
            return cls(**{"holder_uid": location.uid, "source_id": location.group, "account_id": location.name,
                          "ledger_category": wc_constants.LedgerCategory.Account})
        elif location.category == yjj.category.STRATEGY:
            return cls(**{"holder_uid": location.uid, "client_id": location.name, "ledger_category": wc_constants.LedgerCategory.Strategy})
        else:
            raise ValueError('invalid location category {}'.format(location.category))


class BookEvent:
    def __init__(self, msg_type, data):
        self.msg_type = msg_type
        self.data = data

    def as_dict(self):
        return {"msg_type": self.msg_type, "data": msg_utils.object_as_dict(self.data)}

    def __repr__(self):
        return str(self.as_dict())


class AccountBook(pywingchun.Book):
    def __init__(self, ctx, location, **kwargs):
        pywingchun.Book.__init__(self)
        self.ctx = ctx
        self.location = location
        self.tags = AccountBookTags.make_from_location(self.location)
        self.setup_trading_day(kwargs.pop("trading_day", None))
        self.initial_equity = kwargs.pop("initial_equity", 0.0)
        self.static_equity = kwargs.pop("static_equity", 0.0)
        self.avail = kwargs.pop("avail", 0.0)
        self.frozen_cash = kwargs.pop("frozen_cash", 0.0)
        self.frozen_margin = kwargs.pop("frozen_margin", 0.0)
        self.intraday_fee = kwargs.pop("intraday_fee", 0.0)
        self.accumulated_fee = kwargs.pop("accumulated_fee", 0.0)
        self.realized_pnl = kwargs.pop("realized_pnl", 0.0)

        self._orders = {}
        self._tickers = {}
        self._positions = {}

        self._last_check = 0

        self.subject = Subject()

    def get_location_uid(self):
        return self.location.uid

    def setup_trading_day(self, trading_day):
        self.trading_day = trading_day
        if not self.trading_day:
            self.trading_day = self.ctx.trading_day
        elif isinstance(self.trading_day, str):
            self.trading_day = datetime.datetime.strptime(self.trading_day, DATE_FORMAT)

    def on_trading_day(self, event, daytime):
        self.apply_trading_day(kft.to_datetime(daytime))
        self.subject.on_next(self.event)

    def on_quote(self, event, quote):
        self._tickers[quote.uid] = quote
        temp = pykungfu.longfist.types.Position()
        temp.holder_uid = self.location.uid
        temp.instrument_id = quote.instrument_id
        temp.exchange_id = quote.exchange_id
        for dir in [pykungfu.longfist.enums.Direction.Long, pykungfu.longfist.enums.Direction.Short]:
            temp.direction = dir
            if temp.uid in self._positions:
                position = self._positions[temp.uid]
                position.apply_quote(quote)
        self._on_interval_check(event.gen_time)

    def on_order_input(self, event, input):
        self.ctx.logger.debug("{} received order input event: {}".format(self.location.uname, input))
        input.frozen_price = input.limit_price if input.price_type == wc_constants.PriceType.Limit \
            else self.get_last_price(input.instrument_id, input.exchange_id)
        order = pywingchun.utils.order_from_input(input)
        order.insert_time = event.gen_time
        self._orders[order.order_id] = order
        instrument_type = wc_utils.get_instrument_type(input.instrument_id, input.exchange_id)
        direction = wc_utils.get_position_effect(instrument_type, input.side, input.offset)
        position = self._get_position(input.instrument_id, input.exchange_id, direction)
        position.apply_order_input(input)

    def on_order(self, event, order):
        self.ctx.logger.debug("{} received order event: {}".format(self.location.uname, order))
        order.frozen_price = self.get_frozen_price(order.order_id)
        self._orders[order.order_id] = order
        instrument_type = wc_utils.get_instrument_type(order.instrument_id, order.exchange_id)
        direction = wc_utils.get_position_effect(instrument_type, order.side, order.offset)
        position = self._get_position(order.instrument_id, order.exchange_id, direction)
        position.apply_order(order)
        self.subject.on_next(self.event)

    def on_trade(self, event, trade):
        self.ctx.logger.debug("{} received trade event: {}".format(self.location.uname, trade))
        instrument_type = wc_utils.get_instrument_type(trade.instrument_id, trade.exchange_id)
        direction = wc_utils.get_position_effect(instrument_type, trade.side, trade.offset)
        self._get_position(trade.instrument_id, trade.exchange_id, direction).apply_trade(trade)
        self.subject.on_next(self.event)

    def on_asset(self, event, asset):
        self.ctx.logger.info("{} [{:08x}] asset report received, msg_type: {}, data: {}".
                             format(self.location.uname, self.location.uid, event.msg_type, asset))
        self.avail = asset.avail
        if asset.realized_pnl > 0:
            self.realized_pnl = asset.realized_pnl

    def on_positions(self, positions):
        self.ctx.logger.debug("{} [{:08x}] position report received, size: {}".
                              format(self.location.uname, self.location.uid, len(positions)))
        for pos in positions:
            self.ctx.logger.info(pos)
        self._positions = {}
        for pos in positions:
            if isinstance(pos, pykungfu.longfist.types.Position):
                pos = msg_utils.object_as_dict(pos)
            if isinstance(pos, dict):
                try:
                    pos = Position.factory(ctx=self.ctx, book=self, **pos)
                except Exception as err:
                    exc_type, exc_obj, exc_tb = sys.exc_info()
                    self.ctx.logger.error('init position from dict %s, error [%s] %s', pos, exc_type,
                                          traceback.format_exception(exc_type, exc_obj, exc_tb))
                    continue
            if isinstance(pos, Position):
                self._positions[pos.uid] = pos
            else:
                raise TypeError("Position object required, but {} provided".format(type(pos)))
        if self.ctx.name == "ledger":
            self.subject.on_next(self.event)
            for pos in self.positions:
                self.subject.on_next(pos.event)

    def on_position_details(self, details):
        pass

    @property
    def positions(self):
        return list(self._positions.values())

    @property
    def active_orders(self):
        return list([order for order in self._orders.values() if order.status in [
            pykungfu.longfist.enums.OrderStatus.Submitted, pykungfu.longfist.enums.OrderStatus.Pending,
            pykungfu.longfist.enums.OrderStatus.PartialFilledActive
        ]])

    @property
    def total_cash(self):
        return self.avail + self.frozen_cash

    @property
    def margin(self):
        return sum([position.margin for position in self._positions.values()])

    @property
    def market_value(self):
        return sum([position.market_value for position in self._positions.values() if isinstance(position, StockPosition)])

    @property
    def dynamic_equity(self):
        total_value = self.avail
        for pos in self.positions:
            if isinstance(pos, FuturePosition):
                total_value += (pos.margin + pos.position_pnl)
            elif isinstance(pos, StockPosition):
                total_value += pos.market_value
        return total_value

    @property
    def unrealized_pnl(self):
        return sum([position.unrealized_pnl for position in self._positions.values()])

    @property
    def event(self):
        data = pykungfu.longfist.types.Asset()
        data.avail = self.avail
        data.margin = self.margin
        data.market_value = self.market_value
        data.frozen_cash = self.frozen_cash
        data.frozen_margin = self.frozen_margin
        data.intraday_fee = self.intraday_fee
        data.accumulated_fee = self.accumulated_fee
        data.unrealized_pnl = self.unrealized_pnl
        data.realized_pnl = self.realized_pnl
        return self.make_event(wc_msg.Asset, data)

    def make_event(self, msg_type, data):
        data.trading_day = self.trading_day.strftime(DATE_FORMAT)
        data.update_time = self.ctx.now()
        data.source_id = self.tags.source_id
        data.client_id = self.tags.client_id
        data.account_id = self.tags.account_id
        data.holder_uid = self.tags.holder_uid
        data.ledger_category = self.tags.ledger_category
        event = BookEvent(msg_type, data)
        return event

    def get_position(self, instrument_id, exchange_id, direction=wc_constants.Direction.Long):
        uid = get_position_uid(instrument_id, exchange_id, direction)
        return self._positions.get(uid, None)

    def apply_trading_day(self, trading_day):
        for pos in self._positions.values():
            pos.apply_trading_day(trading_day)
        if not self.trading_day == trading_day:
            self.ctx.logger.debug(
                "{} [{:08x}] apply trading day, switch from {} to {}".format(self.location.uname, self.location.uid, self.trading_day, trading_day))
            self.trading_day = trading_day
            self.static_equity = self.dynamic_equity
            self.subject.on_next(self.event)
        else:
            self.ctx.logger.debug("{} [{:08x}] receive duplicate trading_day message {}".format(self.location.uname, self.location.uid, trading_day))

    def get_ticker(self, instrument_id, exchange_id):
        symbol_id = yjj.hash_str_32("{}.{}".format(instrument_id, exchange_id))
        return self._tickers.get(symbol_id, None)

    def get_frozen_price(self, order_id):
        if order_id in self._orders:
            return self._orders[order_id].frozen_price
        else:
            return 0.0

    def get_last_price(self, instrument_id, exchange_id):
        ticker = self.get_ticker(instrument_id, exchange_id)
        if ticker and wc_utils.is_valid_price(ticker.last_price):
            return ticker.last_price
        else:
            return 0.0

    def _on_interval_check(self, now):
        if self._last_check + int(1e9) * 30 < now:
            for order in self.active_orders:
                if order.status == wc_constants.OrderStatus.Submitted and now - order.insert_time >= int(1e9) * 5:
                    order.status = wc_constants.OrderStatus.Unknown
                    self.apply_order(order)
            self.subject.on_next(self.event)
            self._last_check = now

    def _get_position(self, instrument_id, exchange_id, direction=wc_constants.Direction.Long):
        uid = get_position_uid(instrument_id, exchange_id, direction)
        if uid not in self._positions:
            position = Position.factory(ctx=self.ctx, book=self, instrument_id=instrument_id, exchange_id=exchange_id, direction=direction)
            self._positions[uid] = position
        return self._positions[uid]
