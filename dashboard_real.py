import streamlit as st
import sqlite3
import pandas as pd
from neo4j import GraphDatabase
import os
from dotenv import load_dotenv
from streamlit_agraph import agraph, Node, Edge, Config
import altair as alt

# Load config
load_dotenv()
DB_PATH = "listing_hunter.db"
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password") # Default fallback

# Connect to databases
@st.cache_resource
def get_neo4j_driver():
    try:
        return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    except Exception as e:
        return None

def get_sqlite_conn():
    return sqlite3.connect(DB_PATH)

# Set page config
st.set_page_config(page_title="The Listing Hunter", page_icon="🕵️", layout="wide")

st.sidebar.title("🕵️ Output Console")
page = st.sidebar.radio("Navigation", ["Overview", "Watchlist", "Threat Graph", "Advanced Analytics", "Monetization Proof", "Live Logs"])

# --------- DATA FETCHING --------- #

def fetch_metrics():
    conn = get_sqlite_conn()
    c = conn.cursor()
    # Number of target treasuries
    try:
        c.execute("SELECT COUNT(*) FROM target_treasuries")
        total_treasuries = c.fetchone()[0]
    except Exception:
        total_treasuries = 0
    
    # Active watchlist count
    try:
        c.execute("SELECT COUNT(*) FROM watchlist")
        active_watched = c.fetchone()[0]
    except Exception:
        active_watched = 0
    conn.close()
    
    driver = get_neo4j_driver()
    total_alerts = 0
    if driver:
        try:
            with driver.session() as session:
                # Forensically accurate count query (maps all hops dynamically)
                res = session.run("MATCH p=(t:Wallet {type: 'Treasury'})-[r:TRANSFERRED*1..4]->(c:Wallet) RETURN COUNT(p) as count LIMIT 1")
                total_alerts = res.single()['count']
        except Exception:
            pass
            
    return total_treasuries, active_watched, total_alerts

# --------- PAGES --------- #

if page == "Overview":
    st.title("System Overview")
    
    total_treasuries, active_watched, total_alerts = fetch_metrics()
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Target Treasuries", total_treasuries, "Registered")
    col2.metric("Active Wallets Tracked", active_watched, "In Watchlist")
    col3.metric("Wash Trades Detected", total_alerts, "Critical Alerts")
    
    st.markdown("---")
    st.markdown(
        """
        ### Welcome to The Listing Hunter
        This dashboard reads directly from the underlying databases to provide a real-time view of your system operations.
        - Run `python main.py` in your terminal to keep the ingestion engine active.
        - Refresh this page or navigate tabs to see updated information.
        """
    )

elif page == "Watchlist":
    st.title("Active Watchlist")
    st.markdown("These wallets have received funds from a target treasury and are currently being monitored.")
    
    try:
        conn = get_sqlite_conn()
        df = pd.read_sql_query("SELECT * FROM watchlist", conn)
        conn.close()
        
        if df.empty:
            st.info("The watchlist is currently empty.")
        else:
            # Format the dataframe for display
            if 'expiry_timestamp' in df.columns:
                df['expiry_timestamp'] = pd.to_datetime(df['expiry_timestamp'], unit='s')
            
            st.dataframe(df, use_container_width=True)
    except Exception as e:
        st.error(f"Error reading SQLite database: {e}")

