#Importing Important Libraries - Code Lines from 1 to 33 are those self made components that will be used in the whole program

import psycopg2
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
import pandas_market_calendars as market_calendars

# Primary calendar
nse = market_calendars.get_calendar('XNSE')        # NSE
bse = market_calendars.get_calendar('XBOM')        # BSE

load_dotenv()

# ── LOGGING SETUP ────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

LOG_WIDTH = 92

def log_blank():
  logger.info("")

def log_rule(title=None):
  if title:
    logger.info("=" * LOG_WIDTH)
    logger.info(title.center(LOG_WIDTH))
    logger.info("=" * LOG_WIDTH)
  else:
    logger.info("-" * LOG_WIDTH)

def log_kv(label, value):
  logger.info(f"  {label:<18}: {value}")

def log_step(step_number, message):
  log_rule(f"STEP {step_number} - {message}")

def log_batch_header(batch_number, source, start_value, end_value):
  log_rule(f"BATCH #{batch_number} | {source}")
  log_kv("Window start", start_value)
  log_kv("Window end", end_value)
  log_kv("Started at", dt.now().strftime('%Y-%m-%d %H:%M:%S'))

def log_record_sample(source, records):
  if records is None:
    log_kv(f"{source} sample", "No payload returned")
    return
  if len(records) == 0:
    log_kv(f"{source} sample", "Empty payload")
    return
  first_record = records[0]
  if isinstance(first_record, dict):
    preview_keys = list(first_record.keys())[:8]
    preview = {key: first_record.get(key) for key in preview_keys}
    log_kv(f"{source} sample", preview)
  else:
    log_kv(f"{source} sample", first_record)

def log_date_list(label, values):
  if not values:
    log_kv(label, "None")
    return
  log_kv(label, values)

# ─────────────────────────────────────────────────────────────────────────────

#For Null Values Check
empty_data_list = [None, "None", "0", 0, "-", "NaN", "Null", "NULL", "null", "none", "nan"] #Used only during data cleaning
latest_injection_summary = {}

# ── STARTUP BANNER ───────────────────────────────────────────────────────────

logger.info(f"")
logger.info(f"╔══════════════════════════════════════════════════════════════════════╗")
logger.info(f"║   NIFTY INDEX HISTORICAL VALUATION DATA INGESTION — EXECUTION LOG         ║")
logger.info(f"╠══════════════════════════════════════════════════════════════════════╣")
logger.info(f"║  RUN TIMESTAMP : {dt.now().strftime('%d-%b-%Y %I:%M:%S %p'):<52}║")
logger.info(f"║  SCRIPT        : valuation_data_ingestion.py                             ║")
logger.info(f"║  PURPOSE       : Bulk Historical Valuation Data Ingestion (Rolling 30-Day)    ║")
logger.info(f"╚══════════════════════════════════════════════════════════════════════╝")
logger.info(f"")

# ─────────────────────────────────────────────────────────────────────────────

log_step(1, "Awaiting index id from user input")
logger.info(f"  STEP 1        : Awaiting Index ID from user input...")
index_id = int(input("Enter Index ID: "))
log_kv("Index ID", index_id)
logger.info(f"  INDEX ID      : {index_id}")
logger.info(f"")

def database_engine_connection():

  #Engine Connection Established
  database_password = os.getenv("database_password_cockroach_db")
  log_kv("DB password env", "present" if database_password else "missing")
  DB_URL = f"cockroachdb://postgres:{database_password}@megadox-27437.j77.aws-ap-south-1.cockroachlabs.cloud:26257/index_value_strategy?sslmode=verify-full"
  log_kv("DB target", "cockroachdb://postgres:***@megadox-27437.j77.aws-ap-south-1.cockroachlabs.cloud:26257/index_value_strategy?sslmode=verify-full")
  engine = create_engine(DB_URL)
  log_kv("Engine object", "created")
  return engine

log_step(2, "Establishing database engine connection")
logger.info(f"  STEP 2        : Establishing database engine connection...")
output_database_engine_connection = database_engine_connection()
logger.info(f"  DB ENGINE     : ✓  Connected to index_value_strategy")
logger.info(f"")

def index_name_fetcher(index_id):
  
  #Extract Info
  with output_database_engine_connection.connect() as conn: #Using the Connection done via Engine
    log_kv("Metadata lookup", f"index_id={index_id}")

    #Fetching Index_Long_Name and Trading_Index_Name
    query = text("SELECT index_id, index_long_name, trading_index_name FROM index_metadata WHERE index_id = :index_id_program")
    result = conn.execute(query, {"index_id_program": index_id}).fetchone()

    #Decode the Index Long Name
    index_long_name = result.index_long_name
    encoded_index_long_name = urllib.parse.quote(index_long_name)
    log_kv("Encoded long name", encoded_index_long_name)

    #Decode the Trading Index Name
    trading_index_name = result.trading_index_name
    encoded_trading_index_name = urllib.parse.quote(trading_index_name)
    log_kv("Encoded trading", encoded_trading_index_name)

    return {"index_long_name":index_long_name, "trading_index_name":trading_index_name}

