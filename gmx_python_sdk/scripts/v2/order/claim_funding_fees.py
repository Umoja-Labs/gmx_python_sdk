import logging

from web3 import Web3

from hexbytes import HexBytes

from ..get.get_markets import Markets

from ..gmx_utils import convert_to_checksum_address, \
    get_exchange_router_contract, create_connection, \
    determine_swap_route, contract_map


class ClaimFundingFees:

    def __init__(
        self,
        config,
        markets: list,
        tokens: list,
        max_fee_per_gas: int = None,
        debug_mode: bool = False
    ) -> None:
        self.config = config
        self.markets = markets
        self.tokens = tokens
        self.max_fee_per_gas = max_fee_per_gas
        self.debug_mode = debug_mode

        if self.max_fee_per_gas is None:
            block = create_connection(
                config
            ).eth.get_block('latest')
            self.max_fee_per_gas = block['baseFeePerGas'] * 1.35

        self._exchange_router_contract_obj = get_exchange_router_contract(
            config
        )

        self._connection = create_connection(config)

        self.all_markets_info = Markets(config).get_available_markets()

        self.log = logging.getLogger(__name__)
        self.log.info("Creating order...")

    def determine_gas_limits(self):

        pass

    def _submit_transaction(
        self, user_wallet_address: str
    ):
        """
        Submit Transaction
        """
        self.log.info("Building transaction...")

        nonce = self._connection.eth.get_transaction_count(
            user_wallet_address
        )

        raw_txn = self._exchange_router_contract_obj.functions.claimFundingFees(
            self.markets,
            self.tokens,
            user_wallet_address
        ).build_transaction(
            {
                'value': 0,
                'chainId': self.config.chain_id,
                'gas': 8000000,

                # TODO - this is NOT correct
                # 'gas': (
                #    self._gas_limits_order_type.call() + self._gas_limits_order_type.call()
                # ),
                'maxFeePerGas': int(self.max_fee_per_gas),
                'maxPriorityFeePerGas': 0,
                'nonce': nonce
            }
        )
        if not self.debug_mode:

            signed_txn = self._connection.eth.account.sign_transaction(
                raw_txn, self.config.private_key
            )
            tx_hash = self._connection.eth.send_raw_transaction(
                signed_txn.rawTransaction
            )
            self.log.info("Txn submitted!")
            self.log.info(
                "Check status: https://arbiscan.io/tx/{}".format(tx_hash.hex())
            )
            self.log.info("Transaction submitted!")
            return tx_hash.hex()
        else:
            return None

    def create_funding_fee_claim(self):

        user_wallet_address = self.config.user_wallet_address

        self.determine_gas_limits()

        user_wallet_address = convert_to_checksum_address(
            self.config,
            user_wallet_address
        )

        return self._submit_transaction(
            user_wallet_address
        )
