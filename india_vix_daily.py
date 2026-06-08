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

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

#Workflow - Establish connection to the database -> Run a loop over the postgresql table index_metadata -> for each of the indices, use their index_long_name -> prepare payload for NSE INDIA only combined with today's date -> Fetch the data -> Parse and Clean the Data -> Finally Push it to actual price_metadata table -> Do it repeatedly until each index is finished!

#For Null Values Check
empty_data_list = [None, "None", "0", 0, "-", "NaN", "Null", "NULL", "null", "none", "", " ", "nan"] #Used only during data cleaning

def database_engine_connection():

  #Engine Connection Established
  database_password = os.getenv("database_password_cockroach_db")
  DB_URL = f"cockroachdb+psycopg://postgres:{database_password}@megadox-27437.j77.aws-ap-south-1.cockroachlabs.cloud:26257/index_value_strategy?sslmode=require"
  engine = create_engine(DB_URL)
  return engine

output_database_engine_connection = database_engine_connection()

#Index Dictionary for INDIA VIX Only
index_dictionary = {136: "INDIA VIX"}

def today_date_fetch():

  today = date.today()
  return today

today_date = today_date_fetch() #- timedelta(days=4) #Just dump this line of code to test for previous days
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

def nse_main_data_fetch(acceptable_start_date, index_id):
    
    # The Actual Data Fetch
    encoded_index_long_name = urllib.parse.quote(index_dictionary.get(index_id))

    url = f"https://www.nseindia.com/api/historicalOR/vixhistory?from={today_date}&to={today_date}"

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

    date_program = data_nse_value[bracket_nse].get("EOD_TIMESTAMP") #Fetched Date from Dictionary

    if date_program is None:
      continue

    date_program_datetime = datetime.strptime(date_program, "%d-%b-%Y") #Converting <str> datatype into datetime datatype
    date_program_formatted = date_program_datetime.strftime("%Y-%m-%d") #Changed the Format of Date to match PostgreSQL
    date_program_formatted_datetime = datetime.strptime(date_program_formatted, "%Y-%m-%d") #Converting <str> datatype into datetime datatype as changing format turns the date into <str> format
    date_program_formatted_datetime_onlydate = date_program_formatted_datetime.date() #Contains only the date part and not the time part

    #Formatting the Data into correct datatype
    open_index_value = data_nse_value[bracket_nse].get("EOD_OPEN_INDEX_VAL")
    high_index_value = data_nse_value[bracket_nse].get("EOD_HIGH_INDEX_VAL")
    low_index_value = data_nse_value[bracket_nse].get("EOD_LOW_INDEX_VAL")
    close_index_value = data_nse_value[bracket_nse].get("EOD_CLOSE_INDEX_VAL")
    previous_close_value = data_nse_value[bracket_nse].get("EOD_PREV_CLOSE")
    points_change_value = data_nse_value[bracket_nse].get("VIX_PTS_CHG")
    percentage_change_value = data_nse_value[bracket_nse].get("VIX_PERC_CHG")

    if open_index_value is None and high_index_value is None and low_index_value is None and close_index_value is None and previous_close_value is None and points_change_value is None and percentage_change_value is None:
      continue
      
    #Finally Pushing Whole Data into the Database
    query = text("INSERT INTO india_vix_metadata (index_id, trade_date, open_price, high_price, low_price, close_price, previous_close_price, points_change, percentage_change, last_updated_time) VALUES (:index_id, :trade_date, :open_price, :high_price, :low_price, :close_price, :previous_close_price, :points_change, :percentage_change, :last_updated_time)")
    conn.execute(query, {"index_id":index_id, "trade_date":date_program_formatted_datetime_onlydate, "open_price":open_index_value, "high_price":high_index_value, "low_price":low_index_value, "close_price":close_index_value, "previous_close_price":previous_close_value, "points_change":points_change_value, "percentage_change":percentage_change_value, "last_updated_time":datetime.now(ZoneInfo("Asia/Kolkata"))})
    conn.commit()

  return data_nse_value

with output_database_engine_connection.connect() as conn:
    
  session = output_environment_setup_nse_main.get("session")
  headers = output_environment_setup_nse_main.get("headers")

  logger.info(f"")
  logger.info(f"╔══════════════════════════════════════════════════════════════════════╗")
  logger.info(f"║           INDIA VIX DAILY PRICE FETCHER — EXECUTION LOG              ║")
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

  for index_id in index_dictionary.keys():

    logger.info(f"┌──────────────────────────────────────────────────────────────────────┐")
    logger.info(f"│  INDEX ID     : {str(index_id):<54}│")
    logger.info(f"│  INDEX NAME   : {index_dictionary.get(index_id):<54}│")
    logger.info(f"└──────────────────────────────────────────────────────────────────────┘")

    output_nse_main_data_fetch = nse_main_data_fetch(today_date, index_id)

    if output_nse_main_data_fetch.get("response_code") == 200:

      if output_nse_main_data_fetch.get("data") is None:

        skipped_count += 1
        logger.info(f"  STATUS        : ⚠  DATA IS NONE — SKIPPED")
        skipped_indices.append(f"{index_id}: {index_dictionary.get(index_id)} (No Data)")
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
            output_nse_main_data_fetch.get("data"), index_id)

          # ── OUTPUT BLOCK ─────────────────────────────────────────────────
          logger.info(f"  ┌─ OUTPUT AFTER CLEANING (INJECTED TO DB) {'─'*29}┐")
          for i, record in enumerate(output_injection):
            logger.info(f"  │  Record [{i+1}]")
            for key, value in record.items():
              logger.info(f"  │    {key:<35} : {value}")
          logger.info(f"  └{'─'*71}┘")
          logger.info(f"")

          success_count += 1
          last_updated = datetime.now(ZoneInfo("Asia/Kolkata"))
          logger.info(f"  INJECTION     : ✓  COMMITTED TO price_metadata")
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