log_step(3, "Fetching index metadata from database")
logger.info(f"  STEP 3        : Fetching index metadata from database...")
output_index_name_fetcher = index_name_fetcher(index_id)
log_kv("Index long name", output_index_name_fetcher.get('index_long_name'))
log_kv("Trading name", output_index_name_fetcher.get('trading_index_name'))
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
  log_kv("UA selected", impersonate_choice)

  return {"user_agent_choice":user_agent_choice, "impersonate_choice":impersonate_choice}

output_user_agent_and_impersonates_selection = user_agent_and_impersonates_selection()

def environment_setup_nse_main():
    
  # Mimic Behaviour of Real Human's System
    session = requests.Session() #Sets up a continuous relationship between user and the server
    selected_identity = user_agent_and_impersonates_selection()
    headers = {
    "User-Agent": selected_identity.get("user_agent_choice"),
    "Accept": "*/*",
    "Referer": "https://www.nseindia.com/"
    }
    log_kv("NSE session", "requests.Session created")
    log_kv("NSE impersonate", selected_identity.get("impersonate_choice"))
    log_kv("NSE referer", headers.get("Referer"))

    # 2. Visiting home to get the required cookies
    bootstrap_response = session.get("https://www.nseindia.com", headers=headers, timeout=10)
    log_kv("NSE cookie prime", f"HTTP {bootstrap_response.status_code}")

    # Small pause to ensure cookies are registered
    cookies_sleeping_time_NSE = random.uniform(2, 5)
    log_kv("NSE cookie wait", f"{cookies_sleeping_time_NSE:.4f} seconds")
    time.sleep(cookies_sleeping_time_NSE)

    return {"session":session, "headers":headers}

def environment_setup_nifty_indices():

    url = "https://www.niftyindices.com/Backpage.aspx/getpepbHistoricaldataDBtoString"
    session = requests.Session() 
    selected_identity = user_agent_and_impersonates_selection()

    # These headers are mandatory for Nifty Indices backend
    headers = {
    "User-Agent": selected_identity.get("user_agent_choice"),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Content-Type": "application/json; charset=UTF-8", # Mandatory for POST
    "Origin": "https://www.niftyindices.com",
    "Referer": "https://www.niftyindices.com/reports/historical-data",
    "X-Requested-With": "XMLHttpRequest"
    }
    log_kv("NI endpoint", url)
    log_kv("NI session", "requests.Session created")
    log_kv("NI impersonate", selected_identity.get("impersonate_choice"))
    log_kv("NI origin", headers.get("Origin"))

    # Visiting home to get the required cookies
    bootstrap_response = session.get("https://www.niftyindices.com/", headers=headers, impersonate=selected_identity.get("impersonate_choice"), timeout=10)
    log_kv("Nifty Indices cookie prime", f"HTTP {bootstrap_response.status_code}")

    # Small pause to ensure cookies are registered
    cookies_sleeping_time = random.uniform(2, 5)
    log_kv("Nifty Indices cookie wait", f"{cookies_sleeping_time:.4f} seconds")
    time.sleep(cookies_sleeping_time)

    return {"session":session, "headers":headers, "url":url}

def nifty_indices_data_fetch(acceptable_start_date, acceptable_rolling_date):

  payload = f'{{"name":"{output_index_name_fetcher.get("index_long_name")}","startDate":"{acceptable_start_date}","endDate":"{acceptable_rolling_date}","indexName":"{output_index_name_fetcher.get("index_long_name")}"}}'

  cinfo_data ={"cinfo":payload}
  request_start = dt.now()
  log_kv("Fetch source", "NIFTY INDICES")
  log_kv("Fetch endpoint", output_environment_setup_nifty_indices.get("url"))
  log_kv("Fetch payload", payload)

  response = requests.post(output_environment_setup_nifty_indices.get("url"), headers=output_environment_setup_nifty_indices.get("headers"), json=cinfo_data, timeout=10)
 
  response.encoding = 'utf-8-sig'

  data_niftyindices = response.json()
  data_niftyindices_value_dummy = data_niftyindices.get('d')
  data = json.loads(data_niftyindices_value_dummy)
  request_duration = (dt.now() - request_start).total_seconds()
  log_kv("Fetch status", response.status_code)
  log_kv("Fetch duration", f"{request_duration:.3f} seconds")
  log_kv("Records parsed", 0 if data is None else len(data))
  log_record_sample("NI", data)

  return {"response_code":response.status_code, "data":data}

