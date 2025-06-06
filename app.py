from flask import Flask, render_template, request, redirect, url_for, session, flash, abort
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, login_user, login_required, current_user, UserMixin, logout_user
from datetime import datetime
from models import db, User, Venue, Timeslot, Booking,venue_managers
from dotenv import load_dotenv

import os

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'default-secret')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
migrate = Migrate(app, db)


login_manager = LoginManager(app)
login_manager.login_view = 'liff_login'  #====可試著移除
login_manager.init_app(app)

#======刪除==========
@app.before_request
def log_request_info():
    print(f"📥 Request method: {request.method} URL: {request.url}")
#===========================



# -----------------------
# Get liff id
# -----------------------
@app.context_processor
def inject_liff_id():
    return dict(LIFF_ID=os.environ.get("LIFF_ID", ""))

# -----------------------
# Login Manager
# -----------------------
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# -----------------------
# Routes
# -----------------------
@app.route('/')
def index():

    
    venues = Venue.query.all()
    selected_date_str = session.get('selected_date', datetime.now().strftime('%Y-%m-%d'))
    timeslots = Timeslot.query.filter(Timeslot.date >= datetime.now().strftime('%Y-%m-%d')).all()
    
    return render_template('index.html',
                           venues=venues,
                           timeslots=timeslots,
                           selected_date=selected_date_str)



# ----LIFF Login
# -----------------------
@app.route('/liff_login', methods=['GET','POST'])
def liff_login():
    if request.method == 'GET':
        return "此頁僅供 LIFF 自動登入用，請從正確入口進入。", 405
    # 從前端接收 LIFF 傳來的 LINE 用戶資訊
    data = request.json
    line_id = data.get('line_id')
    display_name = data.get('display_name')
    
    if not line_id:
        return {'success': False, 'message': '缺少 LINE User ID'}, 400

    user = User.query.filter_by(line_id=line_id).first()
    if user:
        # 如果用戶已存在，直接登入
        login_user(user)
        return {'success': True, 'redirect_url': url_for('index')}
    else:
        # 如果用戶不存在，創建新用戶
        new_user = User(line_id=line_id, display_name=display_name, permission='guest')
        db.session.add(new_user)
        db.session.commit()
        login_user(new_user)
        return {'success': True, 'redirect_url': url_for('index')}

#====應該不需要登出功能
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash("您已成功登出。", "info")
    return redirect(url_for('index'))


# ----------------------
# Venue Page
# ----------------------
@app.route("/venue/<int:venue_id>")
@login_required
def venue(venue_id):
    venue = Venue.query.get_or_404(venue_id)
    
    # 獲取今天或 session 中選擇的日期，並過濾時段
    selected_date_str = session.get('selected_date', datetime.now().strftime('%Y-%m-%d'))
    
    # 根據選定的日期和場地 ID 獲取時段
    timeslots = Timeslot.query.filter(Timeslot.venue_id == venue_id, Timeslot.date >= selected_date_str).order_by(Timeslot.date, Timeslot.start_time).all()
    
    # 建立每個時段的報名資料字典
    bookings = {}
    
    for slot in timeslots:
        records = Booking.query.filter_by(timeslot_id=slot.id).all()
        total = sum(b.number_of_people for b in records)
        bookings[slot.id] = {"records": records, "total": total}

    # ✅ 取得此場地的 manager user_id 清單
    venue_managers = [user.id for user in venue.managers]

    return render_template("venue.html",
                           venue=venue,
                           timeslots=timeslots,
                           bookings=bookings,
                           venue_managers=venue_managers,
                           selected_date=selected_date_str)

