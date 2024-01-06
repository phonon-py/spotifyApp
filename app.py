import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from flask import Flask, render_template, request, redirect, url_for
from flask_bootstrap import Bootstrap
import requests
import json
import os

CLIENT_ID = os.environ.get('CLIENT_ID')
CLIENT_SECRET = os.environ.get('CLIENT_SECRET')
NOTION_TOKEN = os.environ.get('NOTION_TOKEN')
NOTION_PAGE_ID = os.environ.get('NOTION_PAGE_ID')

# エラーハンドリング：環境変数が設定されていない場合
if CLIENT_ID == 'YourDefaultClientId' or CLIENT_SECRET == 'YourDefaultClientSecret':
    print("環境変数 CLIENT_ID または CLIENT_SECRET が設定されていません。")
if NOTION_TOKEN == 'YourDefaultNotionToken' or NOTION_PAGE_ID == 'YourDefaultNotionPageId':
    print("環境変数 NOTION_TOKEN または NOTION_PAGE_ID が設定されていません。")

# Notionへデータ送信
def send_to_notion(data):
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }

    notion_data = {
        "parent": {"page_id": NOTION_PAGE_ID},
        "properties": {
            "title": {
                "title": [
                    {
                        "text": {
                            "content": f"{data['track_name']} by {data['artist_name']}"
                        }
                    }
                ]
            }
        },
        "children": [
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {
                                "content": data['description']
                            }
                        }
                    ]
                }
            }
        ]
    }

    return requests.post('https://api.notion.com/v1/pages', headers=headers, json=notion_data)

# Spotify APIのクライアントIDとシークレットを設定
client_id = CLIENT_ID
client_secret = CLIENT_SECRET

client_credentials_manager = SpotifyClientCredentials(client_id=client_id, client_secret=client_secret)
sp = spotipy.Spotify(client_credentials_manager=client_credentials_manager)

def get_artist_id(track):
    return track['artists'][0]['id']

def get_related_artists(artist_id):
    related_artists = sp.artist_related_artists(artist_id)
    return related_artists

def get_track_info(track_url):
    try:
        track_result = sp.track(track_url)
        artist_name = track_result['album']['artists'][0]['name']
        track_name = track_result['name']
        artist_id = get_artist_id(track_result)
        related_artists = get_related_artists(artist_id)
        related_artists_names = [artist['name'] for artist in related_artists['artists']]

        track_info = sp.audio_features(track_url)
        key = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'][track_info[0]['key']]
        mode = ['major', 'minor'][track_info[0]['mode']]
        bpm = track_info[0]['tempo']

        artist_uri = track_result['album']['artists'][0]['uri']
        artist_info = sp.artist(artist_uri)
        genres = artist_info['genres']

        data = {
        "artist_name": artist_name,
        "track_name": track_name, 
        "description": f"関連アーティスト: {', '.join(related_artists_names)}\nGenres: {', '.join(genres)}\nBPM: {bpm}\nKey: {key}, Mode: {mode}"
    }
        return data

    except Exception as e:
        return f"エラーが発生しました: {e}"

app = Flask(__name__)
bootstrap = Bootstrap(app)

@app.route('/confirm', methods=['GET', 'POST'])
def confirm():
    if request.method == 'POST':
        raw_data = request.form['confirmed_data']
        print("Raw data:", raw_data)  # デバッグ出力
        try:
            data = json.loads(request.form['confirmed_data'])
            response = send_to_notion(data)
            if response.status_code != 200:
                print("Error:", response.json())
                return "Notionへの送信に失敗しました。"
            return "Notionに情報を送信しました。"
        except json.JSONDecodeError as e:
            print("JSON解析エラー:", e)
            return "送信データの解析に失敗しました。"
    else:
        data = request.args.get('data')
        return render_template('confirm.html', data=json.loads(data))

@app.route('/', methods=['GET', 'POST'])
def home():
    if request.method == 'POST':
        track_url = request.form['track_url']
        data = get_track_info(track_url)
        return redirect(url_for('confirm', data=json.dumps(data)))
    else:
        return render_template('index.html')

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

if __name__ == '__main__':
    app.run(debug=True)
