#Importing Important Libraries - Code Lines from 1 to 33 are those self made components that will be used in the whole program

import urllib.parse
import time
import json
import random
from sqlalchemy import text
import calendar
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from curl_cffi import requests
from decimal import Decimal
import sys
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
import os
import logging
from datetime import datetime as dt

load_dotenv()

# ── LOGGING SETUP ────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────

#For Null Values Check
empty_data_list = [None, "None", "0", 0, "-", "NaN", "Null", "NULL", "null", "none", "nan"] #Used only during data cleaning

# ── STARTUP BANNER ───────────────────────────────────────────────────────────

logger.info(f"")
logger.info(f"╔══════════════════════════════════════════════════════════════════════╗")
logger.info(f"║        NIFTY INDEX HISTORICAL DATA INGESTION — EXECUTION LOG         ║")
logger.info(f"╠══════════════════════════════════════════════════════════════════════╣")
logger.info(f"║  RUN TIMESTAMP : {dt.now().strftime('%d-%b-%Y %I:%M:%S %p'):<52}║")
logger.info(f"║  SCRIPT        : data_ingestion_price.py                             ║")
logger.info(f"║  PURPOSE       : Bulk Historical Price Ingestion (Rolling 30-Day)    ║")
logger.info(f"╚══════════════════════════════════════════════════════════════════════╝")
logger.info(f"")

# ─────────────────────────────────────────────────────────────────────────────

logger.info(f"  STEP 1        : Awaiting Index ID from user input...")
index_id = int(input("Enter Index ID: "))
logger.info(f"  INDEX ID      : {index_id}")
logger.info(f"")

def database_engine_connection():

  #Engine Connection Established
  database_password = os.getenv("database_password")
  DB_URL = f"postgresql://postgres:{database_password}@localhost:5432/index_value_strategy"
  engine = create_engine(DB_URL)
  return engine

logger.info(f"  STEP 2        : Establishing database engine connection...")
output_database_engine_connection = database_engine_connection()
logger.info(f"  DB ENGINE     : ✓  Connected to index_value_strategy")
logger.info(f"")

def index_name_fetcher(index_id):
  
  #Extract Info
  with output_database_engine_connection.connect() as conn: #Using the Connection done via Engine

    #Fetching Index_Long_Name and Trading_Index_Name
    query = text("SELECT index_id, index_long_name, trading_index_name FROM index_metadata WHERE index_id = :index_id_program")
    result = conn.execute(query, {"index_id_program": index_id}).fetchone()

    #Decode the Index Long Name
    index_long_name = result.index_long_name
    encoded_index_long_name = urllib.parse.quote(index_long_name)

    #Decode the Trading Index Name
    trading_index_name = result.trading_index_name
    encoded_trading_index_name = urllib.parse.quote(trading_index_name)

    return {"index_long_name":index_long_name, "trading_index_name":trading_index_name}

logger.info(f"  STEP 3        : Fetching index metadata from database...")
output_index_name_fetcher = index_name_fetcher(index_id)
logger.info(f"  INDEX LONG    : {output_index_name_fetcher.get('index_long_name')}")
logger.info(f"  TRADING NAME  : {output_index_name_fetcher.get('trading_index_name')}")
logger.info(f"")

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
    "User-Agent": user_agent_and_impersonates_selection().get("user_agent_choice"),
    "Accept": "*/*",
    "Referer": "https://www.nseindia.com/"
    }

    # 2. Visiting home to get the required cookies
    session.get("https://www.nseindia.com", headers=headers, timeout=10)

    # Small pause to ensure cookies are registered
    cookies_sleeping_time_NSE = random.uniform(2, 5)
    time.sleep(cookies_sleeping_time_NSE)

    return {"session":session, "headers":headers}

def environment_setup_nifty_indices():

    url = "https://www.niftyindices.com/Backpage.aspx/getHistoricaldatatabletoString"
    session = requests.Session() 

    # These headers are mandatory for Nifty Indices backend
    headers = {
    "User-Agent": user_agent_and_impersonates_selection().get("user_agent_choice"),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Content-Type": "application/json; charset=UTF-8", # Mandatory for POST
    "Origin": "https://www.niftyindices.com",
    "Referer": "https://www.niftyindices.com/reports/historical-data",
    "X-Requested-With": "XMLHttpRequest"
    }

    # Visiting home to get the required cookies
    session.get("https://www.niftyindices.com/", headers=headers, impersonate=user_agent_and_impersonates_selection().get("impersonate_choice"), timeout=10)

    # Small pause to ensure cookies are registered
    cookies_sleeping_time = random.uniform(2, 5)
    time.sleep(cookies_sleeping_time)

    return {"session":session, "headers":headers, "url":url}

