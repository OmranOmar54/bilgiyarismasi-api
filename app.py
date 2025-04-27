import os
import json
from flask import Flask, request, jsonify
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
import datetime  # Zaman damgası eklemek için
from flask_cors import CORS

# --- Firebase Kurulumu ---
try:
    # Replit Secrets'tan JSON içeriğini al
    firebase_secrets_json = os.environ['/etc/secrets/FIREBASE_CREDENTIALS']
    # JSON içeriğini bir sözlüğe dönüştür
    firebase_credentials_dict = json.loads(firebase_secrets_json)
    # Credentials nesnesi oluştur
    cred = credentials.Certificate(firebase_credentials_dict)
    # Firebase Admin SDK'yı başlat
    firebase_admin.initialize_app(cred)
    # Firestore istemcisini al
    db = firestore.client()
    print("Firebase başarıyla bağlandı.")
except KeyError:
    print(
        "HATA: FIREBASE_CREDENTIALS secret'ı bulunamadı. Replit Secrets'ı kontrol edin."
    )
    exit()  # Secret yoksa uygulamayı durdur
except Exception as e:
    print(f"Firebase başlatılırken bir hata oluştu: {e}")
    exit()  # Başka bir hata olursa durdur

# --- Flask Web Sunucusu ---
app = Flask(__name__)
CORS(app)


@app.route('/')
def home():
    # API'nin çalıştığını kontrol etmek için basit bir ana sayfa
    return "Unity Liderlik Tablosu API'si çalışıyor!"


@app.route('/add_score', methods=['POST'])
def add_score():
    """
    Unity'den gelen kullanıcı adı, IP ve skoru Firestore'a ekler.
    Beklenen JSON formatı: {"username": "oyuncu_adi", "ip": "192.168.1.1", "score": 100}
    """
    try:
        # Gelen isteğin JSON formatında olduğundan emin ol
        if not request.is_json:
            return jsonify({"error": "İstek JSON formatında olmalı"}), 400

        data = request.get_json()

        # Gerekli alanların varlığını kontrol et
        username = data.get('username')
        ip_address = data.get('ip')
        score = data.get(
            'score')  # Skoru da ekledim, liderlik tablosu için gerekli

        if not username or score is None:  # IP zorunlu olmayabilir, ama kullanıcı adı ve skor olmalı
            return jsonify({
                "error":
                "Eksik veri: 'username' ve 'score' alanları gereklidir."
            }), 400

        # Firestore'a eklenecek veri
        user_data = {
            'username': username,
            'score':
            int(score
                ),  # Skoru integer olarak kaydetmek sıralama için daha iyi
            'ip_address': ip_address,  # IP adresini de kaydedelim
            'timestamp': firestore.SERVER_TIMESTAMP  # Kayıt zamanını ekle
            # Alternatif: datetime.datetime.now(datetime.timezone.utc)
        }

        # Firestore'a veriyi ekle/güncelle
        # Koleksiyon adı: 'leaderboard' (ya da istediğiniz başka bir isim)
        # Belge ID'si olarak kullanıcı adını kullanabiliriz (eğer benzersizse)
        # Veya Firestore'un otomatik ID oluşturmasını sağlayabiliriz (.add() ile)
        # Kullanıcı adını ID olarak kullanmak, aynı kullanıcının skorunu güncellemeyi kolaylaştırır.
        leaderboard_ref = db.collection('leaderboard')
        # Kullanıcı adını belge ID'si olarak kullan:
        doc_ref = leaderboard_ref.document(username)
        # set() metodu belge yoksa oluşturur, varsa üzerine yazar.
        # merge=True ile sadece belirtilen alanları güncelleyebiliriz ama burada tam kayıt yapıyoruz.
        doc_ref.set(user_data)

        print(f"Kayıt eklendi/güncellendi: {user_data}")
        return jsonify({
            "success":
            True,
            "message":
            f"'{username}' için skor başarıyla eklendi/güncellendi."
        }), 201

    except Exception as e:
        print(f"Skor eklenirken hata: {e}")
        return jsonify({"error": "Sunucu hatası", "details": str(e)}), 500


@app.route('/get_leaderboard', methods=['GET'])
def get_leaderboard():
    """
    Firestore'daki 'leaderboard' koleksiyonundan skorları çeker,
    puana göre büyükten küçüğe sıralar ve ilk 10'u JSON olarak döndürür.
    """
    try:
        leaderboard_ref = db.collection('leaderboard')

        # Skorları 'score' alanına göre azalan sırada sorgula (en yüksek üstte)
        # limit(10) ile sadece ilk 10 skoru al (isteğe bağlı, sayıyı değiştirebilirsin)
        query = leaderboard_ref.order_by('score',
                                         direction=firestore.Query.DESCENDING)

        # Sorgu sonuçlarını al
        results = query.stream()  # veya query.get()

        # Sonuçları bir listeye çevir
        leaderboard_data = []
        rank = 1  # Sıralama numarası eklemek için
        for doc in results:
            entry = doc.to_dict()
            # Sadece gerekli alanları veya istediğin formatı seçebilirsin
            leaderboard_data.append({
                'rank':
                rank,
                'username':
                entry.get(
                    'username',
                    'Bilinmeyen'),  # Kullanıcı adı yoksa varsayılan değer
                'score':
                entry.get('score', 0)  # Skor yoksa varsayılan değer
                # 'timestamp': entry.get('timestamp') # İstersen zaman damgasını da ekleyebilirsin
            })
            rank += 1

        # Listeyi JSON formatında döndür
        return jsonify(leaderboard_data), 200

    except Exception as e:
        print(f"Liderlik tablosu alınırken hata: {e}")
        return jsonify({"error": "Sunucu hatası", "details": str(e)}), 500
