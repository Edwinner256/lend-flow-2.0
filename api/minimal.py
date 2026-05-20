"""
Minimal Flask test for Vercel
"""
from flask import Flask, jsonify

app = Flask(__name__)

@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'message': 'Minimal Flask works!'})

@app.route('/')
def index():
    return jsonify({'status': 'ok', 'message': 'Hello from Vercel!'})
