
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
    level=logging.INFO # Ubah ke logging.INFO untuk produksi jika terlalu banyak log
)
logger = logging.getLogger(__name__)

# ======== BOT CONFIGURATION ========
# Replace these values with your own
TELEGRAM_BOT_TOKEN = "API_BOT_TELEGRAM"  # Replace with your bot token
ADMIN_USER_IDS = [1234569]    # Replace with your Telegram user ID(s)
# ==================================

# Binance API configuration
BINANCE_API_KEY = "API_KEY"  # Your Binance API key
BINANCE_API_SECRET = "API_SECRET" 
BINANCE_API_URL = "https://api.binance.com"
BINANCE_TEST_API_URL = "https://testnet.binance.vision"  # Testnet URL for testing

# Trading modes
TRADING_MODES = {
    "conservative_scalp": {
        "take_profit": 0.5,         # TP sedikit lebih besar dari SL
        "stop_loss": 0.8,           # SL sangat ketat
        "max_trade_time": 180,      # 3 menit, cukup untuk scalping cepat
        "volume_threshold": 250,    # Volume sangat tinggi untuk likuiditas & spread rendah
        "price_change_threshold": 0.15, # Perubahan harga minimal yang sangat kecil, mencari getaran
        "max_trades": 6,            # Bisa buka beberapa posisi scalping
        "description": "Scalping sangat konservatif, target profit kecil, SL ketat, butuh likuiditas tinggi. R/R ~1:1.5"
    },
    "consistent_drip": {
        "take_profit": 1.0,         # Target profit kecil
        "stop_loss": 0.8,           # SL sedikit lebih ketat dari TP
        "max_trade_time": 450,      # Sekitar 7.5 menit
        "volume_threshold": 150,    # Volume tinggi, tapi lebih rendah dari scalping
        "price_change_threshold": 0.3, # Mencari pergerakan yang sedikit lebih jelas
        "max_trades": 4,            # Jumlah trade moderat
        "description": "Mencari profit kecil secara konsisten, SL ketat. R/R ~1:1.25"
    },
    "balanced_growth": {
        "take_profit": 2.0,         # Target profit moderat
        "stop_loss": 1.5,           # SL lebih ketat dari TP
        "max_trade_time": 900,      # 15 menit
        "volume_threshold": 80,     # Volume moderat
        "price_change_threshold": 0.5, # Perubahan harga yang cukup signifikan
        "max_trades": 3,            # Lebih sedikit trade, fokus pada kualitas
        "description": "Pendekatan seimbang, target profit moderat dengan risiko terkontrol. R/R ~1:1.33"
    },
    "momentum_rider": {
        "take_profit": 3.5,         # Target profit lebih besar, mencoba menangkap tren
        "stop_loss": 2.0,           # SL tetap lebih ketat dari TP
        "max_trade_time": 1800,     # 30 menit, memberi waktu tren berkembang
        "volume_threshold": 50,     # Volume cukup, tidak terlalu restriktif
        "price_change_threshold": 0.8, # Mencari tren yang sudah mulai terbentuk
        "max_trades": 2,            # Sangat selektif, fokus pada trade berkualitas tinggi
        "description": "Mencoba menangkap momentum/tren kecil, TP lebih besar, SL terkontrol. R/R ~1:1.75"
    }
}

# Bot configuration
CONFIG = {
    "api_key": BINANCE_API_KEY,
    "api_secret": BINANCE_API_SECRET,
    "trading_pair": "BNBUSDT",  # Default to BNB/USDT
    "amount": 0.01,           # Jumlah BNB yang akan digunakan per trade jika use_percentage = False
                              # Pengguna menyebutkan modal 0.04, jadi ini mungkin cocok.
                              # Jika ini adalah kuantitas base asset untuk pair non-BNB, perlu penyesuaian.
    "use_percentage": False,  # Apakah menggunakan persentase dari saldo BNB
    "trade_percentage": 5.0,  # Persentase saldo BNB yang digunakan (jika use_percentage = True)
    "take_profit": 1.5,       # percentage
    "stop_loss": 5.0,         # percentage
    "trading_enabled": True,
    "whale_detection": True,    # Enable whale detection
    "whale_threshold": 100,     # BNB amount to consider as whale (100 BNB)
    "auto_trade_on_whale": False, # Auto trade when whale is detected
    "trading_strategy": "follow_whale", # follow_whale, counter_whale, dca
    "safety_mode": True,        # Additional safety checks
    "trading_mode": "safe",     # Current trading mode (akan di-override oleh pilihan mode)
    "max_trade_time": 300,      # Maximum time for a trade in seconds
    "auto_select_pairs": True,  # Automatically select best pairs
    "min_volume": 100,          # Minimum volume (dalam BNB) untuk pair selection
    "min_price_change": 1.0,    # Minimum 24h price change percentage
    "max_concurrent_trades": 3, # Maximum number of concurrent trades
    "market_update_interval": 30,  # Update market data every 30 seconds
    "use_testnet": False,        # Gunakan Binance testnet untuk testing - SET KE FALSE UNTUK REAL TRADING
    "use_real_trading": False,  # Set ke True untuk trading sungguhan (PENTING!)
    "mock_mode": True,          # Set ke False jika use_real_trading=True. Ini akan di-force False jika real trading.
    "daily_loss_limit": 5.0,    # Batas kerugian harian dalam persentase
    "daily_profit_target": 2.5, # Target profit harian dalam persentase
    "min_bnb_per_trade": 0.011  # Minimal BNB yang dialokasikan per trade (sekitar 5-6 USD, untuk MIN_NOTIONAL)
                                # Jika hasil perhitungan amount < ini, akan dinaikkan ke nilai ini.
                                # Jika saldo tidak cukup untuk ini, trade tidak akan dilakukan.
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
    {"pair": "SOLBNB", "volume": 5882.66, "quote_volume": 1609.2, "price_change": 4.59, "last_price": 0.2735},
    {"pair": "ALTBNB", "volume": 2184.30, "quote_volume": 137.4, "price_change": 11.33, "last_price": 0.0000629},
    {"pair": "SIGNBNB", "volume": 793.73, "quote_volume": 117.1, "price_change": -0.29, "last_price": 0.00014760},
    {"pair": "FETBNB", "volume": 759.47, "quote_volume": 100.4, "price_change": 6.53, "last_price": 0.001322},
    {"pair": "XRPBNB", "volume": 704.39, "quote_volume": 271.7, "price_change": 1.68, "last_price": 0.003858},
    {"pair": "BNBUSDT", "volume": 12500.45, "quote_volume": 3817687.9, "price_change": 2.3, "last_price": 305.42},
]

