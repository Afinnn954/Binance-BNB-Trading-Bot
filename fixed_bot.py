import time
import json
import logging
import threading
import random
import requests
import asyncio
import hmac
import hashlib
import urllib.parse
import queue
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ======== BOT CONFIGURATION ========
# Replace these values with your own
TELEGRAM_BOT_TOKEN = "BOT_TELEGRAM"  # Replace with your bot token
ADMIN_USER_IDS = [124999]    # Replace with your Telegram user ID(s)
# ==================================

# Binance API configuration
BINANCE_API_KEY = "API_KEY"  # Your Binance API key
BINANCE_API_SECRET = "API_SECRET" # Your Binance API secret
BINANCE_API_URL = "https://api.binance.com"
BINANCE_TEST_API_URL = "https://testnet.binance.vision"  # Testnet URL for testing

# Trading modes
TRADING_MODES = {
    "safe": {
        "take_profit": 1.5,  # 1.5% take profit
        "stop_loss": 5.0,    # 5.0% stop loss
        "max_trade_time": 300,  # 5 minutes max
        "volume_threshold": 100,  # Minimum volume in BNB
        "price_change_threshold": 1.0,  # Minimum 1% price change in 24h
        "max_trades": 3,  # Maximum concurrent trades
        "description": "Safe mode with lower risk and conservative profit targets"
    },
    "standard": {
        "take_profit": 2.5,  # 2.5% take profit
        "stop_loss": 7.5,    # 7.5% stop loss
        "max_trade_time": 600,  # 10 minutes max
        "volume_threshold": 50,  # Minimum volume in BNB
        "price_change_threshold": 0.5,  # Minimum 0.5% price change in 24h
        "max_trades": 5,  # Maximum concurrent trades
        "description": "Standard mode with balanced risk and profit targets"
    },
    "aggressive": {
        "take_profit": 3.5,  # 3.5% take profit
        "stop_loss": 10.0,    # 10% stop loss
        "max_trade_time": 1200,  # 20 minutes max
        "volume_threshold": 20,  # Minimum volume in BNB
        "price_change_threshold": 0.3,  # Minimum 0.3% price change in 24h
        "max_trades": 8,  # Maximum concurrent trades
        "description": "Aggressive mode with higher risk and profit targets"
    },
    "scalping": {
        "take_profit": 0.5,  # 0.5% take profit
        "stop_loss": 1.5,    # 1.5% stop loss
        "max_trade_time": 120,  # 2 minutes max
        "volume_threshold": 200,  # Higher volume requirement for scalping
        "price_change_threshold": 0.2,  # Minimum 0.2% price change
        "max_trades": 10,  # Maximum concurrent trades
        "description": "Ultra-fast scalping mode for quick profits"
    }
}

# Bot configuration
CONFIG = {
    "api_key": BINANCE_API_KEY,
    "api_secret": BINANCE_API_SECRET,
    "trading_pair": "BNBUSDT",  # Default to BNB/USDT
    "amount": 0.01,           # Amount of BASE ASSET to trade (e.g. 0.5 BNB for BNBUSDT, or 10 SOL for SOLBNB)
    "use_percentage": False,  # Whether to use percentage of balance
    "trade_percentage": 5.0,  # Percentage of balance to use (5%)
    "take_profit": 1.5,       # percentage
    "stop_loss": 5.0,         # percentage
    "trading_enabled": True,
    "whale_detection": True,    # Enable whale detection
    "whale_threshold": 100,     # BNB amount to consider as whale (100 BNB)
    "auto_trade_on_whale": False, # Auto trade when whale is detected
    "trading_strategy": "follow_whale", # follow_whale, counter_whale, dca
    "safety_mode": True,        # Additional safety checks
    "trading_mode": "safe",     # Current trading mode
    "max_trade_time": 300,      # Maximum time for a trade in seconds
    "auto_select_pairs": True,  # Automatically select best pairs
    "min_volume": 100,          # Minimum volume for pair selection
    "min_price_change": 1.0,    # Minimum 24h price change percentage
    "max_concurrent_trades": 3, # Maximum number of concurrent trades
    "market_update_interval": 30,  # Update market data every 30 seconds
    "use_testnet": True,        # Use Binance testnet for testing
    "use_real_trading": False,  # Set to True to enable real trading with Binance API
    "mock_mode": True,          # Set to False to disable mock data and use only real data
    "daily_loss_limit": 5.0,    # Daily loss limit in percentage
    "daily_profit_target": 10.0 # Daily profit target in percentage
}

# Active trades
ACTIVE_TRADES = []
COMPLETED_TRADES = []

# Daily statistics
DAILY_STATS = {
    "date": datetime.now().strftime("%Y-%m-%d"),
    "total_trades": 0,
    "winning_trades": 0,
    "losing_trades": 0,
    "total_profit_pct": 0.0,
    "total_profit_bnb": 0.0,
    "starting_balance": 0.0,
    "current_balance": 0.0
}

# Mock whale transactions (only used in mock mode)
MOCK_WHALE_TRANSACTIONS = []

# Initial mock market data for BNB pairs (only used in mock mode)
INITIAL_MARKET_DATA = [
    {"pair": "SOLBNB", "volume": 5882.66, "price_change": 4.59, "last_price": 0.2735},
    {"pair": "ALTBNB", "volume": 2184.30, "price_change": 11.33, "last_price": 0.0000629},
    {"pair": "SIGNBNB", "volume": 793.73, "price_change": -0.29, "last_price": 0.00014760},
    {"pair": "FETBNB", "volume": 759.47, "price_change": 6.53, "last_price": 0.001322},
    {"pair": "XRPBNB", "volume": 704.39, "price_change": 1.68, "last_price": 0.003858},
    {"pair": "CTKBNB", "volume": 543.54, "price_change": 3.67, "last_price": 0.000621},
    {"pair": "HBARBNB", "volume": 426.90, "price_change": 1.88, "last_price": 0.00032261},
    {"pair": "SOLVBNB", "volume": 327.62, "price_change": 14.36, "last_price": 0.0000686},
    {"pair": "SUIBNB", "volume": 316.34, "price_change": 0.27, "last_price": 0.006043},
    {"pair": "BBBNB", "volume": 269.90, "price_change": 8.8, "last_price": 0.000275},
    {"pair": "BNBUSDT", "volume": 12500.45, "price_change": 2.3, "last_price": 305.42},
    {"pair": "BNBBUSD", "volume": 8750.32, "price_change": 2.1, "last_price": 304.98},
    {"pair": "BNBBTC", "volume": 3250.78, "price_change": 1.5, "last_price": 0.00425},
    {"pair": "BNBETH", "volume": 2150.65, "price_change": 0.8, "last_price": 0.0625}
]

# Additional pairs that will be randomly added to simulate new trending pairs
ADDITIONAL_PAIRS = [
    {"pair": "DOGEBNB", "volume": 0, "price_change": 0, "last_price": 0.00012},
    {"pair": "ADABNB", "volume": 0, "price_change": 0, "last_price": 0.00095},
    {"pair": "MATICBNB", "volume": 0, "price_change": 0, "last_price": 0.00032},
    {"pair": "DOTBNB", "volume": 0, "price_change": 0, "last_price": 0.0042},
    {"pair": "LINKBNB", "volume": 0, "price_change": 0, "last_price": 0.0055},
    {"pair": "AVAXBNB", "volume": 0, "price_change": 0, "last_price": 0.0078},
    {"pair": "SHIBBNB", "volume": 0, "price_change": 0, "last_price": 0.0000000085},
    {"pair": "UNIBNB", "volume": 0, "price_change": 0, "last_price": 0.0032},
    {"pair": "ATOMBNB", "volume": 0, "price_change": 0, "last_price": 0.0041},
    {"pair": "LTCBNB", "volume": 0, "price_change": 0, "last_price": 0.0325}
]

class BinanceAPI:
    def __init__(self, config):
        self.config = config
        self.api_key = config["api_key"]
        self.api_secret = config["api_secret"]
        self.base_url = BINANCE_TEST_API_URL if config["use_testnet"] else BINANCE_API_URL

    def _generate_signature(self, data):
        """Generate HMAC SHA256 signature for Binance API"""
        query_string = urllib.parse.urlencode(data)
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature

    def _get_headers(self):
        """Get headers for Binance API requests"""
        return {
            'X-MBX-APIKEY': self.api_key
        }

    def get_exchange_info(self):
        """Get exchange information"""
        try:
            url = f"{self.base_url}/api/v3/exchangeInfo"
            response = requests.get(url)
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Failed to get exchange info: {response.text}")
                return None
        except Exception as e:
            logger.error(f"Error getting exchange info: {e}")
            return None

    def get_account_info(self):
        """Get account information"""
        try:
            url = f"{self.base_url}/api/v3/account"
            timestamp = int(time.time() * 1000)
            params = {
                'timestamp': timestamp
            }
            params['signature'] = self._generate_signature(params)

            headers = self._get_headers()

            response = requests.get(url, params=params, headers=headers)

            if response.status_code != 200:
                logger.error(f"API error response: {response.text}")

            if response.status_code == 200:
                return response.json()
            elif response.status_code == 401:
                logger.error("Authentication failed: Invalid API key or secret")
                return None
            elif response.status_code == 403:
                logger.error("Forbidden: This API key doesn't have permission to access this resource")
                return None
            else:
                logger.error(f"Failed to get account info: {response.text}")
                return None
        except Exception as e:
            logger.error(f"Error getting account info: {e}")
            return None

    def get_ticker_price(self, symbol):
        """Get current price for a symbol"""
        try:
            url = f"{self.base_url}/api/v3/ticker/price"
            params = {'symbol': symbol}

            response = requests.get(url, params=params)
            if response.status_code == 200:
                return float(response.json()['price'])
            else:
                logger.error(f"Failed to get ticker price: {response.text}")
                return None
        except Exception as e:
            logger.error(f"Error getting ticker price: {e}")
            return None

    def get_ticker_24hr(self, symbol=None):
        """Get 24hr ticker data for a symbol or all symbols"""
        try:
            url = f"{self.base_url}/api/v3/ticker/24hr"
            params = {}
            if symbol:
                params['symbol'] = symbol

            response = requests.get(url, params=params)
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Failed to get 24hr ticker: {response.text}")
                return None
        except Exception as e:
            logger.error(f"Error getting 24hr ticker: {e}")
            return None

    def create_order(self, symbol, side, order_type, quantity=None, price=None, time_in_force=None):
        """Create a new order"""
        try:
            url = f"{self.base_url}/api/v3/order"
            timestamp = int(time.time() * 1000)

            params = {
                'symbol': symbol,
                'side': side,  # BUY or SELL
                'type': order_type,  # LIMIT, MARKET, STOP_LOSS, etc.
                'timestamp': timestamp
            }

            if quantity:
                params['quantity'] = quantity

            if price and order_type != 'MARKET':
                params['price'] = price

            if time_in_force and order_type != 'MARKET':
                params['timeInForce'] = time_in_force  # GTC, IOC, FOK

            params['signature'] = self._generate_signature(params)

            response = requests.post(url, params=params, headers=self._get_headers())
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Failed to create order: {response.text}")
                return None
        except Exception as e:
            logger.error(f"Error creating order: {e}")
            return None

    def get_open_orders(self, symbol=None):
        """Get all open orders for a symbol or all symbols"""
        try:
            url = f"{self.base_url}/api/v3/openOrders"
            timestamp = int(time.time() * 1000)

            params = {
                'timestamp': timestamp
            }

            if symbol:
                params['symbol'] = symbol

            params['signature'] = self._generate_signature(params)

            response = requests.get(url, params=params, headers=self._get_headers())
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Failed to get open orders: {response.text}")
                return None
        except Exception as e:
            logger.error(f"Error getting open orders: {e}")
            return None

    def cancel_order(self, symbol, order_id):
        """Cancel an order"""
        try:
            url = f"{self.base_url}/api/v3/order"
            timestamp = int(time.time() * 1000)

            params = {
                'symbol': symbol,
                'orderId': order_id,
                'timestamp': timestamp
            }

            params['signature'] = self._generate_signature(params)

            response = requests.delete(url, params=params, headers=self._get_headers())
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Failed to cancel order: {response.text}")
                return None
        except Exception as e:
            logger.error(f"Error canceling order: {e}")
            return None

    def get_order(self, symbol, order_id):
        """Get order status"""
        try:
            url = f"{self.base_url}/api/v3/order"
            timestamp = int(time.time() * 1000)

            params = {
                'symbol': symbol,
                'orderId': order_id,
                'timestamp': timestamp
            }

            params['signature'] = self._generate_signature(params)

            response = requests.get(url, params=params, headers=self._get_headers())
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Failed to get order: {response.text}")
                return None
        except Exception as e:
            logger.error(f"Error getting order: {e}")
            return None

    def get_all_orders(self, symbol, limit=500):
        """Get all orders for a symbol"""
        try:
            url = f"{self.base_url}/api/v3/allOrders"
            timestamp = int(time.time() * 1000)

            params = {
                'symbol': symbol,
                'limit': limit,
                'timestamp': timestamp
            }

            params['signature'] = self._generate_signature(params)

            response = requests.get(url, params=params, headers=self._get_headers())
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Failed to get all orders: {response.text}")
                return None
        except Exception as e:
            logger.error(f"Error getting all orders: {e}")
            return None

    def get_bnb_pairs(self):
        """Get all BNB trading pairs"""
        try:
            exchange_info = self.get_exchange_info()
            if not exchange_info:
                return []

            bnb_pairs = []
            for symbol in exchange_info['symbols']:
                if 'BNB' in symbol['symbol'] and symbol['status'] == 'TRADING':
                    bnb_pairs.append(symbol['symbol'])

            return bnb_pairs
        except Exception as e:
            logger.error(f"Error getting BNB pairs: {e}")
            return []

    def get_market_data(self):
        """Get market data for BNB pairs"""
        try:
            # Get all BNB pairs
            bnb_pairs = self.get_bnb_pairs()
            if not bnb_pairs:
                return []

            # Get 24hr ticker data for all symbols
            ticker_data = self.get_ticker_24hr()
            if not ticker_data:
                return []

            # Filter for BNB pairs and format the data
            market_data = []
            for ticker in ticker_data:
                if ticker['symbol'] in bnb_pairs:
                    market_data.append({
                        'pair': ticker['symbol'],
                        'volume': float(ticker['volume']),
                        'price_change': float(ticker['priceChangePercent']),
                        'last_price': float(ticker['lastPrice'])
                    })

            return market_data
        except Exception as e:
            logger.error(f"Error getting market data: {e}")
            return []

