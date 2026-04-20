import os
import logging
from datetime import datetime, timedelta
import pandas as pd
from dotenv import load_dotenv
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException
import gspread
from tenacity import retry, stop_after_attempt, wait_exponential

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# ==============================================================================
# Environment Variables Configuration
# ==============================================================================
# Google Ads
GOOGLE_ADS_DEVELOPER_TOKEN = os.getenv("GOOGLE_ADS_DEVELOPER_TOKEN")
GOOGLE_ADS_CLIENT_ID = os.getenv("GOOGLE_ADS_CLIENT_ID")
GOOGLE_ADS_CLIENT_SECRET = os.getenv("GOOGLE_ADS_CLIENT_SECRET")
GOOGLE_ADS_REFRESH_TOKEN = os.getenv("GOOGLE_ADS_REFRESH_TOKEN")
GOOGLE_ADS_CUSTOMER_ID = os.getenv("GOOGLE_ADS_CUSTOMER_ID")
GOOGLE_ADS_LOGIN_CUSTOMER_ID = os.getenv("GOOGLE_ADS_LOGIN_CUSTOMER_ID") # Needed if using an MCC

# Google Sheets
GOOGLE_SHEETS_CREDENTIALS_JSON = os.getenv("GOOGLE_SHEETS_CREDENTIALS_JSON") 
GOOGLE_SHEETS_DOCUMENT_ID = os.getenv("GOOGLE_SHEETS_DOCUMENT_ID")
GOOGLE_SHEETS_SHEET_NAME = os.getenv("GOOGLE_SHEETS_SHEET_NAME", "Daily Ad Spends")


def authenticate_google_ads() -> GoogleAdsClient:
    """
    Authenticates and initializes the Google Ads API client using credentials.
    """
    try:
        credentials = {
            "developer_token": GOOGLE_ADS_DEVELOPER_TOKEN,
            "client_id": GOOGLE_ADS_CLIENT_ID,
            "client_secret": GOOGLE_ADS_CLIENT_SECRET,
            "refresh_token": GOOGLE_ADS_REFRESH_TOKEN,
            "use_proto_plus": True
        }
        
        # Only use login_customer_id if it's a valid 10-digit number (ignore placeholders)
        if GOOGLE_ADS_LOGIN_CUSTOMER_ID and GOOGLE_ADS_LOGIN_CUSTOMER_ID.replace("-", "").isdigit():
            credentials["login_customer_id"] = GOOGLE_ADS_LOGIN_CUSTOMER_ID.replace("-", "")

        client = GoogleAdsClient.load_from_dict(credentials)
        logger.info("Successfully authenticated with Google Ads API.")
        return client
    except Exception as e:
        logger.error(f"Failed to authenticate with Google Ads API: {e}")
        raise

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
def fetch_google_ads_data(client: GoogleAdsClient, customer_id: str) -> list:
    """
    Fetches the daily advertising metrics for the previous day from Google Ads API.
    """
    logger.info(f"Fetching Google Ads data for customer ID: {customer_id}")
    
    ga_service = client.get_service("GoogleAdsService")
    
    # Get yesterday's date
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    
    query = f"""
        SELECT 
            campaign.name,
            campaign.id,
            segments.date,
            metrics.cost_micros,
            metrics.impressions,
            metrics.clicks,
            metrics.conversions
        FROM campaign
        WHERE segments.date = '{yesterday}'
    """
    
    try:
        search_request = client.get_type("SearchGoogleAdsStreamRequest")
        search_request.customer_id = customer_id
        search_request.query = query
        
        response = ga_service.search_stream(search_request)
        
        results = []
        for batch in response:
            for row in batch.results:
                results.append({
                    "date": row.segments.date,
                    "campaign_id": row.campaign.id,
                    "campaign_name": row.campaign.name,
                    "cost_micros": row.metrics.cost_micros,
                    "impressions": row.metrics.impressions,
                    "clicks": row.metrics.clicks,
                    "conversions": row.metrics.conversions
                })
        
        if not results:
             logger.warning(f"No Google Ads data found for date: {yesterday}")
        else:
             logger.info(f"Successfully fetched {len(results)} rows of data.")
             
        return results
        
    except GoogleAdsException as ex:
        logger.error(f"Google Ads API Error: {ex}")
        for error in ex.failure.errors:
            logger.error(f"\tError with message: {error.message}.")
        raise