def nifty_indices_data_fetch(acceptable_start_date, acceptable_rolling_date):

  payload = f'{{"name":"{output_index_name_fetcher.get("index_long_name")}","startDate":"{acceptable_start_date}","endDate":"{acceptable_rolling_date}","indexName":"{output_index_name_fetcher.get("index_long_name")}"}}'

  cinfo_data ={"cinfo":payload}

  response = requests.post(output_environment_setup_nifty_indices.get("url"), headers=output_environment_setup_nifty_indices.get("headers"), json=cinfo_data, timeout=10)
 
  response.encoding = 'utf-8-sig'

  data_niftyindices = response.json()
  data_niftyindices_value_dummy = data_niftyindices.get('d')
  data = json.loads(data_niftyindices_value_dummy)

  return {"response_code":response.status_code, "data":data}

def nse_main_data_fetch(acceptable_start_date, acceptable_rolling_date):
    
    # The Actual Data Fetch
    encoded_index_long_name = urllib.parse.quote(output_index_name_fetcher.get("index_long_name"))

    url = f"https://www.nseindia.com/api/historicalOR/indicesHistory?indexType={encoded_index_long_name}&from={acceptable_start_date}&to={acceptable_rolling_date}"

    response = output_environment_setup_nse_main.get("session").get(url, headers = output_environment_setup_nse_main.get("headers"), impersonate = output_user_agent_and_impersonates_selection.get("impersonate_choice"), timeout=10)
    data_nse = response.json()
    data = data_nse.get("data")

    return {"response_code":response.status_code, "data":data}

def data_inject_nse_main_database(data_nse_value, index_id):

  for bracket in range (0, len(data_nse_value)):
    for key, value in data_nse_value[bracket].items():

      if isinstance(value, str):
           
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

    date_program = data_nse_value[bracket_nse].get("EOD_TIMESTAMP")
   
    if date_program is None:
      continue

    date_program_datetime = datetime.strptime(date_program, "%d-%b-%Y")
    date_program_formatted = date_program_datetime.strftime("%Y-%m-%d")
    date_program_formatted_datetime = datetime.strptime(date_program_formatted, "%Y-%m-%d")
    date_program_formatted_datetime_onlydate = date_program_formatted_datetime.date()

    current_record_count = 0
    current_record_parameters = ["EOD_OPEN_INDEX_VAL", "EOD_HIGH_INDEX_VAL", "EOD_CLOSE_INDEX_VAL", "EOD_LOW_INDEX_VAL", "HIT_TURN_OVER", "HIT_TRADED_QTY", "EOD_TIMESTAMP"]

    for item in data_nse_value[bracket_nse]:
      if data_nse_value[bracket_nse].get(item) != None and item in current_record_parameters:
          current_record_count += 1
      else:
        continue

    query = text("SELECT * FROM price_metadata WHERE index_id = :index_id AND trade_date = :date_program_formatted_datetime_onlydate;")
    execute_query = conn.execute(query, {"index_id":index_id, "date_program_formatted_datetime_onlydate": date_program_formatted_datetime_onlydate})
    readable_data = execute_query.mappings().fetchall()

    #Counting already present parameters data count

    previous_record_count = 0
    previous_record_parameters = ["trade_date", "open_price", "high_price", "low_price", "close_price", "shares_traded", "turnover_inr_cr"]

    for single_list_item in readable_data: #The readable data is actually just a list containing a single dictionary with all the respective row items taken from the required table
      for item in single_list_item:
        if single_list_item.get(item) != None:
          if item in previous_record_parameters:
            previous_record_count += 1
          else:
            continue
        else:
          continue

    open_index_value = data_nse_value[bracket_nse].get("EOD_OPEN_INDEX_VAL")
    high_index_value = data_nse_value[bracket_nse].get("EOD_HIGH_INDEX_VAL")
    low_index_value = data_nse_value[bracket_nse].get("EOD_LOW_INDEX_VAL")
    close_index_value = data_nse_value[bracket_nse].get("EOD_CLOSE_INDEX_VAL")
    shares_traded_number = data_nse_value[bracket_nse].get("HIT_TRADED_QTY")
    turnover_inr_cr_value = data_nse_value[bracket_nse].get("HIT_TURN_OVER")

    if open_index_value is None and high_index_value is None and low_index_value is None and close_index_value is None and shares_traded_number is None and turnover_inr_cr_value is None:
      continue

    if previous_record_count > current_record_count:
      continue

    elif previous_record_count < current_record_count or previous_record_count == current_record_count:

      if previous_record_count == 0:
      
        query = text("INSERT INTO price_metadata (index_id, trade_date, open_price, high_price, low_price, close_price, last_updated_time, shares_traded, turnover_inr_cr) VALUES (:index_id, :trade_date, :open_price, :high_price, :low_price, :close_price, :last_updated_time, :shares_traded, :turnover_inr_cr)")
        conn.execute(query, {"index_id":index_id, "trade_date":date_program_formatted_datetime_onlydate, "open_price":open_index_value, "high_price":high_index_value, "low_price":low_index_value, "close_price":close_index_value, "last_updated_time":datetime.now(ZoneInfo("Asia/Kolkata")).replace(tzinfo=None), "shares_traded":shares_traded_number, "turnover_inr_cr":turnover_inr_cr_value})
        conn.commit()
 
      elif previous_record_count > 0:

        query = text("UPDATE price_metadata SET open_price = :open_price, high_price = :high_price, low_price = :low_price, close_price = :close_price, last_updated_time = :last_updated_time, shares_traded = :shares_traded, turnover_inr_cr = :turnover_inr_cr WHERE index_id = :index_id AND trade_date = :trade_date")
        conn.execute(query, {"index_id":index_id, "trade_date":date_program_formatted_datetime_onlydate, "open_price":open_index_value, "high_price":high_index_value, "low_price":low_index_value, "close_price":close_index_value, "last_updated_time":datetime.now(ZoneInfo("Asia/Kolkata")).replace(tzinfo=None), "shares_traded":shares_traded_number, "turnover_inr_cr":turnover_inr_cr_value})
        conn.commit()

  return data_nse_value

