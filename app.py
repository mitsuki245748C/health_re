# Flaskアプリの基本構成
# 健康管理アプリ「健やか康くん」
# 基本的な機能（歩数登録/目標登録/ログイン等）を含む

from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date, timedelta
import matplotlib
matplotlib.use('Agg')

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import io,base64
from markupsafe import Markup

plt.rcParams['font.family'] = 'Hiragino Sans ' #macOsによくあるフォント名

app = Flask(__name__)
app.secret_key = 'secret-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///kenkou.db'
db = SQLAlchemy(app)

# ユーザーモデル
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    height = db.Column(db.Float)
    weight = db.Column(db.Float)
    age = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

# 歩数記録
class StepRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date = db.Column(db.Date, default=date.today)
    steps = db.Column(db.Integer, default=0)

# 歩数目標
class StepGoal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date = db.Column(db.Date, default=date.today)
    goal_steps = db.Column(db.Integer, default=0)

# ホーム
@app.route('/home')
def index():
    if 'user_id' in session:
        user = db.session.get(User, session['user_id'])
        today = date.today()
        #今日の歩数と目標を取得
        record = StepRecord.query.filter_by(user_id=user.id, date=today).first()
        goal = StepGoal.query.filter_by(user_id=user.id, date=today).first()

        #目標連続達成記録を計算
        records = StepRecord.query.filter_by(user_id=user.id).order_by(StepRecord.date.desc()).all()
        goals = {g.date: g.goal_steps for g in StepGoal.query.filter_by(user_id=user.id).all()}

        streak = 0
        for r in records:
            g = goals.get(r.date)
            if g and r.steps >= g:
                streak += 1
            else:
                break
        # メッセージ
        if streak >= 1:
            message = f"🌟 目標達成おめでとうございます！現在{streak}日連続で目標達成中です！"
        else:
            message = "がんばって歩きましょう！💪"

        return render_template('home.html',
                                user=user,
                                steps=record.steps if record else 0,
                                goal_steps=goal.goal_steps if goal else 0,
                                streak_days=streak,
                                message=message,
                                today=today.strftime("%-m月%-d日")
                               )
    return redirect(url_for('login'))

#利用者情報一覧表示(管理者機能)
@app.route('/admin/users',methods=['GET'])
def admin_user_list():
    user = db.session.get(User,session['user_id'])
    status_message = request.args.get('message')
    message_category = request.args.get('category', 'info')
    today_date_formatted = datetime.now().strftime("%-m月%-d日")
    all_users = User.query.order_by(User.id.asc()).all()
    return render_template('user_list.html', 
                           all_users=all_users,
                           user=user,
                           today_date_formatted=today_date_formatted,
                           status_message=status_message,
                           message_category=message_category)

@app.route('/admin/users/delete/<int:user_id>',methods=['POST'])
def delete_user(user_id):
    user_to_delete = db.session.get(User,user_id)
    current_user = db.session.get(User, session['user_id'])
    if user_to_delete:
        if user_to_delete.id == current_user.id:
            return redirect(url_for('admin_user_list',message='自分自身のアカウントは削除できません。',category='error'))
        StepRecord.query.filter_by(user_id=user_id).delete()
        StepGoal.query.filter_by(user_id=user_id).delete()
        db.session.delete(user_to_delete)
        db.session.commit()
        return redirect(url_for('admin_user_list', message=f'ユーザー "{user_to_delete.username}" を削除しました。', category='success'))

# 新規登録
@app.route('/register', methods=['GET', 'POST'])
def register():
    error_message = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            error_message = 'そのユーザー名はすでに登録されています。別のユーザー名をお試しください。'
            return render_template('register.html',error_message=error_message,form_data=request.form)

        password = generate_password_hash(request.form['password'])
        height = float(request.form['height'])
        weight = float(request.form['weight'])
        age = int(request.form['age'])
        user = User(username=username, password_hash=password, height=height, weight=weight,age=age)
        db.session.add(user)
        db.session.commit()
        flash('登録が完了しました')
        return redirect(url_for('login'))
    return render_template('register.html',error_message=error_message,form_data=request.form)

# ログイン
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            session['user_id'] = user.id
            return redirect(url_for('index'))
        flash('ログイン失敗')
    return render_template('login.html')

# ログアウト
@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('login'))

