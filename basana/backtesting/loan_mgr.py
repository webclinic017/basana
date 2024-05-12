# Basana
#
# Copyright 2022-2023 Gabriel Martin Becedillas Ruiz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from decimal import Decimal
from typing import Dict, Optional, List
import datetime
import logging

from basana.backtesting import errors, helpers as bt_helpers, value_map
from basana.backtesting.lending import ExchangeContext, Loan, LoanInfo, LendingStrategy
from basana.core import logs
import basana.core.helpers as core_helpers


logger = logging.getLogger(__name__)


class LoanManager:
    def __init__(
            self, lending_strategy: LendingStrategy, exchange_ctx: ExchangeContext
    ):
        self._loans = bt_helpers.ExchangeObjectContainer[Loan]()
        self._exchange_ctx = exchange_ctx
        self._lending_strategy = lending_strategy
        self._collateral_by_loan: Dict[str, value_map.ValueMap] = {}
        self._lending_strategy.set_exchange_context(exchange_ctx)

    def create_loan(
            self, symbol: str, amount: Decimal, now: datetime.datetime
    ) -> LoanInfo:
        if amount <= 0:
            raise errors.Error("Invalid amount")

        # Create the loan and update balances.
        loan = self._lending_strategy.create_loan(symbol, amount, now)
        required_collateral = loan.calculate_collateral(self._exchange_ctx.prices)
        self._exchange_ctx.account_balances.update(
            balance_updates={loan.borrowed_symbol: loan.borrowed_amount},
            borrowed_updates={loan.borrowed_symbol: loan.borrowed_amount},
            hold_updates=required_collateral
        )

        # Save the loan now that balance updates succeeded.
        self._loans.add(loan)
        self._collateral_by_loan[loan.id] = value_map.ValueMap(required_collateral)

        return loan.get_loan_info()

    def get_open_loans(self) -> List[LoanInfo]:
        return list(map(lambda loan: loan.get_loan_info(), self._loans.get_open()))

    def get_loan(self, loan_id: str) -> Optional[LoanInfo]:
        loan = self._loans.get(loan_id)
        return None if loan is None else loan.get_loan_info()

    def repay_loan(self, loan_id: str, now: datetime.datetime):
        loan = self._loans.get(loan_id)
        if not loan:
            raise errors.Error("Loan not found")
        if not loan.is_open:
            raise errors.Error("Loan is not open")

        interest = loan.calculate_interest(now, self._exchange_ctx.prices)
        for symbol, amount in interest.items():
            interest[symbol] = core_helpers.truncate_decimal(
                amount, self._exchange_ctx.config.get_symbol_info(symbol).precision
            )
        collateral = self._collateral_by_loan[loan_id]

        try:
            # Update balances.
            balance_updates = value_map.ValueMap({loan.borrowed_symbol: -loan.borrowed_amount})
            balance_updates -= interest
            self._exchange_ctx.account_balances.update(
                balance_updates=balance_updates,
                borrowed_updates={loan.borrowed_symbol: -loan.borrowed_amount},
                hold_updates={symbol: -amount for symbol, amount in collateral.items()}
            )

            # Close the loan now that balance updates succeeded.
            loan.close()
            self._collateral_by_loan.pop(loan_id)

        except errors.NotEnoughBalance as e:
            logger.debug(logs.StructuredMessage("Failed to repay the loan", loan_id=loan_id, error=str(e)))
            raise