def nse_main_data_fetch(acceptable_start_date, acceptable_rolling_date):
    
    # The Actual Data Fetch
    encoded_index_long_name = urllib.parse.quote(output_index_name_fetcher.get("index_long_name"))

    url = f"https://www.nseindia.com/api/historicalOR/indicesYield?indexType={encoded_index_long_name}&from={acceptable_start_date}&to={acceptable_rolling_date}"
    request_start = dt.now()
    log_kv("Fetch source", "NSE INDIA")
    log_kv("Fetch endpoint", url)

    response = output_environment_setup_nse_main.get("session").get(url, headers = output_environment_setup_nse_main.get("headers"), impersonate = output_user_agent_and_impersonates_selection.get("impersonate_choice"), timeout=10)
    data_nse = response.json()
    data = data_nse.get("data")
    request_duration = (dt.now() - request_start).total_seconds()
    log_kv("Fetch status", response.status_code)
    log_kv("Fetch duration", f"{request_duration:.3f} seconds")
    log_kv("Records parsed", 0 if data is None else len(data))
    log_record_sample("NSE", data)

    return {"response_code":response.status_code, "data":data}

def data_inject_nse_main_database(data_nse_value, index_id):

  global latest_injection_summary
  log_rule("NSE INDIA CLEANING AND DB MERGE")
  log_kv("Raw records", len(data_nse_value))
  cleaned_null_values = 0
  decimal_conversions = 0
  string_fallbacks = 0
  inserted_records = 0
  updated_records = 0
  skipped_missing_date = 0
  skipped_empty_price = 0
  skipped_existing_better = 0

  for bracket in range (0, len(data_nse_value)):
    for key, value in data_nse_value[bracket].items():

      if isinstance(value, str):
           
        data_nse_value[bracket][key] = value.strip()
        value = data_nse_value[bracket][key]

      if value in empty_data_list:
        data_nse_value[bracket][key] = None
        cleaned_null_values += 1

      elif value not in empty_data_list:

        if isinstance(value, float) or isinstance(value, int) or isinstance(value, str):

          try:
            data_nse_value[bracket][key] = Decimal(str(data_nse_value[bracket][key]))
            decimal_conversions += 1
          except:
            data_nse_value[bracket][key] = str(value)
            string_fallbacks += 1
      
        else:   
          continue

  for bracket_nse in range (0, len(data_nse_value)):

    date_program = data_nse_value[bracket_nse].get("IY_DT")
   
    if date_program is None:
      skipped_missing_date += 1
      log_kv("Skipped record", f"NSE row #{bracket_nse + 1}: missing IY_DT")
      continue

    date_program_datetime = datetime.strptime(date_program, "%d-%b-%Y")
    date_program_formatted = date_program_datetime.strftime("%Y-%m-%d")
    date_program_formatted_datetime = datetime.strptime(date_program_formatted, "%Y-%m-%d")
    date_program_formatted_datetime_onlydate = date_program_formatted_datetime.date()

    current_record_count = 0
    current_record_parameters = ["IY_DY", "IY_PE", "IY_PB", "IY_DT"]

    for item in data_nse_value[bracket_nse]:
      if data_nse_value[bracket_nse].get(item) != None and item in current_record_parameters:
          current_record_count += 1
      else:
        continue

    query = text("SELECT * FROM valuation_metadata WHERE index_id = :index_id AND trade_date = :date_program_formatted_datetime_onlydate;")
    execute_query = conn.execute(query, {"index_id":index_id, "date_program_formatted_datetime_onlydate": date_program_formatted_datetime_onlydate})
    readable_data = execute_query.mappings().fetchall()

    #Counting already present parameters data count

    previous_record_count = 0
    previous_record_parameters = ["trade_date", "div_yield", "pb_ratio", "pe_ratio"]

    for single_list_item in readable_data: #The readable data is actually just a list containing a single dictionary with all the respective row items taken from the required table
      for item in single_list_item:
        if single_list_item.get(item) != None:
          if item in previous_record_parameters:
            previous_record_count += 1
          else:
            continue
        else:
          continue

    pe_ratio_value = data_nse_value[bracket_nse].get("IY_PE")
    pb_ratio_value = data_nse_value[bracket_nse].get("IY_PB")
    div_yield_value = data_nse_value[bracket_nse].get("IY_DY")
    
    if pe_ratio_value is None and pb_ratio_value is None and div_yield_value:
      skipped_empty_price += 1
      log_kv("Skipped record", f"{date_program_formatted}: no pe_ratio / pb_ratio / div_yield")
      continue

    if previous_record_count > current_record_count:
      skipped_existing_better += 1
      log_kv("Skipped record", f"{date_program_formatted}: existing DB row has {previous_record_count} fields; API row has {current_record_count}")
      continue

    elif previous_record_count < current_record_count or previous_record_count == current_record_count:

      if previous_record_count == 0:
      
        query = text("INSERT INTO valuation_metadata (index_id, trade_date, pe_ratio, pb_ratio, div_yield, last_updated_time) VALUES (:index_id, :trade_date, :pe_ratio, :pb_ratio, :div_yield, :last_updated_time)")
        conn.execute(query, {"index_id":index_id, "trade_date":date_program_formatted_datetime_onlydate, "pe_ratio":pe_ratio_value, "pb_ratio":pb_ratio_value, "div_yield":div_yield_value, "last_updated_time":datetime.now(ZoneInfo("Asia/Kolkata")).replace(tzinfo=None)})
        conn.commit()

        ingestion_date_set.add(date_program_formatted_datetime_onlydate)
        inserted_records += 1
        log_kv("Inserted", f"{date_program_formatted} | PE={pe_ratio_value}, PB={pb_ratio_value}, D={div_yield_value}")
 
      elif previous_record_count > 0:

        query = text("UPDATE valuation_metadata SET pe_ratio = :pe_ratio, pb_ratio = :pb_ratio, div_yield = :div_yield, last_updated_time = :last_updated_time WHERE index_id = :index_id AND trade_date = :trade_date")
        conn.execute(query, {"index_id":index_id, "trade_date":date_program_formatted_datetime_onlydate, "pe_ratio":pe_ratio_value, "pb_ratio":pb_ratio_value, "div_yield":div_yield_value, "last_updated_time":datetime.now(ZoneInfo("Asia/Kolkata")).replace(tzinfo=None)})
        conn.commit()

        ingestion_date_set.add(date_program_formatted_datetime_onlydate)
        updated_records += 1
        log_kv("Updated", f"{date_program_formatted} | previous fields={previous_record_count}, incoming fields={current_record_count}")

  log_rule("NSE INDIA INJECTION SUMMARY")
  log_kv("Null/empty cleaned", cleaned_null_values)
  log_kv("Decimal conversions", decimal_conversions)
  log_kv("String fallbacks", string_fallbacks)
  log_kv("Inserted records", inserted_records)
  log_kv("Updated records", updated_records)
  log_kv("Skipped missing date", skipped_missing_date)
  log_kv("Skipped empty values", skipped_empty_price)
  log_kv("Skipped DB richer", skipped_existing_better)
  log_kv("Ingestion dates", len(ingestion_date_set))
  latest_injection_summary = {
    "source": "NSE INDIA",
    "raw_records": len(data_nse_value),
    "inserted_records": inserted_records,
    "updated_records": updated_records,
    "written_records": inserted_records + updated_records,
    "skipped_records": skipped_missing_date + skipped_empty_price + skipped_existing_better,
    "null_values_cleaned": cleaned_null_values,
    "decimal_conversions": decimal_conversions,
    "string_fallbacks": string_fallbacks
  }
  return data_nse_value

