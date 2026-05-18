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

load_dotenv()

#For Null Values Check
empty_data_list = [None, "None", "0", 0, "-", "NaN", "Null", "NULL", "null", "none", "nan"] #Used only during data cleaning

def database_engine_connection():

  #Engine Connection Established
  database_password = os.getenv("database_password")
  DB_URL = f"postgresql://postgres:{database_password}@localhost:5432/index_value_strategy"
  engine = create_engine(DB_URL)
  return engine

output_database_engine_connection = database_engine_connection()

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
    print(url)
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

# Data Source
data_source = "NSE INDIA"
print("")

#Months
months_list = ["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV", "DEC"]

#Years
years_list = []

# Input Starting Month and Year
starting_month = str(input("Enter Starting Month (First Three Letters of Month): "))
starting_year = int(input("Enter Starting Year: "))
print("")

# Input Ending Month and Year
ending_month = str(input("Enter Ending Month (First Three Letters of Month): "))
ending_year = int(input("Enter Ending Year: "))
print("")

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

with output_database_engine_connection.connect() as conn:
  print("Connection Established Successfully!")
  print("")

  #Setting up the environment just for one time and then utilizing it to hit API again and again
  session = output_environment_setup_nse_main.get("session")
  headers = output_environment_setup_nse_main.get("headers")

  #Pushing Actual Data

  for iteration_item in compiled_list:

    output_nse_main_data_fetch = nse_main_data_fetch(iteration_item)
    
    if output_nse_main_data_fetch.get("response_code") == 200:

      #Data Injection Code here
      print(f"Data: {output_nse_main_data_fetch.get("data")}")
      print("")
      data_inject_nse_main_database(output_nse_main_data_fetch.get("data"))

      #Randomized Break
      next_request_wait = random.uniform(1, 10)
      print(f"Wait: {next_request_wait} Seconds")
      time.sleep(next_request_wait)
      print("")

    elif output_nse_main_data_fetch.get("response_code") != 200:
      print(f"Response Code: {output_nse_main_data_fetch.get("response_code")}")
      print("Data Fetch Failed!")
      print("Process Aborted!")
      sys.exit()
      break
