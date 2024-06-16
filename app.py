from flask import Flask, render_template, request, redirect, url_for, flash, session
from datetime import datetime
import os
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build

app = Flask(__name__)
app.secret_key = 'your_generated_secret_key'

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
SERVICE_ACCOUNT_INFO = json.loads(os.getenv('GOOGLE_APPLICATION_CREDENTIALS_JSON'))

credentials = service_account.Credentials.from_service_account_info(SERVICE_ACCOUNT_INFO, scopes=SCOPES)
sheets_service = build('sheets', 'v4', credentials=credentials)

SPREADSHEET_ID = os.getenv('SPREADSHEET_ID')
NEW_SPREADSHEET_ID = os.getenv('NEW_SPREADSHEET_ID')
NEW_SHEET_NAME = os.getenv('NEW_SHEET_NAME')

customer_count = 0

def get_event_names():
    sheet = sheets_service.spreadsheets()
    range_name = f'{NEW_SHEET_NAME}!E8:Z8'
    result = sheet.values().get(spreadsheetId=NEW_SPREADSHEET_ID, range=range_name).execute()
    values = result.get('values', [])
    if not values:
        return []
    event_names = values[0] if len(values) > 0 else []
    return event_names

def get_price_for_id(event_name, item_id):
    sheet = sheets_service.spreadsheets()
    range_name = f'{NEW_SHEET_NAME}!E8:Z8'
    result = sheet.values().get(spreadsheetId=NEW_SPREADSHEET_ID, range=range_name).execute()
    event_names = result.get('values', [])[0]

    try:
        event_index = event_names.index(event_name) + 4
    except ValueError:
        return None

    range_name = f'{NEW_SHEET_NAME}!C9:C100'
    result = sheet.values().get(spreadsheetId=NEW_SPREADSHEET_ID, range=range_name).execute()
    item_ids = result.get('values', [])

    for i, row in enumerate(item_ids, start=9):
        if row[0] == item_id:
            item_row = i
            break
    else:
        return None

    range_name = f'{NEW_SHEET_NAME}!{chr(65 + event_index)}{item_row}'
    result = sheet.values().get(spreadsheetId=NEW_SPREADSHEET_ID, range=range_name).execute()
    price = result.get('values', [[None]])[0][0]

    return price

@app.route('/')
def index():
    event_names = get_event_names()
    current_event = session.get('event_name', '未設定')
    selected_price_event = session.get('price_event', '未設定')
    return render_template('index.html', customer_count=customer_count + 1, current_event=current_event, event_names=event_names, selected_price_event=selected_price_event)

@app.route('/set_event', methods=['POST'])
def set_event():
    event_name = request.form.get('event_name')
    session['event_name'] = event_name
    return redirect(url_for('index'))

@app.route('/set_price_event', methods=['POST'])
def set_price_event():
    event_name = request.form.get('price_event')
    session['price_event'] = event_name
    return redirect(url_for('index'))

@app.route('/reset_event', methods=['POST'])
def reset_event():
    global customer_count
    session.pop('event_name', None)
    session.pop('price_event', None)
    customer_count = 0
    return redirect(url_for('index'))

@app.route('/record', methods=['POST'])
def record_sale():
    global customer_count
    customer_count += 1
    customer_id = customer_count

    sales = request.form.get('sales').split(',')
    quantities = request.form.get('quantities').split(',')
    gender = request.form.get('gender')
    age_group = request.form.get('age_group')
    features = request.form.get('features', '')
    event_name = session.get('event_name')
    price_event = session.get('price_event')
    payment_method = request.form.get('payment_method')

    if not sales or not quantities or len(sales) != len(quantities) or not gender or not age_group or not event_name or not price_event or not payment_method:
        flash('すべての必須フィールドに正しく入力してください。')
        customer_count -= 1
        return redirect(url_for('index'))

    try:
        quantities = [int(q) for q in quantities]
    except ValueError:
        flash('数量は整数で入力してください。')
        customer_count -= 1
        return redirect(url_for('index'))

    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    try:
        sheet_metadata = sheets_service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
        sheets = sheet_metadata.get('sheets', '')
        sheet_names = [sheet.get("properties", {}).get("title", "") for sheet in sheets]

        if event_name not in sheet_names:
            requests = [{
                'addSheet': {
                    'properties': {
                        'title': event_name
                    }
                }
            }]
            body = {
                'requests': requests
            }
            sheets_service.spreadsheets().batchUpdate(
                spreadsheetId=SPREADSHEET_ID,
                body=body
            ).execute()
            
            header_values = [["アイテム番号", "顧客番号", "タイムスタンプ", "性別", "年代", "特徴", "支払い方法"]]
            header_body = {
                'values': header_values
            }
            sheets_service.spreadsheets().values().append(
                spreadsheetId=SPREADSHEET_ID,
                range=f'{event_name}!A1',
                valueInputOption='RAW',
                insertDataOption='INSERT_ROWS',
                body=header_body
            ).execute()

    except Exception as error:
        print(f"An error occurred while creating the sheet: {error}")
        flash(f'シート作成中にエラーが発生しました: {error}')
        return redirect(url_for('index'))

    values = []
    total_sales = 0
    for sale, quantity in zip(sales, quantities):
        price = get_price_for_id(price_event, sale.strip())
        if price is None:
            flash(f'アイテム番号 {sale} の価格が見つかりません。')
            customer_count -= 1
            return redirect(url_for('index'))
        total_sales += int(price) * quantity
        for _ in range(quantity):
            values.append([sale.strip(), customer_id, timestamp, gender, age_group, features, payment_method])

    body = {
        'values': values
    }

    try:
        sheets_service.spreadsheets().values().append(
            spreadsheetId=SPREADSHEET_ID,
            range=f'{event_name}!A2',
            valueInputOption='RAW',
            insertDataOption='INSERT_ROWS',
            body=body
        ).execute()
        flash(f'売り上げが記録されました。顧客番号: {customer_id}, 合計売上: {total_sales} 円')
    except Exception as error:
        print(f"An error occurred: {error}")
        flash(f'Googleスプレッドシートにデータを追加する際にエラーが発生しました: {error}')

    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
