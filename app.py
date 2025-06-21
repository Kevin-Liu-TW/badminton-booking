import os
from dotenv import load_dotenv
from config import config_map

load_dotenv()

app_env = os.environ.get("app_env", "development")
app_config = config_map.get(app_env, config_map["development"])


from flask import Flask, render_template, request, redirect, url_for, session, flash, abort, jsonify  
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, login_user, login_required, current_user, UserMixin, logout_user
from datetime import datetime, date, timedelta
from models import db, User, Venue, Timeslot, Booking,venue_managers, CourtBooking

app = Flask(__name__)
app.config.from_object(app_config)

app.secret_key = app.config["SECRET_KEY"]
db.init_app(app)
migrate = Migrate(app, db)

login_manager = LoginManager(app)
login_manager.login_view = 'liff_login'  #====可試著移除
login_manager.init_app(app)



# -----------------------
# Get liff id
# -----------------------
@app.context_processor
def inject_liff_id():
    return dict(LIFF_ID=app.config.get("LIFF_ID", ""))

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

    filter_date = request.args.get("date")
    filter_time = request.args.get("time")
    filter_level = request.args.get("level", type=int)

    today_str = datetime.now().strftime('%Y-%m-%d')

    if filter_date:
        session['selected_date'] = filter_date
        selected_date_str = filter_date
    else:
        session.pop('selected_date', None)  # ✅ 清除 session 中的舊值
        selected_date_str = today_str

    query = Timeslot.query.filter(Timeslot.venue_id == venue.id)

    if not filter_date and not filter_time and not filter_level:
        query = query.filter(Timeslot.date >= today_str)

    if filter_date:
        query = query.filter(Timeslot.date == filter_date)
    elif selected_date_str:
        query = query.filter(Timeslot.date >= selected_date_str)
    if filter_time == "morning":
        query = query.filter(Timeslot.start_time < "12:00")
    elif filter_time == "afternoon":
        query = query.filter(Timeslot.start_time >= "12:00")
    if filter_level:
        query = query.filter(Timeslot.level_min <= filter_level, Timeslot.level_max >= filter_level)

    timeslots = query.order_by(Timeslot.date.asc(), Timeslot.start_time.asc()).all()

    bookings = {}
    for slot in timeslots:
        records = Booking.query.filter_by(timeslot_id=slot.id).all()
        total = sum(b.number_of_people for b in records)
        bookings[slot.id] = {"records": records, "total": total}

    venue_managers = [user.id for user in venue.managers]

    court_bookings = [
        {
        
            "id": b.id,
            "date": b.date.strftime('%Y-%m-%d'),
            "start_time": b.start_time,
            "time_hours": b.time_hours,
            "status": b.status,
            "number_of_courts": b.number_of_courts,
            "note": b.note or ""
        }
        for b in CourtBooking.query.filter_by(venue_id=venue.id)
            .filter(CourtBooking.status.in_(['pending', 'booked', 'cancelled']))
            #.filter(CourtBooking.date >= today_str)
            .all()
    ]
    
    return render_template("venue.html",
                           venue=venue,
                           timeslots=timeslots,
                           bookings=bookings,
                           venue_managers=venue_managers,
                           selected_date=selected_date_str,
                           court_bookings=court_bookings)

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

    open_hour_str = request.form.get('openHour')
    if open_hour_str:
        venue.openHour = datetime.strptime(open_hour_str, '%H:%M').time()
    
    close_hour_str = request.form.get('closeHour')
    if close_hour_str:
        venue.closeHour = datetime.strptime(close_hour_str, '%H:%M').time()
    
    position_str = request.form.get('position')
    if position_str:
        venue.position = int(position_str)

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


# 刪除零打已報名資訊
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


#查詢此場館場地登記狀況
@app.route('/venue/<int:venue_id>/bookings')
@login_required
def get_user_bookings(venue_id):
    today_str = date.today()# 抓當天之後的資料
    seven_days_ago = date.today() - timedelta(days=7)#抓上週之後的資料
    
    #For 個人紀錄
    user_bookings = CourtBooking.query.filter_by(user_id=current_user.id, venue_id=venue_id)\
        .filter(CourtBooking.date >= today_str)\
        .order_by(CourtBooking.date, CourtBooking.start_time).all()
    #For場館紀錄

    all_bookings = CourtBooking.query.filter_by(venue_id=venue_id)\
        .filter(CourtBooking.date >= seven_days_ago)\
        .filter(CourtBooking.status.in_(['pending', 'booked']))\
        .order_by(CourtBooking.date, CourtBooking.start_time).all()

    return jsonify({
        "status": "ok",
        "user_bookings": [
            {
                "id": b.id,
                "date": b.date.strftime('%Y-%m-%d'),
                "start_time": b.start_time,
                "time_hours": b.time_hours,
                "status": b.status,
                "number_of_courts": b.number_of_courts,
                "note": b.note or ""
            } for b in user_bookings
        ],
        "all_bookings": [
            {
                "id": b.id,
                "date": b.date.strftime('%Y-%m-%d'),
                "start_time": b.start_time,
                "time_hours": b.time_hours,
                "status": b.status,
                "number_of_courts": b.number_of_courts,
                "note": b.note or ""
            } for b in all_bookings
        ]
    })
    
