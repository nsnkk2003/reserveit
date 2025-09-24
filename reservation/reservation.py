from flask import Flask, request, jsonify
from pymongo import MongoClient
import requests
import logging
from flask_cors import CORS
from datetime import datetime
import time
from bson.objectid import ObjectId
from datetime import timezone

app = Flask(__name__)
CORS(app)
try:
    client = MongoClient('mongo-db-service', 27017, serverSelectionTimeoutMS=5000)
    client.server_info()
    logger.info("Connected to MongoDB successfully")
except Exception as e:
    logger.error(f"Failed to connect to MongoDB: {e}") # Now this will work
    raise

db = client['reserveit']
resources_collection = db['resources']
slots_collection = db['slots']
bookings_collection = db['bookings']

LOGIN_URL = "http://auth-service:5000/api/auth/validate/"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if resources_collection.count_documents({}) == 0:
    resources = [
        {'name': 'Table 1'}, {'name': 'Table 2'}, {'name': 'Table 3'},
        {'name': 'Classroom A'}, {'name': 'Classroom B'}, {'name': 'Classroom C'},
        {'name': 'Gym Slot A'}, {'name': 'Gym Slot B'}, {'name': 'Gym Slot C'},
        {'name': 'Meeting Room'}
    ]
    resources_collection.insert_many(resources)

@app.route('/api/resources', methods=['GET', 'OPTIONS'])
def get_resources():
    if request.method == 'OPTIONS':
        return _build_cors_preflight_response()
    resources = list(resources_collection.find())
    return _build_cors_response(jsonify({'resources': [{'id': str(r['_id']), 'name': r['name']} for r in resources]}), 200)

@app.route('/api/slots/<resource_id>/<date>', methods=['GET', 'OPTIONS'])
def get_slots(resource_id, date):
    if request.method == 'OPTIONS':
        return _build_cors_preflight_response()
    try:
        # Using the correct, standard format to read the date
        date_obj = datetime.strptime(date, '%Y-%m-%d').date()
        date_datetime = datetime.combine(date_obj, datetime.min.time(), tzinfo=timezone.utc)
        
        slots = list(slots_collection.find({'resource_id': str(resource_id), 'date': date_datetime}))
        
        if not slots:
            slots_to_insert = [
                {
                    'resource_id': str(resource_id),
                    'date': date_datetime,
                    'time_slot': time_slot,
                    'is_booked': False
                } for time_slot in ["10:00", "14:00", "18:00"]
            ]
            slots_collection.insert_many(slots_to_insert)
            slots = list(slots_collection.find({'resource_id': str(resource_id), 'date': date_datetime}))
        
        for slot in slots:
            booking = bookings_collection.find_one({'slot_id': ObjectId(slot['_id'])})
            slot['is_booked'] = bool(booking)

        return _build_cors_response(jsonify({
            'slots': [{'id': str(s['_id']), 'time_slot': s['time_slot'], 'is_booked': s['is_booked']} for s in slots]
        }), 200)
    except ValueError:
        return _build_cors_response(jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400)

@app.route('/api/book', methods=['POST', 'OPTIONS'])
def book():
    if request.method == 'OPTIONS':
        return _build_cors_preflight_response()
    data = request.get_json()
    user_id, slot_id = data.get('user_id'), data.get('slot_id')
    if not all([user_id, slot_id, data.get('name'), data.get('phone'), data.get('email')]):
        return _build_cors_response(jsonify({'error': 'All fields are required'}), 400)
    
    # User validation...
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = requests.get(f"{LOGIN_URL}{user_id}", timeout=2)
            if response.status_code == 200 and response.json().get('valid', False): break
            return _build_cors_response(jsonify({'error': 'Invalid user'}), 401)
        except requests.exceptions.RequestException:
            if attempt == max_retries - 1: return _build_cors_response(jsonify({'error': 'Authentication service unavailable'}), 503)
            time.sleep(0.5)

    try:
        slot = slots_collection.find_one({'_id': ObjectId(slot_id)})
        if not slot or bookings_collection.find_one({'slot_id': ObjectId(slot_id)}):
            return _build_cors_response(jsonify({'error': 'Slot not found or already booked'}), 400)

        booking = bookings_collection.insert_one({
            'user_id': user_id,
            'slot_id': ObjectId(slot_id),
            'resource_id': ObjectId(slot['resource_id']),
            'date': slot['date'],
            'name': data.get('name'),
            'phone': data.get('phone'),
            'email': data.get('email')
        })

        slots_collection.update_one({'_id': ObjectId(slot_id)}, {'$set': {'is_booked': True}})
        return _build_cors_response(jsonify({'message': 'Booking confirmed', 'booking_id': str(booking.inserted_id)}), 201)
    except Exception:
        return _build_cors_response(jsonify({'error': 'Invalid slot ID'}), 400)

@app.route('/api/bookings/<user_id>', methods=['GET', 'OPTIONS'])
def get_bookings(user_id):
    if request.method == 'OPTIONS':
        return _build_cors_preflight_response()
    
    bookings = list(bookings_collection.find({'user_id': user_id}))
    enriched_bookings = []
    
    for b in bookings:
        slot = slots_collection.find_one({'_id': b['slot_id']})
        resource = None
        booking_date_str = 'Unknown'

        # This logic handles both OLD and NEW booking formats.
        if 'resource_id' in b and 'date' in b:
            resource = resources_collection.find_one({'_id': b['resource_id']})
            # --- FINAL FIX --- 
            # Using the correct, standard format to display the date
            booking_date_str = b['date'].strftime('%Y-%m-%d')
        elif slot:
            resource = resources_collection.find_one({'_id': ObjectId(slot['resource_id'])})
            # --- FINAL FIX (for fallback) ---
            booking_date_str = slot['date'].strftime('%Y-%m-%d')
        
        enriched_bookings.append({
            'id': str(b['_id']),
            'slot_id': str(b['slot_id']),
            'name': b['name'],
            'phone': b['phone'],
            'email': b['email'],
            'resource_name': resource['name'] if resource else 'Unknown',
            'slot_time': slot['time_slot'] if slot else 'Unknown',
            'date': booking_date_str
        })
    return _build_cors_response(jsonify({'bookings': enriched_bookings}), 200)

@app.route('/api/cancel/<booking_id>', methods=['POST', 'OPTIONS'])
def cancel(booking_id):
    if request.method == 'OPTIONS':
        return _build_cors_preflight_response()
    try:
        booking = bookings_collection.find_one({'_id': ObjectId(booking_id)})
        if booking:
            slots_collection.update_one({'_id': booking['slot_id']}, {'$set': {'is_booked': False}})
            bookings_collection.delete_one({'_id': ObjectId(booking_id)})
            return _build_cors_response(jsonify({'message': 'Booking cancelled'}), 200)
        return _build_cors_response(jsonify({'error': 'Booking not found'}), 404)
    except Exception:
        return _build_cors_response(jsonify({'error': 'Invalid booking ID'}), 400)

def _build_cors_preflight_response():
    response = app.make_default_options_response()
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    return response

def _build_cors_response(response, status):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.status_code = status
    return response

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)