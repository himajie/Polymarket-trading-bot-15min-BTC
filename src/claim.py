"""
Polymarket Rewards Claimer

This script automatically claims rewards from resolved Polymarket prediction markets.
It uses the Polymarket Relayer API for gasless transactions.

Author: MixasV
Contact: https://t.me/onEXv
Repository: https://github.com/MixasV/Polymarket-Claimer

Keywords: polymarket, claim, rewards, claimer, prediction markets, relayer, gasless,
          conditional tokens, ctf, safe wallet, gnosis safe, automation, crypto
"""

import os
import sys
import requests
import logging
from getpass import getpass
from web3 import Web3
from py_builder_relayer_client.client import RelayClient
from py_builder_relayer_client.models import SafeTransaction, OperationType
from py_builder_signing_sdk.config import BuilderConfig, BuilderApiKeyCreds
from .config import load_settings
from .config_validator import ConfigValidator
from .runner_utils import RunnerHelper


# Constants
CTF_ADDRESS = Web3.to_checksum_address("0x4d97dcd97ec945f40cf65f87097ace5ea0476045")
USDC_ADDRESS = Web3.to_checksum_address("0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174")
RELAYER_URL = "https://relayer-v2.polymarket.com"
DATA_API_URL = "https://data-api.polymarket.com"
CHAIN_ID = 137  # Polygon



