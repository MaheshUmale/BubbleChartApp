import upstox_client
from upstox_client.rest import ApiException
from upstox_client.models import MarketDataStreamerV3
from mpubsub import mpubsub
import threading
import time
import json
import logging
from datetime import datetime

# --- Configuration ---
# Replace with your actual Access Token
ACCESS_TOKEN = "YOUR_UPSTOX_ACCESS_TOKEN" 
# Configure logging for better visibility
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Initialize the mpubsub broker (main process)
# This broker can handle both in-process and inter-process communication
# For inter-process, you'd typically start it separately, but here we can integrate it.
pubsub_broker = mpubsub.LocalPubSub() # Or mpubsub.NetPubSub('your_address') for remote

# --- Upstox WebSocket Publisher ---
class UpstoxDataPublisher:
    def __init__(self, access_token, instrument_keys, pubsub_broker):
        self.access_token = access_token
        self.instrument_keys = instrument_keys
        self.pubsub_broker = pubsub_broker
        self.streamer = None

    def on_open(self, ws):
        logging.info("WebSocket connected. Subscribing to instruments...")
        data = {
            "guid": "some_unique_guid", # A unique identifier for your request
            "method": "sub",
            "data": {
                "mode": "ltpc", # Last Traded Price & Close
                "instrumentKeys": self.instrument_keys,
            },
        }
        # The Upstox WebSocket expects a binary frame
        ws.send(json.dumps(data).encode('utf-8'))

    def on_message(self, ws, message):
        # Decode the protobuf message received from Upstox
        # You'll need the Upstox protobuf definitions and `pip install protobuf`
        # For simplicity, this example assumes the message is JSON if not protobuf
        # You would typically have a decodeProtobuf function here.
        # This part requires the generated `market_data_feed_pb2.py`
        # For demonstration, we'll just print the raw message and try to parse it as JSON
        try:
            decoded_message = json.loads(message.decode('utf-8'))
        except json.JSONDecodeError:
            logging.warning(f"Could not decode message as JSON: {message}")
            return
        
        # Check if it's an actual feed or other market_info frame
        if 'feeds' in decoded_message:
            for instrument_key, feed_data in decoded_message['feeds'].items():
                if 'ltpc' in feed_data:
                    ltpc_data = {
                        "instrument_key": instrument_key,
                        "ltp": feed_data['ltpc']['ltp'],
                        "ltq": feed_data['ltpc']['ltq'], # Last Traded Quantity (if available in mode)
                        "ltt": feed_data['ltpc']['ltt'], # Last Traded Time (if available in mode)
                        "close_price": feed_data['ltpc']['cp'],
                        "timestamp": datetime.now().isoformat()
                    }
                    # Publish the LTPC data to mpubsub
                    self.pubsub_broker.publish(instrument_key, ltpc_data)
                    logging.debug(f"Published {ltpc_data} to topic {instrument_key}")
                else:
                    logging.debug(f"Received non-LTPC feed for {instrument_key}: {feed_data}")
        elif 'market_info' in decoded_message:
            logging.debug(f"Received market info: {decoded_message['market_info']}")
        else:
            logging.warning(f"Unhandled message type: {decoded_message}")


    def on_error(self, ws, error):
        logging.error(f"WebSocket error: {error}")

    def on_close(self, ws, close_status_code, close_msg):
        logging.info(f"WebSocket closed with code {close_status_code}: {close_msg}")

    def start_streaming(self):
        try:
            # Authorize market data feed to get the WebSocket URL
            configuration = upstox_client.Configuration()
            configuration.access_token = self.access_token
            api_client = upstox_client.ApiClient(configuration)
            market_data_feed_api = upstox_client.MarketDataFeedApi(api_client)

            response = market_data_feed_api.authorize_market_data_feed()
            websocket_url = response.data.authorized_redirect_uri

            self.streamer = MarketDataStreamerV3(
                websocket_url,
                self.on_open,
                self.on_message,
                self.on_error,
                self.on_close,
                auto_reconnect=True # Enable auto-reconnect for robustness
            )
            self.streamer.start() # This starts the WebSocket in a new thread
            logging.info("Market data streaming started.")
        except ApiException as e:
            logging.error(f"Upstox API exception: {e}")
        except Exception as e:
            logging.error(f"Error starting market data stream: {e}")

    def stop_streaming(self):
        if self.streamer:
            self.streamer.stop()
            logging.info("Market data streaming stopped.")

# --- Subscriber Functions (for plotting and saving) ---

# Example subscriber for real-time plotting (simulated)
def plot_data_subscriber(message):
    # In a real application, you would update a plot here (e.g., using Matplotlib, Plotly)
    # For a simple local plotter, you might have this running in a different process
    # and send the data over a shared queue or directly through mpubsub.
    logging.info(f"Plotting thread received for {message['instrument_key']}: LTP={message['ltp']}")
    # Simulate plotting time
    time.sleep(0.01) 

# Example subscriber for saving data
def save_data_subscriber(message):
    # In a real application, you would append this to a CSV or database
    # For simplicity, we just print here.
    logging.info(f"Saving thread received for {message['instrument_key']}: {message['ltp']}")
    with open(f"{message['instrument_key'].replace('|', '_')}_ltpc_data.csv", 'a') as f:
        f.write(f"{message['timestamp']},{message['instrument_key']},{message['ltp']},{message['close_price']}\n")
    # Simulate saving time
    time.sleep(0.005)


# --- Main Execution ---
if __name__ == "__main__":
    # Define your list of instrument keys
    # Example for NIFTY 50 and RELIANCE, update with your 30 tickers
    # You can find instrument keys from Upstox instrument master file
    instrument_keys = [
        "NSE_INDEX|Nifty 50",
        "NSE_EQ|INE002A01018", # Reliance Industries Ltd
        # Add your other 28 instrument keys here
    ]

    # --- Start Subscribers in separate processes/threads if needed ---
    # For demonstration, we'll run them as simple functions in the main thread
    # or as separate threads. For true multiprocessing with mpubsub,
    # you'd launch processes and pass the pubsub_broker instance to them.

    # Example for In-Process / Multi-threading
    # Create a separate PubSub instance for each subscriber thread/process
    # This ensures they get their own queue in the LocalPubSub
    
    # Subscriber for Plotting
    plot_pubsub_client = mpubsub.LocalPubSub()
    plot_pubsub_client.subscribe_all(plot_data_subscriber)
    plot_thread = threading.Thread(target=plot_pubsub_client.run, daemon=True)
    plot_thread.start()
    logging.info("Plotting subscriber thread started.")

    # Subscriber for Saving
    save_pubsub_client = mpubsub.LocalPubSub()
    save_pubsub_client.subscribe_all(save_data_subscriber)
    save_thread = threading.Thread(target=save_pubsub_client.run, daemon=True)
    save_thread.start()
    logging.info("Saving subscriber thread started.")


    # --- Start Upstox Data Publisher ---
    data_publisher = UpstoxDataPublisher(ACCESS_TOKEN, instrument_keys, pubsub_broker)
    publisher_thread = threading.Thread(target=data_publisher.start_streaming, daemon=True)
    publisher_thread.start()
    logging.info("Upstox Data Publisher thread started.")

    try:
        # Keep the main thread alive to allow the other threads to run
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("Shutting down...")
        data_publisher.stop_streaming()
        # pubsub_broker.stop() # If you were using a broker that needs explicit stopping
        logging.info("Application terminated.")

