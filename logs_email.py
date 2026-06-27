import smtplib #Simple Mail Transfer Protocol Library
import ssl #Secure sockets layer so whatever we send over the internet is encrypted properly
from email.mime.multipart import MIMEMultipart #Multipurpose Internet Mail Extensions - used to create a container box that holds different sections of emails together - headers, body, files, etc
from email.mime.text import MIMEText #Converts modern components like Emojis, etc properly into formatted text that Gmail can render properly
from email.mime.application import MIMEApplication #Used to handle the file data
from dotenv import load_dotenv
import os
from datetime import date

today_date = date.today() #date datatype along with the format of YYYY-MM-DD

formatted_date = today_date.strftime("%d-%m-%Y") #Plug in the file name

load_dotenv() #Used to load the environment variables in the python script i.e. email addresses or passwords

#Coordinates

SMTP_SERVER = "smtp.gmail.com" #The server that we will use to send the email
SMTP_PORT = 465 #Port on Google's server that builds a secure encrypted tunnel before sending any mail or message
SENDER_EMAIL = os.getenv("sender_email")
RECEIVER_EMAIL = os.getenv("receiver_email")
APP_PASSWORD = os.getenv("email_app_password") #another password that gives full access to google account for sending emails

#Building the Payload to send via Email
message = MIMEMultipart() #Initializes the blank electronic mail envelope
message["From"] = SENDER_EMAIL
message["To"] = RECEIVER_EMAIL
message["Subject"] = "📊 Megadox Automated Log Report"

#Putting the exact body_text into the email
body_text = "This is an automated Email from the Megadox for notification regarding latest execution logs of Data Ingestion Pipeline"
message.attach(MIMEText(body_text, "plain")) #Converts Python String to formatted strcuctured email text to be put inside the email and puts it there

#Reading the file with the help of file path
owner_name = os.getenv("owner_name")
file_path = f"/home/{owner_name}/Megadox/logs/fetch_log_{formatted_date}.md"

try:
  with open(file_path, "rb") as f: #Opens the file in binary read mode to properly render the images and any kind of attachments
    file_data = f.read() #Stores all file data in form of binary 
    file_name = os.path.basename(file_path)

    #Package it into the MIME Container
    attachment = MIMEApplication(file_data, _subtype="octet-stream")

    #Giving the attachment file a header so inbox knows how to download it
    attachment.add_header(
      "Content-Disposition",
      f"attachment; filename={file_name}"
    ) #lets email client understand that this file to not to be shown as raw text, instead a download clip icon must be showed to the user

    #Drop attachment into main message box
    message.attach(attachment)
    print(f"Successfully attached: {file_name}")

except FileNotFoundError:
  print(f"⚠️ Error: The file at {file_path} was not found! Sending email without attachment.")

#Opening established Tunnel and sending email safely
context = ssl.create_default_context() #Fulfills the encryption requirements for the connection

try:
  with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, context=context) as server: #with statement automatically opens and closes the connection as soon as the task is executed - with is just like a context manager - it has two parts - __enter__() - which runs at the beginning of each block and __exit__() block which runs automatically as soon the block is left
    server.login(SENDER_EMAIL, APP_PASSWORD) #logs into the required google account to send the email
    server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, message.as_string())#It finally structures everything we did above as the message and use Google's infrastructure to send the email
  print("Email Sent Successfully!")

except Exception as e:
  print(f"Error sending Email: {e}") #Shows what type of error caused failure to send the email