#建立場地預約資料
@app.route('/venue/<int:venue_id>/court-booking', methods=['POST']) 
@login_required
def create_court_booking(venue_id):
    try:
        data = request.get_json()
        phone = data.get('phone')
        note = data.get('note', '')
        number_of_courts = int(data.get('number_of_courts', 1))
        
        court_booking_date = data.get('date')
        
        start_time = data.get('start_time')
        time_hours = int(data.get('time_hours', 1))
        venue = Venue.query.get_or_404(venue_id)
        
        start_hour = int(start_time.split(":")[0])

        open_hour = int(venue.openHour.hour)
        close_hour = int(venue.closeHour.hour)
        
        booking_date = datetime.strptime(court_booking_date, "%Y-%m-%d").date()
        now = datetime.now()
        
        # 檢查不能預約以前的時段
        if booking_date < date.today():
            return jsonify({
                "status": "fail",
                "message": "無法預約今天以前的日期"
            }), 400
        # 檢查不能預約今天中已經過去的時段
        if booking_date == date.today() and start_hour <= now.hour:
            return jsonify({
                "status": "fail",
                "message": f"時段已過，請改約{now.hour}點以後"
            }), 400
        
        # 檢查是否超出場館營業時間
        if start_hour < open_hour or (start_hour + time_hours) > close_hour:
            return jsonify({
                "status": "fail",
                "message": f"預約時間超出場館營業時間 ({open_hour}:00 - {close_hour}:00)"
            }), 400

        # 每小時檢查場地是否超額
        for offset in range(time_hours):
            hour = start_hour + offset
            time_str = f"{hour:02d}:00"
            existing = db.session.query(db.func.sum(CourtBooking.number_of_courts)).filter_by(
                venue_id=venue.id,
                date=court_booking_date,
                start_time=time_str
            ).filter(CourtBooking.status.in_(['pending', 'booked', 'cancelled'])).scalar() or 0

            if existing + number_of_courts > (venue.position or 0):
                return jsonify({
                    "status": "fail",
                    "message": f"{time_str}～{hour+1:02d}:00 時段場地已滿"
                }), 400

        booking = CourtBooking(
            user_id=current_user.id,
            venue_id=venue.id,
            phone=phone,
            note=note,
            number_of_courts=number_of_courts,
            date=booking_date,
            start_time=start_time,
            time_hours=time_hours,
            status='pending'
        )

        db.session.add(booking)
        db.session.commit()

        return jsonify({"status": "ok"})

    except Exception as e:
        print("❗ 錯誤：", e)
        return jsonify({"status": "fail", "message": "系統錯誤，請稍後再試"}), 500


