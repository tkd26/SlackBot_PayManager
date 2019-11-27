# -*- coding: utf-8 -*-
import os
import json
import logging
import urllib.request

import datetime
import pickle
import jpholiday
import os.path
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

# ログ設定
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def handle_slack_event(slack_event: dict, context) -> str:

    # 受け取ったイベント情報をCloud Watchログに出力
    logging.info(json.dumps(slack_event))

    # Event APIの認証
    if "challenge" in slack_event:
        return slack_event.get("challenge")

    # ボットによるイベントまたはメッセージ投稿イベント以外の場合
    # 反応させないためにそのままリターンする
    # Slackには何かしらのレスポンスを返す必要があるのでOKと返す
    # （返さない場合、失敗とみなされて同じリクエストが何度か送られてくる）
    if is_bot(slack_event) or not is_message_event(slack_event):
        return "OK"

    # Slackにメッセージを投稿する
    text = slack_event.get("event").get("text")

    pay_msg = MakePayMsg()
    
    if 'help' in text:
        msg = '知りたい情報に対応する番号を入力してください！\n'
        msg += '(1)来月の給料\n'
        msg += '(2)今年の給料\n'
        msg += '(3)給料のログ\n'
    elif text == '1':
        msg = '来月の給料は￥{}です！'.format(pay_msg.monthpay())
    elif text == '2':
        msg = '{}'.format(pay_msg.yearpay())
    elif text == '3':
        msg = '給料ログ\n{}'.format(pay_msg.paylog())
    else:
        msg = '\クエー/'
        
    post_message_to_slack_channel(msg, slack_event.get("event").get("channel"))

    # メッセージの投稿とは別に、Event APIによるリクエストの結果として
    # Slackに何かしらのレスポンスを返す必要があるのでOKと返す
    # （返さない場合、失敗とみなされて同じリクエストが何度か送られてくる）
    return "OK"

def is_bot(slack_event: dict) -> bool:
    return slack_event.get("event").get("subtype") == "bot_message"


def is_message_event(slack_event: dict) -> bool:
    return slack_event.get("event").get("type") == "message"

def post_message_to_slack_channel(message: str, channel: str):
    # Slackのchat.postMessage APIを利用して投稿する
    # ヘッダーにはコンテンツタイプとボット認証トークンを付与する
    url = "https://slack.com/api/chat.postMessage"
    headers = {
        "Content-Type": "application/json; charset=UTF-8",
        "Authorization": "Bearer {0}".format(os.environ['SLACK_BOT_USER_ACCESS_TOKEN'])
    }
    data = {
        "token": os.environ['SLACK_APP_AUTH_TOKEN'],
        "channel": channel,
        "text": message,
        "username": "Bot-Sample"
    }
    req = urllib.request.Request(url, data=json.dumps(data).encode("utf-8"), method="POST", headers=headers)
    urllib.request.urlopen(req)
    return



class MakePayMsg():
    def __init__(self):
    
        self.SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']
        self.now = datetime.datetime.now()
        self.events = self.get_event()
        self.pay_log = self.make_paylog()

    def get_event(self):
        creds = None
        if os.path.exists('token.pickle'):
            with open('token.pickle', 'rb') as token:
                creds = pickle.load(token)
        # If there are no (valid) credentials available, let the user log in.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    'credentials.json', self.SCOPES)
                creds = flow.run_local_server(port=0)
            # Save the credentials for the next run
            with open('/tmp/token.pickle', 'wb') as token:
                pickle.dump(creds, token)

        service = build('calendar', 'v3', credentials=creds)

        calender_id = os.environ['CALENDER_ID']

        page_token = None
        events = service.events().list(calendarId=calender_id, pageToken=page_token).execute()
        return events


    def make_paylog(self):
        pay_log = []
        cal = CalculatePay(1013, 1063, 1.25, 22)
        for event in self.events['items']:
            stime = event['start']['dateTime']
            stime = datetime.datetime(
                int(stime[0:4]), int(stime[5:7]), int(stime[8:10]),
                int(stime[11:13]), int(stime[14:16]))
            etime = event['end']['dateTime']
            etime = datetime.datetime(
                int(etime[0:4]), int(etime[5:7]), int(etime[8:10]),
                int(etime[11:13]), int(etime[14:16]))
            
            if self.now.month != 12:
                sdate = datetime.date(self.now.year-1, 12, 1)
                edate = datetime.date(self.now.year, 11, 30)
            else:
                sdate = datetime.date(self.now.year, 12, 1)
                edate = datetime.date(self.now.year+1, 11, 30)

            if (stime.date() >= sdate) and (etime.date() <= edate):
                daypay = cal.calculate(stime, etime)
                if stime.month==12:
                    daypay_dir = {'date':stime.date(), 'month':1, 'pay':daypay}
                else:
                    daypay_dir = {'date':stime.date(), 'month':stime.month+1, 'pay':daypay}
                pay_log += [daypay_dir]
        
        return pay_log
            

    def monthpay(self):
        mpay = 0
        for i in self.pay_log:
            if i['month'] == (self.now.month+1):
                mpay += i['pay']
        return mpay

    def yearpay(self):
        mpay_list = [0] * 12
        for i in self.pay_log:
            mpay_list[i['month']-1] += i['pay']
        
        msg = ''
        for i, mpay in enumerate(mpay_list):
            msg += '{}月 ￥{:,}\n'.format(i+1, mpay)
        msg += '\n合計￥{}'.format(sum(mpay_list))
        return msg

    def paylog(self):
        msg = ''
        month = 0
        for i in self.pay_log:
            while i['month'] != month:
                msg += '\n{}月\n'.format(month+1)
                month += 1
            msg += '{} ￥{:,}\n'.format(i['date'], i['pay'])
        return msg


class CalculatePay():
  def __init__(
    self, basic_pay, irregular_pay, night_rate, night_time):
    
    self.basic_pay = basic_pay
    self.irregular_pay = irregular_pay
    self.night_rate = night_rate
    self.night_time = night_time

  def calculate(self, stime, etime):
    night_time = datetime.datetime(
      stime.year, stime.month, stime.day, self.night_time)
    
    if stime.weekday() >= 5 or jpholiday.is_holiday(stime.date()):
      pay = self.irregular_pay
    else:
      pay = self.basic_pay

    if etime >= night_time:
      normal_time = self.get_h(night_time - stime)
      night_time = self.get_h(etime - night_time)
      daypay = normal_time * pay + night_time * (pay * self.night_rate)
    else:
      normal_time = self.get_h(etime - stime)
      daypay = normal_time * pay

    return round(daypay)

  def get_h(self, delta_time):
    h = delta_time.seconds / 3600
    return h
