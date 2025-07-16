import streamlit as st
import requests
from decimal import Decimal, getcontext
from datetime import datetime

getcontext().prec = 28  # increase precision for Decimal

SUBGRAPH_URL = "https://api.goldsky.com/api/public/project_cmbbm2iwckb1b01t39xed236t/subgraphs/uniswap-v3-hyperevm-position/prod/gn"

# Function to fetch LP positions from subgraph
def fetch_positions(wallet=None):
    if wallet:
        wallet = wallet.lower()
        query = f"""
        {{
          positions(first: 20, where: {{ owner: \"{wallet}\" }}, orderBy: liquidity, orderDirection: desc) {{
            id
            owner
            liquidity
            tickLower {{ tickIdx }}
            tickUpper {{ tickIdx }}
            pool {{
              id
              feeTier
              sqrtPrice
              token0 {{ symbol decimals }}
              token1 {{ symbol decimals }}
              liquidity
            }}
          }}
        }}
        """
    else:
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

# Function to fetch the first mint for a position to determine the initial price and timestamp
def fetch_position_mint(position_id):
    query = f"""
    {{
      mints(first: 1, where: {{ position: \"{position_id}\" }}, orderBy: timestamp, orderDirection: asc) {{
        timestamp
        sqrtPrice
      }}
    }}
    """
    response = requests.post(SUBGRAPH_URL, json={"query": query})
    mints = response.json().get("data", {}).get("mints", [])
    if mints:
        return Decimal(mints[0]["sqrtPrice"]), int(mints[0]["timestamp"])
    return None, None

# Function to fetch collected fees for a position
def fetch_fees_collected(position_id):
    query = f"""
    {{
      collects(where: {{ position: \"{position_id}\" }}) {{
        amount0
        amount1
      }}
    }}
    """
    response = requests.post(SUBGRAPH_URL, json={"query": query})
    collects = response.json().get("data", {}).get("collects", [])
    total0 = sum(Decimal(c.get("amount0", "0")) for c in collects)
    total1 = sum(Decimal(c.get("amount1", "0")) for c in collects)
    return total0, total1

# Convert sqrtPriceX96 to price
def sqrt_price_to_price(sqrt_price_x96, token0_decimals, token1_decimals):
    sqrt_price = Decimal(sqrt_price_x96) / (2 ** 96)
    price = sqrt_price ** 2 * (10 ** (token0_decimals - token1_decimals))
    return price

# Estimate token0/token1 amounts from liquidity
def estimate_lp_token_amounts(liquidity, price, tick_lower, tick_upper):
    liquidity = Decimal(liquidity)
    sqrtP = Decimal(price).sqrt()
    sqrtPl = Decimal(1.0001) ** (Decimal(tick_lower) / 2)
    sqrtPu = Decimal(1.0001) ** (Decimal(tick_upper) / 2)

    if sqrtP <= sqrtPl:
        amount0 = liquidity * (sqrtPu - sqrtPl) / (sqrtPl * sqrtPu)
        amount1 = Decimal(0)
    elif sqrtP < sqrtPu:
        amount0 = liquidity * (sqrtPu - sqrtP) / (sqrtP * sqrtPu)
        amount1 = liquidity * (sqrtP - sqrtPl)
    else:
        amount0 = Decimal(0)
        amount1 = liquidity * (sqrtPu - sqrtPl)

    return amount0, amount1

# Calculate Impermanent Loss (approximate)
def calculate_impermanent_loss(price_initial, price_current):
    if price_initial == 0:
        return Decimal(0)
    ratio = Decimal(price_current) / Decimal(price_initial)
    il = (2 * (ratio.sqrt() / (1 + ratio)) - 1) * 100  # in percent
    return il

# Display LP data
st.title("🔍 PRJX LP Tracker — Hyperliquid")

wallet_input = st.text_input("🔑 Adresse du wallet (0x...)", "")
positions = fetch_positions(wallet_input if wallet_input else None)

if not positions:
    st.warning("Aucune position LP trouvée pour ce wallet.")
else:
    for pos in positions:
        pool = pos["pool"]
        token0 = pool["token0"]
        token1 = pool["token1"]
        price = sqrt_price_to_price(pool["sqrtPrice"], int(token0["decimals"]), int(token1["decimals"]))

        amount0, amount1 = estimate_lp_token_amounts(
            pos["liquidity"], price, int(pos["tickLower"]["tickIdx"]), int(pos["tickUpper"]["tickIdx"])
        )

        sqrt_price_initial, ts = fetch_position_mint(pos["id"])
        if sqrt_price_initial:
            price_initial = sqrt_price_to_price(sqrt_price_initial, int(token0["decimals"]), int(token1["decimals"]))
            il_percent = calculate_impermanent_loss(price_initial, price)
            dt = datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d %H:%M UTC')
        else:
            price_initial = Decimal(1)
            il_percent = Decimal(0)
            dt = "Non disponible"

        fees0, fees1 = fetch_fees_collected(pos["id"])

        with st.expander(f"🔹 Position {pos['id'][:8]}... by {pos['owner'][:8]}..."):
            st.markdown(f"**Pool**: `{token0['symbol']}` / `{token1['symbol']}`")
            st.markdown(f"**Liquidity**: `{pos['liquidity']}`")
            st.markdown(f"**Tick Range**: `{pos['tickLower']['tickIdx']}` - `{pos['tickUpper']['tickIdx']}`")
            st.markdown(f"**Current Price**: `1 {token0['symbol']} ≈ {price:.6f} {token1['symbol']}`")
            st.markdown(f"**Fee Tier**: `{int(pool['feeTier']) / 10000:.2%}`")
            st.markdown(f"**Estimated holdings**: 🧮\n- `{amount0:.6f}` {token0['symbol']}\n- `{amount1:.6f}` {token1['symbol']}")
            st.markdown(f"**Initial Entry Price**: `{price_initial:.6f}` | 📅 `{dt}`")
            st.markdown(f"**Estimated Impermanent Loss**: `{il_percent:.2f}%`)\n")
            st.markdown(f"**Fees collected**: 💸\n- `{fees0:.6f}` {token0['symbol']}\n- `{fees1:.6f}` {token1['symbol']}")

