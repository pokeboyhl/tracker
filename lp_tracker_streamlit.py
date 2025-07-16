import streamlit as st
import requests
from decimal import Decimal

SUBGRAPH_URL = "https://api.goldsky.com/api/public/project_cmbbm2iwckb1b01t39xed236t/subgraphs/uniswap-v3-hyperevm-position/prod/gn"

# Function to fetch LP positions from subgraph
def fetch_positions():
    query = """
    {
      positions(first: 10, orderBy: liquidity, orderDirection: desc) {
        id
        owner
        liquidity
        tickLower { tickIdx }
        tickUpper { tickIdx }
        pool {
          id
          feeTier
          sqrtPrice
          token0 { symbol decimals }
          token1 { symbol decimals }
          liquidity
        }
      }
    }
    """
    response = requests.post(SUBGRAPH_URL, json={"query": query})
    return response.json()["data"]["positions"]

# Convert sqrtPriceX96 to price

def sqrt_price_to_price(sqrt_price_x96, token0_decimals, token1_decimals):
    sqrt_price = Decimal(sqrt_price_x96) / (2 ** 96)
    price = sqrt_price ** 2 * (10 ** (token0_decimals - token1_decimals))
    return price

# Display LP data
st.title("🔍 PRJX LP Tracker — Hyperliquid")

positions = fetch_positions()

for pos in positions:
    pool = pos["pool"]
    token0 = pool["token0"]
    token1 = pool["token1"]
    price = sqrt_price_to_price(pool["sqrtPrice"], int(token0["decimals"]), int(token1["decimals"]))

    with st.expander(f"🔹 Position {pos['id'][:8]}... by {pos['owner'][:8]}..."):
        st.markdown(f"**Pool**: `{token0['symbol']}` / `{token1['symbol']}`")
        st.markdown(f"**Liquidity**: `{pos['liquidity']}`")
        st.markdown(f"**Tick Range**: `{pos['tickLower']['tickIdx']}` - `{pos['tickUpper']['tickIdx']}`")
        st.markdown(f"**Current Price**: `1 {token0['symbol']} ≈ {price:.6f} {token1['symbol']}`")
        st.markdown(f"**Fee Tier**: `{int(pool['feeTier']) / 10000:.2%}`")

        # Placeholder for future: estimated value + IL
        st.info("➡️ Prochaines étapes : Calcul valeur LP + Impermanent Loss")