def data_inject_nifty_indices_database(data_nifty_indices_value, index_id):

  for bracket in range (0, len(data_nifty_indices_value)):
    for key, value in data_nifty_indices_value[bracket].items():

      if isinstance(value, str):
           
        data_nifty_indices_value[bracket][key] = value.strip()
        value = data_nifty_indices_value[bracket][key]

      if value in empty_data_list:
        data_nifty_indices_value[bracket][key] = None

      elif value not in empty_data_list:

        if isinstance(value, float) or isinstance(value, int) or isinstance(value, str):

          try:
            data_nifty_indices_value[bracket][key] = Decimal(str(data_nifty_indices_value[bracket][key]))
          except:
            data_nifty_indices_value[bracket][key] = str(value)
      
        else:   
          continue

  for bracket_nse in range (0, len(data_nifty_indices_value)):

    trade_date_niftyindices = data_nifty_indices_value[bracket_nse].get("HistoricalDate")

    if trade_date_niftyindices is None:
      continue

    trade_date_niftyindices_datetime_datatype = datetime.strptime(trade_date_niftyindices, "%d %b %Y")
    trade_date_data_formatted = trade_date_niftyindices_datetime_datatype.strftime("%Y-%m-%d")
    final_trade_date = datetime.strptime(trade_date_data_formatted, "%Y-%m-%d")

    current_record_count = 0
    current_record_parameters = ["HistoricalDate", "OPEN", "HIGH", "LOW", "CLOSE"]

    for item in data_nifty_indices_value[bracket_nse]:
      if data_nifty_indices_value[bracket_nse].get(item) != None and item in current_record_parameters:
          current_record_count += 1
      else:
        continue

    query = text("SELECT * FROM price_metadata WHERE index_id = :index_id AND trade_date = :final_trade_date;")
    execute_query = conn.execute(query, {"index_id":index_id, "date_program_formatted_datetime_onlydate": final_trade_date})
    readable_data = execute_query.mappings().fetchall()

    #Counting already present parameters data count

    previous_record_count = 0
    previous_record_parameters = ["trade_date", "open_price", "high_price", "low_price", "close_price", "shares_traded", "turnover_inr_cr"]

    for single_list_item in readable_data: #The readable data is actually just a list containing a single dictionary with all the respective row items taken from the required table
      for item in single_list_item:
        if single_list_item.get(item) != None:
          if item in previous_record_parameters:
            previous_record_count += 1
          else:
            continue
        else:
          continue

    open_price_niftyindices = data_nifty_indices_value[bracket_nse].get("OPEN")
    high_price_niftyindices = data_nifty_indices_value[bracket_nse].get("HIGH")
    low_price_niftyindices = data_nifty_indices_value[bracket_nse].get("LOW")
    close_price_niftyindices = data_nifty_indices_value[bracket_nse].get("CLOSE")

    if open_price_niftyindices is None and high_price_niftyindices is None and low_price_niftyindices is None and close_price_niftyindices is None:
      continue

    if previous_record_count > current_record_count:
      continue

    elif previous_record_count < current_record_count or previous_record_count == current_record_count:

      if previous_record_count == 0:
      
        query = text("INSERT INTO price_metadata (index_id, trade_date, open_price, high_price, low_price, close_price, last_updated_time, shares_traded, turnover_inr_cr) VALUES (:index_id, :trade_date, :open_price, :high_price, :low_price, :close_price, :last_updated_time, :shares_traded, :turnover_inr_cr)")
        conn.execute(query, {"index_id":index_id, "trade_date":final_trade_date, "open_price":open_price_niftyindices, "high_price":high_price_niftyindices, "low_price":low_price_niftyindices, "close_price":close_price_niftyindices, "last_updated_time":datetime.now(ZoneInfo("Asia/Kolkata")).replace(tzinfo=None), "shares_traded":None, "turnover_inr_cr":None})
        conn.commit()

      elif previous_record_count > 0:

        query = text("UPDATE price_metadata SET open_price = :open_price, high_price = :high_price, low_price = :low_price, close_price = :close_price, last_updated_time = :last_updated_time, shares_traded = :shares_traded, turnover_inr_cr = :turnover_inr_cr WHERE index_id = :index_id AND trade_date = :trade_date")
        conn.execute(query, {"index_id":index_id, "trade_date":final_trade_date, "open_price":open_price_niftyindices, "high_price":high_price_niftyindices, "low_price":low_price_niftyindices, "close_price":close_price_niftyindices, "last_updated_time":datetime.now(ZoneInfo("Asia/Kolkata")).replace(tzinfo=None), "shares_traded":None, "turnover_inr_cr":None})
        conn.commit()

  return data_nifty_indices_value

