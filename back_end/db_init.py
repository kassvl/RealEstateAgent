"""
Veritabanını oluşturmak için araç.
"""

from models import db, Listing, ListingDetail, Image, RoomClassification, SameRoomRelation, AnalysisResult
from flask import Flask
import os
import argparse

def init_db():
    """Veritabanını oluştur."""
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////Users/kadirhan/Desktop/ev/real_estate_agent_v2/back_end/real_estate_analysis.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SQLALCHEMY_ECHO'] = False
    
    db.init_app(app)
    
    parser = argparse.ArgumentParser(description='Initialize or reset the database.')
    parser.add_argument('--reset', action='store_true', help='Drop all tables before creating them.')
    args = parser.parse_args()

    with app.app_context():
        if args.reset:
            print("Veritabanı sıfırlanıyor (tüm tablolar siliniyor)...")
            db.metadata.drop_all(bind=db.engine)
            print("Tüm tablolar silindi.")
        
        db.metadata.create_all(bind=db.engine)
        if args.reset:
            print("Veritabanı başarıyla sıfırlandı ve yeniden oluşturuldu.")
        else:
            print("Veritabanı başarıyla oluşturuldu/güncellendi (mevcut veriler korundu).")

if __name__ == '__main__':
    init_db()
