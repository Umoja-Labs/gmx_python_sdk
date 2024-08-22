import logging
import numpy as np

from .get import GetData
from .get_oracle_prices import OraclePrices

from ..gmx_utils import (get_tokens_address_dict,
                         convert_to_checksum_address, create_hash)

chain = 'arbitrum'

ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"


def get_position_key(account: str, market_address: str, collateral_address: str, is_long: bool):
    return create_hash(['address', 'address', 'address', 'bool'], [account, market_address, collateral_address, is_long]).hex()


def transform_to_dict(account_positions_list, processed_positions):
    result = []
    for i in range(len(account_positions_list)):
        pos = account_positions_list[i]
        ppos = processed_positions[i]
        # Unpack the components of each position
        position, fees, executionPriceResult, base_pnl_usd, uncapped_base_pnl_usd, pnl_after_price_impact_usd = pos

        position_dict = {
            # addresses
            "account_address": position[0][0],
            "market_address": position[0][1],
            "collateral_token_address": position[0][2],
            # numbers
            "size_in_usd": position[1][0],
            "size_in_tokens": position[1][1],
            "collateral_amount": position[1][2],
            "borrowing_factor": position[1][3],
            "funding_fee_amount_per_size": position[1][4],
            "long_token_claimable_funding_amount_per_size": position[1][5],
            "short_token_claimable_funding_amount_per_size": position[1][6],
            "increased_at_block": position[1][7],
            "decreased_at_block": position[1][8],
            "increased_at_time": position[1][9],
            "decreased_at_time": position[1][10],
            "is_long": position[2][0],
            # fees
            "funding_fee_amount": fees[1][0],
            "claimable_long_token_amount": fees[1][1],
            "claimable_short_token_amount": fees[1][2],
            "latest_funding_fee_amount_per_size": fees[1][3],
            "latest_long_token_claimable_funding_amount_per_size": fees[1][4],
            "latest_short_token_claimable_funding_amount_per_size": fees[1][5],
            # borrowing fee
            "borrowing_fee_usd": fees[2][0],
            "borrowing_fee_amount": fees[2][1],
            "borrowing_fee_receiver_factor": fees[2][2],
            "borrowing_fee_amount_for_fee_receiver": fees[2][3],
            # token price
            "collateral_token_price_min": fees[4][0],
            "collateral_token_price_max": fees[4][1],
            "position_fee_factor": fees[5],
            "protocol_fee_amount": fees[6],
            "position_fee_receiver_factor": fees[7],
            "fee_receiver_amount": fees[8],
            "fee_amount_for_pool": fees[9],
            "position_fee_amount_for_pool": fees[10],
            "position_fee_amount": fees[11],
            "total_cost_amount_excluding_funding": fees[12],
            "total_cost_amount": fees[13],
            "base_pnl_usd": base_pnl_usd,
            "uncapped_base_pnl_usd": uncapped_base_pnl_usd,
            "pnl_after_price_impact_usd": pnl_after_price_impact_usd,
        }
        position_dict.update(ppos)
        result.append(position_dict)
    return result


