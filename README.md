# The Listing Hunter: Solana Forensic Wash-Trading Engine

**The Listing Hunter** is a high-performance forensic analytics engine designed to detect pre-market wash-trading and "Mule" wallet activity on the Solana blockchain. By integrating real-time WebSocket ingestion with graph-based path analysis, the system provides a comprehensive threat visualization for professional blockchain forensics.

---

## Core Features

### 1. Real-Time Forensic Scanning
Monitors Solana WebSockets for any transaction involving known "Treasury" (deployer) wallets. It automatically parses instruction logs to detect capital disbursement patterns across hundreds of wallets in real-time.

### 2. Historical Replay Engine (Backtesting)
Performs "Time-Teleportation" to specific token listings (e.g., WIF, BOME). It fetches and re-analyzes historical transaction chains right before a CEX listing announcement to prove pre-market "Alpha" and insider accumulation.

### 3. Advanced Forensic Analytics
*   **Network Topology (Hub Detection):** Identifies "Command and Control" nodes in a laundering network by calculating anomalous branching factors (Out-Degree).
*   **Amount Entropy (Synthetic Uniformity):** Mathematically proves algorithmic botting by detecting repetitive, non-random transfer amounts (e.g., the 12.5M "Hydra" batch).

### 4. Interactive Threat Graph
Visualizes a global directed-property graph using **Neo4j**, linking origin Treasuries to final Exchange deposit addresses (Binance, Kraken, Coinbase, etc.), even across multiple intermediate "Mule" hops.

---

## Setup & Installation

### 1. Prerequisites
*   **Python 3.10+**
*   **Neo4j Database** (Local or AuraDB)
*   **Solana RPC** (Private Helius/QuickNode recommended for high-volume scanning)

### 2. Environment Configuration
Create a `.env` file in the root directory (refer to `.env.example`):
```bash
SOLANA_RPC_HTTP_URL=your_private_rpc_url
SOLANA_RPC_WS_URL=your_private_ws_url
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password
```

### 3. Install Dependencies
Run the provided setup script or manual install:
```bash
chmod +x setup_env.sh
./setup_env.sh
# OR manually
pip install -r requirements.txt
```

---

## Usage

### A. Running Live Detection
To start the real-time ingestor and monitor treasury wallets:
```bash
python main.py
```

### B. Running a Historical Backtest
To replay a specific token listing (e.g., verifying the WIF 12.5M batch):
```bash
python auto_backtester.py
```

### C. Launching the Forensic Dashboard
To visualize the Threat Graph and access Advanced Analytics:
```bash
streamlit run dashboard_real.py
```

---

## Architecture Overview

| Module | Purpose |
| :--- | :--- |
| `main.py` | Core listener orchestrator for live signals. |
| `forensics.py` | Pattern-matching engine for mule and wash-trade heuristics. |
| `replay_history.py` | Paginated forensic deep-crawler for backtesting. |
| `graph_manager.py` | Neo4j ingestion and path-finding integration. |
| `db_manager.py` | SQLite persistence for targets and local state. |

---

## Analytics Methodology

**The Listing Hunter** uses a **Multi-Hop Genealogy Tracking** method. Any wallet receiving directly from a Treasury is "Infected" and added to a persistent **Watchlist**. If that wallet sends funds downstream, the recipient is also flagged. The **Graph Analysis** then performs a `Shortest Path` search from any `CEX_Wallet` back to a `Treasury_Origin` to confirm the wash-trade cycle.

---

**Disclaimer:** This tool is for educational and academic forensic analysis only. Ensure you comply with all local regulations and RPC provider terms of service.