# Additional pairs that will be randomly added to simulate new trending pairs
ADDITIONAL_PAIRS = [
    {"pair": "DOGEBNB", "volume": 0, "quote_volume": 0, "price_change": 0, "last_price": 0.00012},
    {"pair": "ADABNB", "volume": 0, "quote_volume": 0, "price_change": 0, "last_price": 0.00095},
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
            response.raise_for_status() 
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting exchange info: {e}")
            return None
        except json.JSONDecodeError:
            logger.error(f"Failed to decode JSON from exchange info: {response.text if 'response' in locals() else 'No response'}")
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
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as http_err:
            logger.error(f"HTTP error getting account info: {http_err} - {response.text}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting account info: {e}")
            return None
        except json.JSONDecodeError:
            logger.error(f"Failed to decode JSON from account info: {response.text if 'response' in locals() else 'No response'}")
            return None


    def get_ticker_price(self, symbol):
        """Get current price for a symbol"""
        try:
            url = f"{self.base_url}/api/v3/ticker/price"
            params = {'symbol': symbol}
            response = requests.get(url, params=params)
            response.raise_for_status()
            return float(response.json()['price'])
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting ticker price for {symbol}: {e}")
            return None
        except (KeyError, ValueError, json.JSONDecodeError):
            logger.error(f"Failed to parse ticker price for {symbol}: {response.text if 'response' in locals() else 'No response'}")
            return None


    def get_ticker_24hr(self, symbol=None):
        """Get 24hr ticker data for a symbol or all symbols"""
        try:
            url = f"{self.base_url}/api/v3/ticker/24hr"
            params = {}
            if symbol:
                params['symbol'] = symbol
            response = requests.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting 24hr ticker: {e}")
            return None
        except json.JSONDecodeError:
            logger.error(f"Failed to decode JSON from 24hr ticker: {response.text if 'response' in locals() else 'No response'}")
            return None

    # ==================== PERBAIKAN DI SINI (BinanceAPI.create_order) ====================
    def create_order(self, symbol, side, order_type, quantity=None, price=None, time_in_force=None):
        """Create a new order"""
        request_params_for_log = {} # Untuk logging jika error
        try:
            url = f"{self.base_url}/api/v3/order"
            timestamp = int(time.time() * 1000)

            params = {
                'symbol': symbol,
                'side': side,
                'type': order_type,
                'timestamp': timestamp
            }

            if quantity is not None:
                # TODO: Idealnya, presisi kuantitas (dan harga) harus diambil dari exchangeInfo
                # Untuk sekarang, format dengan 8 desimal, hapus nol di belakang.
                # Binance biasanya membutuhkan string untuk quantity dan price.
                # Contoh: 0.01000000 menjadi '0.01'
                # Contoh: 123.4500 menjadi '123.45'
                # Untuk menghindari masalah floating point precision, format ke string dengan presisi tertentu,
                # lalu strip trailing zeros.
                
                # Cari tahu stepSize dari exchangeInfo untuk symbol ini.
                # Untuk sementara, kita format ke 8 desimal dan strip.
                # Ini mungkin tidak selalu benar untuk semua pair.
                formatted_quantity = f"{float(quantity):.8f}".rstrip('0').rstrip('.')
                params['quantity'] = formatted_quantity
                

            if order_type != 'MARKET': # Hanya untuk order non-MARKET (LIMIT, etc.)
                if price is not None:
                    # Sama seperti quantity, format price.
                    formatted_price = f"{float(price):.8f}".rstrip('0').rstrip('.')
                    params['price'] = formatted_price
                if time_in_force:
                    params['timeInForce'] = time_in_force
            
            request_params_for_log = params.copy() # Salin sebelum signature untuk logging
            params['signature'] = self._generate_signature(params)

            logger.info(f"Sending order to Binance: URL={url}, Params (pre-signature)={request_params_for_log}")
            response = requests.post(url, params=params, headers=self._get_headers())
            
            logger.info(f"Binance order response: Status={response.status_code}, Text={response.text}")

            # Binance mengembalikan 200 untuk order yang diterima (termasuk yang mungkin langsung terisi atau tidak)
            if response.status_code == 200: 
                return response.json()
            else:
                # Log error dengan lebih detail
                logger.error(f"Failed to create order for {symbol}. Status: {response.status_code}. "
                             f"Response: {response.text}. Sent Params (pre-signature): {request_params_for_log}")
                try:
                    return response.json() # Kembalikan juga error JSON jika ada
                except json.JSONDecodeError:
                    return {"error_message": response.text, "status_code": response.status_code} # Kembalikan error mentah
        except Exception as e:
            logger.error(f"Exception creating order for {symbol}: {e}. "
                         f"Sent Params (pre-signature): {request_params_for_log}", exc_info=True)
            return None # Exception programming, bukan dari Binance API
    # ==================== AKHIR PERBAIKAN (BinanceAPI.create_order) ====================

    def get_open_orders(self, symbol=None):
        """Get all open orders for a symbol or all symbols"""
        try:
            url = f"{self.base_url}/api/v3/openOrders"
            timestamp = int(time.time() * 1000)
            params = {'timestamp': timestamp}
            if symbol:
                params['symbol'] = symbol
            params['signature'] = self._generate_signature(params)
            response = requests.get(url, params=params, headers=self._get_headers())
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting open orders: {e}")
            return None
        except json.JSONDecodeError:
            logger.error(f"Failed to decode JSON from open orders: {response.text if 'response' in locals() else 'No response'}")
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
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error canceling order {order_id} for {symbol}: {e}")
            return None
        except json.JSONDecodeError:
            logger.error(f"Failed to decode JSON from cancel order: {response.text if 'response' in locals() else 'No response'}")
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
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting order {order_id} for {symbol}: {e}")
            return None
        except json.JSONDecodeError:
            logger.error(f"Failed to decode JSON from get order: {response.text if 'response' in locals() else 'No response'}")
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
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting all orders for {symbol}: {e}")
            return None
        except json.JSONDecodeError:
            logger.error(f"Failed to decode JSON from all orders: {response.text if 'response' in locals() else 'No response'}")
            return None

    def get_bnb_pairs(self):
        """Get all BNB trading pairs"""
        try:
            exchange_info = self.get_exchange_info()
            if not exchange_info:
                return []
            bnb_pairs = [sym['symbol'] for sym in exchange_info['symbols'] if 'BNB' in sym['symbol'] and sym['status'] == 'TRADING']
            return bnb_pairs
        except Exception as e:
            logger.error(f"Error getting BNB pairs: {e}")
            return []

    def get_market_data(self):
        """Get market data for BNB pairs"""
        try:
            bnb_pairs_filter = self.get_bnb_pairs() 
            if not bnb_pairs_filter:
                logger.warning("No BNB pairs found from exchange info.")
                return []

            ticker_data = self.get_ticker_24hr() 
            if not ticker_data:
                return []

            market_data = []
            for ticker in ticker_data:
                if ticker['symbol'] in bnb_pairs_filter: 
                    try:
                        market_data.append({
                            'pair': ticker['symbol'],
                            'volume': float(ticker['volume']), 
                            'quote_volume': float(ticker.get('quoteVolume', 0)), 
                            'price_change': float(ticker['priceChangePercent']),
                            'last_price': float(ticker['lastPrice'])
                        })
                    except (ValueError, TypeError, KeyError) as e:
                        logger.warning(f"Could not parse ticker data for {ticker.get('symbol', 'N/A')}: {e}. Data: {ticker}")
            
            market_data.sort(key=lambda x: x.get('quote_volume', x['volume']), reverse=True)
            return market_data
        except Exception as e:
            logger.error(f"Error getting market data: {e}", exc_info=True)
            return []


class MarketAnalyzer:
    def __init__(self, config):
        self.config = config
        self.market_data = INITIAL_MARKET_DATA.copy() if config["mock_mode"] else []
        self.last_update = 0
        self.update_interval = config["market_update_interval"]
        self.update_thread = None
        self.running = False
        self.lock = threading.Lock()
        self.binance_api = BinanceAPI(config) if config["api_key"] and config["api_secret"] else None

    def start_updating(self):
        if not self.running:
            self.running = True
            self.update_thread = threading.Thread(target=self.update_loop)
            self.update_thread.daemon = True
            self.update_thread.start()
            return True
        return False

    def stop_updating(self):
        if self.running:
            self.running = False
            if self.update_thread:
                self.update_thread.join(timeout=5.0)
            return True
        return False

    def update_loop(self):
        while self.running:
            try:
                self.update_market_data()
                time.sleep(self.update_interval)
            except Exception as e:
                logger.error(f"Error in market update loop: {e}", exc_info=True)
                time.sleep(self.update_interval * 2) 

    def update_market_data(self):
        with self.lock:
            current_time = time.time()
            self.last_update = current_time

            if self.binance_api and not self.config.get("mock_mode", True):
                real_market_data = self.binance_api.get_market_data()
                if real_market_data:
                    self.market_data = real_market_data
                    logger.info(f"Updated market data with {len(real_market_data)} pairs from Binance API")
                    return 

            if self.config.get("mock_mode", True): 
                logger.info("Using/Updating mock market data.")
                for pair_data in self.market_data:
                    volume_change = random.uniform(-5, 15) / 100
                    price_change_delta = random.uniform(-2, 3)
                    price_change_val = random.uniform(-1, 2) / 100
                    pair_data["volume"] = max(0, pair_data["volume"] * (1 + volume_change))
                    pair_data["price_change"] += price_change_delta
                    pair_data["last_price"] = max(0.00000001, pair_data["last_price"] * (1 + price_change_val))
                    pair_data["quote_volume"] = pair_data["volume"] * pair_data["last_price"] # Update mock quote_volume

                if random.random() < 0.2 and len(ADDITIONAL_PAIRS) > 0 and len(self.market_data) < 20:
                    new_pair = random.choice(ADDITIONAL_PAIRS)
                    new_pair_copy = new_pair.copy()
                    new_pair_copy["volume"] = random.uniform(500, 2000)
                    new_pair_copy["price_change"] = random.uniform(5, 20) * (1 if random.random() > 0.3 else -1)
                    new_pair_copy["last_price"] *= (1 + random.uniform(0.05, 0.2))
                    new_pair_copy["quote_volume"] = new_pair_copy["volume"] * new_pair_copy["last_price"]
                    if not any(p["pair"] == new_pair_copy["pair"] for p in self.market_data):
                        self.market_data.append(new_pair_copy)
                        logger.info(f"Added new MOCK trending pair: {new_pair_copy['pair']}")
                
                if len(self.market_data) > 10 and random.random() < 0.3:
                    sorted_pairs = sorted(self.market_data, key=lambda x: x["volume"])
                    if sorted_pairs:
                        removed_pair = sorted_pairs[0]
                        self.market_data.remove(removed_pair)
                        logger.info(f"Removed MOCK low-volume pair: {removed_pair['pair']}")


    def get_best_trading_pairs(self, min_volume=None, min_price_change=None, limit=5):
        with self.lock:
            min_vol_val = min_volume if min_volume is not None else self.config.get("min_volume", 100)
            min_price_chg_val = min_price_change if min_price_change is not None else self.config.get("min_price_change", 1.0)
            
            filtered_pairs = []
            for pair_data in self.market_data:
                current_volume_metric = 0
                if pair_data['pair'].endswith("BNB"): 
                    volume_to_check = pair_data.get('quote_volume', 0) 
                elif pair_data['pair'].startswith("BNB"): 
                    volume_to_check = pair_data.get('volume', 0) 
                else: 
                    continue 

                if volume_to_check >= min_vol_val and abs(pair_data.get("price_change", 0)) >= min_price_chg_val:
                    filtered_pairs.append(pair_data)

            scored_pairs = []
            for pair in filtered_pairs:
                volume_score = pair.get('quote_volume', pair['volume']) / (1000 if pair.get('quote_volume') else 100) 
                price_change_score = abs(pair.get("price_change",0)) * 2
                score = volume_score + price_change_score
                scored_pairs.append((pair, score))

            scored_pairs.sort(key=lambda x: x[1], reverse=True)
            return [pair for pair, _ in scored_pairs[:limit]]

    def get_trending_pairs(self, limit=5):
        with self.lock:
            trending_pairs = sorted(
                [p for p in self.market_data if p.get("price_change") is not None], 
                key=lambda x: abs(x["price_change"]),
                reverse=True
            )
            return trending_pairs[:limit]

    def get_high_volume_pairs(self, limit=5):
        with self.lock:
            high_volume_pairs = sorted(
                [p for p in self.market_data if p.get("volume") is not None], 
                key=lambda x: x.get('quote_volume', x['volume']),
                reverse=True
            )
            return high_volume_pairs[:limit]

    def get_pair_data(self, pair_name):
        with self.lock:
            if self.binance_api and not self.config.get("mock_mode", True):
                ticker_info = self.binance_api.get_ticker_24hr(symbol=pair_name)
                if ticker_info and isinstance(ticker_info, dict): # Pastikan itu dict tunggal
                    try:
                        return {
                            'pair': ticker_info['symbol'],
                            'volume': float(ticker_info['volume']),
                            'quote_volume': float(ticker_info.get('quoteVolume',0)),
                            'price_change': float(ticker_info['priceChangePercent']),
                            'last_price': float(ticker_info['lastPrice'])
                        }
                    except (ValueError, TypeError, KeyError) as e:
                        logger.warning(f"Could not parse live ticker data for {pair_name}: {e}. Data: {ticker_info}")
            
            for pair in self.market_data:
                if pair["pair"].lower() == pair_name.lower():
                    return pair.copy()
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
        if not self.running:
            self.running = True
            self.detection_thread = threading.Thread(target=self.detection_loop)
            self.detection_thread.daemon = True
            self.detection_thread.start()
            return True
        return False

    def stop_detection(self):
        if self.running:
            self.running = False
            if self.detection_thread:
                self.detection_thread.join(timeout=5.0) 
            return True
        return False

    def detection_loop(self):
        while self.running:
            try:
                if self.config.get("mock_mode", True) and self.config["whale_detection"]: 
                    if random.random() < 0.1: 
                        whale_transaction = self.generate_mock_whale_transaction()
                        if whale_transaction: 
                            MOCK_WHALE_TRANSACTIONS.append(whale_transaction)
                            current_time = time.time()
                            if current_time - self.last_notification_time > 30:
                                self.last_notification_time = current_time
                                whale_message = (
                                    f"🐋 WHALE ALERT 🐋\n\n"
                                    f"Token: {whale_transaction['token']}\n"
                                    f"Amount: {whale_transaction['amount']:.2f} {whale_transaction['token'].replace('USDT', '').replace('BUSD', '')}\n"
                                    f"Value: ${whale_transaction['value']:,.2f}\n"
                                    f"Type: {whale_transaction['type']}\n"
                                    f"Time: {whale_transaction['time']}\n\n"
                                    f"Potential Impact: {whale_transaction['impact']}"
                                )
                                keyboard = [
                                    [InlineKeyboardButton("Follow Whale (Buy/Sell)", callback_data=f"follow_whale_{whale_transaction['id']}")],
                                    [InlineKeyboardButton("Ignore Alert", callback_data=f"ignore_whale_{whale_transaction['id']}")]
                                ]
                                if self.trading_bot: 
                                    self.trading_bot.send_notification(whale_message, keyboard)

                                if self.config["auto_trade_on_whale"] and self.trading_bot:
                                    self.process_whale_for_trading(whale_transaction)
                time.sleep(10) 
            except Exception as e:
                logger.error(f"Error in whale detection loop: {e}", exc_info=True)
                time.sleep(20)


    def generate_mock_whale_transaction(self):
        if self.trading_bot and self.trading_bot.market_analyzer:
            market_data = self.trading_bot.market_analyzer.market_data
            if not market_data: 
                logger.warning("Cannot generate mock whale transaction: Market data is empty.")
                return None
            
            pair_data = random.choice(market_data)
            token = pair_data["pair"]
            transaction_type = random.choice(["BUY", "SELL"])
            base_amount = self.config.get("whale_threshold", 100)
            multiplier = random.uniform(1.0, 10.0)
            amount = base_amount * multiplier

            price = pair_data.get("last_price", 0)
            if price == 0 and "BNB" in token: 
                 price = 300 + random.uniform(-20, 20)
            elif price == 0:
                 price = random.uniform(0.001, 10)

            value = amount * price
            impact = "LOW"
            if value > 1000000: impact = "HIGH - Likely significant price movement"
            elif value > 500000: impact = "MEDIUM - Possible price impact"

            return {
                'id': int(time.time()), 'token': token, 'type': transaction_type,
                'amount': amount, 'price': price, 'value': value,
                'time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 'impact': impact
            }
        else:
            logger.warning("Cannot generate mock whale transaction: Trading bot or market analyzer not available.")
            return None


    def process_whale_for_trading(self, whale_transaction):
        if not self.config["trading_enabled"] or "BNB" not in whale_transaction['token']:
            return
        if not self.trading_bot: 
            logger.warning("Cannot process whale for trading: Trading bot not available.")
            return

        strategy = self.config["trading_strategy"]
        trade_type = whale_transaction['type']
        if strategy == "counter_whale":
            trade_type = "SELL" if whale_transaction['type'] == "BUY" else "BUY"
        
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
        self.notification_queue = queue.Queue()
        self.notification_thread = None
        self.binance_api = BinanceAPI(config) if config["api_key"] and config["api_secret"] else None
        
        self.reset_daily_stats()

    def reset_daily_stats(self):
        DAILY_STATS["date"] = datetime.now().strftime("%Y-%m-%d")
        DAILY_STATS["total_trades"] = 0
        DAILY_STATS["winning_trades"] = 0
        DAILY_STATS["losing_trades"] = 0
        DAILY_STATS["total_profit_pct"] = 0.0
        DAILY_STATS["total_profit_bnb"] = 0.0
        
        if self.binance_api and self.config.get("use_real_trading"):
            try:
                account_info = self.binance_api.get_account_info()
                if account_info and 'balances' in account_info:
                    bnb_balance_found = False
                    for asset in account_info['balances']:
                        if asset['asset'] == 'BNB':
                            balance = float(asset['free']) + float(asset['locked'])
                            DAILY_STATS["starting_balance"] = balance
                            DAILY_STATS["current_balance"] = balance
                            bnb_balance_found = True
                            break
                    if not bnb_balance_found: 
                        DAILY_STATS["starting_balance"] = 0.0
                        DAILY_STATS["current_balance"] = 0.0
                else:
                    DAILY_STATS["starting_balance"] = 0.0
                    DAILY_STATS["current_balance"] = 0.0
            except Exception as e:
                logger.error(f"Error getting balance for daily stats: {e}")
                DAILY_STATS["starting_balance"] = 0.0
                DAILY_STATS["current_balance"] = 0.0
        else:
            DAILY_STATS["starting_balance"] = 0.0 # Atau ambil dari config jika simulasi punya starting balance
            DAILY_STATS["current_balance"] = 0.0


    def set_whale_detector(self, detector):
        self.whale_detector = detector

    def send_notification(self, message, keyboard=None):
        if not self.telegram_bot:
            logger.warning("Cannot send notification: Telegram bot not initialized")
            return
        
        if not hasattr(self.telegram_bot, 'admin_chat_ids') or not self.telegram_bot.admin_chat_ids:
            logger.warning("Cannot send notification: No admin chat IDs available")
            return
        
        try:
            self.notification_queue.put((message, keyboard))
        except Exception as e:
            logger.error(f"Error queueing notification: {e}")

# Di dalam kelas TradingBot

    def process_notification_queue(self):
        logger.info("Starting notification queue processor thread")
        
        # Dapatkan loop PTB dari TelegramBotHandler.
        # Ini harus loop tempat Application.run_polling() berjalan.
        ptb_event_loop = None
        if self.telegram_bot and hasattr(self.telegram_bot, 'application') and \
           self.telegram_bot.application and hasattr(self.telegram_bot.application, 'bot') and \
           self.telegram_bot.application.bot and hasattr(self.telegram_bot.application.bot, 'loop'):
            ptb_event_loop = self.telegram_bot.application.bot.loop
        else:
            logger.warning("PTB event loop not accessible at notification thread start. Will try to get it later or use fallback.")

        while True:
            try:
                item = self.notification_queue.get(block=True)
                if item is None: 
                    logger.info("Notification queue processor received stop signal.")
                    self.notification_queue.task_done()
                    break 
                
                message, keyboard = item
                logger.debug(f"Processing notification from queue: {message[:30]}...")

                if not self.telegram_bot or not hasattr(self.telegram_bot, 'application') or \
                   not self.telegram_bot.application or \
                   not hasattr(self.telegram_bot.application, 'bot') or not self.telegram_bot.application.bot or \
                   not hasattr(self.telegram_bot, 'admin_chat_ids') or not self.telegram_bot.admin_chat_ids:
                    logger.error("Cannot send notification: Telegram bot/application/bot object/admin_chat_ids not fully initialized")
                    self.notification_queue.task_done()
                    time.sleep(1)
                    continue
                
                # Coba lagi dapatkan loop jika belum ada (mungkin bot baru terinisialisasi penuh)
                if ptb_event_loop is None and hasattr(self.telegram_bot.application.bot, 'loop'):
                    ptb_event_loop = self.telegram_bot.application.bot.loop
                    if ptb_event_loop:
                        logger.info("PTB event loop acquired for notifications.")

                for chat_id in self.telegram_bot.admin_chat_ids:
                    coro_sent_async = False
                    if ptb_event_loop: # Hanya coba asyncio jika loopnya ada
                        try:
                            coro = None
                            if keyboard:
                                coro = self.telegram_bot.application.bot.send_message(
                                    chat_id=chat_id,
                                    text=message,
                                    reply_markup=InlineKeyboardMarkup(keyboard)
                                )
                            else:
                                coro = self.telegram_bot.application.bot.send_message(
                                    chat_id=chat_id,
                                    text=message
                                )
                            
                            future = asyncio.run_coroutine_threadsafe(coro, ptb_event_loop)
                            future.result(timeout=20) # Tambah timeout sedikit
                            logger.debug(f"Sent notification to {chat_id} via asyncio.")
                            coro_sent_async = True
                        except asyncio.TimeoutError:
                            logger.error(f"Timeout sending notification to {chat_id} via asyncio. Trying fallback...")
                        except Exception as e:
                            logger.error(f"Failed to send notification to {chat_id} via asyncio: {type(e).__name__} - {e}. Trying fallback...", exc_info=False)
                    else:
                        logger.debug("PTB event loop not available for asyncio send, proceeding to fallback.")

                    if not coro_sent_async: # Jika asyncio gagal atau loop tidak ada
                        try:
                            logger.info(f"Using fallback requests to send notification to {chat_id}.")
                            token = self.telegram_bot.token
                            url = f"https://api.telegram.org/bot{token}/sendMessage"
                            payload = {'chat_id': chat_id, 'text': message, 'parse_mode': 'HTML'}
                            if keyboard:
                                keyboard_json = [[{'text': btn.text, 'callback_data': btn.callback_data} for btn in row] for row in keyboard]
                                payload['reply_markup'] = json.dumps({'inline_keyboard': keyboard_json})
                            
                            response = requests.post(url, json=payload, timeout=15) # Tambah timeout
                            if response.status_code == 200:
                                logger.info(f"Sent notification to {chat_id} using fallback requests.")
                            else:
                                logger.error(f"Fallback requests failed for {chat_id}: {response.status_code} - {response.text}")
                        except Exception as e_fallback:
                             logger.error(f"Fallback requests method also failed for {chat_id}: {e_fallback}", exc_info=True)

                self.notification_queue.task_done()
                time.sleep(0.25) # Sedikit delay antar notifikasi batch

            except Exception as e:
                logger.error(f"Error in notification_queue processing (outer loop): {e}", exc_info=True)
                if 'item' in locals() and item is not None: # Pastikan item ada sebelum task_done
                    try:
                        self.notification_queue.task_done()
                    except ValueError: # Jika task_done sudah dipanggil karena error sebelumnya
                        pass
                time.sleep(5) 
        logger.info("Notification queue processor thread finished.")


    # ==================== PERBAIKAN DI SINI (TradingBot.start_trading) ====================
    def start_trading(self):
        """Start the trading loop in a separate thread"""
        if not self.running:
            # Force mock_mode off if real_trading is on
            if self.config.get("use_real_trading", False):
                logger.info("Real trading is enabled. Forcing mock_mode to False for critical operations.")
                self.config["mock_mode"] = False
                if self.market_analyzer:
                    self.market_analyzer.config["mock_mode"] = False # Pastikan MarketAnalyzer juga tahu
                if self.whale_detector: 
                     self.whale_detector.config["mock_mode"] = False # Dan WhaleDetector

            self.running = True
            self.apply_trading_mode_settings() # Terapkan mode sebelum memulai thread
            if self.market_analyzer: self.market_analyzer.start_updating()

            self.trading_thread = threading.Thread(target=self.trading_loop)
            self.trading_thread.daemon = True
            self.trading_thread.start()

            self.trade_monitor_thread = threading.Thread(target=self.monitor_trades_loop)
            self.trade_monitor_thread.daemon = True
            self.trade_monitor_thread.start()
            
            if self.notification_thread is None or not self.notification_thread.is_alive():
                self.notification_thread = threading.Thread(target=self.process_notification_queue)
                self.notification_thread.daemon = True
                self.notification_thread.start()

            if self.config.get("whale_detection", False) and self.whale_detector:
                self.whale_detector.start_detection()

            self.reset_daily_stats() # Reset statistik harian saat memulai
            logger.info(f"Trading bot started. Real Trading: {self.config.get('use_real_trading')}, Mock Mode: {self.config.get('mock_mode')}")
            return True
        logger.info("Trading bot is already running or failed to start.")
        return False
    # ==================== AKHIR PERBAIKAN (TradingBot.start_trading) ====================

    def stop_trading(self):
        if self.running:
            self.running = False 

            if self.market_analyzer: self.market_analyzer.stop_updating()
            if self.whale_detector: self.whale_detector.stop_detection()

            if self.trading_thread and self.trading_thread.is_alive():
                self.trading_thread.join(timeout=5.0)
            if self.trade_monitor_thread and self.trade_monitor_thread.is_alive():
                self.trade_monitor_thread.join(timeout=5.0)
            
            if self.notification_thread and self.notification_thread.is_alive():
                try:
                    self.notification_queue.put(None) # Sentinel value untuk menghentikan thread
                    self.notification_thread.join(timeout=5.0)
                except Exception as e:
                    logger.error(f"Error stopping notification thread: {e}")

            logger.info("Trading bot stopped.")
            return True
        logger.info("Trading bot is already stopped.")
        return False


    def apply_trading_mode_settings(self):
        mode = self.config.get("trading_mode", "safe") # Default ke 'safe' jika tidak ada
        if mode in TRADING_MODES:
            mode_settings = TRADING_MODES[mode]
            self.config.update({
                "take_profit": mode_settings["take_profit"],
                "stop_loss": mode_settings["stop_loss"],
                "max_trade_time": mode_settings["max_trade_time"],
                "min_volume": mode_settings.get("volume_threshold", self.config.get("min_volume")), 
                "min_price_change": mode_settings.get("price_change_threshold", self.config.get("min_price_change")),
                "max_concurrent_trades": mode_settings["max_trades"]
            })
            logger.info(f"Applied '{mode}' trading mode settings.")
        else:
            logger.warning(f"Trading mode '{mode}' not found. Using current/default settings.")


    def _format_auto_trade_notification(self, trade, selection_detail_text):
        bnb_amount = trade.get('bnb_value_of_trade', 0) # Menggunakan key yang lebih deskriptif
        
        real_trade_status = "No (Simulation)"
        if trade.get('order_id'): # Jika ada order_id, berarti percobaan real trade dilakukan
            if trade.get('real_trade_filled'): # Jika berhasil diisi
                real_trade_status = f"Yes (Order ID: {trade['order_id']}, Filled)"
            elif trade.get('real_trade_opened'): # Jika order dibuka tapi belum tentu terisi (misal LIMIT)
                 real_trade_status = f"Yes (Order ID: {trade['order_id']}, Opened)"
            else: # Jika order_id ada tapi real_trade_filled/opened False, berarti gagal
                 real_trade_status = f"Yes (Order ID: {trade['order_id']}, FAILED on Binance)"
        elif self.config.get("use_real_trading") and not trade.get('order_id'): # Real trading aktif tapi tidak ada order_id
             real_trade_status = "Yes (Attempted, FAILED Pre-Binance)"


        return (
            f"🚀 NEW AUTO-SELECTED TRADE\n\n"
            f"Pair: {trade['pair']}\n"
            f"Type: {trade['type']}\n"
            f"Entry Price: ${trade['entry_price']:.6f}\n"
            f"Amount: {trade['amount']:.8f} {trade['base_asset']}\n" 
            f"BNB Value: {bnb_amount:.6f} BNB (approx)\n" # Presisi lebih untuk BNB value
            f"Take Profit: ${trade['take_profit']:.6f}\n"
            f"Stop Loss: ${trade['stop_loss']:.6f}\n"
            f"Max Time: {trade['max_time_seconds']} seconds\n"
            f"Time: {trade['entry_time']}\n"
            f"Mode: {self.config.get('trading_mode','N/A').capitalize()}\n"
            f"Selection: Auto ({selection_detail_text})\n"
            f"Real Trade: {real_trade_status}"
        )

    def check_daily_limits(self):
        if DAILY_STATS["starting_balance"] > 0 and self.config.get("use_real_trading"): 
            current_profit_pct = (DAILY_STATS["current_balance"] - DAILY_STATS["starting_balance"]) / DAILY_STATS["starting_balance"] * 100
            
            profit_target = self.config.get("daily_profit_target", 10.0)
            loss_limit = self.config.get("daily_loss_limit", 5.0)

            if current_profit_pct >= profit_target:
                logger.info(f"Daily profit target reached: {current_profit_pct:.2f}% >= {profit_target}%")
                self.send_notification(
                    f"🎉 DAILY PROFIT TARGET REACHED!\n\n"
                    f"Current profit: {current_profit_pct:.2f}%\nTarget: {profit_target}%\n\n"
                    f"Trading will be paused for today. Use /starttrade to resume."
                )
                return False 
            
            if current_profit_pct <= -loss_limit:
                logger.info(f"Daily loss limit reached: {current_profit_pct:.2f}% <= -{loss_limit}%")
                self.send_notification(
                    f"⚠️ DAILY LOSS LIMIT REACHED!\n\n"
                    f"Current loss: {current_profit_pct:.2f}%\nLimit: -{loss_limit}%\n\n"
                    f"Trading will be paused for today. Use /starttrade to resume."
                )
                return False 
        
        return True 


    # ==================== PERBAIKAN DI SINI (TradingBot.trading_loop) ====================
    def trading_loop(self):
        """Main trading loop - this is where the trading logic would go"""
        while self.running:
            try:
                if not self.config.get("trading_enabled", False):
                    time.sleep(5)
                    continue

                if not self.check_daily_limits():
                    logger.info("Daily limits reached. Disabling auto-trading for today.")
                    self.config["trading_enabled"] = False 
                    time.sleep(3600) # Tunggu 1 jam sebelum cek lagi, atau sampai di-enable manual
                    continue

                active_trades_count = sum(1 for t in ACTIVE_TRADES if not t.get('completed', False))
                if active_trades_count >= self.config.get("max_concurrent_trades", 3):
                    # logger.debug(f"Max concurrent trades ({active_trades_count}) reached.")
                    time.sleep(3) # Cek lebih sering jika sudah max
                    continue

                if self.config.get("auto_select_pairs", True) and self.market_analyzer:
                    best_pairs = self.market_analyzer.get_best_trading_pairs(
                        min_volume=self.config.get("min_volume"),
                        min_price_change=self.config.get("min_price_change"),
                        limit=3 
                    )

                    if best_pairs:
                        selected_pair_data = random.choice(best_pairs)
                        pair_name = selected_pair_data["pair"]
                        
                        # PENGECEKAN DOUBLE TRADE (untuk pair yang sama)
                        is_pair_already_active = any(
                            trade['pair'] == pair_name and not trade.get('completed', False)
                            for trade in ACTIVE_TRADES
                        )
                        if is_pair_already_active:
                            logger.debug(f"Skipping new auto-trade for {pair_name}: already has an active trade.")
                            time.sleep(1) 
                            continue # Lanjut ke iterasi berikutnya di loop `while self.running`

                        trade_type = "BUY" if selected_pair_data.get("price_change",0) > 0 else "SELL"

                        if random.random() < 0.3 : # 30% chance, sesuaikan
                            logger.info(f"Attempting to auto-create trade for {pair_name} type {trade_type}")
                            trade = self.create_trade(pair_name, trade_type, selected_pair_data.get("last_price"))
                            if trade: 
                                selection_details = f"Vol: {selected_pair_data.get('quote_volume', selected_pair_data.get('volume',0)):.2f}, Chg: {selected_pair_data.get('price_change',0):.2f}%"
                                entry_message = self._format_auto_trade_notification(trade, selection_details)
                                self.send_notification(entry_message)
                            else:
                                # create_trade sudah mengirim notifikasi jika gagal karena saldo/API
                                logger.warning(f"Failed to create trade object for {pair_name} (e.g., insufficient balance, API error, or pre-check fail).")
                time.sleep(random.uniform(4,7)) # Randomize sleep to avoid thundering herd
            except Exception as e:
                logger.error(f"Error in trading loop: {e}", exc_info=True)
                time.sleep(10)
    # ==================== AKHIR PERBAIKAN (TradingBot.trading_loop) ====================


    def monitor_trades_loop(self):
        while self.running:
            try:
                current_active_trades = [t for t in ACTIVE_TRADES if not t.get('completed', False)]

                for trade in current_active_trades:
                    current_time = time.time()
                    trade_duration = current_time - trade.get('timestamp', current_time) 
                    
                    current_price = None
                    # Jika trade real dan terisi, prioritas harga dari API
                    if trade.get('real_trade_filled') and self.binance_api and self.config.get("use_real_trading"):
                        current_price = self.binance_api.get_ticker_price(trade['pair'])
                        if current_price is None: 
                            logger.warning(f"Failed to get real price for {trade['pair']} (real trade), falling back to simulated.")
                            current_price = self.simulate_price_movement(trade) 
                    else: # Trade simulasi atau real tapi tidak terisi/gagal
                        current_price = self.simulate_price_movement(trade)

                    if current_price is None: 
                        logger.error(f"Could not determine current price for trade {trade.get('id')}, skipping monitor.")
                        continue

                    tp_hit = False
                    sl_hit = False
                    if trade['type'] == "BUY":
                        if current_price >= trade['take_profit']: tp_hit = True
                        elif current_price <= trade['stop_loss']: sl_hit = True
                    else:  # SELL
                        if current_price <= trade['take_profit']: tp_hit = True
                        elif current_price >= trade['stop_loss']: sl_hit = True
                    
                    time_limit_reached = trade_duration >= trade.get('max_time_seconds', 300)

                    if tp_hit:
                        self.complete_trade(trade, current_price, reason="take_profit")
                    elif sl_hit:
                        self.complete_trade(trade, current_price, reason="stop_loss")
                    elif time_limit_reached:
                        self.complete_trade(trade, current_price, reason="time_limit")

                time.sleep(1) # Cek setiap detik
            except Exception as e:
                logger.error(f"Error in trade monitor loop: {e}", exc_info=True)
                time.sleep(5)

    def simulate_price_movement(self, trade):
        elapsed_time = time.time() - trade.get('timestamp', time.time())
        max_time = trade.get('max_time_seconds', 300)
        if max_time == 0: max_time = 300 
        time_factor = min(elapsed_time / max_time, 1.0)
        
        mode_volatility_factor = {"conservative_scalp": 0.7, "consistent_drip": 0.8, "balanced_growth": 1.0, "momentum_rider": 1.2}
        vol_factor = mode_volatility_factor.get(trade.get('mode', 'balanced_growth'), 1.0)

        # Mengurangi pergerakan simulasi agar lebih realistis untuk TP/SL kecil
        max_movement_pct_base = 1.5 # Base max % pergerakan untuk seluruh durasi trade
        max_movement_pct = max_movement_pct_base * time_factor * vol_factor
        
        movement_pct = random.uniform(-max_movement_pct, max_movement_pct)
        current_price = trade.get('entry_price',0) * (1 + movement_pct / 100)
        return max(0.00000001, current_price) 


    # ==================== PERBAIKAN DI SINI (TradingBot.create_trade) ====================
    def create_trade(self, pair, trade_type, current_price=None):
        """Create a trade for a specific pair, considering balance and MIN_NOTIONAL."""
        if "BNB" in pair:
            base_asset, quote_asset = (pair[:-3], pair[-3:]) if pair.endswith("BNB") else (pair[:3], pair[3:])
        else: # Non-BNB pair
            if len(pair) >= 6 :
                 base_asset, quote_asset = pair[:3], pair[3:]
                 if len(pair) > 7 and pair[-4:] in ["USDT", "BUSD", "USDC", "FDUSD"]: # Handle leveraged tokens like BTCUPUSDT
                     base_asset, quote_asset = pair[:-4], pair[-4:]
            else:
                logger.warning(f"Cannot reliably determine base/quote for non-standard pair {pair}. Defaulting.")
                # Fallback, mungkin tidak akurat
                base_asset, quote_asset = pair[:3], pair[3:] if len(pair) > 3 else (pair, "UNKNOWN")


        if current_price is None and self.market_analyzer:
            pair_data = self.market_analyzer.get_pair_data(pair)
            current_price = pair_data["last_price"] if pair_data and pair_data.get("last_price", 0) > 0 else None
        
        if current_price is None or current_price <= 0:
            logger.error(f"Invalid current_price ({current_price}) for {pair}. Cannot create trade.")
            self.send_notification(f"⚠️ Trade Gagal: Harga tidak valid untuk {pair} ({current_price}).")
            return None

        # Tentukan jumlah BNB yang akan diinvestasikan
        # Default: menggunakan CONFIG['amount'] sebagai jumlah BNB untuk diinvestasikan
        # Jika use_percentage: hitung persentase dari saldo BNB
        # Nilai ini kemudian akan dikonversi ke kuantitas base asset.
        
        # Ambil nilai BNB minimum per trade dari config
        min_bnb_value_per_trade = self.config.get('min_bnb_per_trade', 0.011) # Default ke ~5-6 USD

        bnb_to_invest_calculated = self.config.get('amount', 0.01) # Default jika tidak pakai persentase

        if self.config.get('use_percentage', False) and self.binance_api and self.config.get('use_real_trading', False):
            try:
                account_info = self.binance_api.get_account_info()
                if account_info and 'balances' in account_info:
                    bnb_balance_free = next((float(bal['free']) for bal in account_info['balances'] if bal['asset'] == 'BNB'), 0)
                    if bnb_balance_free > 0:
                        perc_amount_bnb = bnb_balance_free * (self.config.get('trade_percentage', 5.0) / 100.0)
                        # Gunakan hasil persentase, tapi tidak kurang dari min_bnb_value_per_trade
                        bnb_to_invest_calculated = max(min_bnb_value_per_trade, perc_amount_bnb)
                        logger.info(f"Percentage trade: {self.config.get('trade_percentage', 5.0)}% of {bnb_balance_free:.6f} BNB = {perc_amount_bnb:.6f} BNB. Adjusted to invest: {bnb_to_invest_calculated:.6f} BNB.")
                    else:
                        logger.warning("BNB balance is 0 for percentage trade. Falling back to fixed amount check.")
                        # Fallback ke fixed amount, yang juga akan dicek saldonya nanti
                        bnb_to_invest_calculated = max(min_bnb_value_per_trade, self.config.get('amount', 0.01))
                else:
                    logger.warning("Failed to get account info for percentage trade. Falling back to fixed amount.")
                    bnb_to_invest_calculated = max(min_bnb_value_per_trade, self.config.get('amount', 0.01))
            except Exception as e:
                logger.error(f"Error calculating percentage-based trade amount: {e}. Falling back to fixed.")
                bnb_to_invest_calculated = max(min_bnb_value_per_trade, self.config.get('amount', 0.01))
        else: # Tidak pakai persentase atau bukan real trading
            bnb_to_invest_calculated = max(min_bnb_value_per_trade, self.config.get('amount', 0.01))


        # Pemeriksaan saldo akhir (khusus real trading)
        if self.config.get('use_real_trading', False) and self.binance_api:
            account_info_final_check = self.binance_api.get_account_info()
            bnb_available_real = 0
            if account_info_final_check and 'balances' in account_info_final_check:
                bnb_available_real = next((float(bal['free']) for bal in account_info_final_check['balances'] if bal['asset'] == 'BNB'), 0)
            
            if bnb_to_invest_calculated > bnb_available_real:
                err_msg = (f"Insufficient BNB balance for trade on {pair}. "
                           f"Need: {bnb_to_invest_calculated:.8f} BNB, Available: {bnb_available_real:.8f} BNB.")
                logger.error(err_msg)
                self.send_notification(f"⚠️ Trade Gagal: {err_msg}")
                return None # Gagal karena saldo tidak cukup

        # Hitung kuantitas base asset
        trade_quantity = 0
        actual_bnb_value_of_trade = bnb_to_invest_calculated # Ini adalah nilai BNB yang ingin dipertaruhkan

        if quote_asset == 'BNB': # e.g., SOLBNB. `actual_bnb_value_of_trade` adalah jumlah BNB untuk membeli SOL.
            trade_quantity = actual_bnb_value_of_trade / current_price # Kuantitas SOL
        elif base_asset == 'BNB': # e.g., BNBUSDT. `actual_bnb_value_of_trade` adalah kuantitas BNB.
            trade_quantity = actual_bnb_value_of_trade # Kuantitas BNB
        else: # Pair non-BNB (e.g. ETHBTC). Ini lebih kompleks.
              # Asumsikan `actual_bnb_value_of_trade` adalah nilai setara BNB dari trade.
              # Kita perlu harga base_asset dalam BNB. (misal ETH/BNB price).
              # Untuk simplifikasi: jika bukan pair BNB langsung, `CONFIG['amount']` dianggap sebagai kuantitas base asset.
              # Ini berarti untuk pair non-BNB, `use_percentage` dan `min_bnb_per_trade` tidak berlaku langsung.
            logger.warning(f"Pair {pair} is not a direct BNB pair. Amount logic based on `CONFIG['amount']` as base asset quantity.")
            trade_quantity = self.config.get('amount', 0.01) # Ini kuantitas base asset (misal ETH)
            # Perkirakan nilai BNB trade ini: (membutuhkan harga BASE/BNB) - abaikan untuk sekarang jika terlalu rumit
            # actual_bnb_value_of_trade = ... (perlu logic tambahan)
            # Untuk sementara, set ke 0 atau nilai default jika tidak bisa dihitung
            actual_bnb_value_of_trade = 0 # Karena kita tidak tahu harga BASE/BNB nya dengan mudah

        if trade_quantity <= 0:
            logger.error(f"Calculated trade quantity is zero or negative ({trade_quantity}) for {pair}. "
                         f"BNB to invest: {bnb_to_invest_calculated}, Price: {current_price}")
            return None

        # --- Persiapan untuk membuat trade object ---
        take_profit_pct = self.config.get("take_profit", 1.5)
        stop_loss_pct = self.config.get("stop_loss", 5.0)
        entry_price_for_calc = current_price 
        
        tp_price = entry_price_for_calc * (1 + take_profit_pct / 100) if trade_type == "BUY" else entry_price_for_calc * (1 - take_profit_pct / 100)
        sl_price = entry_price_for_calc * (1 - stop_loss_pct / 100) if trade_type == "BUY" else entry_price_for_calc * (1 + stop_loss_pct / 100)

        trade = {
            'id': int(time.time() * 1000), 
            'timestamp': time.time(), 'pair': pair, 'base_asset': base_asset, 'quote_asset': quote_asset,
            'type': trade_type, 
            'entry_price': entry_price_for_calc, # Akan diupdate jika real trade market order terisi
            'amount': trade_quantity, # Akan diupdate jika real trade market order terisi (partial fill)
            'bnb_value_of_trade': actual_bnb_value_of_trade, 
            'take_profit': tp_price, 'stop_loss': sl_price,
            'max_time_seconds': self.config.get('max_trade_time',300),
            'entry_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'completed': False, 'mode': self.config.get('trading_mode','N/A'),
            'order_id': None, 
            'real_trade_opened': False, # True jika order berhasil dikirim ke Binance
            'real_trade_filled': False, # True jika order terisi (status FILLED)
            'strategy': 'Standard Auto-Selected',
            'percentage_based': self.config.get('use_percentage', False)
        }

        # --- Eksekusi Real Trade di Binance (jika diaktifkan) ---
        if self.binance_api and self.config.get("use_real_trading", False):
            logger.info(f"Attempting to create REAL order on Binance: {pair} {trade_type} Qty: {trade_quantity:.8f}")
            # TODO: Sebelum mengirim order, format `trade_quantity` sesuai `LOT_SIZE` (stepSize) dari exchangeInfo.
            # TODO: Periksa juga `MIN_NOTIONAL` (trade_quantity * current_price >= min_notional_value).
            # Untuk sekarang, kita coba langsung. Jika gagal, Binance akan return error.

            order_response = self.binance_api.create_order(
                symbol=pair, side=trade_type, order_type="MARKET", quantity=trade_quantity
            )

            if order_response and order_response.get('orderId'):
                trade['order_id'] = order_response['orderId']
                trade['real_trade_opened'] = True # Order berhasil dikirim
                logger.info(f"SUCCESS: Real trade order PLACED on Binance. Order ID: {order_response['orderId']}, "
                            f"Pair: {pair}, Type: {trade_type}, Status: {order_response.get('status')}")
                
                # Update entry_price dan amount dengan data dari order MARKET yang terisi
                if order_response.get('status') == 'FILLED':
                    trade['real_trade_filled'] = True
                    avg_executed_price = 0
                    total_qty_filled = 0

                    if order_response.get('fills') and len(order_response['fills']) > 0:
                        total_value = sum(float(f['price']) * float(f['qty']) for f in order_response['fills'])
                        total_qty_filled = sum(float(f['qty']) for f in order_response['fills'])
                        if total_qty_filled > 0:
                            avg_executed_price = total_value / total_qty_filled
                    # Beberapa respons MARKET order mungkin hanya punya 'price' dan 'executedQty'
                    elif float(order_response.get('price', 0)) > 0 and float(order_response.get('executedQty', 0)) > 0:
                        avg_executed_price = float(order_response.get('price'))
                        total_qty_filled = float(order_response.get('executedQty'))
                    
                    if avg_executed_price > 0 and total_qty_filled > 0:
                        logger.info(f"Updating entry_price from {trade['entry_price']:.6f} to actual avg executed price {avg_executed_price:.6f} for order {trade['order_id']}")
                        logger.info(f"Updating amount from {trade['amount']:.8f} to actual filled quantity {total_qty_filled:.8f}")
                        trade['entry_price'] = avg_executed_price
                        trade['amount'] = total_qty_filled # Update dengan kuantitas yang benar-benar terisi
                        # Hitung ulang TP/SL berdasarkan harga masuk aktual
                        trade['take_profit'] = avg_executed_price * (1 + take_profit_pct / 100) if trade_type == "BUY" else avg_executed_price * (1 - take_profit_pct / 100)
                        trade['stop_loss'] = avg_executed_price * (1 - stop_loss_pct / 100) if trade_type == "BUY" else avg_executed_price * (1 + stop_loss_pct / 100)
                else: # Status order bukan FILLED (misal NEW, PARTIALLY_FILLED, EXPIRED, CANCELED, REJECTED)
                    logger.warning(f"Real trade order {trade['order_id']} status is {order_response.get('status')}. Not updating entry price/amount from fills.")
                    # Jika REJECTED, idealnya trade ini tidak dianggap aktif
                    if order_response.get('status') == 'REJECTED':
                        trade['real_trade_opened'] = False # Tandai sebagai gagal dibuka
                        # Kirim notifikasi
                        self.send_notification(
                            f"⚠️ REAL TRADE REJECTED BY BINANCE\n"
                            f"Pair: {pair}, Type: {trade_type}, Qty: {trade_quantity:.8f}\n"
                            f"Order ID: {trade['order_id']}\n"
                            f"Reason: {order_response.get('code', '')} {order_response.get('msg', 'Check Binance for details.')}"
                        )
                        # Kita bisa return None di sini agar trade yang direject tidak masuk ACTIVE_TRADES
                        # atau biarkan masuk tapi dengan status 'real_trade_opened = False'
                        # return None # Opsi: batalkan pembuatan trade object jika direject

            else: # Pembuatan order gagal di level API Binance (misal -2010 Insufficient balance)
                err_code = order_response.get('code', 'N/A') if isinstance(order_response, dict) else 'N/A'
                err_msg_api = order_response.get('msg', str(order_response)) if isinstance(order_response, dict) else str(order_response)
                
                logger.error(f"FAILED to create real trade order on Binance: {pair} {trade_type}. "
                             f"API Code: {err_code}, Message: {err_msg_api}")
                self.send_notification(
                    f"⚠️ REAL TRADE FAILED TO OPEN\n"
                    f"Pair: {pair}, Type: {trade_type}, Qty: {trade_quantity:.8f}\n"
                    f"Reason: Binance API Error (Code: {err_code}). Message: {err_msg_api[:100]}"
                )
                # Jika gagal di API, trade ini tidak real. Mungkin return None agar tidak disimulasikan.
                # Untuk sekarang, trade object tetap dibuat, tapi 'real_trade_opened' dan 'real_trade_filled' akan False.
                # return None # Opsi: batalkan pembuatan trade object jika API error

        else: # Bukan real trading atau API tidak tersedia
            if self.config.get("use_real_trading", False) and not self.binance_api:
                logger.warning("Real trading intended but Binance API not available/configured.")
            # trade['real_trade_opened'] dan 'real_trade_filled' tetap False

        # Jika trade adalah real trade tetapi gagal dibuka atau tidak terisi,
        # kita mungkin tidak mau menambahkannya ke ACTIVE_TRADES.
        # Untuk sekarang, kita tambahkan semua, dan status `real_trade_opened/filled` akan menunjukkan apa yang terjadi.
        ACTIVE_TRADES.append(trade)
        return trade
    # ==================== AKHIR PERBAIKAN (TradingBot.create_trade) ====================


    def create_trade_from_whale(self, whale_transaction, trade_type, is_auto_trade=False):
        pair = whale_transaction['token']
        current_price = whale_transaction['price']
        
        if current_price <= 0:
            logger.warning(f"Whale transaction for {pair} has invalid price {current_price}. Cannot create trade.")
            return None

        trade = self.create_trade(pair, trade_type, current_price)
        if not trade: 
            return None

        trade['whale_id'] = whale_transaction['id']
        trade['strategy'] = f"Whale-Based ({self.config.get('trading_strategy','N/A')})"
        
        if is_auto_trade:
            selection_details = f"Whale Alert ID: {whale_transaction['id']}"
            entry_message = self._format_auto_trade_notification(trade, selection_details)
        else: # Manual follow
            real_trade_status = "No (Simulation)"
            if trade.get('order_id'):
                if trade.get('real_trade_filled'): real_trade_status = f"Yes (Order ID: {trade['order_id']}, Filled)"
                elif trade.get('real_trade_opened'): real_trade_status = f"Yes (Order ID: {trade['order_id']}, Opened)"
                else: real_trade_status = f"Yes (Order ID: {trade['order_id']}, FAILED on Binance)"
            elif self.config.get("use_real_trading"): real_trade_status = "Yes (Attempted, FAILED Pre-Binance)"
            
            entry_message = (
                f"🐋 NEW WHALE-BASED TRADE (Manual Follow)\n\n"
                f"Pair: {trade['pair']}\nType: {trade['type']}\n"
                f"Entry Price: ${trade['entry_price']:.6f}\n"
                f"Amount: {trade['amount']:.8f} {trade['base_asset']}\n"
                f"BNB Value: {trade.get('bnb_value_of_trade', 0):.6f} BNB\n"
                f"Take Profit: ${trade['take_profit']:.6f}\nStop Loss: ${trade['stop_loss']:.6f}\n"
                f"Time: {trade['entry_time']}\nMode: {trade.get('mode', 'N/A').capitalize()}\n"
                f"Strategy: {trade['strategy']}\n"
                f"Real Trade: {real_trade_status}"
            )
        self.send_notification(entry_message)
        return trade

    # ==================== PERBAIKAN DI SINI (TradingBot.complete_trade) ====================
    def complete_trade(self, trade, exit_price=None, reason="unknown"):
        """Complete a trade with a result, handling real trade closure on Binance."""
        if trade.get('completed', False): 
            return

        # Tentukan harga keluar jika tidak disediakan
        # Ini adalah harga estimasi jika trade real gagal ditutup atau jika simulasi
        estimated_exit_price = exit_price 
        if estimated_exit_price is None:
            if reason == "take_profit": estimated_exit_price = trade['take_profit']
            elif reason == "stop_loss": estimated_exit_price = trade['stop_loss']
            else: # time_limit, unknown, atau perlu harga pasar saat ini
                if trade.get('real_trade_filled') and self.binance_api and self.config.get("use_real_trading"):
                    current_market_price = self.binance_api.get_ticker_price(trade['pair'])
                    estimated_exit_price = current_market_price if current_market_price else self.simulate_price_movement(trade)
                else:
                    estimated_exit_price = self.simulate_price_movement(trade)
        
        final_exit_price = estimated_exit_price # Harga yang akan digunakan untuk PnL

        # Jika ini adalah trade real yang berhasil dibuka dan terisi, coba tutup di Binance
        if trade.get('real_trade_filled') and self.binance_api and self.config.get("use_real_trading"):
            try:
                opposite_side = "SELL" if trade['type'] == "BUY" else "BUY"
                # Gunakan kuantitas yang benar-benar terisi saat membuka trade
                closing_quantity = trade['amount'] 
                logger.info(f"Attempting to CLOSE REAL trade on Binance: {trade['pair']} {opposite_side} Qty: {closing_quantity:.8f}, Original Order ID: {trade['order_id']}")

                # TODO: Format `closing_quantity` sesuai `LOT_SIZE` (stepSize)
                close_order_response = self.binance_api.create_order(
                    symbol=trade['pair'], side=opposite_side, order_type="MARKET", quantity=closing_quantity
                )

                if close_order_response and close_order_response.get('orderId'):
                    trade['close_order_id'] = close_order_response['orderId']
                    logger.info(f"SUCCESS: Real trade order for CLOSING placed. Closing Order ID: {close_order_response['orderId']}, Status: {close_order_response.get('status')}")
                    
                    if close_order_response.get('status') == 'FILLED':
                        avg_executed_exit_price = 0
                        total_qty_closed = 0
                        if close_order_response.get('fills') and len(close_order_response['fills']) > 0:
                            total_value = sum(float(f['price']) * float(f['qty']) for f in close_order_response['fills'])
                            total_qty_closed = sum(float(f['qty']) for f in close_order_response['fills'])
                            if total_qty_closed > 0: avg_executed_exit_price = total_value / total_qty_closed
                        elif float(close_order_response.get('price', 0)) > 0 and float(close_order_response.get('executedQty', 0)) > 0:
                            avg_executed_exit_price = float(close_order_response.get('price'))
                            total_qty_closed = float(close_order_response.get('executedQty'))

                        if avg_executed_exit_price > 0 and total_qty_closed > 0:
                            logger.info(f"Updating exit_price from estimated {final_exit_price:.6f} to actual avg executed exit price {avg_executed_exit_price:.6f}")
                            final_exit_price = avg_executed_exit_price # Gunakan harga keluar aktual untuk PnL
                            # Verifikasi apakah kuantitas yang ditutup sesuai dengan yang diharapkan
                            if abs(total_qty_closed - closing_quantity) > 1e-8: # Toleransi kecil
                                logger.warning(f"Partial close? Expected to close {closing_quantity:.8f}, but closed {total_qty_closed:.8f} for order {trade['close_order_id']}")
                        else:
                             logger.warning(f"Closing order {trade['close_order_id']} FILLED but no valid price/qty data. PnL will use estimated price.")
                    else: # Status bukan FILLED (misal EXPIRED, CANCELED - tidak mungkin untuk MARKET order, tapi REJECTED bisa)
                        logger.error(f"Closing order {trade['close_order_id']} for {trade['pair']} status is {close_order_response.get('status')}. PnL will use estimated price.")
                else: # Gagal membuat order penutupan
                    err_code_close = close_order_response.get('code', 'N/A') if isinstance(close_order_response, dict) else 'N/A'
                    err_msg_close = close_order_response.get('msg', str(close_order_response)) if isinstance(close_order_response, dict) else str(close_order_response)
                    logger.error(f"FAILED to create closing order for real trade on Binance: {trade['pair']} {opposite_side}. "
                                 f"API Code: {err_code_close}, Msg: {err_msg_close}. PnL will use estimated exit price: {final_exit_price:.6f}")
            except Exception as e_close:
                logger.error(f"EXCEPTION during real trade closing: {e_close}. PnL will use estimated exit price.", exc_info=True)
        
        # Hitung P&L berdasarkan entry_price (yang mungkin sudah diupdate dari order pembukaan)
        # dan final_exit_price (yang mungkin sudah diupdate dari order penutupan)
        result_pct = 0
        if trade['entry_price'] > 0: 
            result_pct = ((final_exit_price - trade['entry_price']) / trade['entry_price']) * 100 if trade['type'] == "BUY" else \
                         ((trade['entry_price'] - final_exit_price) / trade['entry_price']) * 100
        
        profit_in_bnb = 0.0
        # PnL dalam BNB hanya relevan jika BNB adalah quote asset atau base asset yang diperdagangkan
        if trade['quote_asset'] == 'BNB': # e.g. SOLBNB. Profit/Loss adalah selisih harga BNB * kuantitas SOL.
             profit_in_bnb = (final_exit_price - trade['entry_price']) * trade['amount'] if trade['type'] == "BUY" else \
                             (trade['entry_price'] - final_exit_price) * trade['amount']
        elif trade['base_asset'] == 'BNB': # e.g. BNBUSDT. Profit/Loss adalah % PnL * jumlah BNB yang ditrade.
            profit_in_bnb = (result_pct / 100.0) * trade['amount'] # 'amount' di sini adalah kuantitas BNB
        # else: Untuk pair non-BNB, profit_in_bnb lebih rumit atau tidak dihitung.

        trade.update({
            'completed': True, 'exit_price': final_exit_price, 
            'exit_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'result': result_pct, 'close_reason': reason, 'profit_in_bnb': profit_in_bnb
        })

        # Update statistik harian
        DAILY_STATS["total_trades"] += 1
        DAILY_STATS["total_profit_pct"] += result_pct
        DAILY_STATS["total_profit_bnb"] += profit_in_bnb
        if result_pct > 0: DAILY_STATS["winning_trades"] += 1
        else: DAILY_STATS["losing_trades"] += 1
        
        # Update saldo BNB saat ini jika ini adalah trade real
        if (trade.get('real_trade_filled') or (trade.get('close_order_id') and trade.get('real_trade_opened'))) and \
           self.config.get("use_real_trading") and DAILY_STATS["current_balance"] is not None:
            DAILY_STATS["current_balance"] += profit_in_bnb


        is_win = result_pct > 0
        result_text = "WIN" if is_win else "LOSS"
        emoji = "✅" if is_win else "❌"
        reason_map = {"take_profit": "Take Profit Hit", "stop_loss": "Stop Loss Hit", 
                      "time_limit": "Time Limit Reached", "unknown": "Manual/Other"}
        reason_text = reason_map.get(reason, reason.capitalize())
        
        # Status Real Trade untuk notifikasi
        real_trade_status_text = "No (Simulation)"
        if trade.get('order_id'): # Ada percobaan order pembukaan
            if trade.get('real_trade_filled'):
                 real_trade_status_text = f"Yes (Entry ID: {trade['order_id']} FILLED"
                 if trade.get('close_order_id'):
                     real_trade_status_text += f", Exit ID: {trade['close_order_id']} PLACED)" # Status exit bisa beda
                 else: # Gagal membuat order penutup atau tidak perlu (misal karena TP/SL simulasi)
                     real_trade_status_text += ", Exit Simulated/Failed)"
            elif trade.get('real_trade_opened'): # Dibuka tapi tidak terisi
                 real_trade_status_text = f"Yes (Entry ID: {trade['order_id']} OPENED BUT NOT FILLED, Simulated Close)"
            else: # Gagal membuka (misal reject)
                 real_trade_status_text = f"Yes (Entry ID: {trade['order_id']} FAILED TO OPEN/FILL, Simulated)"
        elif self.config.get("use_real_trading") and not trade.get('order_id'): # Real tapi gagal sebelum Binance
            real_trade_status_text = "Yes (Attempted, FAILED Pre-Binance, Simulated)"


        complete_message = (
            f"{emoji} TRADE COMPLETED - {result_text}\n\n"
            f"Pair: {trade['pair']}\nType: {trade['type']}\n"
            f"Entry Price: ${trade['entry_price']:.6f}\nExit Price: ${final_exit_price:.6f}\n"
            f"Profit/Loss: {result_pct:.2f}%\n"
            f"Profit BNB: {profit_in_bnb:.8f} BNB\n"
            f"Amount: {trade['amount']:.8f} {trade['base_asset']}\n" 
            f"Close Reason: {reason_text}\n"
            f"Entry Time: {trade['entry_time']}\nExit Time: {trade['exit_time']}\n"
            f"Duration: {int(time.time() - trade.get('timestamp', time.time()))} seconds\n"
            f"Mode: {trade.get('mode', 'N/A').capitalize()}\n"
            f"Strategy: {trade.get('strategy', 'N/A')}\n"
            f"Real Trade: {real_trade_status_text}"
        )
        self.send_notification(complete_message)

        if trade in ACTIVE_TRADES: ACTIVE_TRADES.remove(trade)
        COMPLETED_TRADES.append(trade)
    # ==================== AKHIR PERBAIKAN (TradingBot.complete_trade) ====================

    def get_daily_stats_message(self):
        win_rate = (DAILY_STATS["winning_trades"] / DAILY_STATS["total_trades"] * 100) if DAILY_STATS["total_trades"] > 0 else 0
        balance_change_pct = 0
        if DAILY_STATS.get("starting_balance",0) > 0: 
            balance_change_pct = ((DAILY_STATS.get("current_balance",0) - DAILY_STATS["starting_balance"]) / DAILY_STATS["starting_balance"]) * 100
            
        stats_message = (
            f"📊 DAILY TRADING STATS - {DAILY_STATS.get('date', 'N/A')}\n\n"
            f"Total Trades: {DAILY_STATS.get('total_trades',0)}\n"
            f"Winning Trades: {DAILY_STATS.get('winning_trades',0)}\n"
            f"Losing Trades: {DAILY_STATS.get('losing_trades',0)}\n"
            f"Win Rate: {win_rate:.1f}%\n\n"
            f"Total P/L (Simulated %): {DAILY_STATS.get('total_profit_pct',0.0):.2f}%\n" # Ini akumulasi % dari tiap trade, bukan % dari total balance
            f"Total P/L BNB (Real/Sim): {DAILY_STATS.get('total_profit_bnb',0.0):.8f} BNB\n\n"
            f"Starting Balance (BNB): {DAILY_STATS.get('starting_balance',0.0):.8f}\n"
            f"Current Balance (BNB): {DAILY_STATS.get('current_balance',0.0):.8f}\n"
            f"Balance Change (BNB): {balance_change_pct:.2f}%\n\n"
            f"Trading Mode: {self.config.get('trading_mode','N/A').capitalize()}\n"
            f"Real Trading: {'Enabled' if self.config.get('use_real_trading', False) else 'Disabled (Simulation)'}"
        )
        return stats_message

# ... (Sisa kode TelegramBotHandler dan main() tetap sama, hanya pastikan API Key/Secret di CONFIG atas diisi dengan benar atau dari variabel global) ...
# ... Pastikan juga TELEGRAM_BOT_TOKEN dan ADMIN_USER_IDS diisi.

class TelegramBotHandler:
    def __init__(self, token, admin_ids):
        self.token = token
        self.admin_user_ids = admin_ids
        self.admin_chat_ids = admin_ids.copy() # Menyimpan chat_id dinamis
        self.trading_bot = None
        self.application = Application.builder().token(token).build()
        self.register_handlers()
        logger.info(f"TelegramBotHandler initialized with admin user IDs: {self.admin_user_ids}")

    def register_handlers(self):
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("status", self.status_command))
        self.application.add_handler(CommandHandler("config", self.config_command))
        self.application.add_handler(CommandHandler("set", self.set_config_command))
        self.application.add_handler(CommandHandler("trades", self.trades_command))
        self.application.add_handler(CommandHandler("whales", self.whales_command))
        self.application.add_handler(CommandHandler("stats", self.stats_command))
        self.application.add_handler(CommandHandler("setpercentage", self.set_percentage_command))
        self.application.add_handler(CommandHandler("bnbpairs", self.bnb_pairs_command))
        self.application.add_handler(CommandHandler("whaleconfig", self.whale_config_command))
        self.application.add_handler(CommandHandler("volume", self.volume_command))
        self.application.add_handler(CommandHandler("trending", self.trending_command))
        self.application.add_handler(CommandHandler("modes", self.trading_modes_command))
        self.application.add_handler(CommandHandler("starttrade", self.start_trading_command))
        self.application.add_handler(CommandHandler("stoptrade", self.stop_trading_command))
        self.application.add_handler(CommandHandler("enablereal", self.enable_real_trading_command))
        self.application.add_handler(CommandHandler("disablereal", self.disable_real_trading_command))
        self.application.add_handler(CommandHandler("balance", self.balance_command))
        self.application.add_handler(CommandHandler("toggletestnet", self.toggle_testnet_command))
        self.application.add_handler(CallbackQueryHandler(self.button_callback))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        self.application.add_error_handler(self.error_handler)
        self.application.add_handler(CommandHandler("testapi", self.test_api_command))


    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.is_authorized(update): return
        if not self.trading_bot:
            await update.message.reply_text("Trading bot not initialized")
            return
        stats_message = self.trading_bot.get_daily_stats_message()
        await update.message.reply_text(stats_message)

    async def set_percentage_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.is_authorized(update): return
        if not self.trading_bot:
            await update.message.reply_text("Trading bot not initialized")
            return

        args = context.args
        if not args:
            current_setting = "enabled" if self.trading_bot.config.get("use_percentage") else "disabled"
            current_percentage = self.trading_bot.config.get("trade_percentage", 5.0)
            min_bnb_val = self.trading_bot.config.get("min_bnb_per_trade", 0.011)
            await update.message.reply_text(
                f"Percentage-based trading is currently {current_setting}.\n"
                f"Current percentage: {current_percentage}%\n"
                f"Min BNB value per trade (override): {min_bnb_val} BNB\n\n"
                "To enable: /setpercentage on [percentage]\n"
                "To disable: /setpercentage off\n\n"
                "Example: /setpercentage on 10"
            )
            return

        if args[0].lower() in ["on", "enable", "true", "yes"]:
            self.trading_bot.config["use_percentage"] = True
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
                f"Bot will use {self.trading_bot.config['trade_percentage']}% of available BNB balance per trade, "
                f"or min_bnb_per_trade ({self.trading_bot.config.get('min_bnb_per_trade',0.011)} BNB) if % is lower."
            )
        elif args[0].lower() in ["off", "disable", "false", "no"]:
            self.trading_bot.config["use_percentage"] = False
            await update.message.reply_text(
                f"✅ Percentage-based trading disabled.\n"
                f"Bot will use fixed amount (from `amount` or `min_bnb_per_trade` in config) per trade."
            )
        else:
            await update.message.reply_text("Invalid option. Use 'on' or 'off'.")


    async def test_api_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.is_authorized(update): return
        if not self.trading_bot:
            await update.message.reply_text("Trading bot not initialized")
            return
        
        cfg = self.trading_bot.config
        if not cfg.get("api_key") or cfg.get("api_key") == "GANTI_DENGAN_API_KEY_ANDA" or \
           not cfg.get("api_secret") or cfg.get("api_secret") == "GANTI_DENGAN_API_SECRET_ANDA":
            await update.message.reply_text(
                "⚠️ API credentials not set or using default placeholders. "
                "Use /set api_key YOUR_KEY and /set api_secret YOUR_SECRET. "
                "Also check BINANCE_API_KEY/SECRET constants at the top of the script if you use them."
            )
            return

        status_msg = await update.message.reply_text("🔄 Testing Binance API connection...")
        # Pastikan binance_api di trading_bot menggunakan config terbaru
        if not self.trading_bot.binance_api or \
           self.trading_bot.binance_api.api_key != cfg["api_key"] or \
           self.trading_bot.binance_api.api_secret != cfg["api_secret"] or \
           self.trading_bot.binance_api.base_url != (BINANCE_TEST_API_URL if cfg["use_testnet"] else BINANCE_API_URL):
             self.trading_bot.binance_api = BinanceAPI(cfg)


        if self.trading_bot.binance_api:
            try:
                ping_url = f"{self.trading_bot.binance_api.base_url}/api/v3/ping"
                ping_response = requests.get(ping_url, timeout=10)
                if ping_response.status_code != 200:
                    await status_msg.edit_text(
                        f"❌ Ping failed. Status: {ping_response.status_code}\nResponse: {ping_response.text}"
                    )
                    return

                server_time_url = f"{self.trading_bot.binance_api.base_url}/api/v3/time"
                server_time_response = requests.get(server_time_url, timeout=10)
                server_time_str = "Unknown"
                if server_time_response.status_code == 200:
                    server_time_data = server_time_response.json()
                    server_time = datetime.fromtimestamp(server_time_data['serverTime'] / 1000)
                    server_time_str = server_time.strftime("%Y-%m-%d %H:%M:%S UTC")
                
                await status_msg.edit_text(
                    f"✅ Ping & Server Time OK.\n"
                    f"Mode: {'Testnet' if cfg.get('use_testnet') else 'Production'}\n"
                    f"Base URL: {self.trading_bot.binance_api.base_url}\n"
                    f"Server Time: {server_time_str}\n\n"
                    f"Now testing authentication (get_account_info)..."
                )
                
                account_info = self.trading_bot.binance_api.get_account_info()
                if account_info and 'balances' in account_info : 
                    balances_str = "\n".join([
                        f"{b['asset']}: {b['free']} (Free) + {b['locked']} (Locked)" 
                        for b in account_info['balances'] if float(b['free']) > 0 or float(b['locked']) > 0][:5] # Top 5
                    )
                    if not balances_str: balances_str = "No assets with non-zero balance found."
                    
                    await status_msg.edit_text(
                        f"✅ API connection test successful!\n\n"
                        f"Mode: {'Testnet' if cfg.get('use_testnet') else 'Production'}\n"
                        f"Can Trade: {account_info.get('canTrade', 'Unknown')}\n"
                        f"Account Type: {account_info.get('accountType', 'Unknown')}\n"
                        f"Top Balances:\n{balances_str}"
                    )
                else: 
                    error_detail = "Check logs for detailed error from Binance."
                    if isinstance(account_info, dict) and 'msg' in account_info: # Jika ada pesan error dari Binance
                        error_detail = f"Binance Msg: {account_info.get('msg')} (Code: {account_info.get('code')})"

                    await status_msg.edit_text(
                        f"❌ API authentication failed (get_account_info).\n"
                        f"Mode: {'Testnet' if cfg.get('use_testnet') else 'Production'}\n"
                        f"Please check API Key, Secret, permissions (Enable Reading, Enable Spot & Margin Trading), "
                        f"and ensure keys match the selected mode (Testnet/Production). Also check IP restrictions.\n"
                        f"{error_detail}"
                    )
            except requests.exceptions.Timeout:
                await status_msg.edit_text("❌ API connection test failed: Request timed out.")
            except Exception as e_conn:
                await status_msg.edit_text(f"❌ API connection test failed: {str(e_conn)}")
        else:
            await status_msg.edit_text("❌ Binance API not initialized. API Key/Secret might be missing in config.")


    async def toggle_testnet_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.is_authorized(update): return
        if not self.trading_bot:
            await update.message.reply_text("Trading bot not initialized")
            return

        self.trading_bot.config["use_testnet"] = not self.trading_bot.config.get("use_testnet", False)
        
        # Re-initialize API clients dengan setting baru
        # Pastikan CONFIG global juga diupdate jika binance_api mengambil dari sana
        # Untuk sekarang, asumsikan CONFIG di trading_bot adalah sumber utama
        self.trading_bot.binance_api = BinanceAPI(self.trading_bot.config)
        if self.trading_bot.market_analyzer: self.trading_bot.market_analyzer.binance_api = self.trading_bot.binance_api
        if self.trading_bot.whale_detector: self.trading_bot.whale_detector.binance_api = self.trading_bot.binance_api

        mode = "Testnet" if self.trading_bot.config["use_testnet"] else "Production"
        await update.message.reply_text(
            f"✅ Switched to {mode} mode.\n"
            f"Ensure your API keys are for {mode}. Test with /testapi."
        )

    async def enable_real_trading_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.is_authorized(update): return
        if not self.trading_bot:
            await update.message.reply_text("Trading bot not initialized")
            return
        
        cfg = self.trading_bot.config
        if not cfg.get("api_key") or cfg.get("api_key") == "GANTI_DENGAN_API_KEY_ANDA" or \
           not cfg.get("api_secret") or cfg.get("api_secret") == "GANTI_DENGAN_API_SECRET_ANDA":
            await update.message.reply_text("⚠️ API credentials not set or using default placeholders. Use /set commands.")
            return

        if cfg.get("use_testnet", False):
            await update.message.reply_text(
                "⚠️ Real trading cannot be enabled while in Testnet mode. "
                "Switch to Production mode first using /toggletestnet, then try again."
            )
            return

        # Test koneksi sebelum benar-benar enable
        status_msg = await update.message.reply_text("🔄 Testing API for Production before enabling real trading...")
        
        # Buat config sementara untuk test
        test_config = cfg.copy()
        test_config["use_real_trading"] = True 
        test_config["use_testnet"] = False # Pastikan production untuk real money
        
        current_binance_api_for_test = BinanceAPI(test_config)
        account_info = current_binance_api_for_test.get_account_info()

        if account_info and account_info.get('canTrade'):
            # Jika test berhasil, terapkan perubahan ke config utama bot
            self.trading_bot.config["use_real_trading"] = True
            self.trading_bot.config["use_testnet"] = False
            self.trading_bot.config["mock_mode"] = False # Force mock_mode off

            # Re-initialize API utama bot
            self.trading_bot.binance_api = BinanceAPI(self.trading_bot.config)
            if self.trading_bot.market_analyzer: 
                self.trading_bot.market_analyzer.config["mock_mode"] = False
                self.trading_bot.market_analyzer.binance_api = self.trading_bot.binance_api
            if self.trading_bot.whale_detector: 
                self.trading_bot.whale_detector.config["mock_mode"] = False
                self.trading_bot.whale_detector.binance_api = self.trading_bot.binance_api
            
            bnb_bal_obj = next((b for b in account_info['balances'] if b['asset'] == 'BNB'), None)
            bnb_bal_str = f"{float(bnb_bal_obj['free']):.6f}" if bnb_bal_obj else "0.000000"
            
            await status_msg.edit_text(
                f"✅ Real trading has been ENABLED on Production!\n"
                f"BNB Balance (Free): {bnb_bal_str}\n"
                f"Mock mode is now OFF.\n"
                f"⚠️ WARNING: Bot will execute REAL trades. Monitor carefully."
            )
        else:
            # self.trading_bot.config["use_real_trading"] = False # Biarkan setting lama jika gagal
            error_detail = "Check logs."
            if isinstance(account_info, dict) and 'msg' in account_info:
                error_detail = f"Binance Msg: {account_info.get('msg')} (Code: {account_info.get('code')})"
            await status_msg.edit_text(
                f"❌ Failed API test for Production or account cannot trade. Real trading NOT enabled.\n"
                f"Ensure API keys are correct for Production, have Spot trading permission, and no IP restrictions.\n"
                f"{error_detail}"
            )


    async def disable_real_trading_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.is_authorized(update): return
        if not self.trading_bot:
            await update.message.reply_text("Trading bot not initialized")
            return
        self.trading_bot.config["use_real_trading"] = False
        # Opsional: Kembalikan mock_mode ke True jika diinginkan
        self.trading_bot.config["mock_mode"] = True
        if self.trading_bot.market_analyzer: self.trading_bot.market_analyzer.config["mock_mode"] = True

        await update.message.reply_text("✅ Real trading has been DISABLED. Bot operates in simulation mode (mock_mode re-enabled).")


    async def balance_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.is_authorized(update): return
        if not self.trading_bot:
            await update.message.reply_text("Trading bot not initialized")
            return
        
        cfg = self.trading_bot.config
        if not cfg.get("api_key") or cfg.get("api_key") == "GANTI_DENGAN_API_KEY_ANDA" or \
           not cfg.get("api_secret") or cfg.get("api_secret") == "GANTI_DENGAN_API_SECRET_ANDA":
            await update.message.reply_text("⚠️ API credentials not set or using default placeholders.")
            return

        status_msg = await update.message.reply_text("🔄 Fetching account balance...")
        if not self.trading_bot.binance_api or \
           self.trading_bot.binance_api.api_key != cfg["api_key"] or \
           self.trading_bot.binance_api.api_secret != cfg["api_secret"] or \
           self.trading_bot.binance_api.base_url != (BINANCE_TEST_API_URL if cfg["use_testnet"] else BINANCE_API_URL):
             self.trading_bot.binance_api = BinanceAPI(cfg)


        if self.trading_bot.binance_api:
            account_info = self.trading_bot.binance_api.get_account_info()
            if account_info and 'balances' in account_info:
                balances = [b for b in account_info['balances'] if float(b['free']) > 0 or float(b['locked']) > 0]
                balances_text = "\n".join([f"{b['asset']}: {b['free']} (Free) + {b['locked']} (Locked)" for b in balances[:15]]) # Max 15
                if not balances: balances_text = "No assets with non-zero balance found."
                elif len(balances) > 15: balances_text += f"\n... and {len(balances) - 15} more assets."
                
                mode_text = "Testnet" if cfg.get("use_testnet") else "Production"
                await status_msg.edit_text(
                    f"📊 ACCOUNT BALANCE ({mode_text})\n\n{balances_text}\n\n"
                    f"Can Trade: {account_info.get('canTrade', 'Unknown')}\n"
                    f"Account Type: {account_info.get('accountType', 'Unknown')}"
                )
            else:
                error_detail = "Check logs."
                if isinstance(account_info, dict) and 'msg' in account_info:
                    error_detail = f"Binance Msg: {account_info.get('msg')} (Code: {account_info.get('code')})"
                await status_msg.edit_text(f"❌ Failed to get account balance. {error_detail}")
        else:
            await status_msg.edit_text("❌ Binance API not initialized. Check API Key/Secret in config.")


    async def is_authorized(self, update: Update) -> bool:
        user_id = update.effective_user.id
        if user_id not in self.admin_user_ids:
            if update.effective_chat: # Hanya kirim pesan jika ada chat context
                 await update.effective_chat.send_message("⛔ You are not authorized to use this bot.")
            logger.warning(f"Unauthorized access attempt by user {user_id} in chat {update.effective_chat.id if update.effective_chat else 'N/A'}")
            return False
        
        # Tambahkan chat_id ke admin_chat_ids jika belum ada (untuk notifikasi)
        if update.effective_chat and update.effective_chat.id not in self.admin_chat_ids:
            self.admin_chat_ids.append(update.effective_chat.id)
            logger.info(f"Added chat ID {update.effective_chat.id} to admin notification list. Current: {self.admin_chat_ids}")
        return True

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.is_authorized(update): return # Ini juga akan menambah chat_id jika user adalah admin
        
        keyboard = [
            [InlineKeyboardButton("🔄 Start Trading", callback_data="select_trading_mode")],
            [InlineKeyboardButton("📊 Top Volume", callback_data="volume"),
             InlineKeyboardButton("📈 Trending", callback_data="trending")],
            [InlineKeyboardButton("⚙️ Settings", callback_data="config"),
             InlineKeyboardButton("📋 Status", callback_data="status")]
        ]
        await update.message.reply_text(
            "Welcome to the Enhanced BNB Trading Bot!\n"
            "Use /help for a list of commands.\n"
            "Current admin chat IDs for notifications: " + ", ".join(map(str,self.admin_chat_ids)),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.is_authorized(update): return
        help_text = (
            "Available commands:\n"
            "/start - Start bot & main menu\n"
            "/help - This help message\n"
            "/status - Bot status\n"
            "/config - View config\n"
            "/set [param] [value] - Set config param\n"
            "/trades - Recent trades\n"
            "/whales - Recent (mock) whale alerts\n"
            "/stats - Daily trading stats\n"
            "/setpercentage [on/off] [val] - % based trading\n"
            "/bnbpairs - Available BNB pairs\n"
            "/volume - High volume BNB pairs\n"
            "/trending - Trending BNB pairs\n"
            "/modes - View/Select trading modes\n"
            "/whaleconfig - Whale detection settings\n"
            "/starttrade - Start trading (prompts for mode)\n"
            "/stoptrade - Stop trading\n\n"
            "Real Trading & API:\n"
            "/enablereal - Enable REAL trading (Production only)\n"
            "/disablereal - Disable REAL trading (Simulation)\n"
            "/balance - Show Binance account balance\n"
            "/testapi - Test Binance API connection\n"
            "/toggletestnet - Switch Testnet/Production API"
        )
        await update.message.reply_text(help_text)

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.is_authorized(update): return
        if not self.trading_bot:
            await (update.callback_query or update.message).reply_text("Trading bot not initialized")
            return

        active_trades_list = [t for t in ACTIVE_TRADES if not t.get('completed', False)]
        
        # Ambil statistik harian yang sudah terformat
        daily_stats_obj = DAILY_STATS 
        win_rate_daily = (daily_stats_obj["winning_trades"] / daily_stats_obj["total_trades"] * 100) if daily_stats_obj["total_trades"] > 0 else 0
        
        real_trading_status = "✅ Enabled" if self.trading_bot.config.get("use_real_trading") else "❌ Disabled (Simulation)"
        api_mode = "Testnet" if self.trading_bot.config.get("use_testnet") else "Production"

        status_text = (
            f"📊 BOT STATUS\n\n"
            f"Trading Engine: {'✅ Running' if self.trading_bot.running else '❌ Stopped'}\n"
            f"Auto-Trading: {'✅ Enabled' if self.trading_bot.config.get('trading_enabled') else '❌ Disabled (e.g. daily limit reached)'}\n"
            f"Current Mode: {self.trading_bot.config.get('trading_mode','N/A').capitalize()}\n"
            f"Real Trading: {real_trading_status} ({api_mode})\n"
            f"TP/SL (from mode): {self.trading_bot.config.get('take_profit',0)}% / {self.trading_bot.config.get('stop_loss',0)}%\n"
            f"Max Trade Time: {self.trading_bot.config.get('max_trade_time',0)}s\n\n"
            f"Active Trades: {len(active_trades_list)}/{self.trading_bot.config.get('max_concurrent_trades',0)}\n"
            f"Completed (Session): {len(COMPLETED_TRADES)}\n" # Sejak bot terakhir restart
            # f"Total Profit (Session): {sum(t.get('result', 0) for t in COMPLETED_TRADES):.2f}% / {sum(t.get('profit_in_bnb', 0.0) for t in COMPLETED_TRADES):.8f} BNB\n"
            # f"Win Rate (Session): {((sum(1 for t in COMPLETED_TRADES if t.get('result', 0) > 0) / len(COMPLETED_TRADES) * 100) if COMPLETED_TRADES else 0):.1f}%\n\n"
            
            f"--- Daily Stats ({daily_stats_obj.get('date', 'N/A')}) ---\n"
            f"Daily Trades: {daily_stats_obj.get('total_trades',0)} (W: {daily_stats_obj.get('winning_trades',0)}, L: {daily_stats_obj.get('losing_trades',0)})\n"
            f"Daily Win Rate: {win_rate_daily:.1f}%\n"
            f"Daily P/L BNB: {daily_stats_obj.get('total_profit_bnb',0.0):.8f} BNB\n"
            f"Daily Balance Change: {((daily_stats_obj.get('current_balance',0) - daily_stats_obj.get('starting_balance',0)) / daily_stats_obj.get('starting_balance',1) * 100 if daily_stats_obj.get('starting_balance',0) > 0 else 0):.2f}%\n\n"

            f"Whale Detection: {'✅ On' if self.trading_bot.config.get('whale_detection') else '❌ Off'}\n"
            f"Auto-Select Pairs: {'✅ On' if self.trading_bot.config.get('auto_select_pairs') else '❌ Off'}\n"
            f"% Based Trading: {'✅ (' + str(self.trading_bot.config.get('trade_percentage')) + '%)' if self.trading_bot.config.get('use_percentage') else '❌ Off'}"
        )
        keyboard = [
            [InlineKeyboardButton("🔄 Start Trading", callback_data="select_trading_mode"),
             InlineKeyboardButton("⏹️ Stop Trading", callback_data="stop_trading")],
            [InlineKeyboardButton("📊 Volume", callback_data="volume"),
             InlineKeyboardButton("📈 Trending", callback_data="trending")],
            [InlineKeyboardButton("⚙️ Settings", callback_data="config"),
             InlineKeyboardButton(f"{'🔴 Disable' if self.trading_bot.config.get('use_real_trading') else '🟢 Enable'} Real",
                                 callback_data="toggle_real_trading")]
        ]
        
        target = update.callback_query.edit_message_text if update.callback_query else update.message.reply_text
        try:
            await target(status_text, reply_markup=InlineKeyboardMarkup(keyboard))
        except Exception as e: # Misal pesan terlalu panjang
            logger.error(f"Error sending status: {e}. Trying to send in parts or shorter.")
            # Coba kirim versi lebih pendek jika error
            short_status = status_text[:4000] # Batas Telegram sekitar 4096
            await target(short_status, reply_markup=InlineKeyboardMarkup(keyboard))


    async def config_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.is_authorized(update): return
        if not self.trading_bot:
            await (update.callback_query or update.message).reply_text("Trading bot not initialized")
            return

        cfg = self.trading_bot.config
        api_key_display = '****' + cfg.get('api_key', '')[-4:] if cfg.get('api_key') and len(cfg.get('api_key', '')) > 4 else 'Not set / Too short'
        api_secret_display = '****' + cfg.get('api_secret', '')[-4:] if cfg.get('api_secret') and len(cfg.get('api_secret', '')) > 4 else 'Not set / Too short'

        config_text = (
            f"⚙️ BOT CONFIGURATION\n\n"
            f"Trading Mode: {cfg.get('trading_mode','N/A').capitalize()}\n"
            f"Fixed Trade Amount (BNB): {cfg.get('amount',0.01)} (if % based is off)\n"
            f"Min BNB Value Per Trade: {cfg.get('min_bnb_per_trade', 0.011)} BNB\n"
            f"% Based Trading: {'Yes (' + str(cfg.get('trade_percentage')) + '%)' if cfg.get('use_percentage') else 'No'}\n"
            f"TP/SL (from mode): {cfg.get('take_profit',0)}% / {cfg.get('stop_loss',0)}%\n"
            f"Max Trade Time: {cfg.get('max_trade_time',0)}s\n"
            f"Max Concurrent Trades: {cfg.get('max_concurrent_trades',0)}\n\n"
            f"Auto Select Pairs: {'On' if cfg.get('auto_select_pairs') else 'Off'}\n"
            f"Min Volume (BNB for pair): {cfg.get('min_volume',0)}\n"
            f"Min Price Change %: {cfg.get('min_price_change',0)}%\n\n"
            f"Whale Detection: {'On' if cfg.get('whale_detection') else 'Off'}\n"
            f"Auto Trade (Whale): {'On' if cfg.get('auto_trade_on_whale') else 'Off'}\n"
            f"Whale Strategy: {cfg.get('trading_strategy','N/A')}\n"
            f"Whale Threshold (BNB): {cfg.get('whale_threshold',0)}\n\n"
            f"Daily Profit Target: {cfg.get('daily_profit_target', 2.5)}%\n"
            f"Daily Loss Limit: {cfg.get('daily_loss_limit', 5.0)}%\n\n"
            f"API Key: {api_key_display}\nAPI Secret: {api_secret_display}\n"
            f"API Mode: {'Testnet' if cfg.get('use_testnet') else 'Production'}\n"
            f"Real Trading: {'Enabled' if cfg.get('use_real_trading') else 'Disabled (Simulation)'}\n"
            f"Mock Data Mode: {'Enabled' if cfg.get('mock_mode') else 'Disabled'}"
        )
        keyboard = [
            [InlineKeyboardButton("Change Mode", callback_data="select_trading_mode")],
            [InlineKeyboardButton("Toggle Auto-Select", callback_data="toggle_auto_select"),
             InlineKeyboardButton("Toggle Whale Detection", callback_data="toggle_whale_detection")],
            [InlineKeyboardButton("Toggle % Based", callback_data="toggle_percentage_based"),
             InlineKeyboardButton(f"{'Disable' if cfg.get('use_real_trading') else 'Enable'} Real Trading",
                                 callback_data="toggle_real_trading")],
            [InlineKeyboardButton("Back to Status", callback_data="status")]
        ]
        
        target = update.callback_query.edit_message_text if update.callback_query else update.message.reply_text
        try:
            await target(config_text, reply_markup=InlineKeyboardMarkup(keyboard))
        except Exception as e:
            logger.error(f"Error sending config: {e}. Message might be too long.")
            short_config = config_text[:4000]
            await target(short_config, reply_markup=InlineKeyboardMarkup(keyboard))


    async def set_config_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.is_authorized(update): return
        if not self.trading_bot:
            await update.message.reply_text("Trading bot not initialized")
            return

        args = context.args
        if len(args) < 2:
            params_list = (
                "amount, trading_mode, take_profit, stop_loss, max_trade_time, min_volume, \n"
                "min_price_change, auto_select_pairs, whale_detection, api_key, api_secret, \n"
                "use_testnet, use_real_trading, trade_percentage, use_percentage, \n"
                "daily_loss_limit, daily_profit_target, min_bnb_per_trade, mock_mode"
            )
            await update.message.reply_text(
                f"Usage: /set [parameter] [value]\nCommon params:\n{params_list}"
            )
            return

        param = args[0].lower()
        value_str = " ".join(args[1:]) 

        if param not in self.trading_bot.config:
            # Allow setting new parameters if needed, but safer to restrict to known ones.
            # For now, let's stick to known parameters.
            await update.message.reply_text(f"Unknown parameter: {param}. Check /config or /help for list.")
            return

        original_value = self.trading_bot.config[param]
        new_value = None
        try:
            if isinstance(original_value, bool): new_value = value_str.lower() in ['true', 'yes', '1', 'on', 'enable']
            elif isinstance(original_value, int): new_value = int(value_str)
            elif isinstance(original_value, float): new_value = float(value_str)
            elif isinstance(original_value, str):
                if param == 'trading_mode' and value_str not in TRADING_MODES:
                    await update.message.reply_text(f"Invalid mode. Modes: {', '.join(TRADING_MODES.keys())}")
                    return
                new_value = value_str
            else: 
                # If original_value is None (e.g. new param not yet in CONFIG dict but allowed)
                # Try to guess type or default to string.
                # For safety, only allow changing existing typed params.
                await update.message.reply_text(f"Parameter {param} has an unsupported type or is not pre-defined with a type.")
                return

        except ValueError:
            await update.message.reply_text(f"Invalid value for {param}. Expected {type(original_value).__name__}, got '{value_str}'.")
            return

        self.trading_bot.config[param] = new_value
        msg = f"Config updated: {param} = {new_value}"

        # Special handling for API related changes
        if param in ['api_key', 'api_secret', 'use_testnet']:
            self.trading_bot.binance_api = BinanceAPI(self.trading_bot.config) # Re-init API client
            if self.trading_bot.market_analyzer: self.trading_bot.market_analyzer.binance_api = self.trading_bot.binance_api
            if self.trading_bot.whale_detector: self.trading_bot.whale_detector.binance_api = self.trading_bot.binance_api
            msg += "\nAPI client re-initialized. Test with /testapi."
        
        if param == 'trading_mode':
            self.trading_bot.apply_trading_mode_settings()
            msg += "\nTrading mode settings applied."
            tm_cfg = TRADING_MODES.get(new_value, {}) # Use .get for safety
            msg += (f"\nNew Mode Settings ({str(new_value).capitalize()}):\n"
                    f"  TP: {tm_cfg.get('take_profit','N/A')}%, SL: {tm_cfg.get('stop_loss','N/A')}%\n"
                    f"  Max Time: {tm_cfg.get('max_trade_time','N/A')}s, Max Trades: {tm_cfg.get('max_trades','N/A')}")
        
        if param == "use_real_trading":
            if new_value is True: # Jika mengaktifkan real trading
                self.trading_bot.config["mock_mode"] = False # Pastikan mock_mode mati
                msg += "\nMock mode automatically set to False."
                if self.trading_bot.market_analyzer: self.trading_bot.market_analyzer.config["mock_mode"] = False
            # Jika menonaktifkan real trading, user bisa set mock_mode manual jika mau
        
        if param == "mock_mode" and new_value is True and self.trading_bot.config.get("use_real_trading") is True:
            self.trading_bot.config["mock_mode"] = False # Tidak bisa mock jika real trading aktif
            msg = f"Cannot enable mock_mode while use_real_trading is True. {param} remains False."


        await update.message.reply_text(msg)


    async def trades_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.is_authorized(update): return
        if not self.trading_bot:
            await update.message.reply_text("Trading bot not initialized.")
            return

        all_trades = ACTIVE_TRADES + COMPLETED_TRADES
        if not all_trades:
            await update.message.reply_text("No trades recorded yet.")
            return

        recent_trades = sorted(all_trades, key=lambda x: x.get('timestamp',0), reverse=True)[:10] # Tampilkan 10
        trades_text = "📊 RECENT TRADES (Max 10)\n\n"
        for trade in recent_trades:
            status = "Active" if not trade.get('completed', False) else f"Completed ({trade.get('close_reason','N/A')})"
            result_pct_str = f"{trade.get('result', 0):.2f}%" if trade.get('completed', False) else "N/A"
            
            time_info = f"Entry: {trade.get('entry_time', 'N/A').split(' ')[1]}" 
            if not trade.get('completed', False):
                elapsed = int(time.time() - trade.get('timestamp',0))
                time_info += f", Elapsed: {elapsed}s"
            else:
                time_info += f", Exit: {trade.get('exit_time', 'N/A').split(' ')[1]}"

            real_trade_display = "No (Sim)"
            if trade.get('order_id'):
                 if trade.get('real_trade_filled'): real_trade_display = f"Yes (ID:{trade.get('order_id')} Filled)"
                 elif trade.get('real_trade_opened'): real_trade_display = f"Yes (ID:{trade.get('order_id')} Opened)"
                 else: real_trade_display = f"Yes (ID:{trade.get('order_id')} FAILED)" # Gagal setelah dikirim
            elif self.trading_bot.config.get("use_real_trading") and not trade.get('order_id'):
                real_trade_display = "Yes (Attempted, FAILED Pre-Send)"


            trades_text += (
                f"Pair: {trade.get('pair','N/A')} ({trade.get('type','N/A')}) | {trade.get('mode','N/A')}\n"
                f"Status: {status}, Result: {result_pct_str}\n"
                f"Entry $: {trade.get('entry_price',0):.6f}, Amount: {trade.get('amount',0):.6f} {trade.get('base_asset','?')}\n"
                f"{time_info}\n"
                f"Real: {real_trade_display}\n"
                f"Profit BNB: {trade.get('profit_in_bnb', 0.0):.8f} (if completed)\n\n"
            )
        
        if len(trades_text) > 4090: # Batas Telegram
            trades_text = trades_text[:4000] + "\n... (message truncated)"
        await update.message.reply_text(trades_text if trades_text.strip() else "No recent trades.")


    async def whales_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.is_authorized(update): return
        if not MOCK_WHALE_TRANSACTIONS: 
            await update.message.reply_text("No (mock) whale transactions detected yet.")
            return

        recent_whales = sorted(MOCK_WHALE_TRANSACTIONS, key=lambda x: x['id'], reverse=True)[:5]
        whales_text = "🐋 RECENT MOCK WHALE TRANSACTIONS (Max 5)\n\n"
        for whale in recent_whales:
            whales_text += (
                f"Token: {whale['token']} ({whale['type']})\n"
                f"Amount: {whale['amount']:.2f}, Value: ${whale['value']:,.2f}\n"
                f"Impact: {whale['impact']}\nTime: {whale['time']}\n\n"
            )
        await update.message.reply_text(whales_text if whales_text.strip() else "No recent mock whale alerts.")


    async def bnb_pairs_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.is_authorized(update): return
        if not self.trading_bot or not self.trading_bot.market_analyzer:
            await (update.callback_query or update.message).reply_text("Market analyzer not ready.")
            return

        ma = self.trading_bot.market_analyzer
        if not ma.config.get("mock_mode", True) and \
           (not ma.market_data or \
            time.time() - ma.last_update > 60): # Jika data real sudah lama
            msg_to_edit = await (update.callback_query or update.message).reply_text("Updating market data from Binance...")
            ma.update_market_data() # Update paksa
            if msg_to_edit and update.callback_query: await msg_to_edit.edit_text("Market data updated. Fetching pairs...")
            elif msg_to_edit: await msg_to_edit.edit_text("Market data updated. Fetching pairs...")


        pairs = ma.market_data
        bnb_base_pairs = [p for p in pairs if p["pair"].startswith("BNB")]
        bnb_quote_pairs = [p for p in pairs if p["pair"].endswith("BNB") and not p["pair"].startswith("BNB")] 

        pairs_text = "📋 BNB TRADING PAIRS (Showing Top 10 by default sort order)\n\n"
        pairs_text += "BNB Base Pairs (e.g., BNBUSDT):\n"
        if bnb_base_pairs:
            for p in bnb_base_pairs[:10]: 
                pairs_text += f"• {p['pair']} (Vol: {p.get('volume',0):.0f} BNB, Chg: {p.get('price_change',0):.2f}%)\n"
        else: pairs_text += "No BNB base pairs found.\n"

        pairs_text += "\nBNB Quote Pairs (e.g., SOLBNB):\n"
        if bnb_quote_pairs:
            for p in bnb_quote_pairs[:10]: 
                pairs_text += f"• {p['pair']} (QVol: {p.get('quote_volume',0):.0f} BNB, Chg: {p.get('price_change',0):.2f}%)\n"
        else: pairs_text += "No BNB quote pairs found.\n"
        
        if not bnb_base_pairs and not bnb_quote_pairs:
            pairs_text = "No BNB pairs found. Market data might be updating or empty. Try again."

        target = update.callback_query.edit_message_text if update.callback_query else update.message.reply_text
        try:
            await target(pairs_text)
        except Exception as e:
            logger.error(f"Error sending bnb_pairs: {e}")
            await target(pairs_text[:4000])


    async def volume_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.is_authorized(update): return
        if not self.trading_bot or not self.trading_bot.market_analyzer:
            await (update.callback_query or update.message).reply_text("Market analyzer not ready.")
            return

        high_volume_pairs = self.trading_bot.market_analyzer.get_high_volume_pairs(10)
        volume_text = "📊 TOP VOLUME BNB PAIRS (Sorted by Quote Volume if available)\n\n"
        keyboard_rows = []
        if high_volume_pairs:
            for i, p in enumerate(high_volume_pairs, 1):
                vol_display = f"QVol: {p.get('quote_volume',0):.0f}" if 'quote_volume' in p and p.get('quote_volume',0) > 0 else f"Vol: {p.get('volume',0):.0f}"
                vol_display += " BNB" if p['pair'].endswith("BNB") or p['pair'].startswith("BNB") else ""
                volume_text += f"{i}. {p['pair']} ({vol_display}, Chg: {p.get('price_change',0):.2f}%)\n"
                if i <= 6: 
                    if i % 2 == 1: keyboard_rows.append([])
                    keyboard_rows[-1].append(InlineKeyboardButton(f"Trade {p['pair']}", callback_data=f"trade_{p['pair']}"))
        else:
            volume_text += "No high volume pairs found. Market data might be empty or filtering too strict."
        
        keyboard_rows.append([InlineKeyboardButton("Back to Status", callback_data="status")])
        reply_markup = InlineKeyboardMarkup(keyboard_rows)
        
        target = update.callback_query.edit_message_text if update.callback_query else update.message.reply_text
        await target(volume_text, reply_markup=reply_markup)


    async def trending_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.is_authorized(update): return
        if not self.trading_bot or not self.trading_bot.market_analyzer:
            await (update.callback_query or update.message).reply_text("Market analyzer not ready.")
            return

        trending_pairs = self.trading_bot.market_analyzer.get_trending_pairs(10)
        trending_text = "📈 TRENDING BNB PAIRS (Sorted by |Price Change|)\n\n"
        keyboard_rows = []
        if trending_pairs:
            for i, p in enumerate(trending_pairs, 1):
                emoji = "🟢" if p.get('price_change',0) > 0 else ("🔴" if p.get('price_change',0) < 0 else "⚪")
                vol_display = f"QVol: {p.get('quote_volume',0):.0f}" if 'quote_volume' in p and p.get('quote_volume',0) > 0 else f"Vol: {p.get('volume',0):.0f}"
                trending_text += f"{i}. {p['pair']} {emoji} (Chg: {p.get('price_change',0):.2f}%, {vol_display})\n"
                if i <= 6:
                    if i % 2 == 1: keyboard_rows.append([])
                    keyboard_rows[-1].append(InlineKeyboardButton(f"Trade {p['pair']}", callback_data=f"trade_{p['pair']}"))
        else:
            trending_text += "No trending pairs found. Market data might be empty or no significant changes."

        keyboard_rows.append([InlineKeyboardButton("Back to Status", callback_data="status")])
        reply_markup = InlineKeyboardMarkup(keyboard_rows)
        
        target = update.callback_query.edit_message_text if update.callback_query else update.message.reply_text
        await target(trending_text, reply_markup=reply_markup)


    async def trading_modes_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.is_authorized(update): return
        modes_text = "⚙️ AVAILABLE TRADING MODES\n\n"
        keyboard = []
        for name, settings in TRADING_MODES.items():
            modes_text += (f"📌 {name.replace('_',' ').capitalize()}: {settings['description']}\n"
                           f"   TP: {settings['take_profit']}%, SL: {settings['stop_loss']}%, Time: {settings['max_trade_time']}s, Trades: {settings['max_trades']}\n"
                           f"   VolThresh: {settings.get('volume_threshold','N/A')}, PriceChgThresh: {settings.get('price_change_threshold','N/A')}%\n\n")
        keyboard.append([InlineKeyboardButton("Back to Config", callback_data="config")]) # Atau ke status
        
        target = update.callback_query.edit_message_text if update.callback_query else update.message.reply_text
        try:
            await target(modes_text, reply_markup=InlineKeyboardMarkup(keyboard))
        except Exception as e:
            logger.error(f"Error sending trading_modes: {e}")
            await target(modes_text[:4000], reply_markup=InlineKeyboardMarkup(keyboard))


    async def whale_config_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.is_authorized(update): return
        if not self.trading_bot:
            await (update.callback_query or update.message).reply_text("Trading bot not initialized.")
            return
        
        cfg = self.trading_bot.config
        keyboard = [
            [InlineKeyboardButton(f"Detection: {'Disable' if cfg.get('whale_detection') else 'Enable'}", callback_data="toggle_whale_detection")],
            [InlineKeyboardButton(f"Auto-Trade: {'Disable' if cfg.get('auto_trade_on_whale') else 'Enable'}", callback_data="toggle_auto_trade_whale")],
            [InlineKeyboardButton("Strat: Follow", callback_data="strategy_follow_whale"),
             InlineKeyboardButton("Strat: Counter", callback_data="strategy_counter_whale")],
            [InlineKeyboardButton(f"Threshold: {cfg.get('whale_threshold',0)} BNB (Tap to cycle)", callback_data="cycle_whale_threshold")],
            [InlineKeyboardButton("Back to Config", callback_data="config")] # Atau ke Status
        ]
        text = (
            "🐋 WHALE DETECTION CONFIG\n\n"
            f"Detection: {'On' if cfg.get('whale_detection') else 'Off'}\n"
            f"Auto-Trade: {'On' if cfg.get('auto_trade_on_whale') else 'Off'}\n"
            f"Strategy: {cfg.get('trading_strategy','N/A')}\n"
            f"Threshold: {cfg.get('whale_threshold',0)} BNB (Mock mode only)"
        )
        target = update.callback_query.edit_message_text if update.callback_query else update.message.reply_text
        await target(text, reply_markup=InlineKeyboardMarkup(keyboard))


    async def start_trading_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.is_authorized(update): return
        if not self.trading_bot:
            await update.message.reply_text("Trading bot not initialized.")
            return
        
        if self.trading_bot.running:
             await update.message.reply_text(f"Trading engine is already running in '{self.trading_bot.config.get('trading_mode','N/A')}' mode.")
             return
        
        # Jika real trading, pastikan API key ada
        if self.trading_bot.config.get("use_real_trading") and \
           (not self.trading_bot.config.get("api_key") or self.trading_bot.config.get("api_key") == "GANTI_DENGAN_API_KEY_ANDA" or \
            not self.trading_bot.config.get("api_secret") or self.trading_bot.config.get("api_secret") == "GANTI_DENGAN_API_SECRET_ANDA"):
            await update.message.reply_text("⚠️ Cannot start real trading: API Key/Secret not set or using placeholders. Please use /set commands.")
            return


        await self.show_trading_mode_selection(update, context, for_starting_trade=True)


    async def show_trading_mode_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE, for_starting_trade=False):
        action_verb = "Start with" if for_starting_trade else "Set to"
        callback_prefix = "start_mode_" if for_starting_trade else "set_mode_"
        current_mode = self.trading_bot.config.get('trading_mode', 'N/A') if self.trading_bot else 'N/A'
        
        modes_text = f"🔄 SELECT TRADING MODE TO {action_verb.upper()}\n"
        modes_text += f"(Current mode: {current_mode.capitalize()})\n\n"
        keyboard = []
        for name, settings in TRADING_MODES.items():
            modes_text += (f"📌 {name.replace('_',' ').capitalize()}: TP {settings['take_profit']}% / SL {settings['stop_loss']}%\n"
                           #f"   {settings['description']}\n" # Bisa terlalu panjang
                           )
            keyboard.append([InlineKeyboardButton(f"{action_verb} {name.replace('_',' ').capitalize()}", callback_data=f"{callback_prefix}{name}")])
        
        keyboard.append([InlineKeyboardButton("Cancel / Back to Status", callback_data="status")])
        
        target = update.callback_query.edit_message_text if update.callback_query else update.message.reply_text
        await target(modes_text, reply_markup=InlineKeyboardMarkup(keyboard))


    async def stop_trading_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.is_authorized(update): return
        if not self.trading_bot:
            await update.message.reply_text("Trading bot not initialized.")
            return

        if self.trading_bot.stop_trading():
            await update.message.reply_text("Trading engine stopped. All trading loops are being terminated.")
        else:
            await update.message.reply_text("Trading engine is already stopped.")


    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.is_authorized(update): return # Termasuk menambah chat_id
        if not self.trading_bot:
             if update.callback_query: await update.callback_query.answer("Bot not ready or restarting.", show_alert=True)
             return

        query = update.callback_query
        await query.answer() 
        data = query.data

        # Navigasi Utama
        if data == "status": await self.status_command(update, context); return
        if data == "config": await self.config_command(update, context); return
        if data == "volume": await self.volume_command(update, context); return
        if data == "trending": await self.trending_command(update, context); return
        if data == "select_trading_mode": await self.show_trading_mode_selection(update, context, for_starting_trade=True); return
        
        # Start/Set Mode Perdagangan
        if data.startswith("start_mode_") or data.startswith("set_mode_"):
            is_starting_trade = data.startswith("start_mode_")
            mode_name_key = data.replace("start_mode_", "").replace("set_mode_", "")
            
            if mode_name_key in TRADING_MODES:
                self.trading_bot.config["trading_mode"] = mode_name_key
                self.trading_bot.apply_trading_mode_settings() # Terapkan langsung
                tm_cfg = TRADING_MODES[mode_name_key]
                
                if is_starting_trade:
                    self.trading_bot.config["trading_enabled"] = True # Pastikan auto-trade bisa jalan
                    # Cek API key jika real trading sebelum start
                    if self.trading_bot.config.get("use_real_trading") and \
                       (not self.trading_bot.config.get("api_key") or self.trading_bot.config.get("api_key") == "GANTI_DENGAN_API_KEY_ANDA" or \
                        not self.trading_bot.config.get("api_secret") or self.trading_bot.config.get("api_secret") == "GANTI_DENGAN_API_SECRET_ANDA"):
                        await query.edit_message_text("⚠️ Cannot start real trading: API Key/Secret not set or using placeholders. Please use /set commands and try again.")
                        return

                    if self.trading_bot.start_trading(): 
                        await query.edit_message_text(
                            f"Trading engine started with '{mode_name_key.replace('_',' ').capitalize()}' mode!\n"
                            f"TP: {tm_cfg['take_profit']}%, SL: {tm_cfg['stop_loss']}%, Time: {tm_cfg['max_trade_time']}s\n"
                            "Monitoring markets..."
                        )
                    else: 
                        await query.edit_message_text(f"Trading engine is already running or failed to start. Current mode: '{self.trading_bot.config.get('trading_mode','N/A').replace('_',' ').capitalize()}'")
                else: # Hanya set mode, tidak start engine
                     await query.edit_message_text(
                        f"Trading mode set to '{mode_name_key.replace('_',' ').capitalize()}'!\n"
                        f"TP: {tm_cfg['take_profit']}%, SL: {tm_cfg['stop_loss']}%, Time: {tm_cfg['max_trade_time']}s\n"
                        "Use 'Start Trading' from main menu or /starttrade command to start the engine."
                    )
            else:
                await query.edit_message_text(f"Error: Trading mode '{mode_name_key}' not found.")
            return

        # Stop Trading
        if data == "stop_trading":
            if self.trading_bot.stop_trading(): 
                await query.edit_message_text("Trading engine stopped. All loops terminated.")
            else:
                await query.edit_message_text("Trading engine is already stopped.")
            return

        # Inisiasi Trade Manual dari tombol Volume/Trending
        if data.startswith("trade_"):
            pair = data.replace("trade_", "")
            if not self.trading_bot.running or not self.trading_bot.config.get("trading_enabled"):
                await query.edit_message_text("Trading engine not active or auto-trading disabled. Start/Enable first.", show_alert=True)
                return
            if not self.trading_bot.market_analyzer:
                await query.edit_message_text("Market analyzer not ready for manual trade.", show_alert=True)
                return

            pair_data = self.trading_bot.market_analyzer.get_pair_data(pair)
            if pair_data and pair_data.get("last_price",0) > 0:
                # Untuk manual trade, mungkin kita mau konfirmasi BUY/SELL? Atau default berdasarkan tren.
                # Default: Berdasarkan price_change.
                trade_type = "BUY" if pair_data.get("price_change",0) > 0 else "SELL"
                
                # Cek double trade
                is_pair_already_active = any(
                    t['pair'] == pair and not t.get('completed', False) for t in ACTIVE_TRADES
                )
                if is_pair_already_active:
                    await query.edit_message_text(f"Cannot manually trade {pair}: already has an active trade.", show_alert=True)
                    return

                trade = self.trading_bot.create_trade(pair, trade_type, pair_data["last_price"])
                if trade:
                    details = f"Manual Selection ({pair})"
                    msg = self.trading_bot._format_auto_trade_notification(trade, details)
                    # Kirim sebagai pesan baru agar tidak mengedit menu volume/trending
                    await context.bot.send_message(chat_id=query.message.chat_id, text=msg)
                    await query.edit_message_text(f"Trade initiated for {pair}. See new message for details.", reply_markup=None) # Hapus tombol dari pesan lama
                else:
                     await query.edit_message_text(f"Failed to create trade object for {pair}. Possible reasons: insufficient balance, API error, invalid price, or MIN_NOTIONAL not met. Check logs.", show_alert=True)
            else:
                await query.edit_message_text(f"Could not find valid data or price for pair {pair} to trade.", show_alert=True)
            return

        # Tombol Toggle untuk Config
        if data == "toggle_real_trading":
            # Panggil command handler yang sesuai agar logic lengkapnya dijalankan
            current_message = query.message # Simpan pesan saat ini
            if self.trading_bot.config.get("use_real_trading"):
                await self.disable_real_trading_command(update, context) 
            else:
                await self.enable_real_trading_command(update, context) 
            # Setelah command selesai, edit pesan asli (jika masih ada dan belum diedit oleh command)
            # Atau, biarkan command yang mengedit/mengirim pesan baru.
            # Untuk konsistensi, kita bisa refresh config view.
            # await asyncio.sleep(0.5) # Beri waktu command untuk proses
            # await self.config_command(update, context) # Refresh config view
            # Karena enable/disable_real_trading_command sudah mengirim pesan, tidak perlu edit di sini lagi.
            return

        if data == "toggle_percentage_based":
            self.trading_bot.config["use_percentage"] = not self.trading_bot.config.get("use_percentage", False)
            await self.config_command(update, context) 
            return
        if data == "toggle_auto_select":
            self.trading_bot.config["auto_select_pairs"] = not self.trading_bot.config.get("auto_select_pairs", True)
            await self.config_command(update, context) 
            return
        
        # Tombol untuk Whale Config
        if data == "toggle_whale_detection":
            self.trading_bot.config["whale_detection"] = not self.trading_bot.config.get("whale_detection", True)
            await self.whale_config_command(update, context) 
            return
        if data == "toggle_auto_trade_whale":
            self.trading_bot.config["auto_trade_on_whale"] = not self.trading_bot.config.get("auto_trade_on_whale", False)
            await self.whale_config_command(update, context) 
            return
        if data == "strategy_follow_whale": self.trading_bot.config["trading_strategy"] = "follow_whale"; await self.whale_config_command(update, context); return
        if data == "strategy_counter_whale": self.trading_bot.config["trading_strategy"] = "counter_whale"; await self.whale_config_command(update, context); return
        if data == "cycle_whale_threshold":
            current = self.trading_bot.config.get("whale_threshold",100)
            thresholds = [10, 25, 50, 100, 200, 500] # Pilihan threshold
            try:
                current_idx = thresholds.index(current)
                next_idx = (current_idx + 1) % len(thresholds)
            except ValueError: 
                next_idx = thresholds.index(100) if 100 in thresholds else 0 # Default ke 100 atau awal
            self.trading_bot.config["whale_threshold"] = thresholds[next_idx]
            await self.whale_config_command(update, context)
            return

        # Aksi Alert Whale
        if data.startswith("follow_whale_"):
            if not self.trading_bot.running or not self.trading_bot.config.get("trading_enabled"):
                await query.edit_message_text("Trading engine not active or auto-trading disabled. Cannot follow whale.", show_alert=True)
                return
            
            # Cek double trade
            whale_id = int(data.split("_")[2])
            whale_tx = next((w for w in MOCK_WHALE_TRANSACTIONS if w['id'] == whale_id), None)
            if not whale_tx:
                await query.edit_message_text(f"Whale transaction {whale_id} not found (might be too old).", show_alert=True)
                return

            pair_to_trade = whale_tx['token']
            is_pair_already_active = any(
                t['pair'] == pair_to_trade and not t.get('completed', False) for t in ACTIVE_TRADES
            )
            if is_pair_already_active:
                await query.edit_message_text(f"Cannot follow whale for {pair_to_trade}: already has an active trade.", show_alert=True)
                return

            # Lanjutkan membuat trade
            trade_obj = self.trading_bot.create_trade_from_whale(whale_tx, whale_tx['type'], is_auto_trade=False) # is_auto_trade=False karena ini manual follow
            if trade_obj:
                # Pesan trade sudah dikirim oleh create_trade_from_whale. Edit pesan alert whale.
                await query.edit_message_text(f"Attempting to follow whale {whale_id} for {whale_tx['token']}. See new message for trade details.", reply_markup=None)
            else:
                await query.edit_message_text(f"Failed to initiate trade for whale {whale_id}. Possible reasons: insufficient balance, API error, etc. Check logs.", show_alert=True)
            return

        if data.startswith("ignore_whale_"):
            whale_id = int(data.split("_")[2])
            await query.edit_message_text(f"Whale alert {whale_id} ignored.", reply_markup=None) # Hapus tombol
            return

        logger.warning(f"Unhandled callback_query data: {data}")
        await query.answer("Action not implemented or data is stale/unknown.", show_alert=True)


    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.is_authorized(update): return
        await update.message.reply_text("I only respond to commands or inline button presses. Use /help for commands.")

    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE):
        logger.error(f"Exception while handling an update: {context.error}", exc_info=context.error)
        
        # Hindari mengirim pesan error jika update adalah None atau tidak memiliki konteks chat
        # (misalnya error dalam job_queue yang tidak terkait langsung dengan interaksi user)
        if update and isinstance(update, Update) and update.effective_chat:
            try:
                await update.effective_chat.send_message(
                    "An error occurred processing your request. The developer has been notified. "
                    "Please try again later or check the bot logs for more details."
                )
            except Exception as e_send: # Jika mengirim pesan error juga gagal
                logger.error(f"Exception in error_handler's send_message: {e_send}")


    def run(self):
        logger.info("Telegram bot application starting polling...")
        # Loop untuk application PTB sudah dihandle oleh run_polling()
        # Tidak perlu membuat loop asyncio manual di sini untuk PTB.
        # application.loop akan tersedia setelah build().
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)
        logger.info("Telegram bot application has stopped.")


    def set_trading_bot(self, trading_bot):
        self.trading_bot = trading_bot