# ----------------------
# Manager Page
# ----------------------
@app.route('/manager')
@login_required
def manager_dashboard():
    if current_user.permission not in ['manager', 'admin']:
        flash("您沒有權限訪問此頁面。")
        return redirect(url_for('index'))
    
    # 獲取場館
    if current_user.permission == 'manager':
        venues = current_user.managed_venues
    else:
        venues = current_user.managed_venues #venues = Venue.query.all()
    
    # 使用 joinedload 或一次性查詢所有 timeslots
    venue_ids = [venue.id for venue in venues]
    timeslots = Timeslot.query.filter(
        Timeslot.venue_id.in_(venue_ids)
    ).order_by(Timeslot.venue_id, Timeslot.date, Timeslot.start_time).all()
    
    # 將 timeslots 分組到對應的 venue
    timeslots_by_venue = {}
    for timeslot in timeslots:
        if timeslot.venue_id not in timeslots_by_venue:
            timeslots_by_venue[timeslot.venue_id] = []
        timeslots_by_venue[timeslot.venue_id].append(timeslot)
    
    # 將 timeslots 分配給 venues
    for venue in venues:
        venue.timeslots = timeslots_by_venue.get(venue.id, [])
    
    
    
    
    # court_bookings 多場館的訂單
    court_bookings = CourtBooking.query.filter(
        CourtBooking.venue_id.in_(venue_ids),
        CourtBooking.status.in_(['pending', 'booked', 'cancelled']),
        CourtBooking.date >= date.today()
    ).all()
    
    
    # 分群：每個場館 -> pending/booked
    court_bookings_by_venue = {}
    for venue in venues:
        court_bookings_by_venue[venue.id] = {
            "pending": [],
            "booked": [],
            "cancelled": []
        }
    
    for b in court_bookings:
        if b.venue_id in court_bookings_by_venue:
            court_bookings_by_venue[b.venue_id][b.status].append(b)

    
        # 若想組成字典或清單方便在模板使用：
    court_bookings_data = [
        {
            "id": b.id,
            "venue_id": b.venue_id,
            "venue_name": b.venue.name,  # 可直接取得場館名稱
            "user_display_name": b.user.display_name if b.user else "未知使用者",
            "date": b.date.strftime('%Y-%m-%d'),
            "start_time": b.start_time,
            "status": b.status,
            "number_of_courts": b.number_of_courts,
            "time_hours": b.time_hours,
            "phone": b.phone,
            "note": b.note
        }
        for b in court_bookings
    ]
    
    return render_template('manager_dashboard.html',
                           venues=venues,
                           court_bookings_data=court_bookings_data,
                           court_bookings_by_venue=court_bookings_by_venue)

'''
#Manager page更新場地租借狀態
@app.route('/court_booking/<int:booking_id>/update', methods=['POST'])
@login_required
def update_court_booking_status(booking_id):
    booking = CourtBooking.query.get_or_404(booking_id)

    # 權限檢查：必須是場館管理員
    if booking.venue_id not in [v.id for v in current_user.managed_venues]:
        flash("您沒有權限修改此預約。")
        return redirect(url_for('manager_dashboard'))

    new_status = request.form.get('status')
    if new_status not in ['booked', 'cancelled']:
        flash("無效的狀態")
        return redirect(url_for('manager_dashboard'))

    booking.status = new_status
    db.session.commit()

    flash(f"預約已更新為 {new_status}")
    return redirect(url_for('manager_dashboard'))
''' 

#Manager page更新場地租借狀態(single & batch)
@app.route('/court_booking/<int:booking_id>/update', methods=['POST'])
@app.route('/court_booking/batch_update', methods=['POST'])
@login_required
def update_court_booking_status(booking_id=None):
    # 批次更新邏輯（JSON 格式）
    if booking_id is None:
        data = request.get_json()
        booking_ids = data.get('ids', [])
        new_status = data.get('status')
        
        if not booking_ids or new_status not in ['booked', 'cancelled']:
            return jsonify({'status': 'fail', 'message': '參數錯誤'}), 400

        bookings = CourtBooking.query.filter(CourtBooking.id.in_(booking_ids)).all()
        venue_ids = [v.id for v in current_user.managed_venues]

        for b in bookings:
            if b.venue_id not in venue_ids:
                return jsonify({'status': 'fail', 'message': f"您沒有修改預約 {b.id} 的權限"}), 403
            b.status = new_status

        db.session.commit()
        return jsonify({'status': 'ok', 'message': f"已更新 {len(bookings)} 筆預約為 {new_status}"})

    # 單筆更新邏輯（保留原來的功能）
    booking = CourtBooking.query.get_or_404(booking_id)
    if booking.venue_id not in [v.id for v in current_user.managed_venues]:
        flash("您沒有權限修改此預約。")
        return redirect(url_for('manager_dashboard'))

    new_status = request.form.get('status')
    if new_status not in ['booked', 'cancelled']:
        flash("無效的狀態")
        return redirect(url_for('manager_dashboard'))

    booking.status = new_status
    db.session.commit()

    flash(f"預約已更新為 {new_status}")
    return redirect(url_for('manager_dashboard'))


# ----------------------
# Admin Page
# ----------------------
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



#venue場地租借刪除
@app.route('/cancel_booking/<int:booking_id>', methods=['POST'])
@login_required
def cancel_court_booking(booking_id):
    from models import CourtBooking
    booking = CourtBooking.query.get_or_404(booking_id)
    if booking.user_id != current_user.id:
        return jsonify({'status': 'fail', 'message': '無權限取消此申請'}), 403
    db.session.delete(booking)
    db.session.commit()
    return jsonify({'status': 'ok'})


if __name__ == "__main__":
    is_dev = app_env == "development"
    app.run(
        host="127.0.0.1" if is_dev else "0.0.0.0",
        port=app.config["PORT"],
        debug=app_config.DEBUG
    )