class GetOpenPositions(GetData):
    def __init__(self, config: str, address: str, referral_storage_address: str):
        super().__init__(config)
        self.address = convert_to_checksum_address(config, address)
        self.referral_storage_address = str(
            convert_to_checksum_address(config, referral_storage_address))

    def get_data(self):
        """
        Get all open positions for a given address on the chain defined in
        class init

        Parameters
        ----------
        address : str
            evm address .

        Returns
        -------
        processed_positions : dict
            a dictionary containing the open positions, where asset and
            direction are the keys.

        """
        raw_positions = self.reader_contract.functions.getAccountPositions(
            self.data_store_contract_address,
            self.address,
            0,
            10
        ).call()

        if len(raw_positions) == 0:
            logging.info(
                'No positions open for address: "{}"" on {}.'.format(
                    self.address,
                    self.config.chain.title()
                )
            )
        # processed_positions = {}
        processed_positions = []

        for raw_position in raw_positions:
            processed_position = self._get_data_processing(raw_position)

            # TODO - maybe a better way of building the key?
            if processed_position['is_long']:
                direction = 'long'
            else:
                direction = 'short'
            processed_positions.append(processed_position)
        prices = []
        for position in processed_positions:
            price = (
                (position['minPrice'], position['maxPrice']),
                (position['minPrice'], position['maxPrice']),
                (position['minPrice'], position['maxPrice'])
            )
            prices.append(price)
        keys = []
        for position in processed_positions:
            key = get_position_key(
                self.address, position['market_address'], position['collateral_token_address'], position['is_long'])
            keys.append(key)
        positionInfos = self.reader_contract.functions.getAccountPositionInfoList(
            self.data_store_contract_address, self.referral_storage_address, keys, prices, ZERO_ADDRESS).call()
        return transform_to_dict(positionInfos, processed_positions)

        # key = "{}_{}".format(
        #    processed_position['market_symbol'][0],
        #    direction
        # )
        # processed_positions[key] = processed_position

    def _get_data_processing(self, raw_position: tuple):
        """
        A tuple containing the raw information return from the reader contract
        query GetAccountPositions

        Parameters
        ----------
        raw_position : tuple
            raw information return from the reader contract .

        Returns
        -------
        dict
            a processed dictionary containing info on the positions.
        """
        market_info = self.markets.info[raw_position[0][1]]

        chain_tokens = get_tokens_address_dict(chain)

        entry_price = (
            raw_position[1][0] / raw_position[1][1]
        ) / 10 ** (
            30 - chain_tokens[market_info['index_token_address']]['decimals']
        )

        leverage = (
            raw_position[1][0] / 10 ** 30
        ) / (
            raw_position[1][2] / 10 ** chain_tokens[
                raw_position[0][2]
            ]['decimals']
        )
        prices = OraclePrices(chain=chain).get_recent_prices()
        maxPrice = float(
            prices[market_info['index_token_address']]['maxPriceFull'])
        minPrice = float(
            prices[market_info['index_token_address']]['minPriceFull'])
        mark_price = np.median(
            [
                float(
                    prices[market_info['index_token_address']]['maxPriceFull']
                ),
                float(
                    prices[market_info['index_token_address']]['minPriceFull']
                )
            ]
        ) / 10 ** (
            30 - chain_tokens[market_info['index_token_address']]['decimals']
        )
        return {
            "account": raw_position[0][0],
            "market": raw_position[0][1],
            "market_address": market_info['gmx_market_address'],
            "market_symbol": (
                self.markets.info[raw_position[0][1]]['market_symbol'],
            ),
            "collateral_token_address": chain_tokens[raw_position[0][2]]['address'],
            "collateral_token": chain_tokens[raw_position[0][2]]['symbol'],
            "position_size": raw_position[1][0] / 10**30,
            "size_in_tokens": raw_position[1][1],
            "entry_price": (
                (
                    raw_position[1][0] / raw_position[1][1]
                ) / 10 ** (
                    30 - chain_tokens[
                        market_info['index_token_address']
                    ]['decimals']
                )
            ),
            "inital_collateral_amount": raw_position[1][2],
            "inital_collateral_amount_usd": (
                raw_position[1][2]
                / 10 ** chain_tokens[raw_position[0][2]]['decimals'],
            ),
            "leverage": leverage,
            "borrowing_factor": raw_position[1][3],
            "funding_fee_amount_per_size": raw_position[1][4],
            "long_token_claimable_funding_amount_per_size": raw_position[1][5],
            "short_token_claimable_funding_amount_per_size": raw_position[1][6],
            "position_modified_at": "",
            "is_long": raw_position[2][0],
            "percent_profit": (
                (
                    1 - (mark_price / entry_price)
                ) * leverage
            ) * 100,
            "mark_price": mark_price,
            "maxPrice": int(maxPrice),
            "minPrice": int(minPrice),
        }


if __name__ == "__main__":
    address = "0x99f5585dcc32e2238634f11f32d9be9bd5e98b49"
    positions = GetOpenPositions(chain='arbitrum', address=address).get_data()

    for position in positions:
        print(positions[position])
