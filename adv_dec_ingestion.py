#Importing Important Libraries
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
logger.info(f"║      ADVANCE DECLINE HISTORICAL DATA INGESTION — EXECUTION LOG       ║")
logger.info(f"╠══════════════════════════════════════════════════════════════════════╣")
logger.info(f"║  RUN TIMESTAMP : {dt.now().strftime('%d-%b-%Y %I:%M:%S %p'):<52}║")
logger.info(f"║  SCRIPT        : adv_dec_ingestion.py                                ║")
logger.info(f"║  PURPOSE       : Market-Wide Advance Decline Monthly Ingestion        ║")
logger.info(f"║  TARGET TABLE  : advance_decline_metadata                             ║")
logger.info(f"╚══════════════════════════════════════════════════════════════════════╝")
logger.info(f"")

# ─────────────────────────────────────────────────────────────────────────────

def database_engine_connection():

  #Engine Connection Established
  database_password = os.getenv("database_password")
  DB_URL = f"postgresql://postgres:{database_password}@localhost:5432/index_value_strategy"
  engine = create_engine(DB_URL)
  return engine

logger.info(f"  STEP 1        : Establishing database engine connection...")
output_database_engine_connection = database_engine_connection()
logger.info(f"  DB ENGINE     : ✓  Connected to index_value_strategy")
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

output_environment_setup_nse_main = environment_setup_nse_main()

def nse_main_data_fetch(iteration_item):
    
    url = f"https://www.nseindia.com/api/historicalOR/advances-decline-monthly?year={iteration_item}"
    logger.info(f"  URL           : {url}")
    response = output_environment_setup_nse_main.get("session").get(url, headers = output_environment_setup_nse_main.get("headers"), impersonate = output_user_agent_and_impersonates_selection.get("impersonate_choice"), timeout=10)
    data_nse = response.json()
    data = data_nse.get("data")

    return {"response_code":response.status_code, "data":data}

def data_inject_nse_main_database(data_nse_value):

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

    date_program = data_nse_value[bracket_nse].get("ADD_DAY_STRING") #Fetched Date from Dictionary

    if date_program is None:
      continue

    date_program_datetime = datetime.strptime(date_program, "%d-%b-%Y") #Converting <str> datatype into datetime datatype
    date_program_formatted = date_program_datetime.strftime("%Y-%m-%d") #Changed the Format of Date to match PostgreSQL
    date_program_formatted_datetime = datetime.strptime(date_program_formatted, "%Y-%m-%d") #Converting <str> datatype into datetime datatype as changing format turns the date into <str> format
    date_program_formatted_datetime_onlydate = date_program_formatted_datetime.date() #Contains only the date part and not the time part

    #Formatting the Data into correct datatype
    advances_value = data_nse_value[bracket_nse].get("ADD_ADVANCES")
    declines_value = data_nse_value[bracket_nse].get("ADD_DECLINES")
    adv_dec_ratio_value = data_nse_value[bracket_nse].get("ADD_ADV_DCLN_RATIO")
      
    if advances_value is None and declines_value is None and adv_dec_ratio_value is None:
      continue
    
    #Finally Pushing Whole Data into the Database
    query = text("INSERT INTO advance_decline_metadata (trade_date, advances, declines, advance_decline_ratio, last_updated_time) VALUES (:trade_date, :advances, :declines, :advance_decline_ratio, :last_updated_time)")
    conn.execute(query, {"trade_date":date_program_formatted_datetime_onlydate,"advances": advances_value, "declines":declines_value, "advance_decline_ratio":adv_dec_ratio_value, "last_updated_time":datetime.now(ZoneInfo("Asia/Kolkata"))})
    conn.commit()

  return data_nse_value

# ─────────────────────────────────────────────────────────────────────────────

# Data Source
data_source = "NSE INDIA"

logger.info(f"  STEP 2        : Setting up NSE INDIA session & cookies...")
logger.info(f"  SESSION       : ✓  NSE INDIA session initialized")
logger.info(f"  USER AGENT    : {output_user_agent_and_impersonates_selection.get('impersonate_choice')}")
logger.info(f"")