# 歩数登録
@app.route('/steps', methods=['POST'])
def update_steps():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    try:
        steps = int(request.form['steps'])
        if steps < 0:
            flash('歩数は0以上の整数で入力してください。')
            return redirect(url_for('index'))
    except ValueError:
        flash('正しい数値を入力してください。')
        return redirect(url_for('index'))
    today = date.today()
    record = StepRecord.query.filter_by(user_id=session['user_id'], date=today).first()
    if not record:
        record = StepRecord(user_id=session['user_id'], date=today, steps=steps)
        db.session.add(record)
    else:
        record.steps = steps
    db.session.commit()

    user_id = session['user_id']
    # 過去の歩数記録を降順で取得
    records = StepRecord.query.filter_by(user_id=user_id).order_by(StepRecord.date.desc()).all()
    # ユーザーの目標を日付ごとに取得
    goals = {g.date: g.goal_steps for g in StepGoal.query.filter_by(user_id=user_id).all()}

    streak = 0
    for r in records:
        g = goals.get(r.date)
        if g and r.steps >= g:
            streak += 1
        else:
            break

    if streak >= 1:
        flash(f"🌟 目標達成おめでとうございます！現在{streak}日連続で目標達成中です！")
    else:
        flash("目標達成までがんばって歩きましょう！💪")

    return redirect(url_for('index'))


# 目標登録
@app.route('/goal', methods=['POST'])
def update_goal():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    try:
        goal = int(request.form['goal'])
        if goal < 0:
            flash('歩数は0以上の整数で入力してください')
            return redirect(url_for('index'))
    except ValueError:
        flash('無効な入力です(数字を入力してください)')
        return redirect(url_for('index'))
    
    today = date.today()
    goal_record = StepGoal.query.filter_by(user_id=session['user_id'], date=today).first()
    if not goal_record:
        goal_record = StepGoal(user_id=session['user_id'], date=today, goal_steps=goal)
        db.session.add(goal_record)
    else:
        goal_record.goal_steps = goal
    db.session.commit()
    return redirect(url_for('index'))

# 歩数履歴表示
@app.route('/history')
def view_history():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    user = db.session.get(User, session['user_id'])

    # ユーザーの全歩数記録を取得（日付順）
    records = StepRecord.query.filter_by(user_id=user_id).order_by(StepRecord.date).all()

    if not records:
        return render_template('history.html', message="記録がありません。")

    # グラフ作成
    dates = [record.date for record in records]
    steps = [record.steps for record in records]

    plt.figure(figsize=(10, 4))
    plt.plot(dates, steps, marker='o', linestyle='-', color='green')
    plt.xticks(rotation=45)
    plt.xlabel("日付")
    plt.ylabel("歩数")
    plt.title("歩数の推移")
    plt.tight_layout()

    # グラフ画像を base64 にエンコード
    img = io.BytesIO()
    plt.savefig(img, format='png')
    img.seek(0)
    img_data = base64.b64encode(img.getvalue()).decode()

    plt.close()

    return render_template('history.html', records=records, img_data=img_data,user=user)

@app.route('/info_change',methods=['GET','POST'])
def user_info_change():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = db.session.get(User, session['user_id'])
    if user is None:
        session.pop('user_id', None)
        flash('ログイン状態が無効です。再度ログインしてください。', 'error')
        return redirect(url_for('login'))

    if request.method == 'POST':
        # フォームから新しい情報を取得
        # 受け取る値が空文字列の場合に備えて、float()やint()に渡す前にチェック
        new_height_str = request.form['height']
        new_weight_str = request.form['weight']
        new_age_str = request.form['age']

        # 身長、体重、年齢が入力されていれば更新、そうでなければ現在の値を維持
        if new_height_str:
            try:
                user.height = float(new_height_str)
            except ValueError:
                flash('身長は正しい数値を入力してください。', 'error')
                return render_template('info_change.html', user=user)
        
        if new_weight_str:
            try:
                user.weight = float(new_weight_str)
            except ValueError:
                flash('体重は正しい数値を入力してください。', 'error')
                return render_template('info_change.html', user=user)

        if new_age_str:
            try:
                user.age = int(new_age_str)
            except ValueError:
                flash('年齢は正しい整数を入力してください。', 'error')
                return render_template('info_change.html', user=user)
        
        # データベースにコミット
        db.session.commit()
        return redirect(url_for('index')) # 変更後にホーム画面へリダイレクト

    # GETリクエストの場合、現在のユーザー情報をフォームに表示するためにテンプレートをレンダリング
    return render_template('info_change.html', user=user)

#ランキング表示
@app.route('/ranking',methods=['GET'])
def ranking_show():
    user = db.session.get(User, session['user_id'])
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    # 今日の日付取得
    today = date.today()
    # 今日の全ユーザーの歩数データを取得し、歩数を多い順に
    # step_recordとuserテーブルを結合して、ユーザー名も取得できるようにする
    # filter_byで今日の日付に絞り込む
    # order_byで歩数を降順に並べ替える
    # .all()で全てのレコードを取得
    ranking_data = db.session.query(
        User.username,
        StepRecord.steps
    ).join(StepRecord,User.id == StepRecord.user_id).filter(
        StepRecord.date == today
    ).order_by(
        StepRecord.steps.desc()
    ).all()

    return render_template('ranking.html', ranking_data=ranking_data,today=today,user=user)


# HTMLファイルの提供
@app.route('/<page>.html')
def render_html(page):
    return render_template(f"{page}.html")

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
