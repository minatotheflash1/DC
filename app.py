import os
import secrets
import requests
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import psycopg2
import psycopg2.extras


app = Flask(__name__, template_folder=".")
CORS(app)

# Environment Variables
DB_URL = os.environ.get("DATABASE_URL")
WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL") # রেলওয়েতে এই ভ্যারিয়েবলটি অ্যাড করবেন

def get_db_connection():
    return psycopg2.connect(DB_URL)

# ================= FRONTEND ROUTES =================
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/admin')
def admin_page():
    return render_template('admin.html')

# ================= BACKEND API ROUTES =================
@app.route('/api/submit', methods=['POST'])
def submit_form():
    data = request.json
    user_token = "TKN-" + secrets.token_hex(4).upper()
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        final_amount = int(data.get('amount', 1000)) 
        cursor.execute('''
            INSERT INTO website_users (name, phone, whatsapp, discord_username, payment_method, sender_number, trx_id, amount, user_token)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (
            data['name'], f"{data['phone_code']} {data['phone']}", f"{data['wa_code']} {data['whatsapp']}", 
            data['discord'], data['method'], data['sender_number'], data['trx'], final_amount, user_token
        ))
        conn.commit()

        # 🆕 ডিসকর্ডে অটোমেটিক লগ পাঠানো
        if WEBHOOK_URL:
            payload = {
                "embeds": [{
                    "title": "💰 New Payment Received!",
                    "color": 0x00FFCC,
                    "fields": [
                        {"name": "Student", "value": data['name'], "inline": True},
                        {"name": "Discord", "value": data['discord'], "inline": True},
                        {"name": "Method", "value": data['method'], "inline": True},
                        {"name": "TrxID", "value": data['trx'], "inline": True},
                        {"name": "Amount", "value": f"{final_amount} BDT", "inline": True}
                    ],
                    "footer": {"text": "Website Enrollment System"}
                }]
            }
            # try-except ব্লক ব্যবহার করা হয়েছে যেন ওয়েবহুকে সমস্যা হলেও ইউজারের ফর্ম সাবমিট ফেইল না করে
            try:
                requests.post(WEBHOOK_URL, json=payload)
            except Exception as req_err:
                print(f"Discord Webhook Error: {req_err}")

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

@app.route('/api/admin/dashboard', methods=['GET'])
def admin_dashboard():
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    cursor.execute("SELECT * FROM website_users ORDER BY created_at DESC")
    users = [dict(u) for u in cursor.fetchall()]
    
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

@app.route('/api/admin/action', methods=['POST'])
def admin_action():
    data = request.json
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE website_users SET status = %s WHERE id = %s", (data['action'], data['id']))
        conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False}), 500
    finally:
        cursor.close()
        conn.close()

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
    cursor.execute("SELECT * FROM coupons WHERE code = %s AND is_active = TRUE", (code,))
    coupon = cursor.fetchone()
    cursor.close()
    conn.close()
    if coupon:
        return jsonify({"success": True, "discount": coupon['discount']})
    return jsonify({"success": False, "message": "Invalid or expired coupon"})

if __name__ == '__main__':
    app.run()