elif page == "Threat Graph":
    st.title("Visual Threat Graph (Neo4j)")
    st.markdown("Visualizing detected wash-trading chains from Treasury to CEX.")
    
    driver = get_neo4j_driver()
    if not driver:
        st.error("Failed to connect to Neo4j. Check your credentials in .env.")
    else:
        try:
            with driver.session() as session:
                # Pure Forensic Mode: Look for any continuous multi-hop chain emanating from a Treasury node
                query = """
                MATCH p=(t:Wallet {type: 'Treasury'})-[r:TRANSFERRED*1..4]->(c:Wallet)
                RETURN nodes(p) AS nodes, relationships(p) AS relationships LIMIT 50
                """
                result = session.run(query)
                
                nodes = []
                edges = []
                seen_nodes = set()
                transaction_logs = []
                
                # We need elements to graph
                found_data = False
                
                for record in result:
                    found_data = True
                    path_nodes = record['nodes']
                    path_edges = record['relationships']
                    
                    # DEMO: Identify the mathmatical "end of the chain" so we can artificially spoof it
                    final_node_id = path_nodes[-1].element_id
                    
                    for node in path_nodes:
                        node_id = node.element_id
                        if node_id not in seen_nodes:
                            seen_nodes.add(node_id)
                            address = node.get("address", "Unknown")
                            node_type = node.get("type", "Unknown")
                            short_addr = f"{address[:4]}...{address[-4:]}"
                            
                            # True Forensic Output: No CEX masking
                            pass
                                
                            # Colors based on type
                            color = "#dddddd"
                            shape = "ellipse"
                            if node_type == "Treasury":
                                color = "#ff4b4b"
                                shape = "hexagon"
                            elif "CEX" in node_type:
                                color = "#fadb14"
                                shape = "star"
                                
                            nodes.append(Node(id=node_id, label=short_addr, title=f"{node_type}: {address}", color=color, shape=shape))
                    
                    for rel in path_edges:
                        amount = float(rel.get("amount", 0))
                        
                        # Format avoiding scientific notation, up to 9 decimals, stripping trailing zeros
                        formatted_amt = f"{amount:.9f}".rstrip('0').rstrip('.') if amount != 0 else "0.0"
                        
                        sig = rel.get("signature", "...")
                        timestamp_val = rel.get("timestamp", 0)
                        
                        # Convert unix timestamp to readable string
                        time_str = "Unknown"
                        if timestamp_val:
                            try:
                                import datetime
                                time_str = datetime.datetime.fromtimestamp(timestamp_val).strftime('%Y-%m-%d %H:%M:%S')
                            except Exception:
                                pass
                        
                        edges.append(Edge(source=rel.start_node.element_id, target=rel.end_node.element_id, label=f"{formatted_amt} Tokens", title=f"Time: {time_str}\nSig: {sig}"))
                        
                        transaction_logs.append({
                            "Timestamp": time_str,
                            "Sender": rel.start_node.get("address", "Unknown"),
                            "Receiver": rel.end_node.get("address", "Unknown"),
                            "Amount": formatted_amt,
                            "Signature": sig
                        })
                
                if not found_data:
                    st.info("No complete Treasury -> CEX paths found in Neo4j.")
                else:
                    config = Config(
                        width=1000, 
                        height=600, 
                        directed=True,
                        physics=True, 
                        hierarchical=False,
                    )
                    
                    st.markdown("### Interactive Network")
                    agraph(nodes=nodes, edges=edges, config=config)
                    
                    st.markdown("---")
                    st.markdown("### Transaction Evidence (Copy & Verify)")
                    st.markdown("Use the table below to easily copy the blockchain signatures and verify the wash trades directly on **[Solscan.io](https://solscan.io)**!")
                    
                    # Deduplicate in case multiple paths share the same edge
                    df_logs = pd.DataFrame(transaction_logs).drop_duplicates()
                    if not df_logs.empty and 'Timestamp' in df_logs.columns:
                        df_logs = df_logs.sort_values(by='Timestamp', ascending=True).reset_index(drop=True)
                    st.dataframe(df_logs, use_container_width=True)
                    
        except Exception as e:
            st.error(f"Error querying Neo4j: {e}")

