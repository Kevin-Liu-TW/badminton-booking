from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()

# 場地 <-> 管理員 多對多（例如：一個場地可由多位使用者管理）
venue_managers = db.Table('venue_managers',
    db.Column('venue_id', db.Integer, db.ForeignKey('venue.id')),
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'))
)

# -------------------
# 模型定義
# -------------------

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    line_id = db.Column(db.String, unique=True, nullable=False)
    display_name = db.Column(db.String(100))
    username = db.Column(db.String(80), unique=True)
    password_hash = db.Column(db.String(128))
    
    permission = db.Column(db.String(20), default='guest')  # 'guest', 'manager', 'admin'
    
    managed_venues = db.relationship('Venue', secondary='venue_managers', back_populates='managers')

    def has_permission(self, perm):
        levels = {'guest': 0, 'manager': 1, 'admin': 2}
        return levels.get(self.permission, 0) >= levels.get(perm, 0)

class Venue(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    
    # 基本資訊欄位
    phone = db.Column(db.String(20))
    city = db.Column(db.String(20))
    address = db.Column(db.String(200))
    openHour = db.Column(db.Time, nullable=True)
    closeHour = db.Column(db.Time, nullable=True)
    position = db.Column(db.Integer, nullable=True)
    
    # 設施欄位 - 儲存為逗號分隔的字串
    facilities = db.Column(db.Text)
    
    # 收費和規則欄位
    pricing = db.Column(db.Text)
    rules = db.Column(db.Text)
    
    # 關聯
    timeslots = db.relationship('Timeslot', backref='venue', lazy=True, cascade='all, delete-orphan')
    managers = db.relationship('User', secondary='venue_managers', back_populates='managed_venues')

    def __repr__(self):
        return f'<Venue {self.name}>'

class Timeslot(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    venue_id = db.Column(db.Integer, db.ForeignKey('venue.id'))
    date = db.Column(db.String(20))  # e.g. "2025-05-30"
    start_time = db.Column(db.String(5))  # e.g. "19:30"
    end_time = db.Column(db.String(5))    # e.g. "21:30"
    capacity = db.Column(db.Integer)
    level_min = db.Column(db.Integer, default=1, nullable=False)
    level_max = db.Column(db.Integer, default=18, nullable=False)

    bookings = db.relationship('Booking', backref='timeslot', lazy=True)
    
    court_bookings = db.relationship('CourtBooking', backref='timeslot', lazy=True, cascade='all, delete-orphan')

class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timeslot_id = db.Column(db.Integer, db.ForeignKey('timeslot.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    display_name = db.Column(db.String(100))
    note = db.Column(db.Text)
    number_of_people = db.Column(db.Integer)
    
class CourtBooking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    venue_id = db.Column(db.Integer, db.ForeignKey('venue.id'), nullable=False)

    timeslot_id = db.Column(db.Integer, db.ForeignKey('timeslot.id'), nullable=True)

    date = db.Column(db.Date, nullable=False)  # "2025-06-13"
    start_time = db.Column(db.String(5), nullable=False)  # e.g. "09:00"
    time_hours = db.Column(db.Integer, default=1)
    number_of_courts = db.Column(db.Integer, default=1)
    phone = db.Column(db.String(20))
    note = db.Column(db.Text)
    status = db.Column(db.String(20), default='pending')  # pending/booked/rejected/cancelled

    user = db.relationship('User', backref='court_bookings')
    venue = db.relationship('Venue', backref='court_bookings')

    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())