def main():
    # Pastikan CONFIG menggunakan konstanta global untuk API keys jika mereka diset di sana
    # Dan pastikan nilai default di CONFIG sudah sesuai keinginan Anda.
    if BINANCE_API_KEY and BINANCE_API_KEY != "API_KEY" and BINANCE_API_KEY != "GANTI_DENGAN_API_KEY_ANDA":
        CONFIG["api_key"] = BINANCE_API_KEY
    if BINANCE_API_SECRET and BINANCE_API_SECRET != "API_SECRET" and BINANCE_API_SECRET != "GANTI_DENGAN_API_SECRET_ANDA":
        CONFIG["api_secret"] = BINANCE_API_SECRET

    if TELEGRAM_BOT_TOKEN == "API_BOT_TELEGRAM" or not TELEGRAM_BOT_TOKEN:
        print("CRITICAL: TELEGRAM_BOT_TOKEN is not set. Exiting.")
        logger.critical("CRITICAL: TELEGRAM_BOT_TOKEN is not set. Exiting.")
        return
    if not ADMIN_USER_IDS or ADMIN_USER_IDS == [1234569]: # Ganti 1234569 dengan ID admin default yang tidak valid
        print("WARNING: ADMIN_USER_IDS is not set or using default. Bot might be accessible by unauthorized users if not properly restricted.")
        logger.warning("ADMIN_USER_IDS is not set or using default placeholder.")


    telegram_handler = TelegramBotHandler(TELEGRAM_BOT_TOKEN, ADMIN_USER_IDS)
    trading_bot = TradingBot(CONFIG, telegram_handler) 
    whale_detector = WhaleDetector(CONFIG, trading_bot) # Whale detector juga butuh akses ke trading_bot untuk notif/auto-trade
    
    trading_bot.set_whale_detector(whale_detector)
    telegram_handler.set_trading_bot(trading_bot) # Link krusial

    print("Enhanced BNB Trading Bot is starting...")
    print(f"Admin User IDs configured: {ADMIN_USER_IDS}")
    print(f"Initial Config - Real Trading: {CONFIG.get('use_real_trading')}, Testnet: {CONFIG.get('use_testnet')}, Mock Mode: {CONFIG.get('mock_mode')}")
    print(f"Default trade amount (fixed): {CONFIG.get('amount')} BNB, Min BNB per trade: {CONFIG.get('min_bnb_per_trade')} BNB")
    print("Press Ctrl+C to stop.")

    try:
        # Thread notifikasi sekarang dimulai di dalam trading_bot.start_trading()
        # atau bisa juga dimulai di sini jika mau notifikasi sistem sebelum trading engine jalan
        # Jika trading_bot memiliki referensi ke application loop, itu lebih baik.
        # Untuk sekarang, PTB run_polling akan membuat loopnya sendiri.
        telegram_handler.run()
    except KeyboardInterrupt:
        logger.info("Shutdown signal (Ctrl+C) received.")
    except Exception as e:
        logger.critical(f"Critical error in telegram_handler.run() or main execution: {e}", exc_info=True)
    finally:
        logger.info("Attempting to gracefully stop the Trading Bot...")
        if trading_bot and trading_bot.running:
            trading_bot.stop_trading() # Ini akan menghentikan semua thread internal trading_bot
        logger.info("Bot shutdown process complete.")


if __name__ == "__main__":
    main()