class MarketAnalyzer:
    def __init__(self, config):
        self.config = config
        self.market_data = INITIAL_MARKET_DATA.copy() if config["mock_mode"] else []
        self.last_update = 0
        self.update_interval = config["market_update_interval"]  # Update market data every X seconds
        self.update_thread = None
        self.running = False
        self.lock = threading.Lock()  # Add a lock for thread safety
        self.binance_api = BinanceAPI(config) if config["api_key"] and config["api_secret"] else None

    def start_updating(self):
        """Start the market data update thread"""
        if not self.running:
            self.running = True
            self.update_thread = threading.Thread(target=self.update_loop)
            self.update_thread.daemon = True
            self.update_thread.start()
            return True
        return False

    def stop_updating(self):
        """Stop the market data update thread"""
        if self.running:
            self.running = False
            if self.update_thread:
                self.update_thread.join(timeout=1.0)
            return True
        return False

    def update_loop(self):
        """Continuously update market data in a separate thread"""
        while self.running:
            try:
                self.update_market_data()
                time.sleep(self.update_interval)
            except Exception as e:
                logger.error(f"Error in market update loop: {e}")
                time.sleep(10)  # Sleep longer on error

    def update_market_data(self):
        """Update market data from exchange"""
        with self.lock:  # Use lock to prevent concurrent access
            current_time = time.time()
            self.last_update = current_time

            # If we have Binance API credentials and real trading is enabled, get real data
            if self.binance_api and not self.config["mock_mode"]:
                real_market_data = self.binance_api.get_market_data()
                if real_market_data:
                    self.market_data = real_market_data
                    logger.info(f"Updated market data with {len(real_market_data)} pairs from Binance API")
                    return

            # If we're in mock mode or failed to get real data, update mock data
            if self.config["mock_mode"]:
                # 1. Update existing pairs with random variations
                for pair_data in self.market_data:
                    # Add some random variation to volume and price change
                    volume_change = random.uniform(-5, 15) / 100  # -5% to +15%
                    price_change_delta = random.uniform(-2, 3)  # -2% to +3%
                    price_change = random.uniform(-1, 2) / 100  # -1% to +2%

                    pair_data["volume"] *= (1 + volume_change)
                    pair_data["price_change"] += price_change_delta
                    pair_data["last_price"] *= (1 + price_change)

                # 2. Occasionally add a new trending pair or remove a low-volume pair
                if random.random() < 0.2:  # 20% chance each update
                    if len(ADDITIONAL_PAIRS) > 0 and len(self.market_data) < 20:
                        # Add a new pair with high volume and price change
                        new_pair = random.choice(ADDITIONAL_PAIRS)
                        # Make it look like it's trending
                        new_pair_copy = new_pair.copy()
                        new_pair_copy["volume"] = random.uniform(500, 2000)
                        new_pair_copy["price_change"] = random.uniform(5, 20) * (1 if random.random() > 0.3 else -1)
                        new_pair_copy["last_price"] *= (1 + random.uniform(0.05, 0.2))

                        # Check if this pair is already in market_data
                        if not any(p["pair"] == new_pair_copy["pair"] for p in self.market_data):
                            self.market_data.append(new_pair_copy)
                            logger.info(f"Added new trending pair: {new_pair_copy['pair']}")

                    # Occasionally remove a low-volume pair
                    if len(self.market_data) > 10 and random.random() < 0.3:
                        # Sort by volume and remove one of the lowest volume pairs
                        sorted_pairs = sorted(self.market_data, key=lambda x: x["volume"])
                        removed_pair = sorted_pairs[0]
                        self.market_data.remove(removed_pair)
                        logger.info(f"Removed low-volume pair: {removed_pair['pair']}")

    def get_best_trading_pairs(self, min_volume=None, min_price_change=None, limit=5):
        """Get the best trading pairs based on volume and price change"""
        with self.lock:  # Use lock to prevent concurrent access
            if min_volume is None:
                min_volume = self.config["min_volume"]

            if min_price_change is None:
                min_price_change = self.config["min_price_change"]

            # Filter pairs that meet minimum criteria
            filtered_pairs = [
                pair for pair in self.market_data
                if pair["volume"] >= min_volume and abs(pair["price_change"]) >= min_price_change
            ]

            # Sort by a combined score of volume and absolute price change
            # This prioritizes pairs with both high volume and significant price movement
            scored_pairs = []
            for pair in filtered_pairs:
                # Normalize volume and price change to give them equal weight
                volume_score = pair["volume"] / 1000  # Normalize volume
                price_change_score = abs(pair["price_change"]) * 2  # Give more weight to price change

                # Combined score
                score = volume_score + price_change_score

                scored_pairs.append((pair, score))

            # Sort by score in descending order
            scored_pairs.sort(key=lambda x: x[1], reverse=True)

            # Return the top pairs
            return [pair for pair, _ in scored_pairs[:limit]]

    def get_trending_pairs(self, limit=5):
        """Get trending pairs based on price change"""
        with self.lock:  # Use lock to prevent concurrent access
            # Sort by price change (absolute value) in descending order
            trending_pairs = sorted(
                self.market_data,
                key=lambda x: abs(x["price_change"]),
                reverse=True
            )

            return trending_pairs[:limit]

    def get_high_volume_pairs(self, limit=5):
        """Get pairs with highest volume"""
        with self.lock:  # Use lock to prevent concurrent access
            # Sort by volume in descending order
            high_volume_pairs = sorted(
                self.market_data,
                key=lambda x: x["volume"],
                reverse=True
            )

            return high_volume_pairs[:limit]

    def get_pair_data(self, pair_name):
        """Get data for a specific pair"""
        with self.lock:  # Use lock to prevent concurrent access
            # If we have Binance API and not in mock mode, get real-time price
            if self.binance_api and not self.config["mock_mode"]:
                current_price = self.binance_api.get_ticker_price(pair_name)
                if current_price:
                    # Find the pair in our cached data to get other info
                    for pair in self.market_data:
                        if pair["pair"].lower() == pair_name.lower():
                            # Update the price with real-time data
                            updated_pair = pair.copy()
                            updated_pair["last_price"] = current_price
                            return updated_pair

            # Find the pair in market data (mock or cached)
            for pair in self.market_data:
                if pair["pair"].lower() == pair_name.lower():
                    return pair.copy()  # Return a copy to prevent modification

            return None

class WhaleDetector:
    def __init__(self, config, trading_bot=None):
        self.config = config
        self.trading_bot = trading_bot
        self.running = False
        self.detection_thread = None
        self.last_notification_time = 0
        self.binance_api = BinanceAPI(config) if config["api_key"] and config["api_secret"] else None

    def start_detection(self):
        """Start the whale detection loop in a separate thread"""
        if not self.running:
            self.running = True
            self.detection_thread = threading.Thread(target=self.detection_loop)
            self.detection_thread.daemon = True
            self.detection_thread.start()
            return True
        return False

    def stop_detection(self):
        """Stop the whale detection loop"""
        if self.running:
            self.running = False
            if self.detection_thread:
                self.detection_thread.join(timeout=1.0)
            return True
        return False

    def detection_loop(self):
        """Main whale detection loop"""
        while self.running:
            try:
                # In a real implementation, this would connect to Binance API or blockchain
                # to monitor large transactions. Here we'll simulate it.

                # Simulate whale detection (random chance of detecting a whale)
                if random.random() < 0.1 and self.config["whale_detection"]:  # 10% chance each cycle
                    whale_transaction = self.generate_mock_whale_transaction()

                    if self.config["mock_mode"]:
                        MOCK_WHALE_TRANSACTIONS.append(whale_transaction)

                    # Only notify if it's been at least 30 seconds since last notification
                    current_time = time.time()
                    if current_time - self.last_notification_time > 30:
                        self.last_notification_time = current_time

                        # Send whale alert notification
                        whale_message = (
                            f"🐋 WHALE ALERT 🐋\n\n"
                            f"Token: {whale_transaction['token']}\n"
                            f"Amount: {whale_transaction['amount']:.2f} {whale_transaction['token'].replace('USDT', '').replace('BUSD', '')}\n"
                            f"Value: ${whale_transaction['value']:,.2f}\n"
                            f"Type: {whale_transaction['type']}\n"
                            f"Time: {whale_transaction['time']}\n\n"
                            f"Potential Impact: {whale_transaction['impact']}"
                        )

                        # Create action buttons based on the whale transaction
                        keyboard = [
                            [InlineKeyboardButton("Follow Whale (Buy/Sell)", callback_data=f"follow_whale_{whale_transaction['id']}")],
                            [InlineKeyboardButton("Ignore Alert", callback_data=f"ignore_whale_{whale_transaction['id']}")]
                        ]

                        # Send the notification directly using the synchronous method
                        self.trading_bot.send_notification(whale_message, keyboard)

                        # Auto-trade based on whale if enabled
                        if self.config["auto_trade_on_whale"]:
                            self.process_whale_for_trading(whale_transaction)

                time.sleep(5)  # Check every 5 seconds

            except Exception as e:
                logger.error(f"Error in whale detection loop: {e}")
                time.sleep(10)  # Sleep longer on error

    def generate_mock_whale_transaction(self):
        """Generate a mock whale transaction for demonstration"""
        # Get market data from the trading bot's market analyzer
        if self.trading_bot and self.trading_bot.market_analyzer:
            market_data = self.trading_bot.market_analyzer.market_data
            # Get a random pair from market data
            pair_data = random.choice(market_data)
            token = pair_data["pair"]

            # Determine if it's a buy or sell
            transaction_type = random.choice(["BUY", "SELL"])

            # Generate a random large amount
            base_amount = self.config["whale_threshold"]
            multiplier = random.uniform(1.0, 10.0)
            amount = base_amount * multiplier

            # Calculate approximate value in USD
            if "BNB" in token:
                price = 300 + random.uniform(-20, 20)  # Approximate BNB price
            else:
                price = pair_data["last_price"]

            value = amount * price

            # Determine potential market impact
            if value > 1000000:  # Over $1M
                impact = "HIGH - Likely significant price movement"
            elif value > 500000:  # Over $500K
                impact = "MEDIUM - Possible price impact"
            else:
                impact = "LOW - Limited price impact expected"

            return {
                'id': int(time.time()),
                'token': token,
                'type': transaction_type,
                'amount': amount,
                'price': price,
                'value': value,
                'time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'impact': impact
            }
        else:
            # Fallback if market analyzer is not available
            return {
                'id': int(time.time()),
                'token': "BNBUSDT",
                'type': random.choice(["BUY", "SELL"]),
                'amount': self.config["whale_threshold"] * random.uniform(1.0, 10.0),
                'price': 300 + random.uniform(-20, 20),
                'value': 30000 * random.uniform(10, 100),
                'time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'impact': "MEDIUM - Possible price impact"
            }

    def process_whale_for_trading(self, whale_transaction):
        """Process a whale transaction for potential trading"""
        # Only process if trading is enabled and it's a BNB pair
        if not self.config["trading_enabled"] or "BNB" not in whale_transaction['token']:
            return

        strategy = self.config["trading_strategy"]

        if strategy == "follow_whale":
            # Follow the whale (buy when whale buys, sell when whale sells)
            trade_type = whale_transaction['type']
        elif strategy == "counter_whale":
            # Counter the whale (sell when whale buys, buy when whale sells)
            trade_type = "SELL" if whale_transaction['type'] == "BUY" else "BUY"
        else:
            # Default to following
            trade_type = whale_transaction['type']

        # Create a trade based on the whale transaction
        self.trading_bot.create_trade_from_whale(whale_transaction, trade_type, is_auto_trade=True)