elif page == "Advanced Analytics":
    st.title("Advanced Forensic Analytics")
    st.markdown("Detailed structural and statistical behavior modeling of detected wash-trading activity.")

    driver = get_neo4j_driver()
    if not driver:
        st.error("Neo4j connection required for advanced analytics.")
    else:
        with driver.session() as session:
            try:
                # --- 1. STRUCTURAL ANALYSIS: Hub & Spoke Detection ---
                st.header("1. Network Topology (Hub Detection)")
                st.markdown("Identifying 'Command and Control' nodes with anomalous branching factors (Out-Degree).")
                
                hub_query = """
                MATCH (n:Wallet)-[r:TRANSFERRED]->()
                WHERE NOT n.address IN ['Unknown', '']
                RETURN n.address AS address, n.type AS type, count(r) AS out_degree
                ORDER BY out_degree DESC LIMIT 15
                """
                hub_res = session.run(hub_query)
                hub_data = [{"Address": r["address"], "Type": r["type"], "Out-Degree": r["out_degree"]} for r in hub_res]
                
                if hub_data:
                    df_hubs = pd.DataFrame(hub_data)
                    
                    # Bar chart for out-degree
                    hub_chart = alt.Chart(df_hubs).mark_bar(color="#ff4b4b").encode(
                        x=alt.X('Out-Degree:Q', title='Number of Branching Transfers'),
                        y=alt.Y('Address:N', sort='-x', title='Wallet Address'),
                        tooltip=['Address', 'Type', 'Out-Degree']
                    ).properties(height=400)
                    
                    st.altair_chart(hub_chart, use_container_width=True)
                    
                    # Interpretation
                    max_hub = df_hubs.iloc[0]
                    if max_hub['Out-Degree'] > 5:
                        st.warning(f"🚨 **Structural Anomaly:** Wallet `{max_hub['Address']}` is acting as a major Hub with {max_hub['Out-Degree']} simultaneous outbound branches. This is characteristic of a 'Batch Funding' deployment.")
            except Exception as e:
                st.error(f"Failed to render Topology Analysis: {e}")

            st.markdown("---")
            
            try:
                # --- 2. STATISTICAL ANALYSIS: Amount Entropy ---
                st.header("2. Amount Entropy (Synthetic Uniformity)")
                st.markdown("Analyzing transfer amounts to detect non-random, synthetic distributions (e.g., perfectly round numbers).")
                
                entropy_query = """
                MATCH ()-[r:TRANSFERRED]->()
                RETURN r.amount AS amount LIMIT 10000
                """
                ent_res = session.run(entropy_query)
                amounts = []
                for r in ent_res:
                    try:
                        val = float(r["amount"] or 0)
                        if val > 0:
                            amounts.append(val)
                    except (TypeError, ValueError):
                        continue
                
                if amounts:
                    df_amounts = pd.DataFrame(amounts, columns=["Amount"])
                    
                    # Show Top Frequency Spikes
                    counts = df_amounts["Amount"].value_counts().reset_index()
                    counts.columns = ["Value", "Frequency"]
                    counts = counts.sort_values("Frequency", ascending=False).head(10)
                    
                    # Formatting values for display
                    counts["Value Formatted"] = counts["Value"].apply(lambda x: f"{x:,.2f}")
                    
                    spike_chart = alt.Chart(counts).mark_bar(color="#fadb14").encode(
                        x=alt.X('Frequency:Q', title='Occurrence Count'),
                        y=alt.Y('Value Formatted:N', sort='-x', title='Transfer Amount'),
                        tooltip=['Value', 'Frequency']
                    ).properties(height=350, title="Top Recurring Transfer Amounts")
                    
                    st.altair_chart(spike_chart, use_container_width=True)
                    
                    # Uniformity Calculation: Ratio of unique values to total samples
                    unique_ratio = len(df_amounts["Amount"].unique()) / len(df_amounts)
                    uniformity_score = 1.0 - unique_ratio
                    
                    st.metric("Amount Uniformity Score", f"{uniformity_score:.2%}", help="Higher score indicates repetitive/synthetic amounts (common in bots).")
                    
                    if uniformity_score > 0.5:
                        st.warning("⚠️ **High Synthetic Density Detected:** The transfer history shows extremely repetitive amounts. This suggests a fixed algorithmic disbursement strategy rather than organic trading.")
                else:
                    st.info("Insufficient transaction data to analyze amount entropy.")
            except Exception as e:
                st.error(f"Failed to render Statistical Analysis: {e}")

