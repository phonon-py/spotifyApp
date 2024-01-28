import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_bootstrap import Bootstrap
from flask_login import login_user, logout_user, UserMixin, LoginManager, login_required
from flask import session
import requests
import json
from config import CLIENT_ID, CLIENT_SECRET, NOTION_TOKEN, NOTION_PAGE_ID
import os
import logging
from werkzeug.security import generate_password_hash, check_password_hash

# loggingの設定
logging.basicConfig(filename='app.log', level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')

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
    logging.info(f"get_track_info 関数開始: {track_url}")
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
        logging.info("get_track_info 関数終了")
        return data

    except Exception as e:
        logging.error(f"get_track_info 関数でエラー: {e}", exc_info=True)
        return f"エラーが発生しました: {e}"

app = Flask(__name__)
# Flask-Loginの設定
login_manager = LoginManager()
login_manager.login_view = 'login'  # 未認証ユーザーがリダイレクトされるビュー
login_manager.init_app(app)  # FlaskアプリにLoginManagerを登録

# ユーザーローダーの設定
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# セッション管理のためのシークレットキーを設定します。ランダムなキーを生成するには os.urandom(24) を使用できます。
app.secret_key = os.urandom(24)
# または、ハードコードされたキーを設定することもできますが、それは秘密に保つ必要があります：
# app.secret_key = 'あなたの秘密のキー'z

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////Users/kimuratoshiyuki/Dropbox/Python/SpotifyApp/site.db'
db = SQLAlchemy(app)
bootstrap = Bootstrap(app)


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))  # パスワードのハッシュ
    searches = db.relationship('Search', backref='author', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Search(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        # ユーザー名が既に存在するかチェック
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            # 既に存在するユーザー名であることを通知する
            return "このユーザー名は既に使用されています。別のユーザー名を選んでください。"

        # パスワードのハッシュ化
        hashed_password = generate_password_hash(password)

        # 新しいユーザーの作成
        new_user = User(username=username, password_hash=hashed_password)
        db.session.add(new_user)
        db.session.commit()

        return redirect(url_for('login'))  # ログインページへリダイレクト

    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()

        # ユーザーの存在とパスワードの確認
        if user and check_password_hash(user.password_hash, password):  # 'password' を 'password_hash' に修正
            login_user(user)
            session['username'] = username
            return redirect(url_for('home'))  # ホームページへリダイレクト

        else:
            # ログイン失敗
            return 'Invalid username or password'

    return render_template('login.html')

@app.route('/save_search', methods=['POST'])
@login_required
def save_search():
    try:
        # フォームからJSONデータを取得
        confirmed_data = request.form.get('confirmed_data')
        if confirmed_data:
            # JSONデータをPythonオブジェクトに変換
            track_data = json.loads(confirmed_data)

            # 現在ログインしているユーザーの取得
            user = User.query.filter_by(username=session['username']).first()
            if user:
                # 新しい検索オブジェクトの作成
                new_search = Search(content=confirmed_data, user_id=user.id)

                # 検索オブジェクトをデータベースに追加
                db.session.add(new_search)
                db.session.commit()

                # ユーザーページにリダイレクト
                return redirect(url_for('user_page'))
            else:
                return "ユーザーが見つかりません。", 404
        else:
            return "確認データがありません。", 400
    except Exception as e:
        # エラー処理
        return str(e), 500

@app.route('/logout')
@login_required  # ログアウトはログイン済みのユーザーのみがアクセス可能
def logout():
    logout_user()  # ユーザーのログアウト処理
    return redirect(url_for('home'))  # ログインページにリダイレクト

def create_tables():
    with app.app_context():
        db.create_all()
        
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
        logging.info(f"トラックURL受信: {track_url}")
        # 'intl-ja' を削除する処理
        track_url = track_url.replace('intl-ja', '')

        # URL内の '//' を '/' に置き換える
        track_url = track_url.replace('//', '/')

        # 'https:/' を 'https://' に戻す
        track_url = track_url.replace('https:/', 'https://')

        data = get_track_info(track_url)
        return redirect(url_for('confirm', data=json.dumps(data)))
    else:
        return render_template('index.html')

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

if __name__ == '__main__':
    # 本番環境ではより細かくマイグレーションを管理する必要がある
    create_tables()
    app.run(debug=True)
