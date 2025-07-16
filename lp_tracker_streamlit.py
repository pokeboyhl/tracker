import streamlit as st
import requests
from decimal import Decimal, getcontext
from datetime import datetime
import pandas as pd
import altair as alt

getcontext().prec = 28

SUBGRAPH_URL = "https://api.goldsky.com/api/public/project_cmbbm2iwckb1b01t39xed236t/subgraphs/uniswap-v3-hyperevm-position/prod/gn"

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

def sqrt_price_to_price(sqrt_price_x96, token0_decimals, token1_decimals):
    sqrt_price = Decimal(sqrt_price_x96) / (2 ** 96)
    price = sqrt_price ** 2 * Decimal(10) ** (token0_decimals - token1_decimals)
    return price

def tick_to_price(tick, token0_decimals, token1_decimals):
    return Decimal(1.0001) ** tick * Decimal(10) ** (token0_decimals - token1_decimals)

def get_token_amounts(liquidity, sqrt_price_x96, tick_lower, tick_upper, token0_decimals, token1_decimals):
    liquidity = Decimal(liquidity)
    sqrt_price = Decimal(sqrt_price_x96)

    sqrtPl = Decimal(1.0001) ** Decimal(tick_lower)
    sqrtPu = Decimal(1.0001) ** Decimal(tick_upper)

    sqrtPlX96 = sqrtPl * (2 ** 96)
    sqrtPuX96 = sqrtPu * (2 ** 96)

    if sqrt_price <= sqrtPlX96:
        amount0 = liquidity * (sqrtPuX96 - sqrtPlX96) / (sqrtPlX96 * sqrtPuX96)
        amount1 = Decimal(0)
    elif sqrt_price < sqrtPuX96:
        amount0 = liquidity * (sqrtPuX96 - sqrt_price) / (sqrt_price * sqrtPuX96)
        amount1 = liquidity * (sqrt_price - sqrtPlX96) / (2 ** 96)
    else:
        amount0 = Decimal(0)
        amount1 = liquidity * (sqrtPuX96 - sqrtPlX96) / (2 ** 96)

    return (
        amount0 / Decimal(10 ** token0_decimals),
        amount1 / Decimal(10 ** token1_decimals)
    )
    ),
        amount1 / Decimal(10 ** token1_decimals),
    )

def calculate_impermanent_loss(price_initial, price_current):
    if price_initial == 0:
        return Decimal(0)
    ratio = Decimal(price_current) / Decimal(price_initial)
    il = (2 * (ratio.sqrt() / (1 + ratio)) - 1) * 100
    return il

st.title("🔍 PRJX LP Tracker — Hyperliquid")

wallet_input = st.text_input("🔑 Adresse du wallet (0x...)", "")
positions = fetch_positions(wallet_input if wallet_input else None)

export_data = []

if not positions:
    st.warning("Aucune position LP trouvée pour ce wallet.")
else:
    for pos in positions:
        pool = pos["pool"]
        token0 = pool["token0"]
        token1 = pool["token1"]
        token0_decimals = int(token0["decimals"])
        token1_decimals = int(token1["decimals"])
        sqrt_price_x96 = Decimal(pool["sqrtPrice"])
        price = sqrt_price_to_price(sqrt_price_x96, token0_decimals, token1_decimals)

        amount0, amount1 = get_token_amounts(
            pos["liquidity"], sqrt_price_x96, int(pos["tickLower"]["tickIdx"]), int(pos["tickUpper"]["tickIdx"]), token0_decimals, token1_decimals
        )

        sqrt_price_initial, ts = fetch_position_mint(pos["id"])
        if sqrt_price_initial:
            price_initial = sqrt_price_to_price(sqrt_price_initial, token0_decimals, token1_decimals)
            il_percent = calculate_impermanent_loss(price_initial, price)
            dt = datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d %H:%M UTC')
        else:
            price_initial = Decimal(1)
            il_percent = Decimal(0)
            dt = "Non disponible"

        fees0, fees1 = fetch_fees_collected(pos["id"])
        fees0 /= Decimal(10 ** token0_decimals)
        fees1 /= Decimal(10 ** token1_decimals)

        roi_net = (fees0 + fees1) - (amount0 + amount1) * il_percent / 100

        price_lower = tick_to_price(int(pos["tickLower"]["tickIdx"]), token0_decimals, token1_decimals)
        price_upper = tick_to_price(int(pos["tickUpper"]["tickIdx"]), token0_decimals, token1_decimals)

        export_data.append({
            "Position": pos['id'],
            "Token0": token0['symbol'],
            "Token1": token1['symbol'],
            "Holdings0": float(amount0),
            "Holdings1": float(amount1),
            "Fees0": float(fees0),
            "Fees1": float(fees1),
            "IL (%)": float(il_percent),
            "Date": dt,
            "ROI net": float(roi_net)
        })

        with st.expander(f"🔹 Position {pos['id'][:8]}... by {pos['owner'][:8]}..."):
            st.markdown(f"**Pool**: `{token0['symbol']}` / `{token1['symbol']}`")
            st.markdown(f"**Estimated Position Size**: ~`{amount0:.4f}` {token0['symbol']} + `{amount1:.4f}` {token1['symbol']}")
            st.markdown(f"**Active Range**: ~[{price_lower:.4f} - {price_upper:.4f}] {token1['symbol']}")
            st.markdown(f"**Current Price**: `1 {token0['symbol']} ≈ {price:.6f} {token1['symbol']}`")
            st.markdown(f"**Fee Tier**: `{Decimal(pool['feeTier']) / 1000000:.2%}`")
            if amount0 == 0 and amount1 == 0:
                st.warning("⚠️ Position currently out of range — no tokens active.")
            st.markdown(f"**Estimated holdings**: 🧮\n- `{amount0:.6f}` {token0['symbol']}\n- `{amount1:.6f}` {token1['symbol']}")
            st.markdown(f"**Initial Entry Price**: `{price_initial:.6f}` | 📅 `{dt}`")
            st.markdown(f"**Estimated Impermanent Loss**: `{il_percent:.2f}%`")
            st.markdown(f"**Fees collected**: 💸\n- `{fees0:.6f}` {token0['symbol']}\n- `{fees1:.6f}` {token1['symbol']}`")
            st.markdown(f"**ROI net (approx.)**: `{roi_net:.4f}`")

            chart_data = pd.DataFrame({
                "Category": ["Holdings", "Fees"],
                "Value": [float(amount0 + amount1), float(fees0 + fees1)]
            })
            bar_chart = alt.Chart(chart_data).mark_bar().encode(
                x="Category",
                y="Value",
                color="Category"
            ).properties(width=400, height=300)
            st.altair_chart(bar_chart, use_container_width=True)

    df = pd.DataFrame(export_data)
    st.download_button("⬇️ Télécharger CSV des positions", data=df.to_csv(index=False), file_name="positions_lp.csv", mime="text/csv")