class TradingBot:
    def __init__(self, config, telegram_bot=None):
        self.config = config
        self.telegram_bot = telegram_bot
        self.running = False
        self.trading_thread = None
        self.whale_detector = None
        self.market_analyzer = MarketAnalyzer(config)
        self.trade_monitor_thread = None
        # Use a standard Python queue instead of asyncio.Queue
        self.notification_queue = queue.Queue()
        self.notification_thread = None
        self.binance_api = BinanceAPI(config) if config["api_key"] and config["api_secret"] else None
        
        # Initialize daily stats
        self.reset_daily_stats()

    def reset_daily_stats(self):
        """Reset daily statistics"""
        DAILY_STATS["date"] = datetime.now().strftime("%Y-%m-%d")
        DAILY_STATS["total_trades"] = 0
        DAILY_STATS["winning_trades"] = 0
        DAILY_STATS["losing_trades"] = 0
        DAILY_STATS["total_profit_pct"] = 0.0
        DAILY_STATS["total_profit_bnb"] = 0.0
        
        # Get current balance if available
        if self.binance_api and self.config["use_real_trading"]:
            try:
                account_info = self.binance_api.get_account_info()
                if account_info:
                    for asset in account_info.get('balances', []):
                        if asset['asset'] == 'BNB':
                            balance = float(asset['free']) + float(asset['locked'])
                            DAILY_STATS["starting_balance"] = balance
                            DAILY_STATS["current_balance"] = balance
                            break
            except Exception as e:
                logger.error(f"Error getting balance for daily stats: {e}")
                DAILY_STATS["starting_balance"] = 0.0
                DAILY_STATS["current_balance"] = 0.0
        else:
            DAILY_STATS["starting_balance"] = 0.0
            DAILY_STATS["current_balance"] = 0.0

    def set_whale_detector(self, detector):
        """Set the whale detector instance"""
        self.whale_detector = detector

    # FIXED: Replace the asyncio queue with direct notification sending
    def send_notification(self, message, keyboard=None):
        """Send notification directly to all admin chat IDs"""
        if not self.telegram_bot:
            logger.warning("Cannot send notification: Telegram bot not initialized")
            return
        
        if not hasattr(self.telegram_bot, 'admin_chat_ids') or not self.telegram_bot.admin_chat_ids:
            logger.warning("Cannot send notification: No admin chat IDs available")
            return
        
        # Add to queue for processing by notification thread
        try:
            self.notification_queue.put((message, keyboard))
            logger.info(f"Added notification to queue: {message[:30]}...")
        except Exception as e:
            logger.error(f"Error queueing notification: {e}")

    def process_notification_queue(self):
        """Process the notification queue in a separate thread"""
        logger.info("Starting notification queue processor thread")

        import asyncio

        # Create a new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        while True:
            try:
                # Get the next notification from the queue (blocking)
                message, keyboard = self.notification_queue.get(block=True)

                # Log that we're processing a notification
                logger.info(f"Processing notification: {message[:30]}...")

                # Check if telegram_bot and admin_chat_ids are available
                if not self.telegram_bot or not hasattr(self.telegram_bot, 'admin_chat_ids') or not self.telegram_bot.admin_chat_ids:
                    logger.error("Cannot send notification: Telegram bot not initialized or no admin chat IDs")
                    self.notification_queue.task_done()
                    time.sleep(5)
                    continue

                # Send to all admin chat IDs
                for chat_id in self.telegram_bot.admin_chat_ids:
                    try:
                        # First try with asyncio.run_coroutine_threadsafe
                        try:
                            if keyboard:
                                future = asyncio.run_coroutine_threadsafe(
                                    self.telegram_bot.application.bot.send_message(
                                        chat_id=chat_id,
                                        text=message,
                                        reply_markup=InlineKeyboardMarkup(keyboard)
                                    ),
                                    loop
                                )
                                # Wait for the result (with timeout)
                                future.result(timeout=10)
                            else:
                                future = asyncio.run_coroutine_threadsafe(
                                    self.telegram_bot.application.bot.send_message(
                                        chat_id=chat_id,
                                        text=message
                                    ),
                                    loop
                                )
                                # Wait for the result (with timeout)
                                future.result(timeout=10)
                            logger.info(f"Sent notification to {chat_id}")
                        except Exception as e1:
                            logger.error(f"Failed to send notification using asyncio: {e1}")

                            # Fallback: Try using requests directly
                            try:
                                logger.info("Trying fallback method to send notification...")
                                # Get the token - try different possible attribute names
                                token = None
                                if hasattr(self.telegram_bot, 'token'):
                                    token = self.telegram_bot.token
                                elif hasattr(self.telegram_bot, 'telegram_token'):
                                    token = self.telegram_bot.telegram_token
                                elif hasattr(self.telegram_bot.application, 'token'):
                                    token = self.telegram_bot.application.token

                                if not token:
                                    logger.error("Could not find Telegram token")
                                    raise Exception("Telegram token not found")

                                url = f"https://api.telegram.org/bot{token}/sendMessage"

                                payload = {
                                    'chat_id': chat_id,
                                    'text': message,
                                    'parse_mode': 'HTML'
                                }

                                if keyboard:
                                    # Convert keyboard to JSON format for API
                                    keyboard_json = []
                                    for row in keyboard:
                                        keyboard_row = []
                                        for button in row:
                                            keyboard_row.append({
                                                'text': button.text,
                                                'callback_data': button.callback_data
                                            })
                                        keyboard_json.append(keyboard_row)

                                    payload['reply_markup'] = json.dumps({
                                        'inline_keyboard': keyboard_json
                                    })

                                response = requests.post(url, json=payload)
                                if response.status_code == 200:
                                    logger.info(f"Sent notification to {chat_id} using fallback method")
                                else:
                                    logger.error(f"Fallback method failed with status code {response.status_code}: {response.text}")
                                    raise Exception(f"HTTP error: {response.status_code}")
                            except Exception as e2:
                                logger.error(f"Fallback method also failed: {e2}")
                                raise e2
                    except Exception as e:
                        logger.error(f"Failed to send notification to {chat_id}: {e}")

                # Mark task as done
                self.notification_queue.task_done()

                # Small delay to prevent flooding
                time.sleep(0.5)

            except Exception as e:
                logger.error(f"Error processing notification queue: {e}")
                time.sleep(5)  # Sleep on error

    def start_trading(self):
        """Start the trading loop in a separate thread"""
        if not self.running:
            self.running = True

            # Apply trading mode settings
            self.apply_trading_mode_settings()

            # Start the market analyzer
            self.market_analyzer.start_updating()

            # Start the trading thread
            self.trading_thread = threading.Thread(target=self.trading_loop)
            self.trading_thread.daemon = True
            self.trading_thread.start()

            # Start the trade monitor thread
            self.trade_monitor_thread = threading.Thread(target=self.monitor_trades_loop)
            self.trade_monitor_thread.daemon = True
            self.trade_monitor_thread.start()
            
            # Start the notification processor thread
            self.notification_thread = threading.Thread(target=self.process_notification_queue)
            self.notification_thread.daemon = True
            self.notification_thread.start()

            # Also start whale detection if enabled
            if self.config["whale_detection"] and self.whale_detector:
                self.whale_detector.start_detection()

            # Reset daily stats when starting trading
            self.reset_daily_stats()

            return True
        return False

    def stop_trading(self):
        """Stop the trading loop"""
        if self.running:
            self.running = False

            # Stop the market analyzer
            self.market_analyzer.stop_updating()

            if self.trading_thread:
                self.trading_thread.join(timeout=1.0)

            if self.trade_monitor_thread:
                self.trade_monitor_thread.join(timeout=1.0)

            # Also stop whale detection
            if self.whale_detector:
                self.whale_detector.stop_detection()

            return True
        return False

    def apply_trading_mode_settings(self):
        """Apply settings from the selected trading mode"""
        mode = self.config["trading_mode"]
        if mode in TRADING_MODES:
            mode_settings = TRADING_MODES[mode]

            # Apply settings from the mode
            self.config["take_profit"] = mode_settings["take_profit"]
            self.config["stop_loss"] = mode_settings["stop_loss"]
            self.config["max_trade_time"] = mode_settings["max_trade_time"]
            self.config["min_volume"] = mode_settings["volume_threshold"]
            self.config["min_price_change"] = mode_settings["price_change_threshold"]
            self.config["max_concurrent_trades"] = mode_settings["max_trades"]

            logger.info(f"Applied {mode} trading mode settings")

    def _format_auto_trade_notification(self, trade, selection_detail_text):
        """Helper function to format the 'NEW AUTO-SELECTED TRADE' notification."""
        bnb_amount = trade.get('bnb_amount', 0)

        return (
            f"🚀 NEW AUTO-SELECTED TRADE\n\n"
            f"Pair: {trade['pair']}\n"
            f"Type: {trade['type']}\n"
            f"Entry Price: ${trade['entry_price']:.6f}\n"
            f"Amount: {trade['amount']} {trade['base_asset']}\n"
            f"BNB Value: {bnb_amount:.4f} BNB\n"
            f"Take Profit: ${trade['take_profit']:.6f}\n"
            f"Stop Loss: ${trade['stop_loss']:.6f}\n"
            f"Max Time: {trade['max_time_seconds']} seconds\n"
            f"Time: {trade['entry_time']}\n"
            f"Mode: {self.config['trading_mode'].capitalize()}\n"
            f"Selection: Auto ({selection_detail_text})"
        )

    def check_daily_limits(self):
        """Check if daily profit target or loss limit has been reached"""
        # If we have real trading enabled and have starting balance
        if DAILY_STATS["starting_balance"] > 0:
            current_profit_pct = (DAILY_STATS["current_balance"] - DAILY_STATS["starting_balance"]) / DAILY_STATS["starting_balance"] * 100
            
            # Check if we've hit the daily profit target
            if current_profit_pct >= self.config["daily_profit_target"]:
                logger.info(f"Daily profit target reached: {current_profit_pct:.2f}% >= {self.config['daily_profit_target']}%")
                self.send_notification(
                    f"?? DAILY PROFIT TARGET REACHED!\n\n"
                    f"Current profit: {current_profit_pct:.2f}%\n"
                    f"Target: {self.config['daily_profit_target']}%\n\n"
                    f"Trading will be paused for today. Use /starttrade to resume."
                )
                return False
            
            # Check if we've hit the daily loss limit
            if current_profit_pct <= -self.config["daily_loss_limit"]:
                logger.info(f"Daily loss limit reached: {current_profit_pct:.2f}% <= -{self.config['daily_loss_limit']}%")
                self.send_notification(
                    f"⚠️ DAILY LOSS LIMIT REACHED!\n\n"
                    f"Current loss: {current_profit_pct:.2f}%\n"
                    f"Limit: -{self.config['daily_loss_limit']}%\n\n"
                    f"Trading will be paused for today. Use /starttrade to resume."
                )
                return False
        
        return True

    def trading_loop(self):
        """Main trading loop - this is where the trading logic would go"""
        while self.running:
            try:
                # Check daily limits
                if not self.check_daily_limits():
                    self.stop_trading()
                    break

                # Check if we can open more trades
                active_trades = [t for t in ACTIVE_TRADES if not t.get('completed', False)]
                if len(active_trades) >= self.config["max_concurrent_trades"]:
                    time.sleep(2)  # Wait before checking again
                    continue

                # If auto-select pairs is enabled, find the best pair to trade
                if self.config["auto_select_pairs"]:
                    best_pairs = self.market_analyzer.get_best_trading_pairs(
                        min_volume=self.config["min_volume"],
                        min_price_change=self.config["min_price_change"],
                        limit=3
                    )

                    if best_pairs:
                        # Choose one of the top pairs randomly
                        selected_pair_data = random.choice(best_pairs)
                        pair_name = selected_pair_data["pair"]

                        # Determine if we should buy or sell based on price change direction
                        if selected_pair_data["price_change"] > 0:
                            # Price is going up, so buy
                            trade_type = "BUY"
                        else:
                            # Price is going down, so sell
                            trade_type = "SELL"

                        # Create a trade for this pair
                        if random.random() < 0.3 and self.config["trading_enabled"]:  # 30% chance to create a trade
                            trade = self.create_trade(pair_name, trade_type, selected_pair_data["last_price"])

                            # Use helper for notification
                            selection_details = f"Volume: {selected_pair_data['volume']:.2f}, Change: {selected_pair_data['price_change']:.2f}%"
                            entry_message = self._format_auto_trade_notification(trade, selection_details)

                            # Send the notification
                            self.send_notification(entry_message)

                time.sleep(5)  # Sleep to prevent high CPU usage

            except Exception as e:
                logger.error(f"Error in trading loop: {e}")
                time.sleep(10)  # Sleep longer on error

    def monitor_trades_loop(self):
        """Monitor active trades for completion"""
        while self.running:
            try:
                # Check all active trades
                for trade in list(ACTIVE_TRADES):
                    if not trade.get('completed', False):
                        current_time = time.time()
                        trade_duration = current_time - trade['timestamp']

                        # Check if max time has been reached
                        if trade_duration >= trade['max_time_seconds']:
                            # Force close the trade due to time limit
                            self.complete_trade(trade, reason="time_limit")
                        else:
                            # Get current price
                            current_price = None

                            # If we have Binance API and real trading is enabled, get real price
                            if self.binance_api and self.config["use_real_trading"]:
                                current_price = self.binance_api.get_ticker_price(trade['pair'])

                            # If we couldn't get real price or not using real trading, simulate price
                            if current_price is None:
                                current_price = self.simulate_price_movement(trade)

                            # Check if take profit or stop loss has been hit
                            if trade['type'] == "BUY":
                                if current_price >= trade['take_profit']:
                                    self.complete_trade(trade, current_price, reason="take_profit")
                                elif current_price <= trade['stop_loss']:
                                    self.complete_trade(trade, current_price, reason="stop_loss")
                            else:  # SELL
                                if current_price <= trade['take_profit']:
                                    self.complete_trade(trade, current_price, reason="take_profit")
                                elif current_price >= trade['stop_loss']:
                                    self.complete_trade(trade, current_price, reason="stop_loss")

                time.sleep(1)  # Check frequently

            except Exception as e:
                logger.error(f"Error in trade monitor loop: {e}")
                time.sleep(5)  # Sleep on error

    def simulate_price_movement(self, trade):
        """Simulate price movement for a trade"""
        # Get the elapsed time as a percentage of max time
        elapsed_time = time.time() - trade['timestamp']
        time_factor = min(elapsed_time / trade['max_time_seconds'], 1.0)

        # Generate a price movement based on time and randomness
        # More time passed = more potential movement
        max_movement_pct = 3.0 * time_factor  # Up to 3% movement at max time
        movement_pct = random.uniform(-max_movement_pct, max_movement_pct)

        # Apply movement to entry price
        current_price = trade['entry_price'] * (1 + movement_pct / 100)

        return current_price

    def create_trade(self, pair, trade_type, current_price=None):
        """Create a trade for a specific pair"""
        # Extract base and quote assets from pair
        if "BNB" in pair:
            if pair.startswith("BNB"):
                base_asset = "BNB"
                quote_asset = pair.replace("BNB", "")
            else:
                base_asset = pair.replace("BNB", "")
                quote_asset = "BNB"
        else:
            # Default
            base_asset = pair[:3]
            quote_asset = pair[3:]

        # If current price not provided, get it from market data
        if current_price is None:
            pair_data = self.market_analyzer.get_pair_data(pair)
            if pair_data:
                current_price = pair_data["last_price"]
            else:
                # Fallback price
                current_price = 0.001 if "BNB" in pair else 300

        # Determine trade amount based on BNB
        min_bnb_amount = 0.01  # Minimum BNB amount for trading

        if self.config['use_percentage'] and self.binance_api and self.config['use_real_trading']:
            try:
                account_info = self.binance_api.get_account_info()
                if account_info:
                    # Find the BNB balance
                    for asset_balance in account_info.get('balances', []):
                        if asset_balance['asset'] == 'BNB':
                            free_balance = float(asset_balance['free'])
                            # Calculate amount as percentage of available balance
                            percentage_amount = free_balance * (self.config['trade_percentage'] / 100.0)
                            # Use percentage amount if it's valid and above minimum
                            if percentage_amount >= min_bnb_amount:
                                bnb_amount = percentage_amount
                            else:
                                bnb_amount = min_bnb_amount
                            break
                    else:
                        bnb_amount = min_bnb_amount
            except Exception as e:
                logger.error(f"Error calculating percentage-based trade amount: {e}")
                bnb_amount = min_bnb_amount
        else:
            # Use fixed amount from config, but ensure it's at least the minimum
            bnb_amount = max(self.config['amount'], min_bnb_amount)

        # Convert BNB amount to target coin amount based on pair type
        if quote_asset == 'BNB':
            # For pairs like SOLBNB, ALTBNB, etc.
            # Amount of target coin = BNB amount / price
            trade_amount = bnb_amount / current_price
        else:
            # For pairs like BNBUSDT, BNBBTC, etc.
            # Amount is directly in BNB
            trade_amount = bnb_amount

        # Calculate take profit and stop loss prices
        take_profit_pct = self.config["take_profit"]
        stop_loss_pct = self.config["stop_loss"]

        if trade_type == "BUY":
            take_profit = current_price * (1 + take_profit_pct / 100)
            stop_loss = current_price * (1 - stop_loss_pct / 100)
        else:  # SELL
            take_profit = current_price * (1 - take_profit_pct / 100)
            stop_loss = current_price * (1 + stop_loss_pct / 100)

        # Create the trade object
        trade = {
            'id': int(time.time()),
            'timestamp': time.time(),
            'pair': pair,
            'base_asset': base_asset,
            'quote_asset': quote_asset,
            'type': trade_type,
            'entry_price': current_price,
            'amount': trade_amount,
            'bnb_amount': bnb_amount,  # Store the BNB amount for reference
            'take_profit': take_profit,
            'stop_loss': stop_loss,
            'max_time_seconds': self.config['max_trade_time'],
            'entry_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'completed': False,
            'mode': self.config['trading_mode'],
            'order_id': None,
            'real_trade': self.config['use_real_trading'],
            'strategy': 'Standard Auto-Selected', # Default strategy for trades from create_trade
            'percentage_based': self.config['use_percentage']  # Flag to indicate if amount was percentage-based
        }

        # If using real trading with Binance API, create the actual order
        if self.binance_api and self.config["use_real_trading"]:
            try:
                # Create the order on Binance
                order = self.binance_api.create_order(
                    symbol=pair,
                    side=trade_type,
                    order_type="MARKET",
                    quantity=trade_amount
                )

                if order:
                    trade['order_id'] = order['orderId']
                    trade['real_trade'] = True
                    logger.info(f"Created real trade on Binance: {pair} {trade_type} at {current_price}")
                else:
                    logger.error(f"Failed to create real trade on Binance: {pair} {trade_type}")
            except Exception as e:
                logger.error(f"Error creating real trade: {e}")

        # Add the trade to the active trades list
        ACTIVE_TRADES.append(trade)

        return trade


    def create_trade_from_whale(self, whale_transaction, trade_type, is_auto_trade=False):
        """Create a trade based on a whale transaction"""
        # Extract the trading pair from the whale transaction
        pair = whale_transaction['token']

        # Use the price from the whale transaction
        current_price = whale_transaction['price']

        # Create the trade
        trade = self.create_trade(pair, trade_type, current_price)

        # Add whale-specific information
        trade['whale_id'] = whale_transaction['id']
        # Override strategy to reflect it's whale-based
        trade['strategy'] = f"Whale-Based ({self.config['trading_strategy']})"

        # Different notification formats for auto vs manual follow
        if is_auto_trade:
            # Use helper for auto-trade notification
            selection_details = f"Whale Alert ID: {whale_transaction['id']}"
            entry_message = self._format_auto_trade_notification(trade, selection_details)
        else: # Manual follow (when button is pressed)
            # Specific notification for manual follow
            title_emoji = "🐋 NEW WHALE-BASED TRADE (Manual Follow)"
            trigger_info = f"Trigger: Manual Follow (Whale ID: {whale_transaction['id']})"
            entry_message = (
                f"{title_emoji}\n\n"
                f"Pair: {trade['pair']}\n"
                f"Type: {trade['type']}\n"
                f"Entry Price: ${trade['entry_price']:.6f}\n"
                f"Amount: {trade['amount']} {trade['base_asset']}\n"
                f"Take Profit: ${trade['take_profit']:.6f}\n"
                f"Stop Loss: ${trade['stop_loss']:.6f}\n"
                f"Max Time: {trade['max_time_seconds']} seconds\n"
                f"Time: {trade['entry_time']}\n"
                f"Mode: {self.config['trading_mode'].capitalize()}\n"
                f"Strategy: {trade['strategy']}\n"
                f"{trigger_info}"
            )

        # Send the notification
        self.send_notification(entry_message)

        return trade

    def complete_trade(self, trade, exit_price=None, reason="unknown"):
        """Complete a trade with a result"""
        if exit_price is None:
            # Determine exit price based on reason
            if reason == "take_profit":
                exit_price = trade['take_profit']
            elif reason == "stop_loss":
                exit_price = trade['stop_loss']
            elif reason == "time_limit":
                # For time limit, use current price
                if self.binance_api and self.config["use_real_trading"]:
                    current_price = self.binance_api.get_ticker_price(trade['pair'])
                    if current_price:
                        exit_price = current_price
                    else:
                        exit_price = self.simulate_price_movement(trade)
                else:
                    exit_price = self.simulate_price_movement(trade)
            else:
                # Default to current price
                if self.binance_api and self.config["use_real_trading"]:
                    current_price = self.binance_api.get_ticker_price(trade['pair'])
                    if current_price:
                        exit_price = current_price
                    else:
                        exit_price = self.simulate_price_movement(trade)
                else:
                    exit_price = self.simulate_price_movement(trade)

        # Calculate result percentage
        if trade['type'] == "BUY":
            result_pct = ((exit_price - trade['entry_price']) / trade['entry_price']) * 100
        else:
            result_pct = ((trade['entry_price'] - exit_price) / trade['entry_price']) * 100

        # Update trade with completion details
        trade['completed'] = True
        trade['exit_price'] = exit_price
        trade['exit_time'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        trade['result'] = result_pct
        trade['close_reason'] = reason

        # Calculate profit in BNB
        profit_in_bnb = 0.0
        if trade['quote_asset'] == 'BNB':
            if trade['type'] == "BUY":
                profit_in_bnb = (exit_price - trade['entry_price']) * trade['amount']
            else:
                profit_in_bnb = (trade['entry_price'] - exit_price) * trade['amount']
        elif trade['base_asset'] == 'BNB':
            profit_in_bnb = (result_pct / 100.0) * trade['amount']
        trade['profit_in_bnb'] = profit_in_bnb

        # Update daily stats
        DAILY_STATS["total_trades"] += 1
        DAILY_STATS["total_profit_pct"] += result_pct
        DAILY_STATS["total_profit_bnb"] += profit_in_bnb
        
        if result_pct > 0:
            DAILY_STATS["winning_trades"] += 1
        else:
            DAILY_STATS["losing_trades"] += 1
            
        # Update current balance if we're using real trading
        if self.config["use_real_trading"] and DAILY_STATS["current_balance"] > 0:
            DAILY_STATS["current_balance"] += profit_in_bnb

        # If this was a real trade with an order ID, close the position if needed
        if trade['real_trade'] and trade['order_id'] and self.binance_api:
            try:
                # For market orders, we need to place a new order in the opposite direction
                opposite_side = "SELL" if trade['type'] == "BUY" else "BUY"

                # Create the closing order
                close_order = self.binance_api.create_order(
                    symbol=trade['pair'],
                    side=opposite_side,
                    order_type="MARKET",
                    quantity=trade['amount']
                )

                if close_order:
                    trade['close_order_id'] = close_order['orderId']
                    logger.info(f"Closed real trade on Binance: {trade['pair']} {opposite_side} at {exit_price}")
                else:
                    logger.error(f"Failed to close real trade on Binance: {trade['pair']} {opposite_side}")
            except Exception as e:
                logger.error(f"Error closing real trade: {e}")

        # Determine if win or loss
        is_win = result_pct > 0
        result = "WIN" if is_win else "LOSS"
        emoji = "✅" if is_win else "❌"

        # Get reason text
        if reason == "take_profit":
            reason_text = "Take Profit Hit"
        elif reason == "stop_loss":
            reason_text = "Stop Loss Hit"
        elif reason == "time_limit":
            reason_text = "Time Limit Reached"
        else:
            reason_text = "Manual Close"

        # Send completion notification
        complete_message = (
            f"{emoji} TRADE COMPLETED - {result}\n\n"
            f"Pair: {trade['pair']}\n"
            f"Type: {trade['type']}\n"
            f"Entry Price: ${trade['entry_price']:.6f}\n"
            f"Exit Price: ${exit_price:.6f}\n"
            f"Profit/Loss: {result_pct:.2f}%\n"
            f"Profit BNB: {trade.get('profit_in_bnb', 0.0):.8f} BNB\n"
            f"Amount: {trade['amount']} {trade['base_asset']}\n"
            f"Close Reason: {reason_text}\n"
            f"Entry Time: {trade['entry_time']}\n"
            f"Exit Time: {trade['exit_time']}\n"
            f"Duration: {int(time.time() - trade['timestamp'])} seconds\n"
            f"Mode: {trade.get('mode', 'Standard').capitalize()}\n"
            f"Strategy: {trade.get('strategy', 'N/A')}\n"
            f"Real Trade: {'Yes' if trade.get('real_trade', False) else 'No (Simulation)'}"
        )

        # Send the notification
        self.send_notification(complete_message)

        # Move the trade from active to completed
        if trade in ACTIVE_TRADES:
            ACTIVE_TRADES.remove(trade)
            COMPLETED_TRADES.append(trade)

    def get_daily_stats_message(self):
        """Get a formatted message with daily trading statistics"""
        win_rate = 0
        if DAILY_STATS["total_trades"] > 0:
            win_rate = (DAILY_STATS["winning_trades"] / DAILY_STATS["total_trades"]) * 100
            
        balance_change = 0
        if DAILY_STATS["starting_balance"] > 0:
            balance_change = ((DAILY_STATS["current_balance"] - DAILY_STATS["starting_balance"]) / DAILY_STATS["starting_balance"]) * 100
            
        stats_message = (
            f"📊 DAILY TRADING STATS - {DAILY_STATS['date']}\n\n"
            f"Total Trades: {DAILY_STATS['total_trades']}\n"
            f"Winning Trades: {DAILY_STATS['winning_trades']}\n"
            f"Losing Trades: {DAILY_STATS['losing_trades']}\n"
            f"Win Rate: {win_rate:.1f}%\n\n"
            f"Total Profit/Loss: {DAILY_STATS['total_profit_pct']:.2f}%\n"
            f"Total Profit BNB: {DAILY_STATS['total_profit_bnb']:.8f} BNB\n\n"
            f"Starting Balance: {DAILY_STATS['starting_balance']:.8f} BNB\n"
            f"Current Balance: {DAILY_STATS['current_balance']:.8f} BNB\n"
            f"Balance Change: {balance_change:.2f}%\n\n"
            f"Trading Mode: {self.config['trading_mode'].capitalize()}\n"
            f"Real Trading: {'Enabled' if self.config['use_real_trading'] else 'Disabled (Simulation)'}"
        )
        
        return stats_message

class TelegramBotHandler:
    def __init__(self, token, admin_ids):
        self.token = token
        self.admin_user_ids = admin_ids
        # Initialize admin_chat_ids with admin_user_ids to enable immediate notifications
        self.admin_chat_ids = admin_ids.copy()  # Use a copy of admin_user_ids
        self.trading_bot = None
        self.bot = None
        self.application = Application.builder().token(token).build()

        # Register handlers
        self.register_handlers()
        
        # Log the initialization
        logger.info(f"TelegramBotHandler initialized with admin chat IDs: {self.admin_chat_ids}")

    def register_handlers(self):
        """Register all command handlers"""
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("status", self.status_command))
        self.application.add_handler(CommandHandler("config", self.config_command))
        self.application.add_handler(CommandHandler("set", self.set_config_command))
        self.application.add_handler(CommandHandler("trades", self.trades_command))
        self.application.add_handler(CommandHandler("whales", self.whales_command))
        self.application.add_handler(CommandHandler("stats", self.stats_command))
        self.application.add_handler(CommandHandler("setpercentage", self.set_percentage_command))

        # BNB-specific commands
        self.application.add_handler(CommandHandler("bnbpairs", self.bnb_pairs_command))
        self.application.add_handler(CommandHandler("whaleconfig", self.whale_config_command))
        self.application.add_handler(CommandHandler("volume", self.volume_command))
        self.application.add_handler(CommandHandler("trending", self.trending_command))
        self.application.add_handler(CommandHandler("modes", self.trading_modes_command))

        # Start/stop trading commands
        self.application.add_handler(CommandHandler("starttrade", self.start_trading_command))
        self.application.add_handler(CommandHandler("stoptrade", self.stop_trading_command))

        # Real trading commands
        self.application.add_handler(CommandHandler("enablereal", self.enable_real_trading_command))
        self.application.add_handler(CommandHandler("disablereal", self.disable_real_trading_command))
        self.application.add_handler(CommandHandler("balance", self.balance_command))

        self.application.add_handler(CommandHandler("toggletestnet", self.toggle_testnet_command))

        # Callback query handler for inline buttons
        self.application.add_handler(CallbackQueryHandler(self.button_callback))

        # Message handler for text messages
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))

        # Error handler
        self.application.add_error_handler(self.error_handler)

        self.application.add_handler(CommandHandler("testapi", self.test_api_command))

    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /stats command to show daily trading statistics"""
        if not await self.is_authorized(update):
            return

        if not self.trading_bot:
            await update.message.reply_text("Trading bot not initialized")
            return

        stats_message = self.trading_bot.get_daily_stats_message()
        await update.message.reply_text(stats_message)

    async def set_percentage_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /setpercentage command to enable/disable percentage-based trading"""
        if not await self.is_authorized(update):
            return

        if not self.trading_bot:
            await update.message.reply_text("Trading bot not initialized")
            return

        args = context.args
        if not args:
            current_setting = "enabled" if self.trading_bot.config["use_percentage"] else "disabled"
            current_percentage = self.trading_bot.config["trade_percentage"]
            await update.message.reply_text(
                f"Percentage-based trading is currently {current_setting}.\n"
                f"Current percentage: {current_percentage}%\n\n"
                "To enable: /setpercentage on [percentage]\n"
                "To disable: /setpercentage off\n\n"
                "Example: /setpercentage on 10"
            )
            return

        if args[0].lower() in ["on", "enable", "true", "yes"]:
            self.trading_bot.config["use_percentage"] = True
            
            # If percentage is provided, update it
            if len(args) > 1:
                try:
                    percentage = float(args[1])
                    if 0.1 <= percentage <= 100:
                        self.trading_bot.config["trade_percentage"] = percentage
                    else:
                        await update.message.reply_text("Percentage must be between 0.1 and 100")
                        return
                except ValueError:
                    await update.message.reply_text("Invalid percentage value. Please provide a number.")
                    return
            
            await update.message.reply_text(
                f"✅ Percentage-based trading enabled.\n"
                f"The bot will use {self.trading_bot.config['trade_percentage']}% of your available balance for each trade."
            )
        elif args[0].lower() in ["off", "disable", "false", "no"]:
            self.trading_bot.config["use_percentage"] = False
            await update.message.reply_text(
                f"✅ Percentage-based trading disabled.\n"
                f"The bot will use fixed amount of {self.trading_bot.config['amount']} for each trade."
            )
        else:
            await update.message.reply_text("Invalid option. Use 'on' or 'off'.")

    async def test_api_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /testapi command to test the Binance API connection"""
        if not await self.is_authorized(update):
            return

        if not self.trading_bot:
            await update.message.reply_text("Trading bot not initialized")
            return

        # Check if API credentials are set
        if not self.trading_bot.config["api_key"] or not self.trading_bot.config["api_secret"]:
            await update.message.reply_text(
                "⚠️ API credentials not set.\n\n"
                "Please set your Binance API credentials first:\n"
                "/set api_key YOUR_API_KEY\n"
                "/set api_secret YOUR_API_SECRET"
            )
            return

        # Send initial message
        status_msg = await update.message.reply_text("🔄 Testing Binance API connection... Please wait.")

        # Test the API connection
        if self.trading_bot.binance_api:
            # First try a simple ping to check connectivity
            try:
                ping_url = f"{self.trading_bot.binance_api.base_url}/api/v3/ping"
                ping_response = requests.get(ping_url)
                if ping_response.status_code != 200:
                    await status_msg.edit_text(
                        f"❌ Failed to connect to Binance API. Server returned status code: {ping_response.status_code}\n\n"
                        f"Response: {ping_response.text}\n\n"
                        f"Please check your internet connection and Binance server status."
                    )
                    return

                server_time_url = f"{self.trading_bot.binance_api.base_url}/api/v3/time"
                server_time_response = requests.get(server_time_url)
                if server_time_response.status_code == 200:
                    server_time = datetime.fromtimestamp(server_time_response.json()['serverTime'] / 1000)
                    server_time_str = server_time.strftime("%Y-%m-%d %H:%M:%S")
                else:
                    server_time_str = "Unknown"

                await status_msg.edit_text(
                    f"✅ Successfully connected to Binance API!\n\n"
                    f"Mode: {'Testnet' if self.trading_bot.config['use_testnet'] else 'Production'}\n"
                    f"Base URL: {self.trading_bot.binance_api.base_url}\n"
                    f"Server Time: {server_time_str}\n\n"
                    f"Now testing authentication..."
                )

                account_info = self.trading_bot.binance_api.get_account_info()
                if account_info:
                    balances = []
                    for asset in account_info.get('balances', [])[:5]:  # Show first 5 assets
                        free = float(asset['free'])
                        locked = float(asset['locked'])
                        if free > 0 or locked > 0:
                            balances.append(f"{asset['asset']}: {free} (Free) + {locked} (Locked)")

                    balance_text = "\n".join(balances) if balances else "No assets with non-zero balance found."

                    await status_msg.edit_text(
                        f"✅ API connection test successful!\n\n"
                        f"Mode: {'Testnet' if self.trading_bot.config['use_testnet'] else 'Production'}\n"
                        f"Account Status: {account_info.get('status', 'Unknown')}\n"
                        f"Can Trade: {account_info.get('canTrade', 'Unknown')}\n"
                        f"Can Withdraw: {account_info.get('canWithdraw', 'Unknown')}\n"
                        f"Can Deposit: {account_info.get('canDeposit', 'Unknown')}\n\n"
                        f"Top Balances:\n{balance_text}"
                    )
                else:
                    try:
                        test_url = f"{self.trading_bot.binance_api.base_url}/api/v3/account"
                        timestamp = int(time.time() * 1000)
                        params = {'timestamp': timestamp}
                        signature = self.trading_bot.binance_api._generate_signature(params)
                        params['signature'] = signature
                        headers = {'X-MBX-APIKEY': self.trading_bot.config["api_key"]}

                        test_response = requests.get(test_url, params=params, headers=headers)
                        error_msg = f"Status code: {test_response.status_code}, Response: {test_response.text}"

                        if test_response.status_code == 401:
                            guidance = "Your API key is invalid. Please check that you've entered it correctly."
                        elif test_response.status_code == 403:
                            guidance = "Your API key doesn't have permission to access this resource. Make sure you've enabled 'Enable Reading' and 'Enable Spot & Margin Trading' permissions."
                        elif "signature" in test_response.text.lower():
                            guidance = "API signature verification failed. Make sure your API secret is correct."
                        elif "timestamp" in test_response.text.lower():
                            guidance = "Timestamp error. Please check that your system clock is synchronized."
                        elif "IP" in test_response.text.upper():
                            guidance = "IP restriction error. Make sure your API key doesn't have IP restrictions or add your current IP to the whitelist."
                        else:
                            guidance = "Please check your API credentials and permissions."

                        await status_msg.edit_text(
                            f"❌ API connection test failed at authentication step.\n\n"
                            f"Error: {error_msg}\n\n"
                            f"Guidance: {guidance}\n\n"
                            f"Make sure your API key has the following permissions:\n"
                            f"- Enable Reading\n"
                            f"- Enable Spot & Margin Trading\n\n"
                            f"Also check if you're using {'testnet' if self.trading_bot.config['use_testnet'] else 'production'} API keys."
                        )
                    except Exception as e_auth:
                        await status_msg.edit_text(
                            f"❌ API connection test failed during authentication: {str(e_auth)}\n\n"
                            f"Please check your API credentials and permissions."
                        )
            except Exception as e_conn:
                await status_msg.edit_text(
                    f"❌ API connection test failed: {str(e_conn)}\n\n"
                    f"Please check your internet connection."
                )
        else:
            await status_msg.edit_text(
                "❌ Binance API not initialized. Please check your API credentials."
            )

    async def toggle_testnet_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /toggletestnet command to switch between testnet and production"""
        if not await self.is_authorized(update):
            return

        if not self.trading_bot:
            await update.message.reply_text("Trading bot not initialized")
            return

        self.trading_bot.config["use_testnet"] = not self.trading_bot.config["use_testnet"]

        self.trading_bot.binance_api = BinanceAPI(self.trading_bot.config)
        self.trading_bot.market_analyzer.binance_api = self.trading_bot.binance_api
        if self.trading_bot.whale_detector:
            self.trading_bot.whale_detector.binance_api = self.trading_bot.binance_api

        mode = "Testnet" if self.trading_bot.config["use_testnet"] else "Production"
        await update.message.reply_text(
            f"✅ Switched to {mode} mode.\n\n"
            f"{'⚠️ You are now using the Binance Testnet. API keys for the main Binance site will not work.' if self.trading_bot.config['use_testnet'] else '⚠️ You are now using the Binance Production API. Testnet API keys will not work.'}\n\n"
            f"Please make sure your API keys are for {mode}."
        )

    async def enable_real_trading_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /enablereal command to enable real trading"""
        if not await self.is_authorized(update):
            return

        if not self.trading_bot:
            await update.message.reply_text("Trading bot not initialized")
            return

        if not self.trading_bot.config["api_key"] or not self.trading_bot.config["api_secret"]:
            await update.message.reply_text(
                "⚠️ API credentials not set.\n\n"
                "Please set your Binance API credentials first:\n"
                "/set api_key YOUR_API_KEY\n"
                "/set api_secret YOUR_API_SECRET"
            )
            return

        status_msg = await update.message.reply_text("🔄 Testing Binance API connection before enabling real trading...")

        if self.trading_bot.binance_api:
            try:
                account_info = self.trading_bot.binance_api.get_account_info()
                if account_info:
                    self.trading_bot.config["use_real_trading"] = True
                    bnb_balance = 0
                    for asset in account_info.get('balances', []):
                        if asset['asset'] == 'BNB':
                            bnb_balance = float(asset['free'])
                            break
                    await status_msg.edit_text(
                        f"✅ Real trading has been ENABLED!\n\n"
                        f"Mode: {'Testnet' if self.trading_bot.config['use_testnet'] else 'Production'}\n"
                        f"Account Status: {account_info.get('status', 'Unknown')}\n"
                        f"BNB Balance: {bnb_balance}\n\n"
                        f"⚠️ WARNING: The bot will now execute REAL trades on Binance using your account.\n"
                        f"Please monitor your trades carefully."
                    )
                else:
                    await status_msg.edit_text(
                        f"❌ Failed to connect to Binance API. Please check your API credentials.\n\n"
                        f"Real trading has NOT been enabled."
                    )
            except Exception as e:
                await status_msg.edit_text(
                    f"❌ Error testing API connection: {str(e)}\n\n"
                    f"Real trading has NOT been enabled."
                )
        else:
            await status_msg.edit_text(
                "❌ Binance API not initialized. Please check your API credentials.\n\n"
                "Real trading has NOT been enabled."
            )

    async def disable_real_trading_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /disablereal command to disable real trading"""
        if not await self.is_authorized(update):
            return

        if not self.trading_bot:
            await update.message.reply_text("Trading bot not initialized")
            return

        self.trading_bot.config["use_real_trading"] = False
        await update.message.reply_text(
            "✅ Real trading has been DISABLED.\n\n"
            "The bot will now operate in simulation mode only."
        )

    async def balance_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /balance command to show Binance account balance"""
        if not await self.is_authorized(update):
            return

        if not self.trading_bot:
            await update.message.reply_text("Trading bot not initialized")
            return

        if not self.trading_bot.config["api_key"] or not self.trading_bot.config["api_secret"]:
            await update.message.reply_text(
                "⚠️ API credentials not set.\n\n"
                "Please set your Binance API credentials first:\n"
                "/set api_key YOUR_API_KEY\n"
                "/set api_secret YOUR_API_SECRET"
            )
            return

        status_msg = await update.message.reply_text("🔄 Fetching account balance... Please wait.")

        if self.trading_bot.binance_api:
            try:
                account_info = self.trading_bot.binance_api.get_account_info()
                if account_info:
                    non_zero_balances = []
                    for asset in account_info.get('balances', []):
                        free = float(asset['free'])
                        locked = float(asset['locked'])
                        if free > 0 or locked > 0:
                            non_zero_balances.append({
                                'asset': asset['asset'],
                                'free': free,
                                'locked': locked
                            })
                    sorted_balances = sorted(non_zero_balances, key=lambda x: x['free'] + x['locked'], reverse=True)
                    balance_text = "📊 ACCOUNT BALANCE\n\n"
                    if sorted_balances:
                        for balance in sorted_balances[:10]:  # Show top 10 assets
                            balance_text += f"{balance['asset']}: {balance['free']} (Free) + {balance['locked']} (Locked)\n"
                        if len(sorted_balances) > 10:
                            balance_text += f"\n... and {len(sorted_balances) - 10} more assets"
                    else:
                        balance_text += "No assets with non-zero balance found."
                    balance_text += f"\n\nAccount Status: {account_info.get('status', 'Unknown')}"
                    balance_text += f"\nCan Trade: {account_info.get('canTrade', 'Unknown')}"
                    balance_text += f"\nCan Withdraw: {account_info.get('canWithdraw', 'Unknown')}"
                    balance_text += f"\nCan Deposit: {account_info.get('canDeposit', 'Unknown')}"
                    balance_text += f"\n\nMode: {'Testnet' if self.trading_bot.config['use_testnet'] else 'Production'}"
                    await status_msg.edit_text(balance_text)
                else:
                    await status_msg.edit_text(
                        "❌ Failed to get account balance. Please check your API credentials."
                    )
            except Exception as e:
                await status_msg.edit_text(
                    f"❌ Error getting account balance: {str(e)}\n\n"
                    f"Please check your API credentials and permissions."
                )
        else:
            await status_msg.edit_text(
                "❌ Binance API not initialized. Please check your API credentials."
            )

    async def is_authorized(self, update: Update) -> bool:
        """Check if the user is authorized to use the bot"""
        user_id = update.effective_user.id
        if user_id not in self.admin_user_ids:
            await update.effective_chat.send_message(
                "⛔ You are not authorized to use this bot."
            )
            logger.warning(f"Unauthorized access attempt by user {user_id}")
            return False
        return True

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /start command"""
        if not await self.is_authorized(update):
            return

        chat_id = update.effective_chat.id
        if chat_id not in self.admin_chat_ids:
            self.admin_chat_ids.append(chat_id)
            logger.info(f"Added chat ID {chat_id} to admin chats. Current admin chats: {self.admin_chat_ids}")
        else:
            logger.info(f"Chat ID {chat_id} already in admin chats: {self.admin_chat_ids}")

        keyboard = [
            [InlineKeyboardButton("🔄 Start Trading", callback_data="select_trading_mode")],
            [InlineKeyboardButton("📊 Top Volume", callback_data="volume"),
             InlineKeyboardButton("📈 Trending", callback_data="trending")],
            [InlineKeyboardButton("⚙️ Settings", callback_data="config"),
             InlineKeyboardButton("📋 Status", callback_data="status")]
        ]

        await update.message.reply_text(
            "Welcome to the Enhanced BNB Trading Bot!\n\n"
            "This bot specializes in trading BNB and BNB-related tokens with:\n"
            "• Volume-based pair selection\n"
            "• Fast trading with configurable timeframes\n"
            "• Multiple trading modes\n"
            "• Whale detection\n\n"
            "Use /help to see available commands.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /help command"""
        if not await self.is_authorized(update):
            return

        help_text = (
            "Available commands:\n\n"
            "/start - Start the bot\n"
            "/help - Show this help message\n"
            "/status - Show current bot status\n"
            "/config - Show current configuration\n"
            "/set [param] [value] - Set configuration parameter (e.g., /set amount 0.1)\n"
            "/trades - Show recent trades\n"
            "/whales - Show recent whale transactions\n"
            "/bnbpairs - Show available BNB trading pairs\n"
            "/volume - Show highest volume BNB pairs\n"
            "/trending - Show trending BNB pairs\n"
            "/modes - Show available trading modes\n"
            "/whaleconfig - Configure whale detection settings\n"
            "/starttrade - Start trading (select mode first)\n"
            "/stoptrade - Stop trading\n"
            "/stats - Show daily trading statistics\n"
            "/setpercentage [on/off] [percentage] - Enable/disable percentage-based trading\n\n"
            "Real Trading Commands:\n"
            "/enablereal - Enable real trading with Binance API\n"
            "/disablereal - Disable real trading (simulation only)\n"
            "/balance - Show your Binance account balance\n"
            "/testapi - Test your Binance API connection\n"
            "/toggletestnet - Switch between Binance Testnet and Production\n"
        )
        await update.message.reply_text(help_text)

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /status command"""
        if not await self.is_authorized(update):
            return

        if not self.trading_bot:
            message = "Trading bot not initialized"
            if update.callback_query:
                await update.callback_query.edit_message_text(message)
            else:
                await update.message.reply_text(message)
            return

        active_trades = [t for t in ACTIVE_TRADES if not t.get('completed', False)]
        completed_trades = COMPLETED_TRADES

        total_profit_pct = 0
        win_count = 0
        loss_count = 0
        total_profit_bnb = 0.0

        for trade in completed_trades:
            result = trade.get('result', 0)
            total_profit_pct += result
            if result > 0:
                win_count += 1
            else:
                loss_count += 1
            total_profit_bnb += trade.get('profit_in_bnb', 0.0)

        win_rate = (win_count / len(completed_trades) * 100) if completed_trades else 0
        real_trading_status = "✅ Enabled" if self.trading_bot.config["use_real_trading"] else "❌ Disabled (Simulation)"

        status_text = (
            f"📊 BOT STATUS\n\n"
            f"Trading: {'✅ Running' if self.trading_bot.running else '❌ Stopped'}\n"
            f"Mode: {self.trading_bot.config['trading_mode'].capitalize()}\n"
            f"Take Profit: {self.trading_bot.config['take_profit']}%\n"
            f"Stop Loss: {self.trading_bot.config['stop_loss']}%\n"
            f"Max Trade Time: {self.trading_bot.config['max_trade_time']} seconds\n\n"
            f"Real Trading: {real_trading_status}\n"
            f"Active Trades: {len(active_trades)}/{self.trading_bot.config['max_concurrent_trades']}\n"
            f"Completed Trades: {len(completed_trades)}\n"
            f"Total Profit %: {total_profit_pct:.2f}%\n"
            f"Total Profit BNB: {total_profit_bnb:.8f} BNB\n"
            f"Win Rate: {win_rate:.1f}% ({win_count}/{len(completed_trades)})\n\n"
            f"Whale Detection: {'✅ Enabled' if self.trading_bot.config['whale_detection'] else '❌ Disabled'}\n"
            f"Auto-Select Pairs: {'✅ Enabled' if self.trading_bot.config['auto_select_pairs'] else '❌ Disabled'}\n"
            f"Percentage-Based Trading: {'✅ Enabled (' + str(self.trading_bot.config['trade_percentage']) + '%)' if self.trading_bot.config['use_percentage'] else '❌ Disabled'}\n"
            f"Recent Whale Alerts: {len(MOCK_WHALE_TRANSACTIONS) if self.trading_bot.config['mock_mode'] else 'N/A'}"
        )

        keyboard = [
            [InlineKeyboardButton("🔄 Start Trading", callback_data="select_trading_mode"),
             InlineKeyboardButton("⏹️ Stop Trading", callback_data="stop_trading")],
            [InlineKeyboardButton("📊 Top Volume", callback_data="volume"),
             InlineKeyboardButton("📈 Trending", callback_data="trending")],
            [InlineKeyboardButton("⚙️ Settings", callback_data="config"),
             InlineKeyboardButton(f"{'🔴 Disable' if self.trading_bot.config['use_real_trading'] else '🟢 Enable'} Real Trading",
                                 callback_data="toggle_real_trading")]
        ]

        if update.callback_query:
            await update.callback_query.edit_message_text(
                status_text,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await update.message.reply_text(
                status_text,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

    async def config_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /config command"""
        if not await self.is_authorized(update):
            return

        if not self.trading_bot:
            message = "Trading bot not initialized"
            if update.callback_query:
                await update.callback_query.edit_message_text(message)
            else:
                await update.message.reply_text(message)
            return

        config_display = self.trading_bot.config.copy()
        if 'api_key' in config_display:
            config_display['api_key'] = '****' if config_display['api_key'] else 'Not set'
        if 'api_secret' in config_display:
            config_display['api_secret'] = '****' if config_display['api_secret'] else 'Not set'

        config_text = "⚙️ BOT CONFIGURATION\n\n"
        config_text += "Trading Settings:\n"
        config_text += f"• Mode: {config_display['trading_mode'].capitalize()}\n"
        config_text += f"• Base Trade Amount: {config_display['amount']} (Base Asset Units)\n"
        config_text += f"• Percentage-Based: {'Yes (' + str(config_display['trade_percentage']) + '%)' if config_display['use_percentage'] else 'No'}\n"
        config_text += f"• Take Profit: {config_display['take_profit']}%\n"
        config_text += f"• Stop Loss: {config_display['stop_loss']}%\n"
        config_text += f"• Max Trade Time: {config_display['max_trade_time']} seconds\n"
        config_text += f"• Max Concurrent Trades: {config_display['max_concurrent_trades']}\n\n"
        config_text += "Pair Selection:\n"
        config_text += f"• Auto Select: {'Enabled' if config_display['auto_select_pairs'] else 'Disabled'}\n"
        config_text += f"• Min Volume: {config_display['min_volume']} BNB\n"
        config_text += f"• Min Price Change: {config_display['min_price_change']}%\n\n"
        config_text += "Whale Detection:\n"
        config_text += f"• Enabled: {'Yes' if config_display['whale_detection'] else 'No'}\n"
        config_text += f"• Auto Trade: {'Yes' if config_display['auto_trade_on_whale'] else 'No'}\n"
        config_text += f"• Strategy: {config_display['trading_strategy']}\n"
        config_text += f"• Threshold: {config_display['whale_threshold']} BNB\n\n"
        config_text += "API Settings:\n"
        config_text += f"• API Key: {config_display['api_key']}\n"
        config_text += f"• API Secret: {config_display['api_secret']}\n"
        config_text += f"• Use Testnet: {'Yes' if config_display['use_testnet'] else 'No'}\n"
        config_text += f"• Real Trading: {'Enabled' if config_display['use_real_trading'] else 'Disabled (Simulation)'}\n"

        keyboard = [
            [InlineKeyboardButton("Change Mode", callback_data="select_trading_mode")],
            [InlineKeyboardButton("Toggle Auto-Select", callback_data="toggle_auto_select"),
             InlineKeyboardButton("Toggle Whale Detection", callback_data="toggle_whale_detection")],
            [InlineKeyboardButton("Toggle Percentage-Based", callback_data="toggle_percentage_based"),
             InlineKeyboardButton(f"{'Disable' if self.trading_bot.config['use_real_trading'] else 'Enable'} Real Trading",
                                 callback_data="toggle_real_trading")],
            [InlineKeyboardButton("Back to Status", callback_data="status")]
        ]

        if update.callback_query:
            await update.callback_query.edit_message_text(
                config_text,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await update.message.reply_text(
                config_text,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

    async def set_config_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /set command to update configuration"""
        if not await self.is_authorized(update):
            return

        if not self.trading_bot:
            await update.message.reply_text("Trading bot not initialized")
            return

        args = context.args
        if len(args) < 2:
            await update.message.reply_text(
                "Usage: /set [parameter] [value]\n\n"
                "Common parameters:\n"
                "• amount (base trade amount, e.g., 0.5 for BNB in BNBUSDT)\n"
                "• trading_mode (safe, standard, aggressive, scalping)\n"
                "• take_profit (percentage)\n"
                "• stop_loss (percentage)\n"
                "• max_trade_time (seconds)\n"
                "• min_volume (BNB amount)\n"
                "• min_price_change (percentage)\n"
                "• auto_select_pairs (true/false)\n"
                "• whale_detection (true/false)\n"
                "• api_key (your Binance API key)\n"
                "• api_secret (your Binance API secret)\n"
                "• use_testnet (true/false)\n"
                "• use_real_trading (true/false)\n"
                "• trade_percentage (percentage of balance to use)\n"
                "• use_percentage (true/false)"
            )
            return

        param = args[0].lower()
        value_str = args[1]

        if param not in self.trading_bot.config:
            await update.message.reply_text(f"Unknown parameter: {param}. Use /config to see available parameters.")
            return

        original_value = self.trading_bot.config[param]
        new_value = None

        try:
            if isinstance(original_value, bool):
                new_value = value_str.lower() in ['true', 'yes', '1', 'on']
            elif isinstance(original_value, int):
                new_value = int(value_str)
            elif isinstance(original_value, float):
                new_value = float(value_str)
            elif isinstance(original_value, str):
                if param == 'trading_mode' and value_str not in TRADING_MODES:
                    await update.message.reply_text(
                        f"Invalid trading mode: {value_str}\n"
                        f"Available modes: {', '.join(TRADING_MODES.keys())}"
                    )
                    return
                new_value = value_str
            else:
                new_value = value_str
        except ValueError:
            await update.message.reply_text(f"Invalid value format for {param}: {value_str}. Expected type: {type(original_value).__name__}")
            return

        self.trading_bot.config[param] = new_value

        if param in ['api_key', 'api_secret', 'use_testnet']:
            self.trading_bot.binance_api = BinanceAPI(self.trading_bot.config)
            self.trading_bot.market_analyzer.binance_api = self.trading_bot.binance_api
            if self.trading_bot.whale_detector:
                self.trading_bot.whale_detector.binance_api = self.trading_bot.binance_api

        if param == 'trading_mode':
            self.trading_bot.apply_trading_mode_settings()
            await update.message.reply_text(
                f"Trading mode changed to {new_value}. Applied new settings:\n"
                f"• Take Profit: {self.trading_bot.config['take_profit']}%\n"
                f"• Stop Loss: {self.trading_bot.config['stop_loss']}%\n"
                f"• Max Trade Time: {self.trading_bot.config['max_trade_time']} seconds\n"
                f"• Min Volume: {self.trading_bot.config['min_volume']} BNB\n"
                f"• Min Price Change: {self.trading_bot.config['min_price_change']}%\n"
                f"• Max Concurrent Trades: {self.trading_bot.config['max_concurrent_trades']}"
            )
        else:
            await update.message.reply_text(f"Configuration updated: {param} = {new_value}")

    async def trades_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /trades command to show recent trades"""
        if not await self.is_authorized(update):
            return

        all_trades = ACTIVE_TRADES + COMPLETED_TRADES

        if not all_trades:
            await update.message.reply_text("No trades recorded yet")
            return

        recent_trades = sorted(all_trades, key=lambda x: x['timestamp'], reverse=True)[:5]

        trades_text = "📊 RECENT TRADES\n\n"
        for trade in recent_trades:
            status = "Active" if not trade.get('completed', False) else "Completed"
            result_pct_str = f"{trade.get('result', 0):.2f}%" if trade.get('completed', False) else "N/A"
            profit_bnb_str = f"{trade.get('profit_in_bnb', 0.0):.8f} BNB" if trade.get('completed', False) else "N/A"

            if not trade.get('completed', False):
                elapsed = int(time.time() - trade['timestamp'])
                time_info = f"Elapsed: {elapsed}s"
            else:
                try:
                    entry_dt = datetime.strptime(trade['entry_time'], "%Y-%m-%d %H:%M:%S")
                    exit_dt = datetime.strptime(trade['exit_time'], "%Y-%m-%d %H:%M:%S")
                    duration_seconds = int((exit_dt - entry_dt).total_seconds())
                    time_info = f"Duration: {duration_seconds}s"
                except (KeyError, ValueError):
                    duration_seconds = int(trade.get('exit_timestamp', time.time()) - trade['timestamp'])
                    time_info = f"Duration: {duration_seconds}s (approx)"

            trades_text += (
                f"Pair: {trade['pair']}\n"
                f"Type: {trade['type']}\n"
                f"Status: {status}\n"
                f"Entry: ${trade['entry_price']:.6f}\n"
                f"Result %: {result_pct_str}\n"
                f"Profit BNB: {profit_bnb_str}\n"
                f"{time_info}\n"
                f"Mode: {trade.get('mode', 'Standard').capitalize()}\n"
                f"Real Trade: {'Yes' if trade.get('real_trade', False) else 'No (Simulation)'}\n\n"
            )

        await update.message.reply_text(trades_text)

    async def whales_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /whales command to show recent whale transactions"""
        if not await self.is_authorized(update):
            return

        if not MOCK_WHALE_TRANSACTIONS:
            await update.message.reply_text("No whale transactions detected yet")
            return

        recent_whales = sorted(MOCK_WHALE_TRANSACTIONS, key=lambda x: x['id'], reverse=True)[:5]

        whales_text = "🐋 RECENT WHALE TRANSACTIONS\n\n"
        for whale in recent_whales:
            whales_text += (
                f"Token: {whale['token']}\n"
                f"Type: {whale['type']}\n"
                f"Amount: {whale['amount']:.2f} {whale['token'].replace('USDT', '').replace('BUSD', '')}\n"
                f"Value: ${whale['value']:,.2f}\n"
                f"Impact: {whale['impact']}\n"
                f"Time: {whale['time']}\n\n"
            )

        await update.message.reply_text(whales_text)

    async def bnb_pairs_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /bnbpairs command to show available BNB trading pairs"""
        if not await self.is_authorized(update):
            return

        pairs = self.trading_bot.market_analyzer.market_data
        bnb_base_pairs = [p for p in pairs if p["pair"].startswith("BNB")]
        bnb_quote_pairs = [p for p in pairs if "BNB" in p["pair"] and not p["pair"].startswith("BNB")]

        pairs_text = "📋 BNB TRADING PAIRS\n\n"
        pairs_text += "BNB Base Pairs:\n"
        if bnb_base_pairs:
            for pair in bnb_base_pairs:
                pairs_text += f"• {pair['pair']} - Vol: {pair['volume']:.2f}, Change: {pair['price_change']:.2f}%\n"
        else:
            pairs_text += "No BNB base pairs found.\n"

        pairs_text += "\nBNB Quote Pairs:\n"
        if bnb_quote_pairs:
            for pair in bnb_quote_pairs:
                pairs_text += f"• {pair['pair']} - Vol: {pair['volume']:.2f}, Change: {pair['price_change']:.2f}%\n"
        else:
            pairs_text += "No BNB quote pairs found.\n"

        if update.callback_query:
            await update.callback_query.edit_message_text(pairs_text)
        else:
            await update.message.reply_text(pairs_text)

    async def volume_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /volume command to show highest volume BNB pairs"""
        if not await self.is_authorized(update):
            return

        high_volume_pairs = self.trading_bot.market_analyzer.get_high_volume_pairs(10)
        volume_text = "📊 TOP VOLUME BNB PAIRS\n\n"
        for i, pair in enumerate(high_volume_pairs, 1):
            volume_text += (
                f"{i}. {pair['pair']}\n"
                f"   Volume: {pair['volume']:.2f}\n"
                f"   Price: ${pair['last_price']:.6f}\n"
                f"   Change: {pair['price_change']:.2f}%\n\n"
            )
        keyboard = []
        for i in range(0, min(5, len(high_volume_pairs)), 2):
            row = []
            for j in range(2):
                if i + j < len(high_volume_pairs):
                    pair = high_volume_pairs[i + j]
                    row.append(InlineKeyboardButton(
                        f"Trade {pair['pair']}",
                        callback_data=f"trade_{pair['pair']}"
                    ))
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton("Back to Status", callback_data="status")])

        if update.callback_query:
            await update.callback_query.edit_message_text(
                volume_text,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await update.message.reply_text(
                volume_text,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

    async def trending_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /trending command to show trending BNB pairs"""
        if not await self.is_authorized(update):
            return

        trending_pairs = self.trading_bot.market_analyzer.get_trending_pairs(10)
        trending_text = "📈 TRENDING BNB PAIRS\n\n"
        for i, pair in enumerate(trending_pairs, 1):
            emoji = "🟢" if pair['price_change'] > 0 else "🔴"
            trending_text += (
                f"{i}. {pair['pair']} {emoji}\n"
                f"   Change: {pair['price_change']:.2f}%\n"
                f"   Volume: {pair['volume']:.2f}\n"
                f"   Price: ${pair['last_price']:.6f}\n\n"
            )
        keyboard = []
        for i in range(0, min(5, len(trending_pairs)), 2):
            row = []
            for j in range(2):
                if i + j < len(trending_pairs):
                    pair = trending_pairs[i + j]
                    row.append(InlineKeyboardButton(
                        f"Trade {pair['pair']}",
                        callback_data=f"trade_{pair['pair']}"
                    ))
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton("Back to Status", callback_data="status")])

        if update.callback_query:
            await update.callback_query.edit_message_text(
                trending_text,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await update.message.reply_text(
                trending_text,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

    async def trading_modes_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /modes command to show available trading modes"""
        if not await self.is_authorized(update):
            return

        modes_text = "⚙️ AVAILABLE TRADING MODES\n\n"
        for mode_name, mode_settings in TRADING_MODES.items():
            modes_text += f"📌 {mode_name.capitalize()}\n"
            modes_text += f"• {mode_settings['description']}\n"
            modes_text += f"• Take Profit: {mode_settings['take_profit']}%\n"
            modes_text += f"• Stop Loss: {mode_settings['stop_loss']}%\n"
            modes_text += f"• Max Trade Time: {mode_settings['max_trade_time']} seconds\n"
            modes_text += f"• Max Trades: {mode_settings['max_trades']}\n\n"
        keyboard = []
        for mode_name in TRADING_MODES.keys():
            keyboard.append([InlineKeyboardButton(
                f"Select {mode_name.capitalize()}",
                callback_data=f"set_mode_{mode_name}"
            )])
        keyboard.append([InlineKeyboardButton("Back to Status", callback_data="status")])

        if update.callback_query:
            await update.callback_query.edit_message_text(
                modes_text,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await update.message.reply_text(
                modes_text,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

    async def whale_config_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /whaleconfig command to configure whale detection"""
        if not await self.is_authorized(update):
            return

        if not self.trading_bot:
            message = "Trading bot not initialized"
            if update.callback_query:
                await update.callback_query.edit_message_text(message)
            else:
                await update.message.reply_text(message)
            return

        keyboard = [
            [InlineKeyboardButton(
                f"Whale Detection: {'Disable' if self.trading_bot.config['whale_detection'] else 'Enable'}",
                callback_data="toggle_whale_detection"
            )],
            [InlineKeyboardButton(
                f"Auto-Trade on Whale: {'Disable' if self.trading_bot.config['auto_trade_on_whale'] else 'Enable'}",
                callback_data="toggle_auto_trade_whale"
            )],
            [InlineKeyboardButton("Strategy: Follow Whale", callback_data="strategy_follow_whale"),
             InlineKeyboardButton("Strategy: Counter Whale", callback_data="strategy_counter_whale")],
            [InlineKeyboardButton(
                f"Set Threshold: {self.trading_bot.config['whale_threshold']} BNB",
                callback_data="set_whale_threshold"
            )],
            [InlineKeyboardButton("Back to Status", callback_data="status")]
        ]
        whale_config_text = (
            "🐋 WHALE DETECTION CONFIGURATION\n\n"
            f"Whale Detection: {'Enabled' if self.trading_bot.config['whale_detection'] else 'Disabled'}\n"
            f"Auto-Trade on Whale: {'Yes' if self.trading_bot.config['auto_trade_on_whale'] else 'No'}\n"
            f"Trading Strategy: {self.trading_bot.config['trading_strategy']}\n"
            f"Whale Threshold: {self.trading_bot.config['whale_threshold']} BNB\n\n"
            "Use the buttons below to configure whale detection settings:"
        )

        if update.callback_query:
            await update.callback_query.edit_message_text(
                whale_config_text,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await update.message.reply_text(
                whale_config_text,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

    async def start_trading_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /starttrade command"""
        if not await self.is_authorized(update):
            return

        if not self.trading_bot:
            await update.message.reply_text("Trading bot not initialized")
            return

        await self.show_trading_mode_selection(update, context)

    async def show_trading_mode_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show trading mode selection menu"""
        modes_text = "🔄 SELECT TRADING MODE\n\n"
        for mode_name, mode_settings in TRADING_MODES.items():
            modes_text += f"📌 {mode_name.capitalize()}\n"
            modes_text += f"• {mode_settings['description']}\n"
            modes_text += f"• Take Profit: {mode_settings['take_profit']}%\n"
            modes_text += f"• Stop Loss: {mode_settings['stop_loss']}%\n"
            modes_text += f"• Max Trade Time: {mode_settings['max_trade_time']} seconds\n\n"
        keyboard = []
        for mode_name in TRADING_MODES.keys():
            keyboard.append([InlineKeyboardButton(
                f"Start with {mode_name.capitalize()}",
                callback_data=f"start_mode_{mode_name}"
            )])
        keyboard.append([InlineKeyboardButton("Cancel", callback_data="status")])

        if update.callback_query:
            await update.callback_query.edit_message_text(
                modes_text,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await update.message.reply_text(
                modes_text,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

    async def stop_trading_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /stoptrade command"""
        if not await self.is_authorized(update):
            return

        if not self.trading_bot:
            await update.message.reply_text("Trading bot not initialized")
            return

        self.trading_bot.config["trading_enabled"] = False
        if self.trading_bot.stop_trading():
            await update.message.reply_text("Trading stopped. No new trades will be opened.")
        else:
            await update.message.reply_text("Trading is already stopped")

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button callbacks"""
        if not await self.is_authorized(update):
            return

        query = update.callback_query
        await query.answer()

        if query.data == "select_trading_mode":
            await self.show_trading_mode_selection(update, context)
            return

        if query.data.startswith("start_mode_"):
            mode = query.data.replace("start_mode_", "")
            if mode in TRADING_MODES:
                self.trading_bot.config["trading_mode"] = mode
                self.trading_bot.apply_trading_mode_settings()
                self.trading_bot.config["trading_enabled"] = True
                if self.trading_bot.start_trading():
                    await query.edit_message_text(
                        f"Trading started with {mode.capitalize()} mode!\n\n"
                        f"• Take Profit: {self.trading_bot.config['take_profit']}%\n"
                        f"• Stop Loss: {self.trading_bot.config['stop_loss']}%\n"
                        f"• Max Trade Time: {self.trading_bot.config['max_trade_time']} seconds\n\n"
                        "You will receive notifications for new trades and whale alerts."
                    )
                else:
                    await query.edit_message_text("Trading is already running")
            return

        if query.data.startswith("set_mode_"):
            mode = query.data.replace("set_mode_", "")
            if mode in TRADING_MODES:
                self.trading_bot.config["trading_mode"] = mode
                self.trading_bot.apply_trading_mode_settings()
                await query.edit_message_text(
                    f"Trading mode set to {mode.capitalize()}!\n\n"
                    f"• Take Profit: {self.trading_bot.config['take_profit']}%\n"
                    f"• Stop Loss: {self.trading_bot.config['stop_loss']}%\n"
                    f"• Max Trade Time: {self.trading_bot.config['max_trade_time']} seconds\n\n"
                    "Use /starttrade to start trading with these settings."
                )
            return

        if query.data.startswith("trade_"):
            pair = query.data.replace("trade_", "")
            if not self.trading_bot.running or not self.trading_bot.config["trading_enabled"]:
                await query.edit_message_text(
                    f"Trading is not active. Please start trading first with /starttrade."
                )
                return
            pair_data = self.trading_bot.market_analyzer.get_pair_data(pair)
            if pair_data:
                trade_type = "BUY" if pair_data["price_change"] > 0 else "SELL"
                trade = self.trading_bot.create_trade(pair, trade_type, pair_data["last_price"])
                # Use helper for notification with manual selection details
                manual_trade_details = f"Manual Pair Selection ({pair})"
                entry_message = self.trading_bot._format_auto_trade_notification(trade, manual_trade_details)
                await query.edit_message_text(entry_message)
            else:
                await query.edit_message_text(f"Could not find data for pair {pair}")
            return

        if query.data == "toggle_real_trading":
            if not self.trading_bot.config["api_key"] or not self.trading_bot.config["api_secret"]:
                await query.edit_message_text(
                    "⚠️ API credentials not set.\n\n"
                    "Please set your Binance API credentials first:\n"
                    "/set api_key YOUR_API_KEY\n"
                    "/set api_secret YOUR_API_SECRET"
                )
                return
            new_state = not self.trading_bot.config["use_real_trading"]
            self.trading_bot.config["use_real_trading"] = new_state
            await query.edit_message_text(
                f"{'✅ Real trading has been ENABLED!' if new_state else '✅ Real trading has been DISABLED.'}\n\n"
                f"{'The bot will now execute REAL trades on Binance using your account.' if new_state else 'The bot will now operate in simulation mode only.'}\n\n"
                f"{'⚠️ WARNING: Please monitor your trades carefully.' if new_state else ''}"
            )
            return

        if query.data == "toggle_percentage_based":
            new_state = not self.trading_bot.config["use_percentage"]
            self.trading_bot.config["use_percentage"] = new_state
            await query.edit_message_text(
                f"{'✅ Percentage-based trading has been ENABLED!' if new_state else '✅ Percentage-based trading has been DISABLED.'}\n\n"
                f"{'The bot will now use ' + str(self.trading_bot.config['trade_percentage']) + '% of your available balance for each trade.' if new_state else 'The bot will now use a fixed amount of ' + str(self.trading_bot.config['amount']) + ' for each trade.'}\n\n"
                f"Use /setpercentage to configure the percentage amount."
            )
            return

        if query.data == "stop_trading":
            self.trading_bot.config["trading_enabled"] = False
            if self.trading_bot.stop_trading():
                await query.edit_message_text("Trading stopped. No new trades will be opened.")
            else:
                await query.edit_message_text("Trading is already stopped")
        elif query.data == "status":
            await self.status_command(update, context)
        elif query.data == "config":
            await self.config_command(update, context)
        elif query.data == "volume":
            await self.volume_command(update, context)
        elif query.data == "trending":
            await self.trending_command(update, context)
        elif query.data == "toggle_whale_detection":
            self.trading_bot.config["whale_detection"] = not self.trading_bot.config["whale_detection"]
            await self.whale_config_command(update, context)
        elif query.data == "toggle_auto_trade_whale":
            self.trading_bot.config["auto_trade_on_whale"] = not self.trading_bot.config["auto_trade_on_whale"]
            await self.whale_config_command(update, context)
        elif query.data == "toggle_auto_select":
            self.trading_bot.config["auto_select_pairs"] = not self.trading_bot.config["auto_select_pairs"]
            await self.config_command(update, context)
        elif query.data == "strategy_follow_whale":
            self.trading_bot.config["trading_strategy"] = "follow_whale"
            await self.whale_config_command(update, context)
        elif query.data == "strategy_counter_whale":
            self.trading_bot.config["trading_strategy"] = "counter_whale"
            await self.whale_config_command(update, context)
        elif query.data == "set_whale_threshold":
            current = self.trading_bot.config["whale_threshold"]
            if current < 50: self.trading_bot.config["whale_threshold"] = 50
            elif current < 100: self.trading_bot.config["whale_threshold"] = 100
            elif current < 200: self.trading_bot.config["whale_threshold"] = 200
            elif current < 500: self.trading_bot.config["whale_threshold"] = 500
            else: self.trading_bot.config["whale_threshold"] = 10
            await self.whale_config_command(update, context)
        elif query.data.startswith("follow_whale_"):
            whale_id = int(query.data.split("_")[2])
            whale_transaction = next((w for w in MOCK_WHALE_TRANSACTIONS if w['id'] == whale_id), None)
            if whale_transaction:
                # Create trade from whale with is_auto_trade=False for manual follow
                self.trading_bot.create_trade_from_whale(whale_transaction, whale_transaction['type'], is_auto_trade=False)
                await query.edit_message_text(f"Processing 'Follow Whale' for transaction {whale_id}. Trade initiated!")
            else:
                await query.edit_message_text(f"Whale transaction {whale_id} not found.")
        elif query.data.startswith("ignore_whale_"):
            whale_id = int(query.data.split("_")[2])
            await query.edit_message_text(f"Whale alert {whale_id} ignored.")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle regular text messages"""
        if not await self.is_authorized(update):
            return
        await update.message.reply_text(
            "I only respond to commands. Use /help to see available commands."
        )

    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle errors in the telegram bot"""
        logger.error(f"Exception while handling an update: {context.error}")
        if update and update.effective_chat:
            await update.effective_chat.send_message(
                "An error occurred while processing your request. Please try again later."
            )

    async def start_notification_processor(self):
        """Start the notification processor"""
        await self.trading_bot.process_notification_queue()

    def run(self):
        """Run the bot"""
        notification_loop = asyncio.new_event_loop()
        notification_thread = threading.Thread(
            target=self._run_notification_processor,
            args=(notification_loop,)
        )
        notification_thread.daemon = True
        notification_thread.start()
        self.application.run_polling()

    def _run_notification_processor(self, loop):
        """Run the notification processor in a separate thread"""
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.start_notification_processor())
    def set_trading_bot(self, trading_bot):
        self.trading_bot = trading_bot
def main():
    token = TELEGRAM_BOT_TOKEN
    telegram_handler = TelegramBotHandler(token, ADMIN_USER_IDS)
    trading_bot = TradingBot(CONFIG, telegram_handler)
    whale_detector = WhaleDetector(CONFIG, trading_bot)
    trading_bot.set_whale_detector(whale_detector)
    telegram_handler.set_trading_bot(trading_bot)

    print("Enhanced BNB Trading Bot is starting...")
    print(f"Admin User IDs: {ADMIN_USER_IDS}")
    print(f"Available Trading Modes: {', '.join(TRADING_MODES.keys())}")
    print("Press Ctrl+C to stop")

    telegram_handler.run()

if __name__ == "__main__":
    main()