def data_inject_nifty_indices_database(data_nifty_indices_value, index_id):

  global latest_injection_summary
  log_rule("NIFTY INDICES CLEANING AND DB MERGE")
  log_kv("Raw records", len(data_nifty_indices_value))
  cleaned_null_values = 0
  decimal_conversions = 0
  string_fallbacks = 0
  inserted_records = 0
  updated_records = 0
  skipped_missing_date = 0
  skipped_empty_price = 0
  skipped_existing_better = 0

  for bracket in range (0, len(data_nifty_indices_value)):
    for key, value in data_nifty_indices_value[bracket].items():

      if isinstance(value, str):
           
        data_nifty_indices_value[bracket][key] = value.strip()
        value = data_nifty_indices_value[bracket][key]

      if value in empty_data_list:
        data_nifty_indices_value[bracket][key] = None
        cleaned_null_values += 1

      elif value not in empty_data_list:

        if isinstance(value, float) or isinstance(value, int) or isinstance(value, str):

          try:
            data_nifty_indices_value[bracket][key] = Decimal(str(data_nifty_indices_value[bracket][key]))
            decimal_conversions += 1
          except:
            data_nifty_indices_value[bracket][key] = str(value)
            string_fallbacks += 1
      
        else:   
          continue

  for bracket_nse in range (0, len(data_nifty_indices_value)):

    trade_date_niftyindices = data_nifty_indices_value[bracket_nse].get("DATE")

    if trade_date_niftyindices is None:
      skipped_missing_date += 1
      log_kv("Skipped record", f"Nifty Indices row #{bracket_nse + 1}: missing DATE")
      continue

    trade_date_niftyindices_datetime_datatype = datetime.strptime(trade_date_niftyindices, "%d %b %Y")
    trade_date_data_formatted = trade_date_niftyindices_datetime_datatype.strftime("%Y-%m-%d")
    final_trade_date = datetime.strptime(trade_date_data_formatted, "%Y-%m-%d")

    current_record_count = 0
    current_record_parameters = ["pe", "pb", "divYield", "DATE"]

    for item in data_nifty_indices_value[bracket_nse]:
      if data_nifty_indices_value[bracket_nse].get(item) != None and item in current_record_parameters:
          current_record_count += 1
      else:
        continue

    query = text("SELECT * FROM valuation_metadata WHERE index_id = :index_id AND trade_date = :final_trade_date;")
    execute_query = conn.execute(query, {"index_id":index_id, "final_trade_date": final_trade_date})
    readable_data = execute_query.mappings().fetchall()

    #Counting already present parameters data count

    previous_record_count = 0
    previous_record_parameters = ["trade_date", "div_yield", "pb_ratio", "pe_ratio"]

    for single_list_item in readable_data: #The readable data is actually just a list containing a single dictionary with all the respective row items taken from the required table
      for item in single_list_item:
        if single_list_item.get(item) != None:
          if item in previous_record_parameters:
            previous_record_count += 1
          else:
            continue
        else:
          continue

    pe_ratio_value_niftyindices = data_nifty_indices_value[bracket_nse].get("pe")
    pb_ratio_value_niftyindices = data_nifty_indices_value[bracket_nse].get("pb")
    div_yield_value_niftyindices = data_nifty_indices_value[bracket_nse].get("divYield")
    
    if pe_ratio_value_niftyindices is None and pb_ratio_value_niftyindices is None and div_yield_value_niftyindices is None:
      skipped_empty_price += 1
      log_kv("Skipped record", f"{trade_date_data_formatted}: no PE_RATIO, PB_RATIO, DIV_YIELD values")
      continue

    if previous_record_count > current_record_count:
      skipped_existing_better += 1
      log_kv("Skipped record", f"{trade_date_data_formatted}: existing DB row has {previous_record_count} fields; API row has {current_record_count}")
      continue

    elif previous_record_count < current_record_count or previous_record_count == current_record_count:

      if previous_record_count == 0:
      
        query = text("INSERT INTO valuation_metadata (index_id, trade_date, pe_ratio, pb_ratio, div_yield, last_updated_time) VALUES (:index_id, :trade_date, :pe_ratio, :pb_ratio, :div_yield, :last_updated_time)")
        conn.execute(query, {"index_id":index_id, "trade_date":final_trade_date, "pe_ratio":pe_ratio_value_niftyindices, "pb_ratio":pb_ratio_value_niftyindices, "div_yield":div_yield_value_niftyindices, "last_updated_time":datetime.now(ZoneInfo("Asia/Kolkata")).replace(tzinfo=None)})
        conn.commit()

        ingestion_date_set.add(final_trade_date.date())
        inserted_records += 1
        log_kv("Inserted", f"{trade_date_data_formatted} | PE={pe_ratio_value_niftyindices}, PB={pb_ratio_value_niftyindices}, DY={div_yield_value_niftyindices}")

      elif previous_record_count > 0:

        query = text("UPDATE valuation_metadata SET pe_ratio = :pe_ratio, pb_ratio = :pb_ratio, div_yield = :div_yield, last_updated_time = :last_updated_time WHERE index_id = :index_id AND trade_date = :trade_date")
        conn.execute(query, {"index_id":index_id, "trade_date":final_trade_date, "pe_ratio":pe_ratio_value_niftyindices, "pb_ratio":pb_ratio_value_niftyindices, "div_yield":div_yield_value_niftyindices, "last_updated_time":datetime.now(ZoneInfo("Asia/Kolkata")).replace(tzinfo=None)})
        conn.commit()

        ingestion_date_set.add(final_trade_date.date())
        updated_records += 1
        log_kv("Updated", f"{trade_date_data_formatted} | previous fields={previous_record_count}, incoming fields={current_record_count}")

  log_rule("NIFTY INDICES INJECTION SUMMARY")
  log_kv("Null/empty cleaned", cleaned_null_values)
  log_kv("Decimal conversions", decimal_conversions)
  log_kv("String fallbacks", string_fallbacks)
  log_kv("Inserted records", inserted_records)
  log_kv("Updated records", updated_records)
  log_kv("Skipped missing date", skipped_missing_date)
  log_kv("Skipped empty values", skipped_empty_price)
  log_kv("Skipped DB richer", skipped_existing_better)
  log_kv("Ingestion dates", len(ingestion_date_set))
  latest_injection_summary = {
    "source": "NIFTY INDICES",
    "raw_records": len(data_nifty_indices_value),
    "inserted_records": inserted_records,
    "updated_records": updated_records,
    "written_records": inserted_records + updated_records,
    "skipped_records": skipped_missing_date + skipped_empty_price + skipped_existing_better,
    "null_values_cleaned": cleaned_null_values,
    "decimal_conversions": decimal_conversions,
    "string_fallbacks": string_fallbacks
  }
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