@app.route('/venue/<int:venue_id>/update_rules', methods=['POST'])
@login_required
def update_venue_rules(venue_id):
    venue = Venue.query.get_or_404(venue_id)

    # 權限檢查：必須是該場地的管理員或 admin
    if current_user.permission != 'admin' and current_user not in venue.managers:
        flash('您沒有權限修改此場地的規則。')
        return redirect(url_for('manager_dashboard'))

    # 更新基本資訊
    venue.phone = request.form.get('phone', '').strip()
    venue.city = request.form.get('city', '').strip()
    venue.address = request.form.get('address', '').strip()
    
    # 更新設施 - 處理多選 checkbox
    facilities = request.form.getlist('facilities')
    venue.facilities = ','.join(facilities) if facilities else ''
    
    # 更新收費規則和使用規則
    venue.pricing = request.form.get('pricing', '').strip()
    venue.rules = request.form.get('rules', '').strip()
    
    try:
        db.session.commit()
        flash('場地資訊已更新！', 'success')
    except Exception as e:
        db.session.rollback()
        flash('更新失敗，請稍後再試。', 'error')
        print(f"Database error: {e}")
    
    return redirect(url_for('manager_dashboard'))


@app.route('/venue/<int:venue_id>/add_timeslot', methods=['POST'])
@login_required
def add_timeslot(venue_id):
    venue = Venue.query.get_or_404(venue_id)

    if current_user.permission != 'admin' and current_user not in venue.managers:
        flash('您沒有權限新增此場地的時段。')
        return redirect(url_for('manager_dashboard'))

    date = request.form['date']
    start_time = request.form['start_time']
    end_time = request.form['end_time']
    capacity = int(request.form['capacity'])
    level_min = int(request.form.get('level_min', 1))
    level_max = int(request.form.get('level_max', 18))

    new_slot = Timeslot(
        venue_id=venue.id,
        date=date,
        start_time=start_time,
        end_time=end_time,
        capacity=capacity,
        level_min=level_min,
        level_max=level_max
    )
    db.session.add(new_slot)
    db.session.commit()
    flash('新的時段已新增！')
    return redirect(url_for('manager_dashboard'))



@app.route('/timeslot/<int:timeslot_id>/delete', methods=['POST'])
@login_required
def delete_timeslot(timeslot_id):
    slot = Timeslot.query.get_or_404(timeslot_id)
    venue = Venue.query.get_or_404(slot.venue_id)

    # 權限檢查：只能由該場地的 manager 或 admin 刪除
    if current_user.permission != 'admin' and current_user not in venue.managers:
        flash('您沒有刪除此時段的權限。')
        return redirect(url_for('manager_dashboard'))

    # 刪除該時段下的所有報名記錄（若不需要自動刪除，請移除這段）
    Booking.query.filter_by(timeslot_id=timeslot_id).delete()

    # 刪除時段
    db.session.delete(slot)
    db.session.commit()
    flash('時段已成功刪除。')
    return redirect(url_for('manager_dashboard'))



@app.route('/book/<int:timeslot_id>', methods=['POST'])
@login_required
def book(timeslot_id):
    display_name = request.form['display_name']
    number = int(request.form['number'])
    note = request.form['note']

    # 計算目前已報名人數
    total_booked = db.session.query(db.func.sum(Booking.number_of_people)).filter_by(timeslot_id=timeslot_id).scalar() or 0
    timeslot = Timeslot.query.get(timeslot_id)

    if total_booked + number > timeslot.capacity:
        flash('報名人數已超過上限，請重新選擇人數或時段。')
        return redirect(url_for('venue', venue_id=timeslot.venue_id))

    booking = Booking(
        timeslot_id=timeslot_id,
        user_id=current_user.id,
        display_name=display_name,
        number_of_people=number,
        note=note
    )
    db.session.add(booking)
    db.session.commit()
    return redirect(url_for('venue', venue_id=timeslot.venue_id))