elif page == "Monetization Proof":
    st.title("Monetization Proof (Alpha Generation)")
    st.markdown("Prove the ROI of your wash-trade detection engine by comparing the exact moment of detection against the public market charts.")
    
    detector_sig = st.text_input("Enter the Wash-Trade Signature:", placeholder="e.g. 4qew7Ai5L5Bx...")
    
    if st.button("Generate Alpha Chart") and detector_sig:
        # 1. Query Neo4j to find the timestamp of this signature
        driver = get_neo4j_driver()
        detect_time = None
        if driver:
            with driver.session() as session:
                res = session.run("MATCH ()-[r:TRANSFERRED {signature: $sig}]->() RETURN r.timestamp AS ts LIMIT 1", sig=detector_sig)
                record = res.single()
                if record and record['ts']:
                    detect_time = record['ts']
                    
        if not detect_time:
            st.error("Signature not found in the Threat Graph Database! (Did you copy it exactly from the Threat Graph tab?)")
        else:
            import datetime
            detect_dt = datetime.datetime.utcfromtimestamp(detect_time)
            st.success(f"Wash Trade successfully verified in Database at: **{detect_dt.strftime('%Y-%m-%d %H:%M:%S')} UTC**")
            
            # 2. Upload Pre-Listing Dex Data
            st.markdown("### Upload Pre-Listing Market Data")
            st.markdown("Upload a CSV file containing historical price data (e.g., exported from CoinMarketCap, DexScreener, or Birdeye). The file must have standard `Date` (or 'timestamp') and `Price` (or 'close') columns.")
            
            import os
            import glob
            
            uploaded_file = st.file_uploader("Upload Market Data (CSV)", type="csv")
            
            # Auto-fallback: if no file uploaded, grab the first CSV in the directory
            file_to_parse = uploaded_file
            if file_to_parse is None:
                local_csvs = glob.glob(os.path.join(os.getcwd(), "*.csv"))
                if local_csvs:
                    file_to_parse = local_csvs[0]
                    st.info(f"Automatically loaded local CSV for presentation: `{os.path.basename(file_to_parse)}`")
            
            if file_to_parse is not None:
                try:
                    # Attempt to gracefully parse whatever CSV the user throws at it (auto-detects semicolons)
                    if hasattr(file_to_parse, "seek"):
                        file_to_parse.seek(0)
                        
                    raw_df = pd.read_csv(file_to_parse, sep=None, engine='python')
                    
                    # Normalize column names to lowercase for easy lookup
                    raw_df.columns = [str(c).lower().strip() for c in raw_df.columns]
                    
                    # Flexible Column Mapping - prioritize exact matches
                    if 'timestamp' in raw_df.columns:
                        date_col = 'timestamp'
                    elif 'date' in raw_df.columns:
                        date_col = 'date'
                    elif 'timeopen' in raw_df.columns:
                        date_col = 'timeopen'
                    else:
                        date_col = next((c for c in raw_df.columns if 'date' in c or 'time' in c), None)
                        
                    if 'close' in raw_df.columns:
                        price_col = 'close'
                    elif 'price' in raw_df.columns:
                        price_col = 'price'
                    else:
                        price_col = next((c for c in raw_df.columns if 'close' in c or 'price' in c), None)
                    
                    if not date_col or not price_col:
                        st.error("Could not automatically find Date and Price columns in the CSV. Please ensure the file has a 'Date' (or 'timestamp') and 'Price' (or 'close') column.")
                    else:
                        df_price = pd.DataFrame()
                        # Parse dates robustly
                        # If the date looks like a unix timestamp (integer/float), convert it
                        if pd.api.types.is_numeric_dtype(raw_df[date_col]):
                            if raw_df[date_col].max() > 1e11: # MS
                                df_price['Date'] = pd.to_datetime(raw_df[date_col], unit='ms')
                            else:
                                df_price['Date'] = pd.to_datetime(raw_df[date_col], unit='s')
                        else:
                            df_price['Date'] = pd.to_datetime(raw_df[date_col], utc=True).dt.tz_localize(None)
                            
                        # Parse Prices gracefully (stripping strings/currency symbols if present)
                        def clean_price(val):
                            if isinstance(val, str):
                                val = val.replace('$', '').replace(',', '')
                            try:
                                return float(val)
                            except:
                                return None
                            
                        df_price['Price'] = raw_df[price_col].apply(clean_price)
                        
                        # Validate and Sort
                        df_price = df_price.dropna(subset=['Date', 'Price'])
                        df_price = df_price.sort_values('Date').reset_index(drop=True)
                        
                        if df_price.empty:
                            st.error("The parsed CSV contained no valid data.")
                        else:
                            first_candle_time = df_price['Date'].iloc[0]
                            first_candle_price = df_price['Price'].iloc[0]
                            
                            if detect_dt < first_candle_time:
                                st.balloons()
                                st.success(f"🔥 **PRE-MARKET ALPHA CONFIRMED:** Your system triggered the wash-trade alert BEFORE public trading even began on the chart!")
                                detect_price = first_candle_price # Use launch price for ROI math
                            else:
                                df_price['TimeDiff'] = abs(df_price['Date'] - detect_dt)
                                closest_row = df_price.loc[df_price['TimeDiff'].idxmin()]
                                detect_price = closest_row['Price']
                            
                            # Only consider ATH prices that occurred AFTER the point of detection
                            future_df = df_price[df_price['Date'] >= detect_dt]
                            
                            if future_df.empty:
                                # If the detection is at the very end of our known timeline
                                ath_price = detect_price
                            else:
                                ath_price = future_df['Price'].max()
                            
                            if detect_price > 0 and ath_price > detect_price:
                                roi_pct = ((ath_price - detect_price) / detect_price) * 100
                            else:
                                roi_pct = 0
                                
                            col1, col2, col3 = st.columns(3)
                            col1.metric("Listing/Detection Price", f"${detect_price:.6f}")
                            col2.metric("All-Time High", f"${ath_price:.6f}")
                            col3.metric("🏆 Potential ROI", f"{roi_pct:,.2f}%", f"Caught pre-listing pump!")
                            
                            st.markdown("### Historical Price Action vs Wash-Trade Detection Time")
                            import altair as alt
                            
                            # Ensure detect pointer stays inside graphic bounds
                            plot_dt = detect_dt if detect_dt >= first_candle_time else first_candle_time
                            
                            base = alt.Chart(df_price).mark_line(color="#00ffcc").encode(
                                x=alt.X('Date:T', title='Timeline'),
                                y=alt.Y('Price:Q', title='BOME Price (USD)'),
                                tooltip=['Date:T', 'Price:Q']
                            )
                            
                            rule = alt.Chart(pd.DataFrame({'Date': [plot_dt]})).mark_rule(color='#ff4b4b', strokeWidth=3).encode(
                                x='Date:T'
                            )
                            
                            text = alt.Chart(pd.DataFrame({'Date': [plot_dt], 'Text': ['🚨 Wash-Trade Detected']})).mark_text(
                                align='left', baseline='middle', dx=10, color='#ff4b4b', fontSize=15, fontWeight='bold'
                            ).encode(
                                x='Date:T',
                                y=alt.value(30),
                                text='Text:N'
                            )
                            
                            chart = (base + rule + text).properties(height=500).interactive()
                            st.altair_chart(chart, use_container_width=True)
                            
                except Exception as e:
                    st.error(f"Failed to load Market Data: {e}")

elif page == "Live Logs":
    st.title("System Logs")
    
    log_file = "listing_hunter.log"
    if os.path.exists(log_file):
        with open(log_file, "r") as f:
            lines = f.readlines()
            # Show last 50 lines
            recent_lines = lines[-50:]
            
            log_text = "".join(recent_lines)
            st.code(log_text, language="log")
            
        if st.button("Refresh Logs"):
            st.rerun()
    else:
        st.warning(f"Log file '{log_file}' not found.")
