from flask import Flask, render_template, request, redirect, url_for, flash, session
from datetime import datetime
import os
from google.oauth2 import service_account
from googleapiclient.discovery import build
import json

app = Flask(__name__)
app.secret_key = 'your_generated_secret_key'

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

# 環境変数からcredentials.jsonの内容を読み込む
credentials_info = json.loads(os.getenv('GOOGLE_APPLICATION_CREDENTIALS_JSON'))
credentials = service_account.Credentials.from_service_account_info(credentials_info, scopes=SCOPES)

sheets_service = build('sheets', 'v4', credentials=credentials)
SPREADSHEET_ID = '1REDUL2cKWozcH1wVOJOPBbySEGENA8t2RstmgrWQDY4'

customer_count = 0

@app.route('/')
def index():
    global customer_count
    current_event = session.get('event_name', '未設定')
    return render_template('index.html', customer_count=customer_count + 1, current_event=current_event)

@app.route('/set_event', methods=['POST'])
def set_event():
    event_name = request.form.get('event_name')
    session['event_name'] = event_name
    return redirect(url_for('index'))

@app.route('/reset_event', methods=['POST'])
def reset_event():
    global customer_count
    session.pop('event_name', None)
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
    payment_method = request.form.get('payment_method')

    if not sales or not quantities or len(sales) != len(quantities) or not gender or not age_group or not event_name or not payment_method:
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

    # シートが存在しない場合は新しいシートを作成
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
            
            # 新しいシートが作成されたらヘッダーを追加
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

    # データをGoogleスプレッドシートに追加
    values = []
    for sale, quantity in zip(sales, quantities):
        for _ in range(quantity):
            values.append([sale.strip(), customer_id, timestamp, gender, age_group, features, payment_method])

    body = {
        'values': values
    }

    try:
        sheets_service.spreadsheets().values().append(
            spreadsheetId=SPREADSHEET_ID,
            range=f'{event_name}!A2',  # データの開始位置をシートの2行目からに設定
            valueInputOption='RAW',
            insertDataOption='INSERT_ROWS',
            body=body
        ).execute()
        flash(f'売り上げが記録されました。顧客番号: {customer_id}')
    except Exception as error:
        print(f"An error occurred: {error}")
        flash(f'Googleスプレッドシートにデータを追加する際にエラーが発生しました: {error}')

    return redirect(url_for('index'))