# ── USER CONFIRMATION BLOCK ──────────────────────────────────────────────────

logger.info(f"┌──────────────────────────────────────────────────────────────────────┐")
logger.info(f"│                        INDEX CONFIRMATION                            │")
logger.info(f"├──────────────────────────────────────────────────────────────────────┤")
logger.info(f"│  INDEX ID     : {str(index_id):<54}│")
logger.info(f"│  INDEX LONG   : {output_index_name_fetcher.get('index_long_name'):<54}│")
logger.info(f"│  TRADING NAME : {output_index_name_fetcher.get('trading_index_name'):<54}│")
logger.info(f"└──────────────────────────────────────────────────────────────────────┘")
logger.info(f"")

logger.info(f"  STEP 4        : Awaiting data source selection from user...")
data_source = str(input("Enter Data Source Preference (NSE INDIA/NIFTY INDICES): "))
logger.info(f"  DATA SOURCE   : {data_source}")
logger.info(f"")

logger.info(f"  STEP 5        : Awaiting green flag from user...")
proceed = int(input("Enter 1 to Proceed and 0 to Abort: "))
logger.info(f"")

if proceed == 1:

  # Input Starting Date
  logger.info(f"  STEP 6        : Awaiting date range input from user...")
  starting_day = int(input("Enter Starting Day: "))
  starting_month = int(input("Enter Starting Month: "))
  starting_year = int(input("Enter Starting Year: "))
  start_date = datetime(starting_year, starting_month, starting_day)
  origin_date = start_date

  ending_day = int(input("Enter Ending Day: "))
  ending_month = int(input("Enter Ending Month: "))
  ending_year = int(input("Enter Ending Year: "))
  end_date = datetime(ending_year, ending_month, ending_day)

  # Rolling Date Calculation
  rolling_date = start_date + timedelta(days=30)

  logger.info(f"")
  logger.info(f"┌──────────────────────────────────────────────────────────────────────┐")
  logger.info(f"│                         INGESTION PARAMETERS                         │")
  logger.info(f"├──────────────────────────────────────────────────────────────────────┤")
  logger.info(f"│  DATA SOURCE  : {data_source:<54}│")
  logger.info(f"│  START DATE   : {start_date.strftime('%d-%b-%Y'):<54}│")
  logger.info(f"│  END DATE     : {end_date.strftime('%d-%b-%Y'):<54}│")
  logger.info(f"│  WINDOW SIZE  : 30 Days (Rolling)                                    │")
  logger.info(f"└──────────────────────────────────────────────────────────────────────┘")
  logger.info(f"")

  # ── COUNTERS ──────────────────────────────────────────────────────────────
  success_count = 0
  skipped_count = 0
  failed_count = 0
  batch_number = 0
  latest_record_injection_date = 0
  start_time = dt.now()
  failed_batches = []   # stores (start, end) date strings for failed batches
  skipped_batches = []  # stores (start, end) date strings for skipped batches
  total_api_records = 0       # total records returned by API across all batches
  total_injected_records = 0  # total records actually inserted into DB after cleaning

  with output_database_engine_connection.connect() as conn:

    logger.info(f"  DB CONN       : ✓  Connection Established Successfully")
    logger.info(f"")
 
    if data_source == "NSE INDIA":

      logger.info(f"  STEP 7        : Setting up NSE INDIA session & cookies...")
      output_environment_setup_nse_main = environment_setup_nse_main()
      session = output_environment_setup_nse_main.get("session")
      headers = output_environment_setup_nse_main.get("headers")
      logger.info(f"  SESSION       : ✓  NSE INDIA session initialized")
      logger.info(f"  USER AGENT    : {output_user_agent_and_impersonates_selection.get('impersonate_choice')}")
      logger.info(f"")
      logger.info(f"  STEP 8        : Beginning rolling batch ingestion from NSE INDIA...")
      logger.info(f"")

      while start_date <= rolling_date:

        batch_number += 1
        acceptable_start_date = start_date.strftime("%d-%m-%Y")
        acceptable_rolling_date = rolling_date.strftime("%d-%m-%Y")

        logger.info(f"┌──────────────────────────────────────────────────────────────────────┐")
        logger.info(f"│  BATCH        : #{str(batch_number):<53}│")
        logger.info(f"│  WINDOW START : {acceptable_start_date:<54}│")
        logger.info(f"│  WINDOW END   : {acceptable_rolling_date:<54}│")
        logger.info(f"│  SOURCE       : NSE INDIA                                            │")
        logger.info(f"└──────────────────────────────────────────────────────────────────────┘")

        output_nse_main_data_fetch = nse_main_data_fetch(acceptable_start_date, acceptable_rolling_date)
    
        if output_nse_main_data_fetch.get("response_code") == 200:

          data_received = output_nse_main_data_fetch.get("data")

          if data_received is None or len(data_received) == 0:

            skipped_count += 1
            skipped_batches.append((acceptable_start_date, acceptable_rolling_date))
            logger.info(f"  STATUS        : ⚠  SKIPPED — No records in window (Response 200, empty data)")
            logger.info(f"")

          else:

            # ── INJECTION ────────────────────────────────────────────────
            output_injection = data_inject_nse_main_database(data_received)

            success_count += 1
            total_api_records += len(data_received)
            total_injected_records += len(output_injection)
            last_updated = datetime.now(ZoneInfo("Asia/Kolkata"))
            logger.info(f"  STATUS        : ✓  INJECTED TO DB — Cleaned & committed to price_metadata")
            logger.info(f"  RECORDS       : {len(data_received)} record(s) returned by API")
            logger.info(f"")

          # Resetting the Dates
          start_date = rolling_date + timedelta(days=1)
          rolling_date = min(start_date + timedelta(days=30), end_date)

          if rolling_date != end_date:
            sleeping_time = random.uniform(1, 10)
            logger.info(f"  WAIT          : {sleeping_time:.4f} Seconds")
            time.sleep(sleeping_time)
          
          logger.info(f"")

        elif output_nse_main_data_fetch.get("response_code") != 200:
          failed_count += 1
          failed_batches.append((acceptable_start_date, acceptable_rolling_date))
          logger.info(f"  STATUS        : ✗  FETCH FAILED")
          logger.info(f"  ERROR CODE    : {output_nse_main_data_fetch.get('response_code')}")
          logger.info(f"  ACTION        : PROCESS ABORTED")
          logger.info(f"")
          break

      # ── UPDATE index_metadata ────────────────────────────────────────────
      source = "NSE INDIA"
      query = text("UPDATE index_metadata SET source = :source, last_updated_time = :last_updated_time, data_origin_date = :data_origin_date WHERE index_id = :index_id")
      conn.execute(query, {"source":source, "index_id":index_id, "last_updated_time":datetime.now(ZoneInfo("Asia/Kolkata")), "data_origin_date":origin_date})
      conn.commit()
      logger.info(f"  METADATA      : ✓  index_metadata Updated (source, last_updated_time, data_origin_date)")
      logger.info(f"")

    elif data_source == "NIFTY INDICES":

      logger.info(f"  STEP 7        : Setting up NIFTY INDICES session & cookies...")
      output_environment_setup_nifty_indices = environment_setup_nifty_indices()
      session = output_environment_setup_nifty_indices.get("session")
      headers = output_environment_setup_nifty_indices.get("headers")
      url = output_environment_setup_nifty_indices.get("url")
      logger.info(f"  SESSION       : ✓  NIFTY INDICES session initialized")
      logger.info(f"  USER AGENT    : {output_user_agent_and_impersonates_selection.get('impersonate_choice')}")
      logger.info(f"")
      logger.info(f"  STEP 8        : Beginning rolling batch ingestion from NIFTY INDICES...")
      logger.info(f"")

      while start_date <= rolling_date:

        batch_number += 1
        acceptable_start_date = start_date.strftime("%d-%b-%Y")
        acceptable_rolling_date = rolling_date.strftime("%d-%b-%Y")

        logger.info(f"┌──────────────────────────────────────────────────────────────────────┐")
        logger.info(f"│  BATCH        : #{str(batch_number):<53}│")
        logger.info(f"│  WINDOW START : {acceptable_start_date:<54}│")
        logger.info(f"│  WINDOW END   : {acceptable_rolling_date:<54}│")
        logger.info(f"│  SOURCE       : NIFTY INDICES                                        │")
        logger.info(f"└──────────────────────────────────────────────────────────────────────┘")

        output_nifty_indices_data_fetch = nifty_indices_data_fetch(acceptable_start_date, acceptable_rolling_date)
    
        if output_nifty_indices_data_fetch.get("response_code") == 200:

          data_received = output_nifty_indices_data_fetch.get("data")

          if data_received is None or len(data_received) == 0:

            skipped_count += 1
            skipped_batches.append((acceptable_start_date, acceptable_rolling_date))
            logger.info(f"  STATUS        : ⚠  SKIPPED — No records in window (Response 200, empty data)")
            logger.info(f"")

          else:

            # ── INJECTION ────────────────────────────────────────────────
            output_injection = data_inject_nifty_indices_database(data_received)

            success_count += 1
            total_api_records += len(data_received)
            total_injected_records += len(output_injection)
            last_updated = datetime.now(ZoneInfo("Asia/Kolkata"))
            logger.info(f"  STATUS        : ✓  INJECTED TO DB — Cleaned & committed to price_metadata")
            logger.info(f"  RECORDS       : {len(data_received)} record(s) returned by API")
            logger.info(f"")

          # Resetting the Dates
          start_date = rolling_date + timedelta(days=1)
          rolling_date = min(start_date + timedelta(days=30), end_date)

          if rolling_date != end_date:
            sleeping_time = random.uniform(1, 10)
            logger.info(f"  WAIT          : {sleeping_time:.4f} Seconds")
            time.sleep(sleeping_time)
          
          logger.info(f"")
      
        elif output_nifty_indices_data_fetch.get("response_code") != 200:
          failed_count += 1
          failed_batches.append((acceptable_start_date, acceptable_rolling_date))
          logger.info(f"  STATUS        : ✗  FETCH FAILED")
          logger.info(f"  ERROR CODE    : {output_nifty_indices_data_fetch.get('response_code')}")
          logger.info(f"  ACTION        : PROCESS ABORTED")
          logger.info(f"")
          break

      # ── UPDATE index_metadata ────────────────────────────────────────────
      source = "NIFTY INDICES"
      query = text("UPDATE index_metadata SET source = :source, last_updated_time = :last_updated_time, data_origin_date = :data_origin_date WHERE index_id = :index_id")
      conn.execute(query, {"source":source, "index_id":index_id, "last_updated_time":datetime.now(ZoneInfo("Asia/Kolkata")), "data_origin_date":origin_date})
      conn.commit()
      logger.info(f"  METADATA      : ✓  index_metadata Updated (source, last_updated_time, data_origin_date)")
      logger.info(f"")

  # ── FINAL SUMMARY ──────────────────────────────────────────────────────────
  end_time = dt.now()
  total_duration = end_time - start_time
  total_seconds = int(total_duration.total_seconds())
  hours = total_seconds // 3600
  minutes = (total_seconds % 3600) // 60
  seconds = total_seconds % 60

  logger.info(f"")
  logger.info(f"╔══════════════════════════════════════════════════════════════════════╗")
  logger.info(f"║                         EXECUTION SUMMARY                            ║")
  logger.info(f"╠══════════════════════════════════════════════════════════════════════╣")
  logger.info(f"║  INDEX ID      : {str(index_id):<52}║")
  logger.info(f"║  INDEX NAME    : {output_index_name_fetcher.get('index_long_name'):<52}║")
  logger.info(f"║  DATA SOURCE   : {data_source:<52}║")
  logger.info(f"╠══════════════════════════════════════════════════════════════════════╣")
  logger.info(f"║  COMPLETED AT  : {dt.now().strftime('%d-%b-%Y %I:%M:%S %p'):<52}║")
  logger.info(f"║  TIME TAKEN    : {f'{hours}h {minutes}m {seconds}s':<52}║")
  logger.info(f"╠══════════════════════════════════════════════════════════════════════╣")
  logger.info(f"║  TOTAL BATCHES : {str(batch_number):<52}║")
  logger.info(f"║  ✓  INJECTED   : {str(success_count):<52}║")
  logger.info(f"║  ⚠  SKIPPED    : {str(skipped_count):<52}║")
  logger.info(f"║  ✗  FAILED     : {str(failed_count):<52}║")
  logger.info(f"╠══════════════════════════════════════════════════════════════════════╣")
  logger.info(f"║  API RECORDS   : {str(total_api_records):<52}║")
  logger.info(f"║  DB INSERTED   : {str(total_injected_records):<52}║")
  logger.info(f"╠══════════════════════════════════════════════════════════════════════╣")
  if failed_count == 0 and skipped_count == 0:
    logger.info(f"║  RESULT        : ✓  ALL BATCHES COMPLETED SUCCESSFULLY               ║")
  elif failed_count > 0:
    logger.info(f"║  RESULT        : ✗  PROCESS ENCOUNTERED FAILURES — REVIEW LOGS       ║")
  else:
    logger.info(f"║  RESULT        : ⚠  COMPLETED WITH SKIPPED WINDOWS                   ║")
  logger.info(f"╚══════════════════════════════════════════════════════════════════════╝")

  if failed_batches:
    logger.info(f"")
    logger.info(f"  ┌─ FAILED BATCH DATE RANGES {'─'*44}┐")
    for i, (s, e) in enumerate(failed_batches, 1):
      logger.info(f"  │  [{i}]  {s}  →  {e:<47}│")
    logger.info(f"  └{'─'*71}┘")

  if skipped_batches:
    logger.info(f"")
    logger.info(f"  ┌─ SKIPPED BATCH DATE RANGES {'─'*43}┐")
    for i, (s, e) in enumerate(skipped_batches, 1):
      logger.info(f"  │  [{i}]  {s}  →  {e:<47}│")
    logger.info(f"  └{'─'*71}┘")

  logger.info(f"")

elif proceed == 0:
  logger.info(f"  ACTION        : ✗  USER ABORTED — Process terminated by user input.")
  logger.info(f"")
  sys.exit()