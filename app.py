from flask import Flask, request, jsonify
from flask_cors import CORS
import psycopg2
import psycopg2.extras
import secrets
import os
import secrets


app = Flask(__name__)
CORS(app)

# তোমার ডাটাবেস লিংক
DB_URL = os.environ.get("DATABASE_URL", "postgres://username:password@localhost:5432/your_database")

def get_db_connection():
    return psycopg2.connect(DB_URL)

@app.route('/api/submit', methods=['POST'])
def submit_form():
    data = request.json
    user_token = "TKN-" + secrets.token_hex(4).upper()
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO website_users (name, phone, whatsapp, discord_username, payment_method, sender_number, trx_id, amount, user_token)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (
            data['name'], f"{data['phone_code']} {data['phone']}", f"{data['wa_code']} {data['whatsapp']}", 
            data['discord'], data['method'], data['sender_number'], data['trx'], 1000, user_token
        ))
        conn.commit()
        return jsonify({"success": True, "token": user_token})
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    data = request.json
    if data['email'] == 'mdananto01@gmail.com' and data['password'] == 'Ananto01@$':
        return jsonify({"success": True})
    return jsonify({"success": False}), 401

# 1. Dashboard Data Fetch Route
@app.route('/api/admin/dashboard', methods=['GET'])
def admin_dashboard():
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    # সব ইউজারের লিস্ট
    cursor.execute("SELECT * FROM website_users ORDER BY created_at DESC")
    users = [dict(u) for u in cursor.fetchall()]
    
    # শুধু Approved স্টুডেন্টদের কাউন্ট এবং রেভিনিউ হিসাব করা (Amount কলাম থেকে)
    cursor.execute("SELECT COUNT(*), COALESCE(SUM(amount), 0) FROM website_users WHERE status = 'Approved'")
    stats = cursor.fetchone()
    total_students = stats[0]
    total_revenue = stats[1]
    
    cursor.close()
    conn.close()
    return jsonify({
        "success": True, 
        "data": users, 
        "total_students": total_students, 
        "total_revenue": total_revenue
    })

# 2. Web Coupon Creation Route (নতুন ফিচার)
@app.route('/api/admin/create_coupon', methods=['POST'])
def create_coupon_web():
    data = request.json
    discount = data.get('discount')
    
    if not discount:
        return jsonify({"success": False})

    code = f"WEB-{secrets.token_hex(3).upper()}"
    
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT INTO coupons (code, discount) VALUES (%s, %s)', (code, int(discount)))
        conn.commit()
        return jsonify({"success": True, "code": code})
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/apply_coupon', methods=['POST'])
def apply_coupon():
    data = request.json
    code = data.get('code')
    
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    # Check if coupon exists and is active
    cursor.execute("SELECT * FROM coupons WHERE code = %s AND is_active = TRUE", (code,))
    coupon = cursor.fetchone()
    
    cursor.close()
    conn.close()
    
    if coupon:
        return jsonify({"success": True, "discount": coupon['discount']})
    return jsonify({"success": False, "message": "Invalid or expired coupon"})

# Submit রাউট আপডেট করুন যেন amount রিসিভ করে
@app.route('/api/submit', methods=['POST'])
def submit_form():
    data = request.json
    user_token = "TKN-" + secrets.token_hex(4).upper()
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # data['amount'] ফ্রন্টএন্ড থেকে আসবে (কুপন অ্যাপ্লাই হওয়ার পর)
        final_amount = int(data.get('amount', 1000)) 
        
        cursor.execute('''
            INSERT INTO website_users (name, phone, whatsapp, discord_username, payment_method, sender_number, trx_id, amount, user_token)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (
            data['name'], f"{data['phone_code']} {data['phone']}", f"{data['wa_code']} {data['whatsapp']}", 
            data['discord'], data['method'], data['sender_number'], data['trx'], final_amount, user_token
        ))
        conn.commit()
        return jsonify({"success": True, "token": user_token})
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

if __name__ == '__main__':
    app.run(debug=True, port=5000)