def process_data(raw_data: list) -> pd.DataFrame:
    """
    Processes the raw Google Ads data into a structured pandas DataFrame summarizing daily metrics.
    """
    if not raw_data:
        return pd.DataFrame()
        
    df = pd.DataFrame(raw_data)
    
    # Identify empty columns (mostly defensive just in case metrics return as none objects)
    df.fillna(0, inplace=True)
    
    # Convert cost from micros to actual currency
    df['cost'] = df['cost_micros'] / 1_000_000
    
    # Group by date to get daily totals across all campaigns
    daily_summary = df.groupby('date').agg({
        'cost': 'sum',
        'impressions': 'sum',
        'clicks': 'sum',
        'conversions': 'sum'
    }).reset_index()
    
    # Round columns for clean output
    daily_summary['cost'] = daily_summary['cost'].round(2)
    daily_summary['conversions'] = daily_summary['conversions'].round(2)
    
    logger.info("Successfully processed data into aggregated daily summary.")
    return daily_summary

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
def update_google_sheets(df: pd.DataFrame):
    """
    Pushes the processed data into Google Sheets.
    """
    if df.empty:
        logger.info("No data to push to Google Sheets. Skipping.")
        return

    try:
        from google.oauth2.credentials import Credentials
        
        # We reuse the OAuth refresh token we generated for Google Ads!
        creds = Credentials(
            token=None,
            refresh_token=GOOGLE_ADS_REFRESH_TOKEN,
            client_id=GOOGLE_ADS_CLIENT_ID,
            client_secret=GOOGLE_ADS_CLIENT_SECRET,
            token_uri="https://oauth2.googleapis.com/token",
            scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
        
        gc = gspread.authorize(creds)
        
        try:
            sh = gc.open_by_key(GOOGLE_SHEETS_DOCUMENT_ID)
            worksheet = sh.worksheet(GOOGLE_SHEETS_SHEET_NAME)
        except gspread.exceptions.SpreadsheetNotFound:
            logger.error(f"Spreadsheet with ID {GOOGLE_SHEETS_DOCUMENT_ID} not found.")
            raise
        except gspread.exceptions.WorksheetNotFound:
             logger.error(f"Worksheet with name '{GOOGLE_SHEETS_SHEET_NAME}' not found.")
             raise
             
        # Check if the first row is empty. If so, write the headers.
        if not worksheet.row_values(1):
            headers = ["Date", "Google Ads Spend", "Facebook Ads Spend", "Week", "Month"]
            worksheet.insert_row(headers, index=1, value_input_option='USER_ENTERED')
            logger.info("Added headers to the top of the sheet.")
             
        # Find the next available row based on Column A
        # This prevents the "shifting" issue seen in the screenshot
        next_row = len(worksheet.col_values(1)) + 1

        rows_to_insert = []
        for index, row in df.iterrows():
            date_obj = datetime.strptime(row['date'], '%Y-%m-%d')
            formatted_date = date_obj.strftime('%b %d, %Y')
            
            # Precisely match A, B, C, D, E column order
            row_data = [
                formatted_date,                # A: Date
                row['cost'],                   # B: Google Ads Spend
                "",                            # C: Facebook Ads Spend
                date_obj.isocalendar()[1],     # D: Week
                date_obj.strftime('%b')        # E: Month
            ]
            rows_to_insert.append(row_data)

        if rows_to_insert:
            # Insert the data starting at next_row, Column A (1)
            worksheet.insert_rows(rows_to_insert, row=next_row, value_input_option='USER_ENTERED')
            logger.info(f"Successfully inserted {len(rows_to_insert)} rows starting at row {next_row}.")
            
    except Exception as e:
        logger.error(f"Failed to update Google Sheets: {e}")
        raise

def main():
    try:
        logger.info("Starting Daily Ads Spend Pulling process...")
        
        # 1. Authenticate with Google Ads
        ga_client = authenticate_google_ads()
        
        # 2. Fetch Data
        # Replace hyphens in customer ID to match Google System Requirement
        customer_id = GOOGLE_ADS_CUSTOMER_ID.replace("-", "") 
        raw_data = fetch_google_ads_data(ga_client, customer_id)
        
        # 3. Process Data
        processed_data = process_data(raw_data)
        
        # 4. Update Google Sheets
        update_google_sheets(processed_data)
        
        logger.info("Process completed successfully.")
        
    except Exception as e:
        logger.error(f"Automation failed: {e}")
        raise

if __name__ == "__main__":
    main()
