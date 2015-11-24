#!/usr/bin/env python

import datetime
from gi.repository import GObject
from gi.repository import Gtk
import ledger
import os
import sys
import threading

import ledgerhelpers as common
from ledgerhelpers import LedgerConfigurationError


class BuyWindow(Gtk.Window):

    def __init__(self):
        Gtk.Window.__init__(self, title="Record purchase")
        self.set_border_width(12)

        grid = Gtk.Grid()
        grid.set_column_spacing(8)
        grid.set_row_spacing(8)
        self.add(grid)

        row = 0

        grid.attach(Gtk.Label("Items purchased"), 0, row, 1, 1)

        self.what = Gtk.Entry()
        grid.attach(self.what, 1, row, 1, 1)
        self.what.set_activates_default(True)

        row += 1

        grid.attach(Gtk.Label("Amount"), 0, row, 1, 1)

        self.amount = common.LedgerAmountEntry()
        grid.attach(self.amount, 1, row, 1, 1)
        self.amount.set_activates_default(True)

        row += 1

        grid.attach(Gtk.Label("Expense account"), 0, row, 1, 1)

        self.expense = common.EagerCompletingEntry()
        self.expense.set_width_chars(50)
        grid.attach(self.expense, 1, row, 1, 1)
        self.expense.set_activates_default(True)

        row += 1

        grid.attach(Gtk.Label("Date of purchase"), 0, row, 1, 1)

        self.when = common.NavigatableCalendar()
        grid.attach(self.when, 1, row, 1, 1)

        row += 1

        self.clearing = Gtk.CheckButton("Date of clearing")
        grid.attach(self.clearing, 0, row, 1, 1)
        self.clearing_when = common.NavigatableCalendar()
        def process_toggle(*args):
            self.clearing_when.set_sensitive(self.clearing.get_active())
        self.clearing.connect("toggled", process_toggle)
        self.clearing_when.set_sensitive(self.clearing.get_active())
        grid.attach(self.clearing_when, 1, row, 1, 1)

        row += 1

        grid.attach(Gtk.Label("Source account"), 0, row, 1, 1)

        self.asset = common.EagerCompletingEntry()
        self.asset.set_width_chars(50)
        grid.attach(self.asset, 1, row, 1, 1)
        self.asset.set_activates_default(True)

        row += 1

        self.transaction_view = common.LedgerTransactionView()
        grid.attach(self.transaction_view, 0, row, 2, 1)

        row += 1

        button_box = Gtk.ButtonBox()
        button_box.set_layout(Gtk.ButtonBoxStyle.END)
        button_box.set_spacing(12)
        self.status = Gtk.Label()
        button_box.add(self.status)
        self.close_button = Gtk.Button(stock=Gtk.STOCK_CLOSE)
        button_box.add(self.close_button)
        self.add_button = Gtk.Button(stock=Gtk.STOCK_ADD)
        button_box.add(self.add_button)
        grid.attach(button_box, 0, row, 2, 1)
        self.add_button.set_can_default(True)
        self.add_button.grab_default()


