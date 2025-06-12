from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Listing(db.Model):
    __tablename__ = 'listings'
    
    id = db.Column(db.Integer, primary_key=True)
    listing_id = db.Column(db.Integer, unique=True)
    url = db.Column(db.String(1000))
    title = db.Column(db.String(500))
    price = db.Column(db.String(100))
    currency = db.Column(db.String(10))
    price_per_m2 = db.Column(db.String(100))
    area_sqm = db.Column(db.Float)
    rooms = db.Column(db.Integer)
    location_string = db.Column(db.String(500))
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    description = db.Column(db.Text)
    seller_name = db.Column(db.String(200))
    seller_type = db.Column(db.String(50))
    image_count = db.Column(db.Integer)
    is_private_owner = db.Column(db.Boolean)
    date_created = db.Column(db.DateTime)
    
    # --- Professional extra fields ---
    floor = db.Column(db.Integer, nullable=True)
    total_floors = db.Column(db.Integer, nullable=True)
    year_built = db.Column(db.Integer, nullable=True)
    building_type = db.Column(db.String(100), nullable=True)  # blok, kamienica, etc.
    condition = db.Column(db.String(100), nullable=True)      # deweloperski, do remontu, etc.
    parking_spaces = db.Column(db.Integer, nullable=True)
    balcony_area = db.Column(db.Float, nullable=True)
    heating_type = db.Column(db.String(100), nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # İlişkiler
    details = db.relationship('ListingDetail', backref='listing', lazy='dynamic', cascade="all, delete-orphan")
    images = db.relationship('Image', backref='listing', lazy='dynamic', cascade="all, delete-orphan")
    analysis_results = db.relationship('AnalysisResult', backref='listing', lazy='dynamic', cascade="all, delete-orphan")

class ListingDetail(db.Model):
    __tablename__ = 'listing_details'
    
    id = db.Column(db.Integer, primary_key=True)
    listing_id = db.Column(db.Integer, db.ForeignKey('listings.id'))
    key = db.Column(db.String(100))
    value = db.Column(db.String(500))

class Image(db.Model):
    __tablename__ = 'images'
    
    id = db.Column(db.Integer, primary_key=True)
    listing_id = db.Column(db.Integer, db.ForeignKey('listings.id'))
    image_url = db.Column(db.String(1000))
    image_index = db.Column(db.Integer)
    
    # İlişkiler
    classifications = db.relationship('RoomClassification', backref='image', lazy='dynamic', cascade="all, delete-orphan")

class RoomClassification(db.Model):
    __tablename__ = 'room_classifications'
    
    id = db.Column(db.Integer, primary_key=True)
    image_id = db.Column(db.Integer, db.ForeignKey('images.id'))
    room_type_id = db.Column(db.String(50), nullable=True)
    room_type_details = db.Column(db.String(500), nullable=True)
    is_habitable = db.Column(db.Boolean, nullable=True)
    is_duplicate = db.Column(db.Boolean, default=False)
    
    # İlişkiler
    same_room_relations = db.relationship('SameRoomRelation', backref='classification', lazy='dynamic', cascade="all, delete-orphan")

class SameRoomRelation(db.Model):
    __tablename__ = 'same_room_relations'
    
    id = db.Column(db.Integer, primary_key=True)
    classification_id = db.Column(db.Integer, db.ForeignKey('room_classifications.id'))
    same_as_image_index = db.Column(db.Integer)

class AnalysisResult(db.Model):
    __tablename__ = 'analysis_results'
    
    id = db.Column(db.Integer, primary_key=True)
    listing_id = db.Column(db.Integer, db.ForeignKey('listings.id'))
    analysis_id = db.Column(db.String(100), unique=True)  # Frontend tarafından kullanılan ID
    total_images = db.Column(db.Integer, default=0)
    successfully_classified = db.Column(db.Integer, default=0)
    unique_rooms_detected = db.Column(db.Integer, default=0)
    duplicate_images_found = db.Column(db.Integer, default=0)
    execution_time = db.Column(db.Float, default=0.0)
    batch_mode_used = db.Column(db.Boolean, default=False)
    status = db.Column(db.String(20), default='pending')  # pending, processing, completed, error
    progress = db.Column(db.Float, default=0.0)  # 0-100
    message = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Oda özeti bilgilerini JSON olarak saklayacağız
    room_summary = db.Column(db.Text)  # JSON formatında
    avg_impression_score = db.Column(db.Float, nullable=True)
    dominant_clutter_level = db.Column(db.String(50), nullable=True)
    max_renovation_need = db.Column(db.String(50), nullable=True)
    property_summary_text = db.Column(db.Text, nullable=True)  # Gemini'den gelen özet metin
    key_features_text = db.Column(db.Text, nullable=True)  # JSON listesi olarak önemli özellikler
    visible_issues_text = db.Column(db.Text, nullable=True)  # JSON listesi olarak görünür sorunlar
    numeric_visual_features_json = db.Column(db.Text, nullable=True)  # JSON olarak sayısal görsel metrikler
    raw_gemini_response = db.Column(db.Text, nullable=True) # Ham Gemini JSON yanıtı
    overall_condition = db.Column(db.String(100), nullable=True) # Gemini'den gelen genel durum
    dominant_style = db.Column(db.String(100), nullable=True) # Gemini'den gelen baskın stil
    overall_lighting = db.Column(db.String(100), nullable=True) # Gemini'den gelen genel aydınlatma
