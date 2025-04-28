import os
import json
from flask import Flask, request, jsonify
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
import datetime  # Zaman damgası eklemek için
from flask_cors import CORS

try:
    # Render Secret File yolunu tanımla
    secret_file_path = '/etc/secrets/FIREBASE_CREDENTIALS'

    # Dosyanın varlığını kontrol et (isteğe bağlı ama iyi bir pratik)
    if not os.path.exists(secret_file_path):
        print(f"HATA: Secret dosyasi bulunamad: {secret_file_path}")
        exit()

    # Secret File içeriğini (JSON string) oku
    with open(secret_file_path, 'r') as f:
        firebase_secrets_json = f.read()

    # JSON içeriğini bir sözlüğe dönüştür
    firebase_credentials_dict = json.loads(firebase_secrets_json)

    # Credentials nesnesi oluştur
    cred = credentials.Certificate(firebase_credentials_dict)

    # Firebase Admin SDK'yı başlat
    if not firebase_admin._apps: # Zaten başlatılmadıysa başlat
        firebase_admin.initialize_app(cred)
    else:
        # Alternatif: Zaten başlatıldıysa mevcut uygulamayı al
        # firebase_admin.get_app()
        print("Firebase zaten başlatilmiş.")


    # Firestore istemcisini al
    db = firestore.client()
    print("Firebase başariyla bağlandi.")

# except FileNotFoundError: # Daha spesifik hata yakalama
#     print(f"HATA: Secret dosyası bulunamadı: {secret_file_path}")
#     exit()
except json.JSONDecodeError:
    print(f"HATA: Secret dosyasinin içeriği geçerli bir JSON değil: {secret_file_path}")
    exit()
except Exception as e:
    print(f"Firebase başlatilirken bir hata oluştu: {e}")
    exit() # Başka bir hata olursa durdur

# --- Flask Web Sunucusu ---
app = Flask(__name__)
CORS(app)


@app.route('/')
def home():
    # API'nin çalıştığını kontrol etmek için basit bir ana sayfa
    return "Unity Liderlik Tablosu API'si çalişiyor!"


@app.route('/add_score', methods=['POST'])
def add_score():
    """
    Unity'den gelen kullanici adı, IP ve skoru Firestore'a ekler.
    Beklenen JSON formati: {"username": "oyuncu_adi", "ip": "192.168.1.1", "score": 100}
    """
    try:
        # Gelen isteğin JSON formatında olduğundan emin ol
        if not request.is_json:
            return jsonify({"error": "İstek JSON formatında olmalı"}), 400

        data = request.get_json()

        # Gerekli alanların varlığını kontrol et
        username = data.get('username')
        ip_address = data.get('ip')
        score = data.get('score')  # Skoru da ekledim, liderlik tablosu için gerekli

        if not username or score is None:  # IP zorunlu olmayabilir, ama kullanıcı adı ve skor olmalı
            return jsonify({
                "error":
                "Eksik veri: 'username' ve 'score' alanlari gereklidir."
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

        print(f"Kayit eklendi/güncellendi: {user_data}")
        return jsonify({
            "success":
            True,
            "message":
            f"'{username}' için skor başariyla eklendi/güncellendi."
        }), 201

    except Exception as e:
        print(f"Skor eklenirken hata: {e}")
        return jsonify({"error": "Sunucu hatasi", "details": str(e)}), 500


@app.route('/get_leaderboard', methods=['GET'])
def get_leaderboard():
    """
    Firestore'daki 'leaderboard' koleksiyonundan skorlari çeker,
    puana göre büyükten küçüğe siralar ve ilk 10'u JSON olarak döndürür.
    """
    try:
        leaderboard_ref = db.collection('leaderboard')

        # Skorları 'score' alanına göre azalan sırada sorgula (en yüksek üstte)
        
        query = leaderboard_ref.order_by('score', direction=firestore.Query.DESCENDING)

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
        print(f"Liderlik tablosu alinirken hata: {e}")
        return jsonify({"error": "Sunucu hatasi", "details": str(e)}), 500
        

@app.route('/check_username', methods=['POST'])
def check_username():
    try:
        data = request.get_json()
        username = data.get('username')
        if not username:
            return jsonify({'success': False, 'message': 'Kullanici adi boş olamaz!'}), 400

        leaderboard_ref = db.collection('leaderboard').document(username)
        doc = leaderboard_ref.get()
        if doc.exists:
            return jsonify({'success': True, 'message': 'Kullanici Bulundu!', 'data':doc.to_dict()}), 200
        else:
            return jsonify({'success': False, 'message': 'Kullanici Bulunamadi!'}), 404
   
    except Exception as e:
        print(f"Kullanici adi sorgulanirken hata: {e}")
        return jsonify({"error": "Sunucu hatasi", "details": str(e)}), 500
    
@app.route('/update_score', methods=['POST'])
def update_score():
    try:
        data = request.get_json()
        username = data.get('username')
        score = data.get('score')
        if not username or score is None:
            return jsonify({'success': False, 'message': 'Puan veya kullanici adi boş olamaz!'}), 400
        
        leaderboard_ref = db.collection('leaderboard').document(username)
        leaderboard_ref.set({'score': score}, merge=True)

        return jsonify({'success': True, 'message': 'Skor güncellendi'}), 200


    except Exception as e:
        print(f"Skor güncellenirken hata: {e}")
        return jsonify({"error": "Sunucu hatasi", "details": str(e)}),500

@app.route('/get_rank', methods=['POST'])
def get_rank():
    try:
        data = request.get_json()
        username = data.get('username')

        if not username:
            return jsonify({'success': False, 'message': 'Kullanici adi gerekli!'}), 400

        # Tüm kullanıcıları score'a göre DESC sırala
        users_ref = db.collection('leaderboard').order_by('score', direction=firestore.Query.DESCENDING)
        users = users_ref.stream()

        rank = 1
        found = False

        for user in users:
            user_data = user.to_dict()
            if user.id == username:
                found = True
                break
            rank += 1

        if not found:
            return jsonify({'success': False, 'message': 'Kullanici bulunamadi!'}), 404

        return jsonify({'success': True, 'username': username, 'rank': rank}), 200

    except Exception as e:
        print(f"Rank bulunurken hata: {e}")
        return jsonify({'success': False, 'error': 'Sunucu hatasi', 'details': str(e)}), 500