log_step(4, "Awaiting data source selection")
logger.info(f"  STEP 4        : Awaiting data source selection from user...")
data_source = str(input("Enter Data Source Preference (NSE INDIA/NIFTY INDICES): "))
log_kv("Data source", data_source)
logger.info(f"  DATA SOURCE   : {data_source}")
logger.info(f"")

log_step(5, "Awaiting user confirmation")
logger.info(f"  STEP 5        : Awaiting green flag from user...")
proceed = int(input("Enter 1 to Proceed and 0 to Abort: "))
log_kv("Proceed flag", proceed)
logger.info(f"")

if proceed == 1:

  # Input Starting Date
  log_step(6, "Awaiting date range input")
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

  start_date_string = start_date.date().strftime('%Y-%m-%d')
  end_date_string = end_date.date().strftime('%Y-%m-%d')

  #Generating Valid Trading days from Starting Date to Ending Date
  trading_days_nse = nse.valid_days(start_date = start_date_string, end_date = end_date_string)
  trading_days_bse = bse.valid_days(start_date = start_date_string, end_date = end_date_string)

  trading_date_set_nse = set()
  for item in trading_days_nse:
    trading_date_set_nse.add(item.date())

  trading_date_set_bse = set()
  for item in trading_days_bse:
    trading_date_set_bse.add(item.date())

  ingestion_date_set = set()
  log_rule("TRADING CALENDAR COVERAGE")
  log_kv("NSE trading days", len(trading_date_set_nse))
  log_kv("BSE trading days", len(trading_date_set_bse))
  log_kv("Calendar start", start_date_string)
  log_kv("Calendar end", end_date_string)

  # Rolling Date Calculation
  rolling_date = start_date + timedelta(days=30)
  log_kv("Initial rolling end", rolling_date.strftime('%Y-%m-%d'))

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
  total_injected_records = 0  # total records inserted or updated in DB after cleaning

  with output_database_engine_connection.connect() as conn:

    logger.info(f"  DB CONN       : ✓  Connection Established Successfully")
    logger.info(f"")
 
    if data_source == "NSE INDIA":

      log_step(7, "Setting up NSE INDIA session and cookies")
      logger.info(f"  STEP 7        : Setting up NSE INDIA session & cookies...")
      output_environment_setup_nse_main = environment_setup_nse_main()
      session = output_environment_setup_nse_main.get("session")
      headers = output_environment_setup_nse_main.get("headers")
      log_kv("Session ready", "NSE INDIA")
      log_kv("Header keys", list(headers.keys()))
      log_kv("Global impersonate", output_user_agent_and_impersonates_selection.get('impersonate_choice'))
      logger.info(f"  SESSION       : ✓  NSE INDIA session initialized")
      logger.info(f"  USER AGENT    : {output_user_agent_and_impersonates_selection.get('impersonate_choice')}")
      logger.info(f"")
      log_step(8, "Beginning rolling batch ingestion from NSE INDIA")
      logger.info(f"  STEP 8        : Beginning rolling batch ingestion from NSE INDIA...")
      logger.info(f"")

      while start_date <= rolling_date:

        batch_number += 1
        acceptable_start_date = start_date.strftime("%d-%m-%Y")
        acceptable_rolling_date = rolling_date.strftime("%d-%m-%Y")
        batch_start_time = dt.now()
        log_batch_header(batch_number, "NSE INDIA", acceptable_start_date, acceptable_rolling_date)

        logger.info(f"┌──────────────────────────────────────────────────────────────────────┐")
        logger.info(f"│  BATCH        : #{str(batch_number):<53}│")
        logger.info(f"│  WINDOW START : {acceptable_start_date:<54}│")
        logger.info(f"│  WINDOW END   : {acceptable_rolling_date:<54}│")
        logger.info(f"│  SOURCE       : NSE INDIA                                            │")
        logger.info(f"└──────────────────────────────────────────────────────────────────────┘")

        output_nse_main_data_fetch = nse_main_data_fetch(acceptable_start_date, acceptable_rolling_date)
        log_kv("Batch fetch done", f"HTTP {output_nse_main_data_fetch.get('response_code')}")
    
        if output_nse_main_data_fetch.get("response_code") == 200:

          data_received = output_nse_main_data_fetch.get("data")

          if data_received is None or len(data_received) == 0:

            skipped_count += 1
            skipped_batches.append((acceptable_start_date, acceptable_rolling_date))
            logger.info(f"  STATUS        : ⚠  SKIPPED — No records in window (Response 200, empty data)")
            logger.info(f"")

          else:

            # ── INJECTION ────────────────────────────────────────────────
            output_injection = data_inject_nse_main_database(data_received, index_id)

            success_count += 1
            total_api_records += len(data_received)
            total_injected_records += latest_injection_summary.get("written_records", len(output_injection))
            last_updated = datetime.now(ZoneInfo("Asia/Kolkata"))
            log_rule("BATCH MERGE RESULT")
            log_kv("Inserted rows", latest_injection_summary.get("inserted_records", 0))
            log_kv("Updated rows", latest_injection_summary.get("updated_records", 0))
            log_kv("Skipped rows", latest_injection_summary.get("skipped_records", 0))
            log_kv("Batch duration", f"{(dt.now() - batch_start_time).total_seconds():.3f} seconds")
            logger.info(f"  STATUS        : ✓  INJECTED TO DB — Cleaned & committed to price_metadata")
            logger.info(f"  RECORDS       : {len(data_received)} record(s) returned by API")
            logger.info(f"")

          # Resetting the Dates
          previous_start_date = start_date
          previous_rolling_date = rolling_date
          start_date = rolling_date + timedelta(days=1)
          rolling_date = min(start_date + timedelta(days=30), end_date)
          log_rule("NEXT WINDOW")
          log_kv("Completed window", f"{previous_start_date.strftime('%Y-%m-%d')} to {previous_rolling_date.strftime('%Y-%m-%d')}")
          log_kv("Next start", start_date.strftime('%Y-%m-%d'))
          log_kv("Next rolling end", rolling_date.strftime('%Y-%m-%d'))

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
      log_rule("INDEX METADATA UPDATE")
      log_kv("Metadata source", source)
      log_kv("Metadata index id", index_id)
      log_kv("Data origin date", origin_date.strftime('%Y-%m-%d'))
      query = text("UPDATE index_metadata SET source = :source, last_updated_time = :last_updated_time, data_origin_date = :data_origin_date WHERE index_id = :index_id")
      conn.execute(query, {"source":source, "index_id":index_id, "last_updated_time":datetime.now(ZoneInfo("Asia/Kolkata")), "data_origin_date":origin_date})
      conn.commit()
      log_kv("Metadata status", "Committed")
      logger.info(f"  METADATA      : ✓  index_metadata Updated (source, last_updated_time, data_origin_date)")
      logger.info(f"")

    elif data_source == "NIFTY INDICES":

      log_step(7, "Setting up NIFTY INDICES session and cookies")
      logger.info(f"  STEP 7        : Setting up NIFTY INDICES session & cookies...")
      output_environment_setup_nifty_indices = environment_setup_nifty_indices()
      session = output_environment_setup_nifty_indices.get("session")
      headers = output_environment_setup_nifty_indices.get("headers")
      url = output_environment_setup_nifty_indices.get("url")
      log_kv("Session ready", "NIFTY INDICES")
      log_kv("Header keys", list(headers.keys()))
      log_kv("Endpoint", url)
      log_kv("Global impersonate", output_user_agent_and_impersonates_selection.get('impersonate_choice'))
      logger.info(f"  SESSION       : ✓  NIFTY INDICES session initialized")
      logger.info(f"  USER AGENT    : {output_user_agent_and_impersonates_selection.get('impersonate_choice')}")
      logger.info(f"")
      log_step(8, "Beginning rolling batch ingestion from NIFTY INDICES")
      logger.info(f"  STEP 8        : Beginning rolling batch ingestion from NIFTY INDICES...")
      logger.info(f"")

      while start_date <= rolling_date:

        batch_number += 1
        acceptable_start_date = start_date.strftime("%d-%b-%Y")
        acceptable_rolling_date = rolling_date.strftime("%d-%b-%Y")
        batch_start_time = dt.now()
        log_batch_header(batch_number, "NIFTY INDICES", acceptable_start_date, acceptable_rolling_date)

        logger.info(f"┌──────────────────────────────────────────────────────────────────────┐")
        logger.info(f"│  BATCH        : #{str(batch_number):<53}│")
        logger.info(f"│  WINDOW START : {acceptable_start_date:<54}│")
        logger.info(f"│  WINDOW END   : {acceptable_rolling_date:<54}│")
        logger.info(f"│  SOURCE       : NIFTY INDICES                                        │")
        logger.info(f"└──────────────────────────────────────────────────────────────────────┘")

        output_nifty_indices_data_fetch = nifty_indices_data_fetch(acceptable_start_date, acceptable_rolling_date)
        log_kv("Batch fetch done", f"HTTP {output_nifty_indices_data_fetch.get('response_code')}")
    
        if output_nifty_indices_data_fetch.get("response_code") == 200:

          data_received = output_nifty_indices_data_fetch.get("data")

          if data_received is None or len(data_received) == 0:

            skipped_count += 1
            skipped_batches.append((acceptable_start_date, acceptable_rolling_date))
            logger.info(f"  STATUS        : ⚠  SKIPPED — No records in window (Response 200, empty data)")
            logger.info(f"")

          else:

            # ── INJECTION ────────────────────────────────────────────────
            output_injection = data_inject_nifty_indices_database(data_received, index_id)

            success_count += 1
            total_api_records += len(data_received)
            total_injected_records += latest_injection_summary.get("written_records", len(output_injection))
            last_updated = datetime.now(ZoneInfo("Asia/Kolkata"))
            log_rule("BATCH MERGE RESULT")
            log_kv("Inserted rows", latest_injection_summary.get("inserted_records", 0))
            log_kv("Updated rows", latest_injection_summary.get("updated_records", 0))
            log_kv("Skipped rows", latest_injection_summary.get("skipped_records", 0))
            log_kv("Batch duration", f"{(dt.now() - batch_start_time).total_seconds():.3f} seconds")
            logger.info(f"  STATUS        : ✓  INJECTED TO DB — Cleaned & committed to price_metadata")
            logger.info(f"  RECORDS       : {len(data_received)} record(s) returned by API")
            logger.info(f"")

          # Resetting the Dates
          previous_start_date = start_date
          previous_rolling_date = rolling_date
          start_date = rolling_date + timedelta(days=1)
          rolling_date = min(start_date + timedelta(days=30), end_date)
          log_rule("NEXT WINDOW")
          log_kv("Completed window", f"{previous_start_date.strftime('%Y-%m-%d')} to {previous_rolling_date.strftime('%Y-%m-%d')}")
          log_kv("Next start", start_date.strftime('%Y-%m-%d'))
          log_kv("Next rolling end", rolling_date.strftime('%Y-%m-%d'))

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
      log_rule("INDEX METADATA UPDATE")
      log_kv("Metadata source", source)
      log_kv("Metadata index id", index_id)
      log_kv("Data origin date", origin_date.strftime('%Y-%m-%d'))
      query = text("UPDATE index_metadata SET source = :source, last_updated_time = :last_updated_time, data_origin_date = :data_origin_date WHERE index_id = :index_id")
      conn.execute(query, {"source":source, "index_id":index_id, "last_updated_time":datetime.now(ZoneInfo("Asia/Kolkata")), "data_origin_date":origin_date})
      conn.commit()
      log_kv("Metadata status", "Committed")
      logger.info(f"  METADATA      : ✓  index_metadata Updated (source, last_updated_time, data_origin_date)")
      logger.info(f"")

  # ── FINAL SUMMARY ──────────────────────────────────────────────────────────
  nse_difference = trading_date_set_nse - ingestion_date_set
  bse_difference = trading_date_set_bse - ingestion_date_set
  nse_extra_ingested_dates = ingestion_date_set - trading_date_set_nse
  bse_extra_ingested_dates = ingestion_date_set - trading_date_set_bse

  difference_list_nse = []
  for item in nse_difference:
    string_date = item.strftime('%Y-%m-%d')
    difference_list_nse.append(string_date)

  sorted_list_nse = sorted(difference_list_nse)

  difference_list_bse = []
  for item in bse_difference:
    string_date = item.strftime('%Y-%m-%d')
    difference_list_bse.append(string_date)

  sorted_list_bse = sorted(difference_list_bse)

  extra_ingested_list_nse = []
  for item in nse_extra_ingested_dates:
    string_date = item.strftime('%Y-%m-%d')
    extra_ingested_list_nse.append(string_date)

  sorted_extra_ingested_list_nse = sorted(extra_ingested_list_nse)

  extra_ingested_list_bse = []
  for item in bse_extra_ingested_dates:
    string_date = item.strftime('%Y-%m-%d')
    extra_ingested_list_bse.append(string_date)

  sorted_extra_ingested_list_bse = sorted(extra_ingested_list_bse)

  log_rule("TRADING DAY RECONCILIATION")
  log_kv("NSE expected days", len(trading_date_set_nse))
  log_kv("BSE expected days", len(trading_date_set_bse))
  log_kv("Ingested dates", len(ingestion_date_set))
  log_kv("NSE missing count", len(sorted_list_nse))
  log_kv("BSE missing count", len(sorted_list_bse))
  log_date_list("NSE missing dates", sorted_list_nse)
  log_date_list("BSE missing dates", sorted_list_bse)
  log_kv("NSE extra count", len(sorted_extra_ingested_list_nse))
  log_kv("BSE extra count", len(sorted_extra_ingested_list_bse))
  log_date_list("NSE extra ingested dates", sorted_extra_ingested_list_nse)
  log_date_list("BSE extra ingested dates", sorted_extra_ingested_list_bse)

  end_time = dt.now()
  total_duration = end_time - start_time
  total_seconds = int(total_duration.total_seconds())
  hours = total_seconds // 3600
  minutes = (total_seconds % 3600) // 60
  seconds = total_seconds % 60
  log_rule("EXECUTION SUMMARY")
  log_kv("Index ID", index_id)
  log_kv("Index name", output_index_name_fetcher.get('index_long_name'))
  log_kv("Data source", data_source)
  log_kv("Completed at", dt.now().strftime('%Y-%m-%d %H:%M:%S'))
  log_kv("Time taken", f"{hours}h {minutes}m {seconds}s")
  log_kv("Total batches", batch_number)
  log_kv("Successful batches", success_count)
  log_kv("Skipped batches", skipped_count)
  log_kv("Failed batches", failed_count)
  log_kv("API records", total_api_records)
  log_kv("DB written", total_injected_records)
  log_kv("Final result", "all batches completed" if failed_count == 0 and skipped_count == 0 else "failures encountered" if failed_count > 0 else "completed with skipped windows")

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
