#Importing Important Libraries - Code Lines from 1 to 33 are those self made components that will be used in the whole program 
import urllib.parse
import time
import json
import random
from sqlalchemy import text
import calendar
from datetime import datetime, timedelta, date
from sqlalchemy import create_engine
from curl_cffi import requests
from decimal import Decimal
import sys
from zoneinfo import ZoneInfo
import os
import logging
from datetime import datetime as dt
from dotenv import load_dotenv

load_dotenv()

# Logging Script

log_folder = r"C:\Users\Riddhima Singh\Desktop\Index Value Strategy\daily_fetch_data_logs"
log_filename = os.path.join(log_folder, f"valuation_fetch_log_{dt.now().strftime('%Y-%m-%d_%H-%M-%S')}.txt")

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[
        logging.FileHandler(log_filename, encoding="utf-8"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

#Workflow - Establish connection to the database -> Run a loop over the postgresql table index_metadata -> for each of the indices, use their index_long_name -> prepare payload for NSE INDIA only combined with today's date -> Fetch the data -> Parse and Clean the Data -> Finally Push it to actual price_metadata table -> Do it repeatedly until each index is finished!

#For Null Values Check
empty_data_list = [None, "None", "0", 0, "-", "NaN", "Null", "NULL", "null", "none", "", " ", "nan"] #Used only during data cleaning

def database_engine_connection():

  #Engine Connection Established
  database_password = os.getenv("database_password")
  DB_URL = f"postgresql://postgres:{database_password}@localhost:5432/index_value_strategy"
  engine = create_engine(DB_URL)
  return engine

output_database_engine_connection = database_engine_connection()

#Index Dictionary manually synced with index_metadata
index_dictionary = {
    1: "NIFTY 100",
    2: "NIFTY 200",
    3: "NIFTY 50",
    4: "NIFTY 500",
    5: "NIFTY INDIA FPI 150",
    6: "NIFTY LARGEMIDCAP 250",
    7: "NIFTY MICROCAP 250",
    8: "NIFTY MIDCAP 100",
    9: "NIFTY MIDCAP 150",
    10: "NIFTY MIDCAP 50",
    11: "NIFTY MIDCAP SELECT",
    12: "NIFTY MIDSMALLCAP 400",
    13: "NIFTY 1D RATE INDEX",
    14: "NIFTY NEXT 50",
    15: "NIFTY SMALLCAP 100",
    16: "NIFTY SMALLCAP 250",
    17: "NIFTY SMALLCAP 50",
    18: "NIFTY MIDSMALLCAP400 50:50",
    19: "NIFTY TOTAL MARKET",
    20: "NIFTY500 LARGEMIDSMALL EQUAL-CAP WEIGHTED",
    21: "NIFTY500 MULTICAP 50:25:25",
    22: "NIFTY AUTO",
    23: "NIFTY BANK",
    24: "NIFTY SMALLCAP 500",
    25: "NIFTY CHEMICALS",
    26: "NIFTY CONSUMER DURABLES",
    27: "NIFTY FINANCIAL SERVICES",
    28: "NIFTY FINANCIAL SERVICES 25/50",
    29: "NIFTY FINANCIAL SERVICES EX-BANK",
    30: "NIFTY FMCG",
    31: "NIFTY HEALTHCARE INDEX",
    32: "NIFTY IT",
    33: "NIFTY MEDIA",
    34: "NIFTY METAL",
    35: "NIFTY MIDSMALL FINANCIAL SERVICES",
    36: "NIFTY MIDSMALL HEALTHCARE",
    37: "NIFTY MIDSMALL IT & TELECOM",
    38: "NIFTY OIL & GAS",
    39: "NIFTY PHARMA",
    40: "NIFTY PRIVATE BANK",
    41: "NIFTY PSU BANK",
    42: "NIFTY REALTY",
    43: "NIFTY REITS & REALTY",
    44: "NIFTY500 HEALTHCARE",
    45: "NIFTY 50 ARBITRAGE",
    46: "NIFTY 50 FUTURES INDEX",
    47: "NIFTY 50 FUTURES TR INDEX",
    48: "NIFTY ALPHA 50",
    49: "NIFTY ALPHA LOW-VOLATILITY 30",
    50: "NIFTY ALPHA QUALITY LOW-VOLATILITY 30",
    51: "NIFTY ALPHA QUALITY VALUE LOW-VOLATILITY 30",
    52: "NIFTY DIVIDEND OPPORTUNITIES 50",
    53: "NIFTY GROWTH SECTORS 15",
    54: "NIFTY HIGH BETA 50",
    55: "NIFTY LOW VOLATILITY 50",
    56: "NIFTY MIDCAP150 MOMENTUM 50",
    57: "NIFTY MIDCAP150 QUALITY 50",
    58: "NIFTY MIDSMALLCAP400 MOMENTUM QUALITY 100",
    59: "NIFTY QUALITY LOW-VOLATILITY 30",
    60: "NIFTY SMALLCAP250 MOMENTUM QUALITY 100",
    61: "NIFTY SMALLCAP250 QUALITY 50",
    62: "NIFTY TOP 10 EQUAL WEIGHT",
    63: "NIFTY TOP 15 EQUAL WEIGHT",
    64: "NIFTY TOP 20 EQUAL WEIGHT",
    65: "NIFTY TOTAL MARKET MOMENTUM QUALITY 50",
    66: "NIFTY100 ALPHA 30",
    67: "NIFTY100 EQUAL WEIGHT",
    68: "NIFTY100 LOW VOLATILITY 30",
    69: "NIFTY100 QUALITY 30",
    70: "NIFTY200 ALPHA 30",
    71: "NIFTY200 MOMENTUM 30",
    72: "NIFTY200 QUALITY 30",
    73: "NIFTY200 VALUE 30",
    74: "NIFTY50 DIVIDEND POINTS",
    75: "NIFTY50 EQUAL WEIGHT",
    76: "NIFTY50 PR 1X INVERSE",
    77: "NIFTY50 PR 2X LEVERAGE",
    78: "NIFTY50 TR 1X INVERSE",
    79: "NIFTY50 TR 2X LEVERAGE",
    80: "NIFTY50 USD",
    81: "NIFTY50 VALUE 20",
    82: "NIFTY500 EQUAL WEIGHT",
    83: "NIFTY500 FLEXICAP QUALITY 30",
    84: "NIFTY500 LOW VOLATILITY 50",
    85: "NIFTY500 MOMENTUM 50",
    86: "NIFTY500 MULTICAP MOMENTUM QUALITY 50",
    87: "NIFTY500 MULTIFACTOR MQVLV 50",
    88: "NIFTY500 QUALITY 50",
    89: "NIFTY500 VALUE 50",
    90: "NIFTY CAPITAL MARKETS",
    91: "NIFTY COMMODITIES",
    92: "NIFTY CONGLOMERATE 50",
    93: "NIFTY CORE HOUSING",
    94: "NIFTY CPSE",
    95: "NIFTY ENERGY",
    96: "NIFTY EV & NEW AGE AUTOMOTIVE",
    97: "NIFTY HOUSING",
    98: "NIFTY INDIA CONSUMPTION",
    99: "NIFTY INDIA CORPORATE GROUP INDEX - ADITYA BIRLA GROUP",
    100: "NIFTY INDIA CORPORATE GROUP INDEX - MAHINDRA GROUP",
    101: "NIFTY INDIA CORPORATE GROUP INDEX - TATA GROUP",
    102: "NIFTY INDIA CORPORATE GROUP INDEX - TATA GROUP 25% CAP",
    103: "NIFTY INDIA DEFENCE",
    104: "NIFTY INDIA DIGITAL",
    105: "NIFTY INDIA INFRASTRUCTURE & LOGISTICS",
    106: "NIFTY INDIA INTERNET",
    107: "NIFTY INDIA MANUFACTURING",
    108: "NIFTY INDIA NEW AGE CONSUMPTION",
    109: "NIFTY INDIA RAILWAYS PSU",
    110: "NIFTY INDIA SELECT 5 CORPORATE GROUPS (MAATR)",
    111: "NIFTY INDIA TOURISM",
    112: "NIFTY INFRASTRUCTURE",
    113: "NIFTY IPO",
    114: "NIFTY MIDCAP LIQUID 15",
    115: "NIFTY MIDSMALL INDIA CONSUMPTION",
    116: "NIFTY MNC",
    117: "NIFTY MOBILITY",
    118: "NIFTY NON-CYCLICAL CONSUMER",
    119: "NIFTY PSE",
    120: "NIFTY REITS & INVITS",
    121: "NIFTY RURAL",
    122: "NIFTY SERVICES SECTOR",
    123: "NIFTY SHARIAH 25",
    124: "NIFTY SME EMERGE",
    125: "NIFTY TRANSPORTATION & LOGISTICS",
    126: "NIFTY WAVES",
    127: "NIFTY100 ENHANCED ESG",
    128: "NIFTY100 ESG",
    129: "NIFTY 100 ESG SECTOR LEADERS",
    130: "NIFTY100 LIQUID 15",
    131: "NIFTY50 SHARIAH",
    132: "NIFTY500 MULTICAP INDIA MANUFACTURING 50:30:20",
    133: "NIFTY500 MULTICAP INFRASTRUCTURE 50:30:20",
    134: "NIFTY500 SHARIAH",
    135: "NIFTY CEMENT"
}

def today_date_fetch():

  today = date.today()
  return today

today_date = today_date_fetch() #- timedelta(days=2) #Just dump this line of code to test for previous days
today_date = today_date.strftime("%d-%m-%Y")

def user_agent_and_impersonates_selection():

  #User-Agent List - Contain 5 Chrome Latest Desktop User Agents (Most Supported by curl_cffi library)
  User_Agent_List = [
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36",
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36",
  ]

  # Mapping Impersonates with each User Agent
  Impersonates_dictionary = {
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36": "chrome124",
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36": "chrome120",
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36": "chrome116",
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36": "chrome110",
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36": "chrome107",
  }
  
  user_agent_choice = random.choice(User_Agent_List)
  impersonate_choice = Impersonates_dictionary.get(user_agent_choice)

  return {"user_agent_choice":user_agent_choice, "impersonate_choice":impersonate_choice}

output_user_agent_and_impersonates_selection = user_agent_and_impersonates_selection()

def environment_setup_nse_main():
    
  # Mimic Behaviour of Real Human's System
    session = requests.Session() #Sets up a continuous relationship between user and the server
    headers = {
    "User-Agent": output_user_agent_and_impersonates_selection.get("user_agent_choice"),
    "Accept": "*/*",
    "Referer": "https://www.nseindia.com/"
    }

    # 2. Visiting home to get the required cookies
    session.get("https://www.nseindia.com", headers=headers, timeout=10)

    # Small pause to ensure cookies are registered
    cookies_sleeping_time_NSE = random.uniform(2, 5)
    time.sleep(cookies_sleeping_time_NSE)

    return {"session":session, "headers":headers}

output_environment_setup_nse_main = environment_setup_nse_main()

def nse_main_data_fetch(today_date, index_id):
    
    # The Actual Data Fetch
    encoded_index_long_name = urllib.parse.quote(index_dictionary.get(index_id))

    url = f"https://www.nseindia.com/api/historicalOR/indicesYield?indexType={encoded_index_long_name}&from={today_date}&to={today_date}"

    response = output_environment_setup_nse_main.get("session").get(url, headers = output_environment_setup_nse_main.get("headers"), impersonate = output_user_agent_and_impersonates_selection.get("impersonate_choice"), timeout=10)
    data_nse = response.json()
    data = data_nse.get("data")

    return {"response_code":response.status_code, "data":data}

def data_inject_nse_main_database(data_nse_value, index_id):

  # Checking for Empty Data - to inject NULL Values 

  for bracket in range (0, len(data_nse_value)):
    for key, value in data_nse_value[bracket].items():

      if isinstance(value, str):  # str datatypes will be stripped without any whitespaces e.g. " NIFTY 50 " to "NIFTY 50". No need to take int or float datatype into account as they strip automatically the whitespaces
           
        data_nse_value[bracket][key] = value.strip()
        value = data_nse_value[bracket][key]

      if value in empty_data_list:
        data_nse_value[bracket][key] = None

      elif value not in empty_data_list:

        if isinstance(value, float) or isinstance(value, int) or isinstance(value, str):

          try:
            data_nse_value[bracket][key] = Decimal(str(data_nse_value[bracket][key]))
          except:
            data_nse_value[bracket][key] = str(value)
      
        else:   
          continue

  for bracket_nse in range (0, len(data_nse_value)):

    date_program = data_nse_value[bracket_nse].get("IY_DT") #Fetched Date from Dictionary

    if date_program is None:
      continue

    date_program_datetime = datetime.strptime(date_program, "%d-%b-%Y") #Converting <str> datatype into datetime datatype
    date_program_formatted = date_program_datetime.strftime("%Y-%m-%d") #Changed the Format of Date to match PostgreSQL
    date_program_formatted_datetime = datetime.strptime(date_program_formatted, "%Y-%m-%d") #Converting <str> datatype into datetime datatype as changing format turns the date into <str> format
    date_program_formatted_datetime_onlydate = date_program_formatted_datetime.date() #Contains only the date part and not the time part

    #Formatting the Data into correct datatype
    pe_value = data_nse_value[bracket_nse].get("IY_PE")
    pb_value = data_nse_value[bracket_nse].get("IY_PB")
    div_yield_value = data_nse_value[bracket_nse].get("IY_DY")

    #Skipping Empty Fields
    if pe_value is None and pb_value is None and div_yield_value is None:
      continue
    
    #Finally Pushing Whole Data into the Database
    query = text("INSERT INTO valuation_metadata (index_id, trade_date, pe_ratio, pb_ratio, div_yield, last_updated_time) VALUES (:index_id, :trade_date, :pe_ratio, :pb_ratio, :div_yield, :last_updated_time)")
    conn.execute(query, {"index_id":index_id, "trade_date":date_program_formatted_datetime_onlydate, "pe_ratio":pe_value, "pb_ratio":pb_value, "div_yield":div_yield_value, "last_updated_time":datetime.now(ZoneInfo("Asia/Kolkata")).replace(tzinfo=None)})
    conn.commit()

  return data_nse_value

with output_database_engine_connection.connect() as conn:
    
  session = output_environment_setup_nse_main.get("session")
  headers = output_environment_setup_nse_main.get("headers")

  logger.info(f"")
  logger.info(f"╔══════════════════════════════════════════════════════════════════════╗")
  logger.info(f"║           NIFTY INDEX DAILY VALUATION FETCHER — EXECUTION LOG        ║")
  logger.info(f"╠══════════════════════════════════════════════════════════════════════╣")
  logger.info(f"║  RUN DATE      : {dt.now().strftime('%d-%b-%Y %I:%M:%S %p'):<52}║")
  logger.info(f"║  FETCH DATE    : {today_date:<52}║")
  logger.info(f"║  TOTAL INDICES : {str(len(index_dictionary)):<52}║")
  logger.info(f"║  DATA SOURCE   : NSE INDIA                                           ║")
  logger.info(f"╚══════════════════════════════════════════════════════════════════════╝")
  logger.info(f"")

  success_count = 0
  skipped_count = 0
  failed_count = 0
  skipped_indices = []
  start_time = dt.now()

  for index_id in range(1, len(index_dictionary) + 1):

    logger.info(f"┌──────────────────────────────────────────────────────────────────────┐")
    logger.info(f"│  INDEX ID     : {str(index_id):<54}│")
    logger.info(f"│  INDEX NAME   : {index_dictionary.get(index_id):<54}│")
    logger.info(f"└──────────────────────────────────────────────────────────────────────┘")

    output_nse_main_data_fetch = nse_main_data_fetch(today_date, index_id)

    if output_nse_main_data_fetch.get("response_code") == 200:

      if output_nse_main_data_fetch.get("data") is None:

        skipped_count += 1
        skipped_indices.append(f"{index_id}: {index_dictionary.get(index_id)} (No Data)")
        logger.info(f"  STATUS        : ⚠  DATA IS NONE — SKIPPED")
        logger.info(f"  RESPONSE CODE : 200 (Empty Payload)")
        logger.info(f"")
        
      elif output_nse_main_data_fetch.get("data") is not None:

        input_injection = output_nse_main_data_fetch.get("data")

        # ── EMPTY LIST CHECK ─────────────────────────────────────────────
        if len(input_injection) == 0:
            skipped_count += 1
            skipped_indices.append(f"{index_id}: {index_dictionary.get(index_id)} (Empty [])")
            logger.info(f"  STATUS        : ⚠  DATA IS EMPTY [] — SKIPPED")
            logger.info(f"  RESPONSE CODE : 200 (No Records Returned)")
            logger.info(f"")

        else:
          # ── INPUT BLOCK ──────────────────────────────────────────────────
          logger.info(f"  STATUS        : ✓  DATA RECEIVED — RESPONSE 200")
          logger.info(f"  RECORDS FOUND : {len(input_injection)}")
          logger.info(f"")
          logger.info(f"  ┌─ INPUT TO DATABASE {'─'*51}┐")
          for i, record in enumerate(input_injection):
            logger.info(f"  │  Record [{i+1}]")
            for key, value in record.items():
              logger.info(f"  │    {key:<35} : {value}")
          logger.info(f"  └{'─'*71}┘")
          logger.info(f"")

          # ── INJECTION ────────────────────────────────────────────────────
          output_injection = data_inject_nse_main_database(
            output_nse_main_data_fetch.get("data"), index_id
          )

          # ── OUTPUT BLOCK ─────────────────────────────────────────────────
          logger.info(f"  ┌─ OUTPUT AFTER CLEANING (INJECTED TO DB) {'─'*29}┐")
          for i, record in enumerate(output_injection):
            logger.info(f"  │  Record [{i+1}]")
            for key, value in record.items():
              logger.info(f"  │    {key:<35} : {value}")
          logger.info(f"  └{'─'*71}┘")
          logger.info(f"")

          success_count += 1
          last_updated = datetime.now(ZoneInfo("Asia/Kolkata")).replace(tzinfo=None)
          logger.info(f"  INJECTION     : ✓  COMMITTED TO valuation_metadata")
          logger.info(f"  LAST UPDATED  : {last_updated.strftime('%d-%b-%Y %I:%M:%S %p')}")
        
    elif output_nse_main_data_fetch.get("response_code") != 200:

      failed_count += 1
      logger.info(f"  STATUS        : ✗  FETCH FAILED")
      logger.info(f"  ERROR CODE    : {output_nse_main_data_fetch.get('response_code')}")
      logger.info(f"  ACTION        : PROCESS ABORTED")
      logger.info(f"")
      sys.exit()

    sleeping_time = random.uniform(1, 10)
    logger.info(f"  WAIT          : {sleeping_time:.4f} Seconds")
    time.sleep(sleeping_time)
    logger.info(f"")

  # ── SUMMARY BLOCK ────────────────────────────────────────────────────────
  logger.info(f"")
  logger.info(f"╔══════════════════════════════════════════════════════════════════════╗")
  logger.info(f"║                         EXECUTION SUMMARY                            ║")
  logger.info(f"╠══════════════════════════════════════════════════════════════════════╣")
  logger.info(f"║  COMPLETED AT  : {dt.now().strftime('%d-%b-%Y %I:%M:%S %p'):<52}║")
  end_time = dt.now()
  total_duration = end_time - start_time
  total_seconds = int(total_duration.total_seconds())
  hours = total_seconds // 3600
  minutes = (total_seconds % 3600) // 60
  seconds = total_seconds % 60
  logger.info(f"║  TIME TAKEN    : {f'{hours}h {minutes}m {seconds}s':<52}║")
  logger.info(f"║  TOTAL         : {str(len(index_dictionary)):<52}║")
  logger.info(f"║  ✓  INJECTED   : {str(success_count):<52}║")
  logger.info(f"║  ⚠  SKIPPED    : {str(skipped_count):<52}║")
  logger.info(f"║  ✗  FAILED     : {str(failed_count):<52}║")
  logger.info(f"╠══════════════════════════════════════════════════════════════════════╣")
  logger.info(f"║  SKIPPED INDEX DETAILS                                               ║")
  logger.info(f"╠══════════════════════════════════════════════════════════════════════╣")
  if skipped_indices:
    for entry in skipped_indices:
      logger.info(f"║  ⚠  {entry:<66}║")
  else:
    logger.info(f"║  ⚠  None — All indices processed successfully                        ║")
    logger.info(f"╚══════════════════════════════════════════════════════════════════════╝")
    logger.info(f"")
  