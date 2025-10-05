
# Technical Specification for V4 Market Data Visualizer

This document details the structure and logic required to replicate the single-file web application for visualizing WSS trade data. The application's core function is to process raw trade ticks from an uploaded file and render them in a real-time-like OHLC candlestick chart, segmented volume bars, and unique "High Impact" trade bubbles.

## 1. Application Goals and Constraints

| Feature | Requirement | 
| :--- | :--- | 
| **Type** | Single-page HTML application | 
| **Output** | Interactive ECharts candlestick and bar chart | 
| **Data Source** | Local file input (simulating a live feed) | 
| **Core Logic** | Aggregation of raw ticks into OHLC bars, four-way volume split, and high-impact trade bubble generation. | 
| **File Mandate** | **MUST** be implemented in a single `index.html` file. | 

## 2. External Dependencies

The application relies on two external libraries, loaded via CDN links in the `<head>` section:

1. **Tailwind CSS:** For all styling and responsive layout. The script `https://cdn.tailwindcss.com` is required. The `Inter` font is specified via a standard CSS `@import`.

2. **ECharts:** For all charting functionality (Candlestick, Bar, Scatter). The script `https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js` is required.

## 3. HTML Structure (`<div id="app">`)

The application must be contained within a responsive wrapper and include three main structural areas:

| ID / Element | Purpose | 
| :--- | :--- | 
| `#app` | Main application container (Max-width 7xl, centered). | 
| **Controls Panel** | A flex container (`flex-wrap`) holding all user inputs. | 
| `#data-file-input` | `input type="file"` for loading the WSS trade messages. | 
| `#security-select` | `select` dropdown to choose the instrument ID found in the file. | 
| `#interval-input` | `input type="text"` for setting OHLC aggregation period (e.g., `30S`, `1T`). | 
| `#threshold-input` | `input type="number"` for **Minimum Total Bubble Volume (Q)**. | 
| `#big-player-threshold-input` | `input type="number"` for **Minimum Single LTQ** (Big Player definition). | 
| `#status-indicator` | Visual status and feedback mechanism. | 
| **Chart Area** | A relative container for the chart and fallback message. | 
| `#trading-chart` | The main `div` where ECharts is initialized and rendered (`h-[65vh]`). | 
| `#no-data-message` | An overlay message displayed when no file is loaded or data is present. | 
| **Debug/Log Area** | Output for simulation messages. | 
| `#last-update-info` | A small, scrollable `div` to log system activity and status updates. | 

## 4. JavaScript Globals and State

The script section must define the following global variables to manage application state and data:

| Variable | Initial Value | Purpose | 
| :--- | :--- | :--- | 
| `tradingChart` | `null` | ECharts instance object. | 
| `chartData` | `{ ohlc: [], bubbles: [] }` | Final aggregated data structures for charting. | 
| `currentSecurity` | `''` | Currently selected instrument ID. | 
| `currentInterval` | `'30S'` | Current OHLC aggregation interval. | 
| `currentThreshold` | `20` | Minimum total quantity for a bubble. | 
| `currentBigPlayerThreshold` | `50` | Minimum single LTQ defining a "Big Player" trade. | 
| `rawTradeData` | `[]` | Array of processed trade objects (ticks) from the file. | 
| `simulatedMessages` | `[]` | Array of raw string lines (WSS messages) from the uploaded file. | 
| `globalAvgLtq` | `1` | Average LTQ across all trades in the loaded file (used for bubble size/impact). | 
| `lastTradePrice` | `null` | Used to determine the **aggressor proxy** for volume split. | 
| `historicalOhlcData` | `[]` | **MUST** remain empty to prevent data contamination. | 

## 5. JavaScript Execution Flow (Key Functions)

The logic must flow strictly through the following steps after a file is selected:

### 5.1. File Loading and Security Scan

1. **`handleFileSelect(event)`:** Triggers upon file input change. Calls `readFileContents(file)`.

2. **`readFileContents(file)`:**

   * Reads the file content as text.

   * Splits the content into an array of lines, populating `simulatedMessages`.

   * Calls `scanMessagesForSecurities(messages)`.

3. **`scanMessagesForSecurities(messages)`:**

   * Iterates through all messages.

   * Parses each line as JSON.

   * Extracts all unique instrument IDs from the `feeds` object keys.

   * Updates the `#security-select` dropdown.

   * Sets `currentSecurity` to the first instrument ID found.

   * On success, calls **`startChartPipeline()`**.

### 5.2. The Orchestrator: `startChartPipeline()`

This function is the single point of truth for data processing:

1. **Cleanup:** Disposes of the existing ECharts instance (`echarts.dispose(tradingChart)`).

2. **Reset:** Clears `rawTradeData = []` and resets `lastTradePrice = null`. **This is critical to prevent old data from polluting the new visualization.**

3. **Process Ticks:** Iterates through all lines in `simulatedMessages`, calling `processTradeMessage(message)` for each one to populate `rawTradeData`.

4. **Calculate Average:** Calls `calculateGlobalAverage(rawTradeData)` to set the global `globalAvgLtq`.

5. **Aggregate:** Calls `aggregateAndResample(rawTradeData, currentThreshold)`.

