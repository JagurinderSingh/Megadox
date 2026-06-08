#Importing Important Libraries
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

def database_engine_connection():

  #Engine Connection Established
  database_password = os.getenv("database_password_cockroach_db")
  DB_URL = f"cockroachdb+psycopg://postgres:{database_password}@megadox-27437.j77.aws-ap-south-1.cockroachlabs.cloud:26257/index_value_strategy?sslmode=require"
  engine = create_engine(DB_URL)
  return engine

def today_date_fetch():

  today = date.today()
  return today

today_date = today_date_fetch() #- timedelta(days=4)
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

def nse_main_data_fetch():
    
    url = f"https://www.nseindia.com/api/live-analysis-advance"
    response = output_environment_setup_nse_main.get("session").get(url, headers = output_environment_setup_nse_main.get("headers"), impersonate = output_user_agent_and_impersonates_selection.get("impersonate_choice"), timeout=10)
    data_nse = response.json()
    data = data_nse.get("data")

    return {"response_code":response.status_code, "data":data_nse}

def data_inject_nse_main_database(data_nse_value):

  for key, value in data_nse_value.items():
      
    if isinstance(value, str):  # str datatypes will be stripped without any whitespaces e.g. " NIFTY 50 " to "NIFTY 50". No need to take int or float datatype into account as they strip automatically the whitespaces
           
      data_nse_value[key] = value.strip()
      value = data_nse_value[key]

    if value in empty_data_list:
      data_nse_value[key] = None

    elif value not in empty_data_list:

      if isinstance(value, float) or isinstance(value, int) or isinstance(value, str):

        try:
          data_nse_value[key] = Decimal(str(data_nse_value[key]))
        except:
          data_nse_value[key] = str(value)
      
      else:   
        continue

  
  date_program_datetime = datetime.strptime(today_date, "%d-%m-%Y") #Converting <str> datatype into datetime datatype
  date_program_formatted = date_program_datetime.strftime("%Y-%m-%d") #Changed the Format of Date to match PostgreSQL
  date_program_formatted_datetime = datetime.strptime(date_program_formatted, "%Y-%m-%d") #Converting <str> datatype into datetime datatype as changing format turns the date into <str> format
    
  #Formatting the Data into correct datatype
  advances_value = data_nse_value.get("Advances")
  declines_value = data_nse_value.get("Declines")
  adv_dec_ratio_value = round((advances_value/declines_value),2)
      
  if advances_value is None and declines_value is None and adv_dec_ratio_value is None:
    logger.info(f"  STATUS        : ✗  ALL DATA IS NONE — PROCESS ABORTED")
    logger.info(f"")
    sys.exit()
    
  #Finally Pushing Whole Data into the Database
  query = text("INSERT INTO advance_decline_metadata (trade_date, advances, declines, advance_decline_ratio, last_updated_time) VALUES (:trade_date, :advances, :declines, :advance_decline_ratio, :last_updated_time)")
  conn.execute(query, {"trade_date":date_program_formatted_datetime,"advances": advances_value, "declines":declines_value, "advance_decline_ratio":adv_dec_ratio_value, "last_updated_time":datetime.now(ZoneInfo("Asia/Kolkata"))})
  conn.commit()

  return data_nse_value

# ── STARTUP BANNER ───────────────────────────────────────────────────────────

logger.info(f"")
logger.info(f"╔══════════════════════════════════════════════════════════════════════╗")
logger.info(f"║       ADVANCE DECLINE DAILY DATA FETCHER — EXECUTION LOG             ║")
logger.info(f"╠══════════════════════════════════════════════════════════════════════╣")
logger.info(f"║  RUN TIMESTAMP : {dt.now().strftime('%d-%b-%Y %I:%M:%S %p'):<52}║")
logger.info(f"║  SCRIPT        : adv_dec_daily_fetcher.py                            ║")
logger.info(f"║  PURPOSE       : Today's Live Advance Decline Injection               ║")
logger.info(f"║  TRADE DATE    : {today_date:<52}║")
logger.info(f"║  TARGET TABLE  : advance_decline_metadata                             ║")
logger.info(f"╚══════════════════════════════════════════════════════════════════════╝")
logger.info(f"")

# ─────────────────────────────────────────────────────────────────────────────

# Data Source
data_source = "NSE INDIA"

logger.info(f"  STEP 1        : Establishing database engine connection...")
output_database_engine_connection = database_engine_connection()
logger.info(f"  DB ENGINE     : ✓  Connected to index_value_strategy")
logger.info(f"")

logger.info(f"  STEP 2        : Setting up NSE INDIA session & cookies...")
logger.info(f"  SESSION       : ✓  NSE INDIA session initialized")
logger.info(f"  USER AGENT    : {output_user_agent_and_impersonates_selection.get('impersonate_choice')}")
logger.info(f"")

