# Google Ads to Sheets Automation Guide

This guide covers setting up the Python-based Google Ads extraction script, replacing your previous Make.com automation.

## Components Provided
- `google_ads_to_sheets.py`: The main automation script handling Google Ads extraction and Sheet pushes.
- `requirements.txt`: Python package dependencies.
- `.env.example`: Env variables template for testing locally.
- `.github/workflows/daily_ads_pull.yml`: Pre-configured GitHub action to run your script independently on a cron schedule.

---

> [!IMPORTANT]
> Because you are extracting data via the native python SDK and not through a 3p provider, you must configure both a **Google Ads Developer Account API** as well as a **Google Cloud Project** for Sheets and OAuth.

## Phase 1: Google Ads API Access
Before you can pull data, you require three elements: Developer Token, OAuth2 Client ID/Secret, and a Refresh Token.

### 1. Get a Developer Token
1. Log into your Google Ads Manager Account (MCC).
2. Go to `Tools & Settings` > `API Center` (under Setup).
3. If it's your first time, complete the developer configuration to get a **Developer Token**. Initially, it will be in "Test" mode, you will need to request Basic Access if pulling live production data for accounts outside your immediate test list.

### 2. Generate OAuth2 Client ID & Secret
1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Create standard New Project (e.g. "Ads Reporting Automations").
3. Go to **APIs & Services** > **Enabled APIs and services**. Enable the **Google Ads API**.
4. Go to **OAuth consent screen** and configure it (you can set it to "Internal" or "External" with testing mode enabled).
5. Go to **Credentials** > **Create Credentials** > **OAuth client ID**.
6. Select **Desktop App** as the application type.
7. Note down your **Client ID** and **Client Secret**.

### 3. Generate a Refresh Token
Since the script needs to run offline in GitHub actions without user supervision, you must supply a refresh token.
Google provides a quick python script or curl setup to do this, but the easiest method:
1. Clone Google's Ads Python library: `git clone https://github.com/googleads/google-ads-python.git`
2. Run their generator: `python google-ads-python/examples/authentication/authenticate_in_desktop_application.py --client_id="YOUR_CLIENT_ID" --client_secret="YOUR_CLIENT_SECRET"`
3. Click the link the script provides in your terminal, authorize with the email that has access to the Google Ads MCC, and paste the code back.
4. You will receive a **Refresh Token**. Store it securely.

## Phase 2: Google Sheets Service Account
You'll use a Service Account so the script can edit the sheet in the background.
1. In your Google Cloud Project, go to **Enabled APIs and services** > Enable **Google Sheets API**.
2. Go to **Credentials** > **Create Credentials** > **Service Account**.
3. Create account (e.g., `sheets-automation@...`). Skip the role additions.
4. Once created, click on the Service Account > **Keys** > **Add Key** > **Create New Key (JSON)**.
5. Download the `.json` file and rename it to `service_account.json` (save this locally next to the script).
6. **Important Check**: Open your Google Sheets document, click "Share", and share Editor access with the email address of the service account you just created.

## Phase 3: Local Setup & Testing

1. Rename `.env.example` to `.env`.
2. Populate the `.env` file with the keys generated above.
   > [!NOTE]
   > `GOOGLE_ADS_LOGIN_CUSTOMER_ID` is strictly required if the email you used to authorize the OAuth flow belongs to an MCC (Manager Account) managing the specific Account ID. Use the MCC's ID without hyphens.
3. Install dependencies: `pip install -r requirements.txt`.
4. Run locally to test: `python google_ads_to_sheets.py`. Check your target Google Sheet.

## Phase 4: GitHub Actions Deployment

Once running locally, let's configure the daily GitHub Action.
1. Push your code to your GitHub Repository.
2. In your repo, go to **Settings** > **Secrets and variables** > **Actions**.
3. Create **New repository secret** for the following:
   - `GOOGLE_ADS_DEVELOPER_TOKEN`
   - `GOOGLE_ADS_CLIENT_ID`
   - `GOOGLE_ADS_CLIENT_SECRET`
   - `GOOGLE_ADS_REFRESH_TOKEN`
   - `GOOGLE_ADS_CUSTOMER_ID`
   - `GOOGLE_ADS_LOGIN_CUSTOMER_ID`
   - `GOOGLE_SHEETS_DOCUMENT_ID`
   - `GOOGLE_SHEETS_CREDENTIALS_JSON` (Paste the absolute stringified content of the `service_account.json` contents directly into this secret)

The Automation `.github/workflows/daily_ads_pull.yml` will now run every day at 02:00 AM UTC and append a new line to the spreadsheet!
