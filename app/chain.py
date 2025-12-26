# app/chain.py
import json, os
from web3 import Web3
from dotenv import load_dotenv

load_dotenv(os.getenv("ENV_FILE", ".env"), override=True)

BESU_RPC_URL = os.getenv("BESU_RPC_URL", "http://127.0.0.1:8545")
CONTRACT_ADDRESS = os.getenv("CARROUTES_ADDRESS")

w3 = Web3(Web3.HTTPProvider(BESU_RPC_URL))
if not w3.is_connected():
    raise RuntimeError(f"Cannot connect to Besu RPC: {BESU_RPC_URL}")

with open(os.path.join(os.path.dirname(__file__), "contract_abi.json"), "r", encoding="utf-8") as f:
    abi_file = json.load(f)
ABI = abi_file["abi"] if isinstance(abi_file, dict) and "abi" in abi_file else abi_file

contract = w3.eth.contract(address=Web3.to_checksum_address(CONTRACT_ADDRESS), abi=ABI)

def get_route(address: str):
    addr = Web3.to_checksum_address(address)
    path_json = contract.functions.getRoute(addr).call()
    try:
        return json.loads(path_json or "[]")
    except Exception:
        return []