logger.info(f"┌──────────────────────────────────────────────────────────────────────┐")
logger.info(f"│                         INGESTION PARAMETERS                         │")
logger.info(f"├──────────────────────────────────────────────────────────────────────┤")
logger.info(f"│  DATA SOURCE  : NSE INDIA (Fixed)                                    │")
logger.info(f"│  TRADE DATE   : {today_date:<54}│")
logger.info(f"│  MODE         : Daily (Single Shot — No Loop)                        │")
logger.info(f"│  ENDPOINT     : /api/live-analysis-advance                           │")
logger.info(f"└──────────────────────────────────────────────────────────────────────┘")
logger.info(f"")

start_time = dt.now()

with output_database_engine_connection.connect() as conn:

  logger.info(f"  DB CONN       : ✓  Connection Established Successfully")
  logger.info(f"")

  #Setting up the environment just for one time and then utilizing it to hit API again and again
  session = output_environment_setup_nse_main.get("session")
  headers = output_environment_setup_nse_main.get("headers")

  #Pushing Actual Data
  logger.info(f"  STEP 3        : Fetching live advance decline data from NSE INDIA...")
  logger.info(f"")
  output_nse_main_data_fetch = nse_main_data_fetch()
    
  if output_nse_main_data_fetch.get("response_code") == 200:

    #Reducing to only required data
    all_data = output_nse_main_data_fetch.get("data")
    all_advance_data = all_data.get("advance")
    all_advance_data_count = all_advance_data.get("count")

    logger.info(f"  STATUS        : ✓  DATA RECEIVED — RESPONSE 200")
    logger.info(f"")

    # ── INPUT BLOCK ──────────────────────────────────────────────────────────
    logger.info(f"  ┌─ RAW INPUT FROM NSE INDIA (advance → count) {'─'*25}┐")
    for key, value in all_advance_data_count.items():
      logger.info(f"  │    {key:<35} : {value}")
    logger.info(f"  └{'─'*71}┘")
    logger.info(f"")

    #Final Data Injection
    output_injection = data_inject_nse_main_database(all_advance_data_count)

    # ── OUTPUT BLOCK — only the 5 fields going into the DB ───────────────────
    date_for_display = datetime.strptime(today_date, "%d-%m-%Y").strftime("%Y-%m-%d")
    advances_display = output_injection.get("Advances")
    declines_display = output_injection.get("Declines")
    ratio_display = round((advances_display / declines_display), 2)
    last_updated_display = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%d-%b-%Y %I:%M:%S %p")

    logger.info(f"  ┌─ CLEANED OUTPUT (INJECTED TO DB) {'─'*36}┐")
    logger.info(f"  │    {'trade_date':<35} : {date_for_display}")
    logger.info(f"  │    {'advances':<35} : {advances_display}")
    logger.info(f"  │    {'declines':<35} : {declines_display}")
    logger.info(f"  │    {'advance_decline_ratio':<35} : {ratio_display}")
    logger.info(f"  │    {'last_updated_time':<35} : {last_updated_display}")
    logger.info(f"  └{'─'*71}┘")
    logger.info(f"")

    last_updated = datetime.now(ZoneInfo("Asia/Kolkata"))
    logger.info(f"  INJECTION     : ✓  COMMITTED TO advance_decline_metadata")
    logger.info(f"  LAST UPDATED  : {last_updated.strftime('%d-%b-%Y %I:%M:%S %p')}")
    logger.info(f"")

  elif output_nse_main_data_fetch.get("response_code") != 200:
    logger.info(f"  STATUS        : ✗  FETCH FAILED")
    logger.info(f"  ERROR CODE    : {output_nse_main_data_fetch.get('response_code')}")
    logger.info(f"  ACTION        : PROCESS ABORTED")
    logger.info(f"")
    sys.exit()

# ── FINAL SUMMARY ─────────────────────────────────────────────────────────────
end_time = dt.now()
total_duration = end_time - start_time
total_seconds = int(total_duration.total_seconds())
hours = total_seconds // 3600
minutes = (total_seconds % 3600) // 60
seconds = total_seconds % 60

logger.info(f"╔══════════════════════════════════════════════════════════════════════╗")
logger.info(f"║                         EXECUTION SUMMARY                            ║")
logger.info(f"╠══════════════════════════════════════════════════════════════════════╣")
logger.info(f"║  DATA SOURCE   : NSE INDIA                                           ║")
logger.info(f"║  TRADE DATE    : {today_date:<52}║")
logger.info(f"║  TARGET TABLE  : advance_decline_metadata                             ║")
logger.info(f"╠══════════════════════════════════════════════════════════════════════╣")
logger.info(f"║  COMPLETED AT  : {dt.now().strftime('%d-%b-%Y %I:%M:%S %p'):<52}║")
logger.info(f"║  TIME TAKEN    : {f'{hours}h {minutes}m {seconds}s':<52}║")
logger.info(f"╠══════════════════════════════════════════════════════════════════════╣")
logger.info(f"║  RESULT        : ✓  DAILY INJECTION COMPLETED SUCCESSFULLY            ║")
logger.info(f"╚══════════════════════════════════════════════════════════════════════╝")
logger.info(f"")