#Months
months_list = ["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV", "DEC"]

#Years
years_list = []

logger.info(f"  STEP 3        : Awaiting date range input from user...")

# Input Starting Month and Year
starting_month = str(input("Enter Starting Month (First Three Letters of Month): "))
starting_year = int(input("Enter Starting Year: "))

# Input Ending Month and Year
ending_month = str(input("Enter Ending Month (First Three Letters of Month): "))
ending_year = int(input("Enter Ending Year: "))

#Building Years List
years_list.append(starting_year)
next_year = starting_year
while next_year < ending_year:
  next_year = next_year + 1
  years_list.append(next_year)

compiled_list = []

if starting_year == ending_year:

  starting_month_index = months_list.index(starting_month)
  ending_month_index = months_list.index(ending_month)

  #Building Compiled List excluding first and last year
  for year in range (0, len(years_list)):
    for month in range (starting_month_index, ending_month_index+1):
      compiled_list.append(f"{months_list[month]}-{years_list[year]}")
      
else:

  #Building List only using first year
  starting_month_index = months_list.index(starting_month)
  for year in range (0,1):
    for month in range(starting_month_index, len(months_list)):
      compiled_list.append(f"{months_list[month]}-{years_list[year]}")

  #Building Compiled List excluding first and last year
  for year in range (1, len(years_list) - 1):
    for month in range (0, len(months_list)):
      compiled_list.append(f"{months_list[month]}-{years_list[year]}")

  #Building List only using last year
  ending_month_index = months_list.index(ending_month)
  for year in range (len(years_list)-1, len(years_list)):
    for month in range (0, ending_month_index+1):
      compiled_list.append(f"{months_list[month]}-{years_list[year]}")

logger.info(f"")
logger.info(f"┌──────────────────────────────────────────────────────────────────────┐")
logger.info(f"│                         INGESTION PARAMETERS                         │")
logger.info(f"├──────────────────────────────────────────────────────────────────────┤")
logger.info(f"│  DATA SOURCE   : NSE INDIA (Fixed)                                   │")
logger.info(f"│  START         : {starting_month}-{starting_year:<52}│")
logger.info(f"│  END           : {ending_month}-{ending_year:<53}│")
logger.info(f"│  TOTAL MONTHS  : {str(len(compiled_list)):<54}│")
logger.info(f"│  COMPILED LIST : {str(compiled_list[:6])[1:-1] + (' ...' if len(compiled_list) > 6 else ''):<54}│")
logger.info(f"└──────────────────────────────────────────────────────────────────────┘")
logger.info(f"")

# ── COUNTERS ─────────────────────────────────────────────────────────────────
success_count = 0
skipped_count = 0
failed_count = 0
iteration_number = 0
start_time = dt.now()
failed_months = []          # stores month-year string for failed iterations
skipped_months = []         # stores month-year string for skipped iterations
total_api_records = 0       # total records returned by API across all iterations
total_injected_records = 0  # total records actually inserted into DB after cleaning