# 刪除已報名資訊
@app.route("/delete_booking/<int:booking_id>", methods=["POST"])
@login_required
def delete_booking(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    timeslot = Timeslot.query.get(booking.timeslot_id)
    venue = Venue.query.get(timeslot.venue_id)

    # 權限檢查
    is_admin = current_user.permission == 'admin'
    is_self = booking.user_id == current_user.id
    is_manager = current_user in venue.managers

    if not (is_admin or is_self or is_manager):
        flash("你沒有權限刪除此報名紀錄")
        return redirect(url_for("venue", venue_id=venue.id))

    db.session.delete(booking)
    db.session.commit()
    flash("已成功刪除報名")
    return redirect(url_for("venue", venue_id=venue.id))


@app.route('/manager')
@login_required
def manager_dashboard():
    if current_user.permission not in ['manager', 'admin']:
        flash("您沒有權限訪問此頁面。")
        return redirect(url_for('index'))

    venues = current_user.managed_venues if current_user.permission == 'manager' else Venue.query.all()

    # 預先載入 timeslots 避免 lazy loading 問題
    for venue in venues:
        venue.timeslots = Timeslot.query.filter_by(venue_id=venue.id).order_by(Timeslot.date, Timeslot.start_time).all()

    return render_template('manager_dashboard.html', venues=venues)




@app.route('/admin_dashboard', methods=['GET', 'POST'])
@login_required
def admin_dashboard():
    if current_user.permission != 'admin':
        return redirect(url_for('index'))
 
    venues = Venue.query.all()
    users = User.query.all()

    # 取得選取的場地 ID（支援從表單或 URL query string 讀取）
    selected_venue_id = request.form.get('selected_venue') or request.args.get('selected_venue')
    selected_venue = Venue.query.get(selected_venue_id) if selected_venue_id else None

    # ✅ 處理新增場地
    if request.method == 'POST' and 'venue_name' in request.form:
        new_name = request.form['venue_name']
        if new_name:
            db.session.add(Venue(name=new_name))
            db.session.commit()
            flash("場地新增成功", "success")
            return redirect(url_for('admin_dashboard'))

    # ✅ 處理指派與解除管理員
    if request.method == 'POST' and selected_venue:
        action = request.form.get('action')
        if action == 'unassign':
            unassign_ids = request.form.getlist('unassign_users')
            for uid in unassign_ids:
                user = User.query.filter_by(line_id=uid).first()
                if user and selected_venue in user.managed_venues:
                    user.managed_venues.remove(selected_venue)
            db.session.commit()
            flash("已解除選擇的管理員", "info")
            return redirect(url_for('admin_dashboard', selected_venue=selected_venue.id))

        elif action == 'assign':
            assign_ids = request.form.getlist('assign_users')
            for uid in assign_ids:
                user = User.query.filter_by(line_id=uid).first()
                if user:
                    if selected_venue not in user.managed_venues:
                        user.managed_venues.append(selected_venue)
                    if user.permission != 'admin':
                        user.permission = 'manager'
            db.session.commit()
            flash("已指派選擇的使用者為管理員", "success")
            return redirect(url_for('admin_dashboard', selected_venue=selected_venue.id))

    # ✅ 準備渲染資料
    venue_managers = selected_venue.managers if selected_venue else []
    eligible_users = [u for u in users if u.permission in ('manager', 'admin')]

    return render_template(
        'admin.html',
        venues=venues,
        users=users,
        selected_venue=selected_venue,
        venue_managers=venue_managers,
        eligible_users=eligible_users
    )



@app.route('/admin/delete_venue', methods=['POST'])
@login_required
def delete_venue_by_select():
    if not current_user.has_permission('admin'):
        flash("您沒有權限執行此操作", "danger")
        return redirect(url_for('admin_dashboard'))

    venue_id = request.form.get('delete_venue_id')
    if venue_id:
        venue = Venue.query.get(venue_id)
        if venue:
            db.session.delete(venue)
            db.session.commit()
            flash(f"場地「{venue.name}」已成功刪除", "success")
        else:
            flash("找不到場地", "warning")
    else:
        flash("請選擇要刪除的場地", "warning")

    return redirect(url_for('admin_dashboard'))


@app.route('/admin/update_permissions', methods=['POST'])
@login_required
def update_permissions():
    if not current_user.permission == 'admin':
        flash("您沒有權限執行此操作", "danger")
        return redirect(url_for('admin_dashboard'))

    users = User.query.all()
    for user in users:
        form_permission = request.form.get(f'permission_{user.line_id}')
        if form_permission and form_permission != user.permission:
            user.permission = form_permission
    db.session.commit()
    flash("使用者權限已更新", "success")
    return redirect(url_for('admin_dashboard'))



if __name__ == "__main__":
    import os
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
