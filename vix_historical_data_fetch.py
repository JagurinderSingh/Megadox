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

load_dotenv()

#For Null Values Check
empty_data_list = [None, "None", "0", 0, "-", "NaN", "Null", "NULL", "null", "none", "nan"] #Used only during data cleaning

index_id = 136

def database_engine_connection():

  #Engine Connection Established
  database_password = os.getenv("database_password")
  DB_URL = f"postgresql://postgres:{database_password}@localhost:5432/index_value_strategy" #No Problem right now even if the password is exposed because this module will only be used to fill past data for all the indices
  engine = create_engine(DB_URL)
  return engine

output_database_engine_connection = database_engine_connection()

def index_name_fetcher(index_id):
  
  #Extract Info
  with output_database_engine_connection.connect() as conn: #Using the Connection done via Engine

    #Fetching Index_Long_Name and Trading_Index_Name
    query = text("SELECT index_id, index_long_name, trading_index_name FROM index_metadata WHERE index_id = :index_id_program")
    result = conn.execute(query, {"index_id_program": index_id}).fetchone()

    #Decode the Index Long Name
    index_long_name = result.index_long_name
    encoded_index_long_name = urllib.parse.quote(index_long_name)

    return {"index_long_name":index_long_name}
  
output_index_name_fetcher = index_name_fetcher(index_id)

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

def nse_main_data_fetch(acceptable_start_date, acceptable_rolling_date):
    
    # The Actual Data Fetch
    encoded_index_long_name = urllib.parse.quote(output_index_name_fetcher.get("index_long_name"))

    url = f"https://www.nseindia.com/api/historicalOR/vixhistory?from={acceptable_start_date}&to={acceptable_rolling_date}"

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

#Printing the Index Long Name to the user
print(f"Index Long Name: {output_index_name_fetcher.get("index_long_name")}")

# Enter Data Source Choice
data_source = "NSE INDIA"
print("")

proceed = int(input("Enter 1 to Proceed and 0 to Abort: ")) #Green Flag Validation
print("")

if proceed == 1:

  # Input Starting Date
  starting_day = int(input("Enter Starting Day: "))
  starting_month = int(input("Enter Starting Month: "))
  starting_year = int(input("Enter Starting Year: "))
  start_date = datetime(starting_year, starting_month, starting_day)
  origin_date = start_date
  print("")

  # Input Ending Date
  ending_day = int(input("Enter Ending Day: "))
  ending_month = int(input("Enter Ending Month: "))
  ending_year = int(input("Enter Ending Year: "))
  end_date = datetime(ending_year, ending_month, ending_day)
  print("")

  # Rolling Date Calculation
  rolling_date = start_date + timedelta(days=30)
  print("")

  with output_database_engine_connection.connect() as conn:
    print("Connection Established Successfully!")
    print("")

    #Setting up the environment just for one time and then utilizing it to hit API again and again
    session = output_environment_setup_nse_main.get("session")
    headers = output_environment_setup_nse_main.get("headers")

    #Pushing Actual Data

    while start_date <= rolling_date:

      # Preparing Dates in acceptable formats
      acceptable_start_date = start_date.strftime("%d-%m-%Y") #For NSE Main Start Date
      acceptable_rolling_date = rolling_date.strftime("%d-%m-%Y") #For NSE Main Rolling Date

      output_nse_main_data_fetch = nse_main_data_fetch(acceptable_start_date, acceptable_rolling_date)
    
      if output_nse_main_data_fetch.get("response_code") == 200:

        #Data Injection Code here
        print(f"{start_date} to {rolling_date}")
        print(f"Data: {output_nse_main_data_fetch.get("data")}")
        print("")
        data_inject_nse_main_database(output_nse_main_data_fetch.get("data"))
          
        # Resetting the Dates
        start_date = rolling_date + timedelta(days=1)
        # Ensure rolling_date doesn't exceed end_date
        rolling_date = min(start_date + timedelta(days=30), end_date) #Takes closer date - end date or the +30 days date

        if rolling_date != end_date:
          #Randomized Break
          next_request_wait = random.uniform(1, 10)
          print(f"Wait: {next_request_wait} Seconds")
          time.sleep(next_request_wait)
          print("")

      elif output_nse_main_data_fetch.get("response_code") != 200:
        print(f"Response Code: {output_nse_main_data_fetch.get("response_code")}")
        print("Data Fetch Failed!")
        break

    print(f"Primary Data Source: NSE INDIA")
    source = "NSE INDIA"
    print(f"Index Long Name: {output_index_name_fetcher.get("index_long_name")}")

    query = text("UPDATE index_metadata SET source = :source, last_updated_time = :last_updated_time, data_origin_date = :data_origin_date WHERE index_id = :index_id")
    conn.execute(query, {"source":source,"index_id":index_id,"last_updated_time":datetime.now(ZoneInfo("Asia/Kolkata")), "data_origin_date":origin_date}) #tzinfo stores that part of time which tells us the timezone by setting it None, we remove that part so clean date and time goes into the table
    conn.commit()
    print("Updated index_metadata Cleanly!")
    print("")

elif proceed == 0:
  print("Process Aborted!")
  sys.exit()
  