with output_database_engine_connection.connect() as conn:

  logger.info(f"  DB CONN       : ✓  Connection Established Successfully")
  logger.info(f"")
  logger.info(f"  STEP 4        : Beginning month-by-month ingestion from NSE INDIA...")
  logger.info(f"")

  #Setting up the environment just for one time and then utilizing it to hit API again and again
  session = output_environment_setup_nse_main.get("session")
  headers = output_environment_setup_nse_main.get("headers")

  #Pushing Actual Data

  for iteration_item in compiled_list:

    iteration_number += 1

    logger.info(f"┌──────────────────────────────────────────────────────────────────────┐")
    logger.info(f"│  ITERATION    : #{str(iteration_number):<53}│")
    logger.info(f"│  MONTH-YEAR   : {iteration_item:<54}│")
    logger.info(f"│  PROGRESS     : {iteration_number} of {len(compiled_list)} months{'':<46}│")
    logger.info(f"│  SOURCE       : NSE INDIA                                            │")
    logger.info(f"└──────────────────────────────────────────────────────────────────────┘")

    output_nse_main_data_fetch = nse_main_data_fetch(iteration_item)
    
    if output_nse_main_data_fetch.get("response_code") == 200:

      data_received = output_nse_main_data_fetch.get("data")

      if data_received is None or len(data_received) == 0:

        skipped_count += 1
        skipped_months.append(iteration_item)
        logger.info(f"  STATUS        : ⚠  SKIPPED — No records for this month (Response 200, empty data)")
        logger.info(f"")

      else:

        # ── INJECTION ────────────────────────────────────────────────────────
        output_injection = data_inject_nse_main_database(data_received)

        success_count += 1
        total_api_records += len(data_received)
        total_injected_records += len(output_injection)
        last_updated = datetime.now(ZoneInfo("Asia/Kolkata"))
        logger.info(f"  STATUS        : ✓  INJECTED TO DB — Cleaned & committed to advance_decline_metadata")
        logger.info(f"  RECORDS       : {len(data_received)} record(s) returned by API")
        logger.info(f"")

      #Randomized Break
      next_request_wait = random.uniform(1, 10)
      logger.info(f"  WAIT          : {next_request_wait:.4f} Seconds")
      time.sleep(next_request_wait)
      logger.info(f"")

    elif output_nse_main_data_fetch.get("response_code") != 200:
      failed_count += 1
      failed_months.append(iteration_item)
      logger.info(f"  STATUS        : ✗  FETCH FAILED")
      logger.info(f"  ERROR CODE    : {output_nse_main_data_fetch.get('response_code')}")
      logger.info(f"  ACTION        : PROCESS ABORTED")
      logger.info(f"")
      sys.exit()
      break

# ── FINAL SUMMARY ─────────────────────────────────────────────────────────────
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
logger.info(f"║  DATA SOURCE   : NSE INDIA                                           ║")
logger.info(f"║  TARGET TABLE  : advance_decline_metadata                             ║")
logger.info(f"╠══════════════════════════════════════════════════════════════════════╣")
logger.info(f"║  COMPLETED AT  : {dt.now().strftime('%d-%b-%Y %I:%M:%S %p'):<52}║")
logger.info(f"║  TIME TAKEN    : {f'{hours}h {minutes}m {seconds}s':<52}║")
logger.info(f"╠══════════════════════════════════════════════════════════════════════╣")
logger.info(f"║  TOTAL MONTHS  : {str(len(compiled_list)):<52}║")
logger.info(f"║  ✓  INJECTED   : {str(success_count):<52}║")
logger.info(f"║  ⚠  SKIPPED    : {str(skipped_count):<52}║")
logger.info(f"║  ✗  FAILED     : {str(failed_count):<52}║")
logger.info(f"╠══════════════════════════════════════════════════════════════════════╣")
logger.info(f"║  API RECORDS   : {str(total_api_records):<52}║")
logger.info(f"║  DB INSERTED   : {str(total_injected_records):<52}║")
logger.info(f"╠══════════════════════════════════════════════════════════════════════╣")
if failed_count == 0 and skipped_count == 0:
  logger.info(f"║  RESULT        : ✓  ALL MONTHS COMPLETED SUCCESSFULLY                ║")
elif failed_count > 0:
  logger.info(f"║  RESULT        : ✗  PROCESS ENCOUNTERED FAILURES — REVIEW LOGS       ║")
else:
  logger.info(f"║  RESULT        : ⚠  COMPLETED WITH SKIPPED MONTHS                    ║")
logger.info(f"╚══════════════════════════════════════════════════════════════════════╝")

if failed_months:
  logger.info(f"")
  logger.info(f"  ┌─ FAILED MONTHS {'─'*55}┐")
  for i, m in enumerate(failed_months, 1):
    logger.info(f"  │  [{i}]  {m:<63}│")
  logger.info(f"  └{'─'*71}┘")

if skipped_months:
  logger.info(f"")
  logger.info(f"  ┌─ SKIPPED MONTHS {'─'*54}┐")
  for i, m in enumerate(skipped_months, 1):
    logger.info(f"  │  [{i}]  {m:<63}│")
  logger.info(f"  └{'─'*71}┘")

logger.info(f"")