class BuyApp(BuyWindow):

    def __init__(self, journal, preferences, initial_purchase):
        BuyWindow.__init__(self)
        self.journal = journal
        self.preferences = preferences
        self.commodities = dict()
        self.accounts = []
        self.initial_purchase = initial_purchase
        t = threading.Thread(target=self.load_accounts_and_commodities_async)
        self.connect("show", lambda _: t.start())
        self.close_button.connect("clicked", lambda _: self.emit('delete-event', None))
        self.add_button.connect("clicked", lambda _: self.process_transaction())
        self.connect("delete-event", lambda _, _a: self.save_preferences())
        self.connect("key-press-event", self.handle_escape)

    def handle_escape(self, window, event, user_data=None):
        if event.keyval == common.EVENT_ESCAPE:
            self.emit('delete-event', None)
            return True
        return False

    def load_accounts_and_commodities_async(self):
        accts, commodities = self.journal.accounts_and_last_commodities()

        def load_accounts_and_commodities_finished(accts, commodities):
            self.accounts = accts
            self.commodities = commodities

            self.what.connect("changed", self.suggest_expense_account)
            self.expense.connect("changed", self.update_amount_commodity)
            self.clearing_when.follow(self.when)

            self.set_accounts_for_completion(accts)

            if self.initial_purchase:
                self.what.set_text(self.initial_purchase)
                self.suggest_expense_account(self.what)
                self.amount.grab_focus()

            self.clearing.set_active(
                self.preferences.get("default_to_clearing", True)
            )
            self.when.set_datetime_date(
                self.preferences.get("last_date", datetime.date.today())
            )

            if self.preferences.get("last_asset_account", None):
                self.asset.set_default_text(self.preferences["last_asset_account"])

            self.what.connect("changed", self.update_transaction_view)
            self.when.connect("day-selected", self.update_transaction_view)
            self.clearing.connect("toggled", self.update_transaction_view)
            self.clearing_when.connect("day-selected", self.update_transaction_view)
            self.amount.connect("changed", self.update_transaction_view)
            self.asset.connect("changed", self.update_transaction_view)
            self.expense.connect("changed", self.update_transaction_view)
            self.update_transaction_view()

        GObject.idle_add(load_accounts_and_commodities_finished, accts, commodities)

    def set_accounts_for_completion(self, account_list):
        for w in "asset", "expense":
            accounts = Gtk.ListStore(GObject.TYPE_STRING)
            [ accounts.append((str(a) ,)) for a in account_list ]
            getattr(self, w).get_completion().set_model(accounts)

    def update_transaction_view(self, ignored=None):
        self.validate()
        amount = self.amount.get_amount()
        if amount is None:
            amount = ""
            negamount = ""
        elif str(amount) == "":
            amount = ""
            negamount = ""
        else:
            negamount = amount * -1
        self.transaction_view.generate_record(
            self.what.get_text(),
            self.when.get_datetime_date(),
            self.clearing_when.get_datetime_date() if self.clearing.get_active() else None,
            [
                (self.asset.get_text(), [negamount]),
                (self.expense.get_text(), [amount]),
            ]
        )

    def validate(self, grab_focus=False):
        if not self.what.get_text().strip():
            if grab_focus: self.what.grab_focus()
            self.status.set_text("Items purchased cannot be empty")
            return False
        if not self.amount.get_amount() or str(self.amount.get_amount()) == "":
            if grab_focus: self.amount.grab_focus()
            self.status.set_text("Enter a valid amount")
            return False
        if not self.expense.get_text().strip():
            if grab_focus: self.expense.grab_focus()
            self.status.set_text("Enter an expense account")
            return False
        if not self.asset.get_text().strip():
            if grab_focus: self.asset.grab_focus()
            self.status.set_text("Enter an asset account")
            return False
        self.status.set_text("")
        return True

    def process_transaction(self):
        if not self.validate(True):
            return
        self.preferences["suggester"].associate(self.what.get_text().strip(),
                                                self.expense.get_text().strip())
        buf = self.transaction_view.get_buffer()
        text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), True)
        self.save_transaction(text)
        self.commodities[self.expense.get_text()] = self.amount.get_amount()
        self.reset_after_save()

    def save_transaction(self, text):
        self.journal.add_text_to_file(text)

    def reset_after_save(self):
        self.what.set_text("")
        self.expense.set_text("")
        self.amount.set_amount("")
        self.what.grab_focus()
        self.status.set_text("Purchase saved")

    def update_amount_commodity(self, expense, *args):
        if not expense.get_text().strip():
            return
        commodity = self.commodities.get(expense.get_text().strip(), None)
        if commodity is not None:
            self.amount.set_default_commodity(commodity)

    def suggest_expense_account(self, what, *args):
        if not self.what.get_text().strip():
            return
        suggestion = self.preferences["suggester"].suggest(self.what.get_text())
        if suggestion:
            self.expense.set_default_text(suggestion)

    def save_preferences(self):
        self.preferences["default_to_clearing"] = self.clearing.get_active()
        if self.when.get_datetime_date() == datetime.date.today():
            del self.preferences["last_date"]
        else:
            self.preferences["last_date"] = self.when.get_datetime_date()
        if not self.asset.get_text().strip():
            del self.preferences["last_asset_account"]
        else:
            self.preferences["last_asset_account"] = self.asset.get_text().strip()
        if self.what.get_text().strip() and self.expense.get_text().strip():
            self.preferences["suggester"].associate(self.what.get_text().strip(),
                                                    self.expense.get_text().strip())
        self.preferences.persist()


class InnocuousBuyApp(BuyApp):

    def save_preferences(self):
        common.debug("Skipping save of preferences")

    def save_transaction(self, text):
        common.debug("Transaction not being saved:")
        common.debug(text)


def main():
    errdialog = lambda msg: common.FatalError("Cannot start buy", msg, outside_mainloop=True)
    try:
        ledger_file = common.find_ledger_file()
    except Exception, e:
        errdialog(str(e))
        return 4
    try:
        price_file = common.find_ledger_price_file()
    except LedgerConfigurationError, e:
        price_file = None
    try:
        journal = common.Journal.from_file(ledger_file, price_file)
    except Exception, e:
        errdialog("Cannot open ledger file: %s" % e)
        return 5
    s = common.Settings.load_or_defaults(os.path.expanduser("~/.ledgerhelpers.ini"))
    args = sys.argv[1:]
    klass = BuyApp
    if args and args[0] == "-n":
        klass = InnocuousBuyApp
        args = args[1:]
    win = klass(journal, s, " ".join(args) if args else None)
    win.connect("delete-event", Gtk.main_quit)
    GObject.idle_add(win.show_all)
    Gtk.main()