class ClaimPolymarket():

    def __init__(self,logger):
        self.settings = load_settings()

    def get_redeemable_positions(self,proxy_wallet: str) -> list:
        """Fetch redeemable positions from Polymarket Data API"""
        url = f"{DATA_API_URL}/positions?user={proxy_wallet.lower()}&redeemable=true"
        response = requests.get(url)
        response.raise_for_status()
        return response.json()


    def create_redeem_transaction(self,condition_id: str) -> SafeTransaction:
        """Create a SafeTransaction for redeeming positions"""
        w3 = Web3()
        
        # Create CTF contract interface
        ctf_contract = w3.eth.contract(
            address=CTF_ADDRESS,
            abi=[{
                "name": "redeemPositions",
                "type": "function",
                "inputs": [
                    {"name": "collateralToken", "type": "address"},
                    {"name": "parentCollectionId", "type": "bytes32"},
                    {"name": "conditionId", "type": "bytes32"},
                    {"name": "indexSets", "type": "uint256[]"}
                ],
                "outputs": []
            }]
        )
        
        # Encode the function call
        call_data = ctf_contract.encode_abi(
            abi_element_identifier="redeemPositions",
            args=[
                USDC_ADDRESS,
                bytes(32),  # parentCollectionId = 0x0
                bytes.fromhex(condition_id[2:] if condition_id.startswith('0x') else condition_id),
                [1, 2]  # indexSets: redeem both YES and NO outcomes
            ]
        )
        
        # Create SafeTransaction object
        return SafeTransaction(
            to=CTF_ADDRESS.lower(),
            operation=OperationType.Call,
            data="0x" + call_data.hex() if isinstance(call_data, bytes) else call_data,
            value="0"
        )


    def run(self):

        """Main function to claim Polymarket rewards"""
        print("\n" + "=" * 70)
        print("POLYMARKET REWARDS CLAIMER")
        print("=" * 70)
        print("\nAuthor: MixasV")
        print("Repository: https://github.com/MixasV/Polymarket-Claimer\n")
        

        # Get required credentials
        private_key = self.settings.private_key
        proxy_wallet = self.settings.funder
        # builder_key = self.settings.api_key
        # builder_secret = self.settings.api_secret
        # builder_passphrase = self.settings.api_passphrase
        builder_key = '019bbcef-4e8d-7421-ac4f-d3c7025ba332'
        builder_secret = 'Z3YbsYAIqIDUtAI2ntvGenr8O7rZjLxYnGbEhHBQs-w='
        builder_passphrase = 'e01a74ad484a84bb60ad08d95bf0a72c018c7edf5750abd1af7ec61f79b1a2ec'
        
        if not all([private_key, proxy_wallet, builder_key, builder_secret, builder_passphrase]):
            print("❌ Missing required environment variables!")
            print("\nRequired variables:")
            print("  - POLYMARKET_PRIVATE_KEY")
            print("  - POLYMARKET_PROXY_WALLET")
            print("  - BUILDER_API_KEY")
            print("  - BUILDER_SECRET")
            print("  - BUILDER_PASSPHRASE")
            print("\nPlease create a .env file with these variables.")
            sys.exit(1)
        
        if not private_key.startswith('0x'):
            private_key = '0x' + private_key
        
        print(f"📍 Proxy Wallet: {proxy_wallet}\n")
        
        # Initialize Relayer client
        print("🔧 Initializing Relayer client...")
        creds = BuilderApiKeyCreds(
            key=builder_key,
            secret=builder_secret,
            passphrase=builder_passphrase
        )
        
        builder_config = BuilderConfig(local_builder_creds=creds)
        
        client = RelayClient(
            RELAYER_URL,
            CHAIN_ID,
            private_key,
            builder_config
        )
        
        print("✅ Relayer client initialized (SAFE type)\n")
        
        # Check Safe deployment
        expected_safe = client.get_expected_safe()
        print(f"🔍 Expected Safe: {expected_safe}")
        
        is_deployed = client.get_deployed(expected_safe)
        print(f"   Deployed: {is_deployed}\n")
        
        if not is_deployed:
            print("⚠️  Safe not deployed. Deploying now...")
            deploy_response = client.deploy()
            deploy_result = deploy_response.wait()
            
            if deploy_result:
                print(f"✅ Safe deployed: {deploy_result.get('transactionHash')}\n")
            else:
                print("❌ Safe deployment failed!")
                sys.exit(1)
        
        # Fetch redeemable positions
        print("🔍 Fetching redeemable positions...")
        try:
            positions = self.get_redeemable_positions(proxy_wallet)
        except Exception as e:
            print(f"❌ Error fetching positions: {e}")
            sys.exit(1)
        
        if not positions:
            print("✅ No redeemable positions found. All rewards already claimed!")
            sys.exit(0)
        
        print(f"✅ Found {len(positions)} redeemable position(s):\n")
        
        for idx, pos in enumerate(positions, 1):
            print(f"   {idx}. {pos['title']}")
            print(f"      Outcome: {pos['outcome']}")
            print(f"      Value: ${pos['currentValue']}")
        
        print()
        
        # return
        # Process each position
        claimed_count = 0
        for pos in positions:
            print(f"📦 Processing: {pos['title']}")
            
            try:
                # Create redeem transaction
                redeem_tx = self.create_redeem_transaction(pos['conditionId'])
                
                print("📤 Submitting to Relayer API...")
                
                # Execute transaction
                response = client.execute([redeem_tx], f"Claim: {pos['title']}")
                
                print(f"✅ Transaction submitted: {response.transaction_id}")
                print("⏳ Waiting for confirmation...\n")
                
                # Wait for confirmation
                result = response.wait()
                
                if result:
                    print("🎉 SUCCESS!")
                    print(f"✅ Transaction Hash: {result.get('transactionHash')}")
                    print(f"🔍 Polygonscan: https://polygonscan.com/tx/{result.get('transactionHash')}")
                    print()
                    claimed_count += 1
                else:
                    print("❌ Transaction failed to confirm\n")
            
            except Exception as e:
                print(f"❌ Error processing position: {e}\n")
                continue
        
        print("=" * 70)
        print(f"✅ Successfully claimed {claimed_count}/{len(positions)} positions")
        print("=" * 70 + "\n")


if __name__ == "__main__":

    logName= "poly-claim"
    runnerHelper=RunnerHelper() 
    logConfig=runnerHelper.getLogConfig(logName)
    logging.config.dictConfig(logConfig)
    logger =  logging.getLogger(logName)
    runner=ClaimPolymarket(logger)
    runner.run()