6. **Render:** Calls `drawChart(chartData.ohlc, chartData.bubbles)`.

### 5.3. Trade Tick Processing: `processTradeMessage(dataString)`

This function translates raw WSS messages into structured trade objects:

1. **Extraction:** Parses the JSON string and extracts `ltp` (price), `ltt` (timestamp), and `ltq` (quantity) for the `currentSecurity`.

2. **Aggressor Proxy Logic (CRITICAL):** Determines the trade direction based on price movement:

   * If `lastTradePrice` is `null` (first trade), set `aggressor` to `'BUY'`.

   * If `newPrice > lastTradePrice` (uptick), set `aggressor` to `'BUY'`.

   * If `newPrice < lastTradePrice` (downtick), set `aggressor` to `'SELL'`.

   * If `newPrice == lastTradePrice`, set `aggressor` to `'BUY'` (assumed momentum/continuation).

3. **Storage:** Pushes the new `{time, price, quantity, aggressor}` object into the `rawTradeData` array.

4. **Update:** Updates `lastTradePrice = newPrice`.

### 5.4. Aggregation: `aggregateAndResample(trades, threshold)`

This function performs two distinct aggregations using the `currentInterval`, `currentThreshold`, and `currentBigPlayerThreshold`:

#### A. High-Impact Bubble Generation (`bubbles`):

1. **Grouping:** Groups trades by **exact timestamp** (`trade.time.getTime()`).

2. **Calculation:** Calculates the `sumLtq` and `maxLtq` for each exact timestamp group.

3. **Filtering:** A group is a high-impact bubble if:

   * `sumLtq >= currentThreshold` **AND**

   * `maxLtq >= currentBigPlayerThreshold`

4. **Impact Score:** The `impactScore` is calculated as $\text{MaxLTQ} / \text{GlobalAvgLTQ}$.

5. **Output:** Returns an array of bubble objects: `{ x: timestamp, y: price, q: sumLtq, impactScore }`.

#### B. OHLC Candlestick Generation (`ohlc`):

1. **Interval Calculation:** Determines `intervalMs` based on `currentInterval` (e.g., '30S' $\rightarrow$ $30000$ ms).

2. **Time Bucketing:** Calculates the `intervalStartMs` for each trade using $\text{Math.floor}(\text{timeMs} / \text{intervalMs}) * \text{intervalMs}$.

3. **OHLCV Update:** For each bucket, updates the `open`, `high`, `low`, `close` and **volume tracking**:

   * **Four-Way Volume Split:** Separately tracks volume based on the `aggressor` and the `isBigPlayer` status ($\text{trade.quantity} \ge \text{currentBigPlayerThreshold}$):

     * `buyVolume`, `bigPlayerBuyVolume`

     * `sellVolume`, `bigPlayerSellVolume`

4. **Output:** Returns a sorted array of OHLC objects.

### 5.5. Chart Rendering: `drawChart(ohlcData, bubbleData)`

1. **Initialization:** Initializes ECharts on the `#trading-chart` element.

2. **Data Mapping:** Converts the OHLC and Volume data into the ECharts array format.

3. **Dynamic Bubble Properties:**

   * **`symbolSize`:** Must be a function that calculates bubble size based on the raw quantity ($\text{data}[2]$) normalized against the global average LTQ ($\text{globalAvgLtq}$). This creates the visual effect of larger bubbles for higher volume trades.

   * **`itemStyle.color`:** Must be a function that calculates color using **HSL** based on the `impactScore` ($\text{data}[3]$). The color should shift across a hue range (e.g., $100^{\circ}$ to $0^{\circ}$) as the impact score increases from $1.0$ up to a maximum visualization cap (e.g., $5.0$).

4. **ECharts Configuration:** Sets up a main grid (Grid 0) for Candlestick/Scatter and a stacked grid (Grid 1) for Volume.

5. **Series Definition (CRITICAL):**

   * **Series 1 (Candlestick):** Uses $\text{xAxisIndex: 0}$, $\text{yAxisIndex: 0}$.

   * **Series 2 (Scatter - Bubbles):** Uses $\text{xAxisIndex: 0}$, $\text{yAxisIndex: 0}$. **Must use a custom `symbolSize` and color function.**

   * **Series 3, 4, 5, 6 (Bar - Volume):** All must use $\text{xAxisIndex: 1}$, $\text{yAxisIndex: 1}$. They must be **stacked** ($\text{stack: 'TotalVolume'}$) and use the four different volume data arrays (Normal Buy, Big Player Buy, Normal Sell, Big Player Sell) with distinct colors.

## 6. Self-Contained Implementation

The entire application logic is contained within the single `index.html` file, including all necessary Firebase boilerplate variables (though unused in the current version) to comply with the canvas environment:

```

// Boilerplate Firebase structure (not used in this example)
const \_\_app\_id = 'trading-file-app';
const \_\_firebase\_config = '{}';
const \_\_initial\_auth\_token = undefined;

```

**Instruction:** The resulting HTML file must be fully self-contained, requiring no external JavaScript or CSS files beyond the CDNs specified.
```

```
```
