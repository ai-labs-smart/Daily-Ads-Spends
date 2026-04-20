import os
import gspread
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials

load_dotenv()

creds = Credentials(
    token=None,
    refresh_token=os.getenv("GOOGLE_ADS_REFRESH_TOKEN"),
    client_id=os.getenv("GOOGLE_ADS_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_ADS_CLIENT_SECRET"),
    token_uri="https://oauth2.googleapis.com/token",
    scopes=["https://www.googleapis.com/auth/spreadsheets"]
)

gc = gspread.authorize(creds)
sh = gc.open_by_key(os.getenv("GOOGLE_SHEETS_DOCUMENT_ID"))
worksheet = sh.worksheet(os.getenv("GOOGLE_SHEETS_SHEET_NAME"))

# The user's historical data from the screenshot
data = [
    ["Jan 01, 2026", "4,446.24", "5,934.65", 1, "Jan", "", "", "", ""],
    ["Jan 02, 2026", "4,265.67", "6,708.32", 1, "Jan", "", "", "", ""],
]

for row in data:
    worksheet.append_row(row, value_input_option='USER_ENTERED')

print("Seeded historical data successfully!")
