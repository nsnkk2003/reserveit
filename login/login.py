import os
import requests
from flask import Flask, jsonify, request, send_from_directory
from pymongo import MongoClient
import logging
from bson.objectid import ObjectId

app = Flask(__name__, static_folder='static', template_folder='templates')

try:
    client = MongoClient('mongo-db-service', 27017, serverSelectionTimeoutMS=5000)
    db = client['reserveit']
    users_collection = db['users']
    logging.info("Connected to MongoDB successfully")
except Exception as e:
    logging.error(f"Failed to connect to MongoDB: {e}")
    raise

RESERVATION_API_URL = "http://reservation-service:5001"

@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.get_json()
    if not all([data.get('name'), data.get('email'), data.get('password')]):
        return jsonify({'error': 'All fields are required'}), 400
    if users_collection.find_one({'email': data['email']}):
        return jsonify({'error': 'Email already registered'}), 400
    users_collection.insert_one({'name': data['name'], 'email': data['email'], 'password': data['password']})
    return jsonify({'message': 'Registration successful'}), 201

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json()
    user = users_collection.find_one({'email': data['email'], 'password': data['password']})
    if user:
        return jsonify({'user_id': str(user['_id']), 'name': user['name'], 'email': user['email']}), 200
    return jsonify({'error': 'Invalid credentials'}), 401

@app.route('/api/auth/validate/<user_id>', methods=['GET'])
def validate_user(user_id):
    user = None
    try:
        # First, try the standard approach: searching by ObjectId
        user = users_collection.find_one({'_id': ObjectId(user_id)})
    except Exception:
        # This will fail if user_id isn't a valid ObjectId hex string.
        # We can ignore the error and proceed to check it as a plain string.
        pass
    
    # If the user wasn't found as an ObjectId, try finding them by the raw string.
    # This handles cases where the _id might have been stored as a string.
    if not user:
        user = users_collection.find_one({'_id': user_id})

    if user:
        return jsonify({'valid': True}), 200
    else:
        return jsonify({'valid': False}), 404

    
# In login.py

@app.route('/api/<path:path>', methods=['GET', 'POST'])
def reservation_proxy(path):
    full_url = f"{RESERVATION_API_URL}/api/{path}"
    response = None

    if request.method == 'GET':
        response = requests.get(full_url, params=request.args)
    elif request.method == 'POST':
        # Check if the incoming request has a JSON body before trying to read it
        if request.is_json:
            response = requests.post(full_url, json=request.get_json())
        else:
            # If no JSON body, forward the request without one
            response = requests.post(full_url)
    else:
        return "Method not allowed", 405
        
    return response.content, response.status_code, response.headers.items()


@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    if path != "" and os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    else:
        return send_from_directory(app.template_folder, 'index.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)